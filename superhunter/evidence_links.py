"""Verify the semantics linking this project's fixed local regression artifacts.

Hashes alone do not prove execution. This checker rejects contradictory claims
and binds the existing DIABLO -> NQC -> reference -> audit circuit. It is not
an exploit engine, a generic task executor, or remote producer authentication.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid

from .safe_io import canonical


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact(actual: object, expected: object, label: str) -> None:
    # JSON comparison distinguishes bool/int and integer/float unlike Python ==.
    if canonical(actual) != canonical(expected):
        raise ValueError(f"linked evidence mismatch: {label}")


def instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("linked evidence timestamp must be text")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("linked evidence timestamp is invalid") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("linked evidence timestamp needs timezone")
    return result


def expected_nqc(rows: list[dict], reference: dict) -> dict:
    """Independent expected result envelope for the fixed small exact domain."""
    body = {
        "schema_version": 1, "status": "RMC016_CAPACITY_FOUNDATION_VALID",
        "solver_mode": "EXACT_BRANCH_AND_BOUND", "global_optimum_claimed": True,
        "conservative_realizable_capacity_only": True,
        "capture_probability": "UNCALIBRATED", "capture_adjusted_capacity_claimed": False,
        "input_opportunity_count": len(rows),
        "selected_opportunity_count": len(reference["selected_opportunity_ids"]),
        **reference,
    }
    return {**body, "commitment": "0x" + digest(body)}


def _event_spec(run_id: str, cases: list[dict]) -> list[tuple[str, dict]]:
    events = [("lab.start", {"run_id": run_id, "fixture_only": True})]
    for case in cases:
        name = case["case"]
        events.extend([
            ("scope.check", {"target": name + ".lab.invalid", "kind": "fixture",
                             "decision": "ALLOW", "reason": "in scope (*.lab.invalid)",
                             "matched_rule": "*.lab.invalid"}),
            ("lab.nqc.start", {"case": name, "input_sha256": digest(case["inputs"])}),
            ("lab.nqc.finish", {"case": name, "output_commitment": case["nqc"]["commitment"]}),
            ("lab.reference.finish", {"case": name, "reference_sha256": digest(case["independent"]),
                                      "matched": True}),
        ])
    events.extend([
        ("scope.check", {"target": "blocked.lab.invalid", "kind": "fixture", "decision": "DENY",
                         "reason": "explicitly out of scope (blocked.lab.invalid)",
                         "matched_rule": "blocked.lab.invalid"}),
        ("lab.nqc.reject", {"case": "duplicate-id", "error": "duplicate opportunity_id"}),
        ("lab.completed", {"run_id": run_id, "cases": len(cases), "vulnerability_confirmed": False}),
    ])
    return events


def verify_semantics(result: dict, cases: list[dict], entries: list[dict]) -> None:
    """Reject success whose state, events, inputs or outputs disagree."""
    try:
        run_id = result["run_id"]
        if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
            raise ValueError("linked run_id is not a canonical UUID")
        start, end = instant(result["started_at"]), instant(result["completed_at"])
        if start > end:
            raise ValueError("linked run time is reversed")
        specs = _event_spec(run_id, cases)
        if type(entries) is not list or len(entries) != len(specs):
            raise ValueError("linked audit event coverage mismatch")
        previous, previous_time = "0" * 64, start
        for index, (entry, (event, data)) in enumerate(zip(entries, specs)):
            timestamp = instant(entry["timestamp"])
            if not previous_time <= timestamp <= end:
                raise ValueError("linked audit event time/order mismatch")
            body = {"index": index, "timestamp": entry["timestamp"], "event": event,
                    "data": data, "prev_hash": previous}
            hashed = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            expected = {**body, "hash": hashlib.sha256(hashed).hexdigest()}
            exact(entry, expected, f"audit event {index}: {event}")
            previous, previous_time = expected["hash"], timestamp
        for case in cases:
            exact(case["match"], True, "reference match")
            exact(case["nqc"], expected_nqc(case["inputs"], case["independent"]), "NQC result envelope")
        expected_result = {
            "schema_version": 2, "status": "LOCAL_INTEGRATION_PASS", "run_id": run_id,
            "started_at": result["started_at"], "completed_at": result["completed_at"],
            "verification_level": "pinned-native-local-regression", "local_component_execution": True,
            "fixture_only": True, "vulnerability_confirmed": False, "forge_executed": False,
            "mainnet_connected": False, "program_scope_verified": False,
            "cases_passed": len(cases), "scope_negative_passed": True,
            "duplicate_negative_passed": True, "audit_head": previous, "audit_count": len(entries),
            "native_functions": ["DIABLO.ScopeGuard.assert_allowed", "DIABLO.AuditLog.append/verify", "NQC.RMC016.solve"],
        }
        exact(result, expected_result, "run verdict")
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("malformed linked evidence") from exc


def make_graph(result: dict, cases: list[dict], entries: list[dict], provenance: dict) -> dict:
    """Materialize the dependency graph of already executed local checks."""
    verify_semantics(result, cases, entries)
    nodes, known = [], {}
    run_id = result["run_id"]

    def add(identifier: str, depends: list[str], payload: object) -> None:
        if identifier in known or len(set(depends)) != len(depends) or any(x not in known for x in depends):
            raise ValueError("evidence graph has duplicate, cyclic or missing dependency")
        body = {"id": identifier, "run_id": run_id, "depends_on": depends,
                "payload_sha256": digest(payload), "parents": {p: known[p] for p in depends}}
        node = {**body, "node_sha256": digest(body)}
        known[identifier] = node["node_sha256"]
        nodes.append(node)

    add("sources", [], provenance)
    completed = []
    for index, case in enumerate(cases):
        name, offset = case["case"], 1 + index * 4
        add("scope:" + name, ["sources"], entries[offset])
        add("input:" + name, ["scope:" + name], {"rows": case["inputs"], "event": entries[offset + 1]})
        add("nqc:" + name, ["input:" + name], {"result": case["nqc"], "event": entries[offset + 2]})
        add("reference:" + name, ["input:" + name], {"result": case["independent"], "event": entries[offset + 3]})
        add("agreement:" + name, ["nqc:" + name, "reference:" + name], {"match": True})
        completed.append("agreement:" + name)
    add("scope-negative", ["sources"], entries[-3])
    add("duplicate-negative", ["sources"], entries[-2])
    add("audit", [*completed, "scope-negative", "duplicate-negative"], entries)
    add("verdict", ["audit"], result)
    return {"schema_version": 1, "run_id": run_id, "scope": "fixed-local-regression-only",
            "producer_authenticated": False, "nodes": nodes, "root_sha256": known["verdict"]}


def check_graph(graph: dict, expected: dict) -> None:
    """An externally supplied graph cannot omit or reorder a mandatory stage."""
    exact(graph, expected, "dependency graph")
