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


def verify_fuzz_audit_links(entries: list[dict], result: dict, records: list[dict],
                           negative_controls: list[str]) -> None:
    """Bind the variable-length numerical campaign to exact execution semantics.

    This supplements recomputation and hash integrity. It is not authentication
    of an external producer and never establishes a production vulnerability.
    """
    required = {
        'schema_version', 'status', 'run_id', 'seed', 'cases', 'tested', 'failed',
        'negative_controls', 'scope_negative_passed', 'permutation_checks',
        'scaling_checks', 'oracle_checks', 'started_at', 'completed_at',
        'vulnerability_confirmed', 'execution_verified', 'fixture_only',
        'forge_executed', 'live_rpc_used', 'audit_count', 'audit_head', 'source',
    }
    if type(result) is not dict or set(result) != required:
        raise ValueError('fuzz summary schema mismatch')
    count = len(records)
    for field, value in (('schema_version', 1), ('cases', count), ('tested', count),
                         ('failed', 0), ('audit_count', 3 * count + 3),
                         ('permutation_checks', count), ('scaling_checks', count),
                         ('oracle_checks', count)):
        if type(result[field]) is not int or result[field] != value:
            raise ValueError('fuzz count/schema must be an exact integer: ' + field)
    seed = result['seed']
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('fuzz seed must be uint64')
    run_id = result['run_id']
    if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
        raise ValueError('invalid fuzz run UUID')
    if (result['status'] != 'LOCAL_FUZZ_PASS' or
            result['source'] != 'DIABLO.ScopeGuard+AuditLog/NQC.RMC016.solve'):
        raise ValueError('fuzz native source/status claim mismatch')
    for field, expected in (('fixture_only', True), ('scope_negative_passed', True),
                            ('vulnerability_confirmed', False), ('execution_verified', False),
                            ('forge_executed', False), ('live_rpc_used', False)):
        if result[field] is not expected:
            raise ValueError('fuzz execution claim mismatch: ' + field)
    if canonical(result['negative_controls']) != canonical(negative_controls):
        raise ValueError('fuzz negative control claim mismatch')
    start, end = _time(result['started_at']), _time(result['completed_at'])
    if end < start:
        raise ValueError('fuzz time interval reversed')
    expected = [('fuzz.start', {'id': run_id, 'seed': seed, 'cases': count, 'fixture_only': True})]
    for index, record in enumerate(records):
        expected.extend([
            ('scope.check', {'target': f'case-{index:04d}.lab.invalid', 'kind': 'fixture',
                             'decision': 'ALLOW', 'reason': 'in scope (*.lab.invalid)',
                             'matched_rule': '*.lab.invalid'}),
            ('fuzz.case.start', {'case': index,
                                'input_sha256': hashlib.sha256(canonical(record['input'])).hexdigest()}),
            ('fuzz.case.pass', {'case': index, 'nqc_commitment': record['nqc']['commitment'],
                               'reference_sha256': hashlib.sha256(canonical(record['reference'])).hexdigest()}),
        ])
    expected.extend([
        ('scope.check', {'target': 'blocked.lab.invalid', 'kind': 'fixture', 'decision': 'DENY',
                         'reason': 'explicitly out of scope (blocked.lab.invalid)',
                         'matched_rule': 'blocked.lab.invalid'}),
        ('fuzz.complete', {'id': run_id, 'cases': count, 'negative_controls': negative_controls,
                           'vulnerability_confirmed': False}),
    ])
    if type(entries) is not list or len(entries) != len(expected):
        raise ValueError('fuzz audit event coverage mismatch')
    last = start
    for index, (entry, (event, data)) in enumerate(zip(entries, expected)):
        if (type(entry) is not dict or set(entry) !=
                {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'}):
            raise ValueError('fuzz audit entry schema mismatch')
        if type(entry['index']) is not int or entry['index'] != index:
            raise ValueError('fuzz audit index type/order mismatch')
        if entry['event'] != event or canonical(entry['data']) != canonical(data):
            raise ValueError(f'fuzz audit semantic binding mismatch at event {index}')
        timestamp = _time(entry['timestamp'])
        if not last <= timestamp <= end:
            raise ValueError('fuzz audit timestamp out of order or run bounds')
        last = timestamp
