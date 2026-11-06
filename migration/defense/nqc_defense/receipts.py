"""X103: strict causal receipts and a pure evaluator for independent local replay."""

import hashlib
import re

from .budget import permits_quarantine
from .codec import Rejected, canonical, fields, identifier, integer
from .config import controls, validate
from .freshness import MAX_TIME, evaluate as evidence_freshness

EVALUATOR = "nqc-local-admission-v2"
READ_ERRORS = {"unsafe_path", "file_type_or_size", "file_size", "file_changed_during_read", "file_unavailable"}


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hex_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise Rejected("receipt_digest")


def observations_for(asset, observations):
    """Require complete, ordered membership; a missing canary is never a clean scan."""
    expected = [("artifact", asset), *(("canary", entry) for entry in asset["canaries"])]
    if type(observations) is not list or len(observations) != len(expected):
        raise Rejected("evidence_membership")
    reasons = []
    for observation, (kind, entry) in zip(observations, expected):
        fields(observation, ("kind", "path", "sha256", "error", "observed_at"))
        if observation["kind"] != kind or observation["path"] != entry["path"]:
            raise Rejected("evidence_membership")
        integer(observation["observed_at"], 0, MAX_TIME)
        if observation["error"] is None:
            hex_digest(observation["sha256"])
            if observation["sha256"] != entry["sha256"]:
                reasons.append("asset_integrity_changed" if kind == "artifact" else "canary_integrity_changed")
        else:
            if observation["error"] not in READ_ERRORS or observation["sha256"] is not None:
                raise Rejected("evidence_error")
            reasons.append("asset_unavailable" if kind == "artifact" else "canary_unavailable")
    return sorted(set(reasons))


def evaluate(policy, asset_id, facts):
    """Reproduce a decision from supplied facts. Does not attest that those facts are true."""
    settings = controls(policy)
    asset = next((a for a in policy["assets"] if a["id"] == asset_id), None)
    if asset is None:
        raise Rejected("unknown_asset")
    fields(facts, ("started_at", "decided_at", "rate_allowed", "duplicate_request",
                   "was_quarantined", "quarantine_count", "observations"))
    for key in ("started_at", "decided_at"):
        integer(facts[key], 0, MAX_TIME)
    for key in ("rate_allowed", "duplicate_request", "was_quarantined"):
        if type(facts[key]) is not bool:
            raise Rejected("receipt_boolean")
    integer(facts["quarantine_count"], 0, len(policy["assets"]))
    if facts["was_quarantined"] and facts["quarantine_count"] == 0:
        raise Rejected("receipt_quarantine_count")
    if type(facts["observations"]) is not list:
        raise Rejected("evidence_membership")
    trace = []

    def outcome(decision, reasons, transition="none"):
        return {"decision": decision, "reasons": reasons, "transition": transition, "checks": trace}

    # Even early denials retain clock-order checks and have no fabricated observations.
    if facts["decided_at"] < facts["started_at"]:
        if facts["observations"]:
            observations_for(asset, facts["observations"])
        trace.append({"gate": "clock", "result": "failed"})
        return outcome("denied", ["clock_regressed"])
    trace.append({"gate": "clock", "result": "passed"})
    trace.append({"gate": "rate", "result": "passed" if facts["rate_allowed"] else "failed"})
    if not facts["rate_allowed"]:
        if facts["observations"]:
            raise Rejected("unexpected_observations")
        return outcome("denied", ["rate_limited"])
    trace.append({"gate": "replay", "result": "failed" if facts["duplicate_request"] else "passed"})
    if facts["duplicate_request"]:
        if facts["observations"]:
            raise Rejected("unexpected_observations")
        return outcome("denied", ["duplicate_request"])
    trace.append({"gate": "existing_quarantine", "result": "failed" if facts["was_quarantined"] else "passed"})
    if facts["was_quarantined"]:
        if facts["observations"]:
            raise Rejected("unexpected_observations")
        return outcome("quarantined", ["asset_quarantined"])
    reasons = observations_for(asset, facts["observations"])
    freshness_reasons = evidence_freshness(facts["started_at"], facts["decided_at"],
                                         [x["observed_at"] for x in facts["observations"]],
                                         settings["evidence_max_age_seconds"])
    trace.append({"gate": "freshness", "result": "failed" if freshness_reasons else "passed"})
    if freshness_reasons:
        return outcome("denied", freshness_reasons)
    trace.append({"gate": "integrity", "result": "failed" if reasons else "passed"})
    if not reasons:
        return outcome("admit", [])
    permitted = permits_quarantine(facts["quarantine_count"], settings["max_quarantined_assets"])
    trace.append({"gate": "containment_budget", "result": "passed" if permitted else "failed"})
    if not permitted:
        return outcome("denied", [*reasons, "quarantine_budget_exhausted"])
    return outcome("quarantined", reasons, "quarantine")


def make(policy, subject, message, facts):
    identifier(subject)
    fields(message, ("asset", "request_id"))
    for value in message.values():
        identifier(value)
    result = evaluate(policy, message["asset"], facts)
    return {"schema": "nqc-decision-receipt-v1", "evaluator": EVALUATOR,
            "policy_digest": hashlib.sha3_256(canonical(policy)).hexdigest(),
            "subject": subject, "request": message, "facts": facts, "outcome": result}


def verify(receipt, policy, expected_digest):
    """Verify exact receipt hash, policy binding, schema and all decision branches."""
    fields(receipt, ("schema", "evaluator", "policy_digest", "subject", "request", "facts", "outcome"))
    hex_digest(expected_digest)
    if digest(receipt) != expected_digest:
        raise Rejected("receipt_integrity")
    if receipt["schema"] != "nqc-decision-receipt-v1" or receipt["evaluator"] != EVALUATOR:
        raise Rejected("receipt_version")
    validate(policy)
    if receipt["policy_digest"] != hashlib.sha3_256(canonical(policy)).hexdigest():
        raise Rejected("receipt_policy_binding")
    expected = make(policy, receipt["subject"], receipt["request"], receipt["facts"])
    if receipt != expected:
        raise Rejected("receipt_replay_mismatch")
    return {"verified": True, "decision": expected["outcome"]["decision"],
            "receipt_sha256": expected_digest, "scope": "replayed_recorded_facts"}
