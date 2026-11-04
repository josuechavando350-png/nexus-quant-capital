"""Semantic links for the fixed native lab; hashes alone are not execution proof."""
from __future__ import annotations

from datetime import datetime
import hashlib
import uuid

from .safe_io import canonical

NATIVE_FUNCTIONS = ["DIABLO.ScopeGuard.assert_allowed", "DIABLO.AuditLog.append/verify", "NQC.RMC016.solve"]


def _time(value):
    if type(value) is not str:
        raise ValueError("lab timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("lab timestamp must include timezone")
    return parsed


def verify_semantics(result: dict, entries: list[dict], cases: list[dict]) -> None:
    """Bind every recorded stage to its fixture, input and numerical result.

    The original verifier checks the chain hashes. This layer checks what each
    entry means. It cannot authenticate a remote operator who controls all bytes.
    """
    required = {"schema_version", "status", "run_id", "started_at", "completed_at",
                "verification_level", "local_component_execution", "fixture_only",
                "vulnerability_confirmed", "forge_executed", "mainnet_connected",
                "program_scope_verified", "cases_passed", "scope_negative_passed",
                "duplicate_negative_passed", "audit_head", "audit_count", "native_functions"}
    if type(result) is not dict or set(result) != required:
        raise ValueError("lab result fields mismatch")
    for name, expected in (("schema_version", 1), ("cases_passed", 5), ("audit_count", 18)):
        if type(result[name]) is not int or result[name] != expected:
            raise ValueError("lab integer declaration mismatch")
    for name in ("local_component_execution", "fixture_only", "scope_negative_passed", "duplicate_negative_passed"):
        if result[name] is not True:
            raise ValueError("lab execution declaration mismatch")
    for name in ("vulnerability_confirmed", "forge_executed", "mainnet_connected", "program_scope_verified"):
        if result[name] is not False:
            raise ValueError("local evidence cannot become a production finding")
    if (result["verification_level"] != "pinned-native-local-regression" or
            result["native_functions"] != NATIVE_FUNCTIONS):
        raise ValueError("lab native component declaration mismatch")
    rid = result["run_id"]
    if type(rid) is not str or str(uuid.UUID(rid)) != rid:
        raise ValueError("lab run id must be canonical UUID")
    start, end = _time(result["started_at"]), _time(result["completed_at"])
    if end < start:
        raise ValueError("lab time order mismatch")
    expected = [("lab.start", {"run_id": rid, "fixture_only": True})]
    for case in cases:
        name = case["case"]
        expected.extend([
            ("scope.check", {"target": name + ".lab.invalid", "kind": "fixture", "decision": "ALLOW",
                             "reason": "in scope (*.lab.invalid)", "matched_rule": "*.lab.invalid"}),
            ("lab.nqc.start", {"case": name, "input_sha256": hashlib.sha256(canonical(case["inputs"])).hexdigest()}),
            ("lab.nqc.finish", {"case": name, "output_commitment": case["nqc"]["commitment"]}),
        ])
    expected.extend([
        ("scope.check", {"target": "blocked.lab.invalid", "kind": "fixture", "decision": "DENY",
                         "reason": "explicitly out of scope (blocked.lab.invalid)", "matched_rule": "blocked.lab.invalid"}),
        ("lab.completed", {"run_id": rid, "cases": 5, "vulnerability_confirmed": False}),
    ])
    if type(entries) is not list or len(entries) != len(expected):
        raise ValueError("audit stage count mismatch")
    previous_time = start
    for index, (entry, (event, data)) in enumerate(zip(entries, expected)):
        if type(entry) is not dict or set(entry) != {"index", "timestamp", "event", "data", "prev_hash", "hash"}:
            raise ValueError("audit entry fields mismatch")
        if type(entry["index"]) is not int or entry["index"] != index:
            raise ValueError("audit index mismatch")
        # Canonical JSON distinguishes bool from int, unlike Python equality.
        if entry["event"] != event or canonical(entry["data"]) != canonical(data):
            raise ValueError("audit semantic link mismatch")
        current = _time(entry["timestamp"])
        if not previous_time <= current <= end:
            raise ValueError("audit timestamp order mismatch")
        previous_time = current
