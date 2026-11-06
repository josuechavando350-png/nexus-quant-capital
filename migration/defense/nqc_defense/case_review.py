"""Evidence-bound local review state machine with authenticated, optimistic append-only history."""
import hmac
import time

from .audit import GENESIS, mac
from .case_evidence import _case, verify_bundle
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import sha256
from .receipts import hex_digest
from .review_credentials import ReviewCredentials
from .review_policy import reason_text

MAX_CASE_REVISIONS = 1000
MAX_TOTAL_REVISIONS = 100000
ORIGIN = {"revision": 0, "head": GENESIS}
SCHEMA = "nqc-case-review-v1"
CURRENT_SCHEMA = "nqc-case-review-v2"


def checkpoint(value):
    fields(value, ("revision", "head"))
    integer(value["revision"], 0, MAX_CASE_REVISIONS)
    hex_digest(value["head"])
    if value["revision"] == 0 and value["head"] != GENESIS:
        raise Rejected("review_checkpoint")
    return dict(value)


def initial_state():
    return {"stage": "unreviewed", "assessment": None, "notes_count": 0, "closed_by": None}


def transition(state, event, revision):
    action = event["action"]
    actor = event["actor"]
    verdict = event["verdict"]
    reason_text(event["reason"])
    if action != "assess" and verdict is not None:
        raise Rejected("review_unexpected_verdict")
    state = dict(state)
    if action == "start":
        if state["stage"] != "unreviewed":
            raise Rejected("review_already_started")
        state["stage"] = "investigating"
    elif action == "reopen":
        if state["stage"] != "closed":
            raise Rejected("review_not_closed")
        state.update(stage="investigating", assessment=None, closed_by=None)
    elif action in ("note", "assess", "close"):
        if state["stage"] != "investigating":
            raise Rejected("review_not_investigating")
        if action == "note":
            state["notes_count"] += 1
            state["assessment"] = None
        elif action == "assess":
            if verdict not in ("benign", "needs_response", "inconclusive"):
                raise Rejected("review_verdict")
            state["assessment"] = {"verdict": verdict, "actor": actor, "revision": revision, "reason": event["reason"]}
        else:
            assessment = state["assessment"]
            if assessment is None or assessment["verdict"] != "benign":
                raise Rejected("review_closure_requires_benign_assessment")
            if assessment["actor"] == actor:
                raise Rejected("review_closure_requires_other_actor")
            state.update(stage="closed", closed_by=actor)
    else:
        raise Rejected("review_action")
    return state


class CaseReview:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self.credentials = ReviewCredentials(store, policy)
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS case_reviews (tenant TEXT NOT NULL, asset TEXT NOT NULL, "
                       "case_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, "
                       "previous TEXT NOT NULL, mac TEXT NOT NULL, PRIMARY KEY(tenant,asset,case_id,revision))")

    def _load(self, db, tenant, asset, case_id, credentials):
        row = db.execute("SELECT body,category,status FROM cases WHERE tenant=? AND asset=? AND id=?", (tenant, asset, case_id)).fetchone()
        rows = db.execute("SELECT revision,payload,previous,mac FROM case_reviews WHERE tenant=? AND asset=? AND case_id=? ORDER BY revision LIMIT ?",
                          (tenant, asset, case_id, MAX_CASE_REVISIONS + 1)).fetchall()
        return verify_case_rows(self.policy, tenant, asset, case_id, row, rows, credentials)

    def view(self, actor, credential, tenant, asset, case_id, *, expected=None, after=0, limit=100, expected_credentials=None):
        hex_digest(case_id)
        integer(after, 0, MAX_CASE_REVISIONS); integer(limit, 1, 200)
        if expected is not None:
            checkpoint(expected)
        with self.credentials.transaction() as db:
            credentials = self.credentials.authorize(db, actor, credential, tenant, asset, "read", expected_credentials)
            case, state, current, history = self._load(db, tenant, asset, case_id, credentials)
            if expected is not None and current != expected:
                raise Rejected("review_checkpoint_mismatch")
            self.credentials.check_time(db, credentials, actor)
        return {"case_id": case_id, "detection_status": case["status"], "review": state, "checkpoint": current,
                "history": history[after:after + limit], "evidence_availability_rechecked": False,
                "human_identity_verified": False, "independent_anchor": False, "credential_checkpoint": credentials.current}

    def apply(self, actor, credential, tenant, asset, case_id, action, reason, request_id, expected,
              bundle, bundle_digest, case_digest, config_digest, *, verdict=None, expected_credentials=None):
        with self.credentials.transaction() as db:
            self.credentials.authorize(db, actor, credential, tenant, asset, action, expected_credentials)
        if action == "read":
            raise Rejected("review_action")
        identifier(request_id); reason_text(reason); checkpoint(expected)
        verify_bundle(bundle, bundle_digest, tenant, asset, case_id, case_digest, config_digest)
        command = {"schema": CURRENT_SCHEMA, "policy_digest": self.policy.digest, "tenant": tenant, "asset": asset,
                   "case_id": case_id, "case_digest": case_digest, "config_digest": config_digest,
                   "bundle_digest": bundle_digest, "actor": actor, "request_id": request_id,
                   "action": action, "reason": reason, "verdict": verdict}
        with self.credentials.transaction() as db:
            credentials = self.credentials.authorize(db, actor, credential, tenant, asset, action, expected_credentials)
            case, state, current, history = self._load(db, tenant, asset, case_id, credentials)
            if sha256(canonical(case)) != case_digest:
                raise Rejected("review_case_snapshot_changed")
            for entry in history:
                if entry["event"]["request_id"] == request_id:
                    old = dict(entry["event"])
                    for key in ("recorded_ns", "schema", "credential_checkpoint"):
                        old.pop(key, None)
                    requested = dict(command); requested.pop("schema")
                    before = {"revision": entry["revision"] - 1, "head": entry["previous"]}
                    if old != requested or expected != before:
                        raise Rejected("review_request_conflict")
                    self.credentials.check_time(db, credentials, actor)
                    return {"applied": False, "idempotent_retry": True, "checkpoint": current, "review": state,
                            "operation_checkpoint": {"revision": entry["revision"], "head": entry["head"]},
                            "credential_checkpoint": credentials.current}
            if expected != current:
                raise Rejected("review_checkpoint_mismatch")
            if history and any(command[key] != history[0]["event"][key] for key in ("case_digest", "config_digest", "bundle_digest")):
                raise Rejected("review_evidence_binding")
            if current["revision"] >= MAX_CASE_REVISIONS or db.execute("SELECT count(*) FROM case_reviews").fetchone()[0] >= MAX_TOTAL_REVISIONS:
                raise Rejected("review_capacity")
            now = time.time_ns()
            self.credentials.check_time(db, credentials, actor, now=now)
            if history and now < history[-1]["event"]["recorded_ns"]:
                raise Rejected("review_clock_regressed")
            event = {**command, "recorded_ns": integer(now, 0, 2**63 - 1), "credential_checkpoint": credentials.current}
            revision = current["revision"] + 1
            state = transition(state, event, revision)
            payload = canonical(event).decode()
            digest = mac(self.policy.key, revision, current["head"], payload)
            db.execute("INSERT INTO case_reviews VALUES(?,?,?,?,?,?,?)", (tenant, asset, case_id, revision, payload, current["head"], digest))
            self.credentials.check_time(db, credentials, actor)
        return {"applied": True, "idempotent_retry": False, "checkpoint": {"revision": revision, "head": digest},
                "review": state, "evidence_rechecked": True, "automatic_response": False, "credential_checkpoint": credentials.current}


def verify_case_rows(policy, tenant, asset, case_id, row, rows, credentials):
    """Replay the exact same case rules for database reads and offline verification."""
    if row is None:
        raise Rejected("review_case_not_found")
    if type(row) not in (list, tuple) or len(row) != 3:
        raise Rejected("review_case_row")
    case = decode(row[0])
    if type(case) is not dict or (case.get("case_id"), case.get("tenant"), case.get("asset")) != (case_id, tenant, asset):
        raise Rejected("review_case_scope")
    if case.get("category") != "authentication":
        raise Rejected("review_case_unsupported")
    if (case.get("category"), case.get("status")) != tuple(row[1:]):
        raise Rejected("review_case_columns")
    case_digest = sha256(canonical(case))
    hex_digest(case.get("config_digest"))
    _case(case, tenant, asset, case_id, case_digest, case["config_digest"])
    if type(rows) not in (list, tuple):
        raise Rejected("review_history_rows")
    if len(rows) > MAX_CASE_REVISIONS:
        raise Rejected("review_case_capacity")
    state, previous, last_time, binding, seen, history = initial_state(), GENESIS, -1, None, set(), []
    credential_revision, versioned = 0, False
    for number, entry in enumerate(rows, 1):
        if type(entry) not in (list, tuple) or len(entry) != 4:
            raise Rejected("review_history_row")
        revision, payload, parent, digest = entry
        integer(revision, 1, MAX_CASE_REVISIONS)
        if revision != number or parent != previous:
            raise Rejected("review_history_sequence")
        if not isinstance(payload, str) or len(payload.encode()) > 16384:
            raise Rejected("review_history_size")
        try:
            hex_digest(digest)
        except Rejected as exc:
            raise Rejected("review_history_integrity") from exc
        if not hmac.compare_digest(digest, mac(policy.key, revision, parent, payload)):
            raise Rejected("review_history_integrity")
        event = decode(payload.encode())
        names = ("schema", "policy_digest", "tenant", "asset", "case_id", "case_digest", "config_digest", "bundle_digest",
                 "actor", "request_id", "action", "reason", "verdict", "recorded_ns")
        current_schema = type(event) is dict and event.get("schema") == CURRENT_SCHEMA
        fields(event, names + (("credential_checkpoint",) if current_schema else ()))
        if canonical(event).decode() != payload or event["schema"] not in (SCHEMA, CURRENT_SCHEMA) or (event["policy_digest"], event["tenant"], event["asset"], event["case_id"]) != (policy.digest, tenant, asset, case_id):
            raise Rejected("review_history_binding")
        now = integer(event["recorded_ns"], 0, 2**63 - 1)
        if current_schema:
            credentials.historical(event["credential_checkpoint"], event["actor"], now)
            if event["credential_checkpoint"]["revision"] < credential_revision:
                raise Rejected("review_credential_regression")
            credential_revision, versioned = event["credential_checkpoint"]["revision"], True
        elif versioned:
            raise Rejected("review_schema_regression")
        for key in ("case_digest", "config_digest", "bundle_digest"):
            hex_digest(event[key])
        if event["case_digest"] != case_digest:
            raise Rejected("review_case_snapshot_changed")
        current = (event["case_digest"], event["config_digest"], event["bundle_digest"])
        if binding is not None and current != binding:
            raise Rejected("review_evidence_binding")
        binding = current
        identifier(event["actor"]); identifier(event["request_id"])
        if event["request_id"] in seen:
            raise Rejected("review_request_duplicate")
        seen.add(event["request_id"])
        if not policy.permits(event["actor"], tenant, asset, event["action"]):
            raise Rejected("review_history_permission")
        if now < last_time:
            raise Rejected("review_clock_regressed")
        state = transition(state, event, revision)
        history.append({"revision": revision, "event": event, "previous": parent, "head": digest})
        previous, last_time = digest, now
    return case, state, {"revision": len(rows), "head": previous}, history
