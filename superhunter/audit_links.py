"""Semantic binding of the fixed DIABLO/NQC lab audit, not producer authentication."""
from __future__ import annotations

from datetime import datetime
import hashlib
import uuid

from .safe_io import canonical

NATIVE_FUNCTIONS = ["DIABLO.ScopeGuard.assert_allowed", "DIABLO.AuditLog.append/verify", "NQC.RMC016.solve"]


def _time(value: str) -> datetime:
    if type(value) is not str:
        raise ValueError("audit timestamp must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("audit timestamp must include timezone")
    return parsed


def verify_audit_links(entries: list[dict], result: dict, cases: list[dict]) -> None:
    """Bind event order, scope, inputs, outputs and run identity to the bundle.

    Hash chains alone do not establish these relationships. A fully forged,
    internally consistent bundle still needs an external trust anchor.
    """
    run_id = result.get("run_id")
    if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
        raise ValueError("invalid lab run UUID")
    for field, expected in (("schema_version", 1), ("cases_passed", len(cases)),
                            ("audit_count", len(entries))):
        if type(result.get(field)) is not int or result[field] != expected:
            raise ValueError("invalid lab count/schema type")
    if (result.get("local_component_execution") is not True or
            result.get("verification_level") != "pinned-native-local-regression" or
            result.get("native_functions") != NATIVE_FUNCTIONS):
        raise ValueError("native execution claims mismatch")
    start, end = _time(result["started_at"]), _time(result["completed_at"])
    if end < start:
        raise ValueError("lab time interval reversed")
    expected = [("lab.start", {"run_id": run_id, "fixture_only": True})]
    for case in cases:
        name = case["case"]
        expected.extend([
            ("scope.check", {"target": name + ".lab.invalid", "kind": "fixture",
                             "decision": "ALLOW", "reason": "in scope (*.lab.invalid)",
                             "matched_rule": "*.lab.invalid"}),
            ("lab.nqc.start", {"case": name,
                               "input_sha256": hashlib.sha256(canonical(case["inputs"])).hexdigest()}),
            ("lab.nqc.finish", {"case": name, "output_commitment": case["nqc"]["commitment"]}),
        ])
    expected.extend([
        ("scope.check", {"target": "blocked.lab.invalid", "kind": "fixture", "decision": "DENY",
                         "reason": "explicitly out of scope (blocked.lab.invalid)",
                         "matched_rule": "blocked.lab.invalid"}),
        ("lab.completed", {"run_id": run_id, "cases": len(cases), "vulnerability_confirmed": False}),
    ])
    if len(entries) != len(expected):
        raise ValueError("audit event coverage mismatch")
    last = start
    for index, (entry, (event, data)) in enumerate(zip(entries, expected)):
        if type(entry.get("index")) is not int or entry["index"] != index:
            raise ValueError("audit index type/order mismatch")
        # Canonical bytes distinguish JSON true from 1 and reject extra keys.
        if entry.get("event") != event or canonical(entry.get("data")) != canonical(data):
            raise ValueError(f"audit semantic binding mismatch at event {index}")
        timestamp = _time(entry["timestamp"])
        if not last <= timestamp <= end:
            raise ValueError("audit timestamp out of order or run bounds")
        last = timestamp
