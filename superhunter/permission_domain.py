"""Exhaustive finite RBAC configuration checking, not exploit planning.

Only JSON policies in our existing sh-rbac-v1 model are evaluated. Variables
independently toggle direct role assignments; this is NOT a reachability model
of a deployed application. No code, URLs, RPC, commands or credentials execute.
A full finite-domain result says nothing about omitted inputs or real enforcement.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
from itertools import islice, product
import json
from pathlib import Path
import uuid

from . import permissions
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle, MAX_BYTES

MODEL = 'sh-rbac-domain-v1'
MAX_VARIABLES = 16
MAX_STATES = 4096
MAX_WORK = 500_000
MAX_WITNESSES = 16
CHUNK = 64
ROOT = Path(__file__).resolve().parent
FILES = {'model.json', 'analysis.json', 'audit.json', 'receipt.json', 'REVIEW.md'}
CODE_FILES = ('permission_domain.py', 'permissions.py', 'safe_io.py',
              'privacy.py', 'native_runtime.py')


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise permissions.PolicyError(code)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_model(raw: object) -> dict:
    _need(type(raw) is dict and set(raw) == {'schema_version', 'model', 'policy',
                                            'variables', 'max_states'}, 'DOMAIN_SCHEMA')
    _need(type(raw['schema_version']) is int and raw['schema_version'] == 1, 'DOMAIN_VERSION')
    _need(raw['model'] == MODEL, 'DOMAIN_MODEL')
    policy = permissions.validate_policy(raw['policy'])
    _need(len(policy['roles']) <= 32 and len(policy['users']) <= 16 and
          len(policy['permissions']) <= 64 and
          sum(len(policy[k]) for k in ('assertions', 'separation_rules', 'revocations')) <= 64,
          'DOMAIN_POLICY_LIMIT')
    variables = raw['variables']
    _need(type(variables) is list and len(variables) <= MAX_VARIABLES, 'DOMAIN_VARIABLE_LIMIT')
    seen = set()
    for variable in variables:
        _need(type(variable) is dict and set(variable) == {'user', 'role'}, 'DOMAIN_VARIABLE_SCHEMA')
        u, r = variable['user'], variable['role']
        _need(type(u) is str and u in policy['users'] and type(r) is str and r in policy['roles'],
              'DOMAIN_UNKNOWN_REFERENCE')
        _need((u, r) not in seen, 'DOMAIN_DUPLICATE_VARIABLE')
        seen.add((u, r))
    _need(type(raw['max_states']) is int and 1 <= raw['max_states'] <= MAX_STATES, 'DOMAIN_STATE_BUDGET')
    return deepcopy(raw)


def _primary_assignment(policy: dict, variables: list[dict], index: int) -> dict:
    users = deepcopy(policy['users'])
    for j, variable in enumerate(variables):
        if (index >> j) & 1:
            roles = set(users[variable['user']]['roles'])
            role = variable['role']
            roles.symmetric_difference_update({role})
            users[variable['user']]['roles'] = sorted(roles)
    return users


def _reference_assignment(policy: dict, variables: list[dict], choices: tuple[bool, ...]) -> dict:
    # Direct membership construction instead of mutating a copy with XOR.
    flags = {(v['user'], v['role']): enabled for v, enabled in zip(variables, choices)}
    return {u: {'roles': sorted(r for r in policy['roles']
                               if (r in spec['roles']) != flags.get((u, r), False)),
                'disabled': spec['disabled']} for u, spec in policy['users'].items()}


def _decisions(policy: dict, users: dict, closures: dict) -> dict:
    result = {}
    for user, spec in sorted(users.items()):
        first = permissions._primary(policy, spec, closures)
        second = permissions._reference(policy, spec)
        _need(canonical(first) == canonical(second), 'DOMAIN_PERMISSION_DISAGREEMENT')
        result[user] = first
    return result


def _property_ids(policy: dict) -> list[str]:
    ids = ['assertion:' + x['id'] for x in policy['assertions']]
    ids += ['separation:' + x['id'] + ':' + u for x in policy['separation_rules']
            for u in sorted(policy['users'])]
    ids += ['revocation:' + x['id'] for x in policy['revocations']]
    _need(len(ids) == len(set(ids)), 'DOMAIN_PROPERTY_ID_COLLISION')
    return ids


def _properties(policy: dict, users: dict, states: dict, closures: dict) -> tuple[list[dict], int]:
    checks, comparisons = [], 0
    for x in policy['assertions']:
        actual = 'ALLOW' if x['permission'] in states[x['user']]['allowed'] else 'DENY'
        checks.append({'id': 'assertion:' + x['id'], 'applicable': True,
                       'passed': actual == x['expected']})
    for x in policy['separation_rules']:
        for u in sorted(users):
            checks.append({'id': 'separation:' + x['id'] + ':' + u, 'applicable': True,
                           'passed': len(set(x['permissions']) & set(states[u]['allowed'])) <= x['max_allowed']})
    for x in policy['revocations']:
        # An atomic, declared removal, not a planned sequence against a service.
        u = x['user']
        applicable = set(x['remove_roles']) <= set(users[u]['roles'])
        passed = None
        if applicable:
            after = deepcopy(users[u])
            after['roles'] = sorted(set(after['roles']) - set(x['remove_roles']))
            checked = _decisions(policy, {u: after}, closures)[u]
            comparisons += 1
            passed = not bool(set(x['must_deny']) & set(checked['allowed']))
        checks.append({'id': 'revocation:' + x['id'], 'applicable': applicable, 'passed': passed})
    return checks, comparisons


def analyze_domain(raw_model: object) -> dict:
    """Enumerate a declared finite Cartesian domain, with complete coverage accounting.

    No randomness, assumptions about production reachability, SMT or code parsing.
    A violating configuration is a counterexample to the model, not an exploit.
    """
    model = validate_model(raw_model)
    policy, variables = model['policy'], model['variables']
    closures = permissions._closures(policy['roles'])
    total = 1 << len(variables)
    ids = _property_ids(policy)
    # Bound the combination of policy size and state count, not merely state count.
    per_state_work = max(1, len(ids) + (len(policy['users']) + len(policy['revocations'])) *
                         (len(policy['roles']) + len(policy['permissions'])))
    safety_limit = max(1, MAX_WORK // per_state_work)
    count = min(total, model['max_states'], safety_limit)
    reasons = []
    if total > model['max_states']:
        reasons.append('STATE_BUDGET')
    if min(total, model['max_states']) > safety_limit:
        reasons.append('WORK_BUDGET')
    coverage = {i: {'evaluated': 0, 'failed': 0, 'not_applicable': 0} for i in ids}
    records, witnesses = [], []
    failed_configs = comparisons = evaluations = 0
    chain = '0' * 64
    combinations = islice(product((False, True), repeat=len(variables)), count)
    for index, tuple_msb in enumerate(combinations):
        users = _primary_assignment(policy, variables, index)
        other_users = _reference_assignment(policy, variables, tuple(reversed(tuple_msb)))
        # Canonicalize role ordering, which has no semantic meaning in this model.
        for spec in users.values():
            spec['roles'] = sorted(spec['roles'])
        _need(canonical(users) == canonical(other_users), 'DOMAIN_ENUMERATION_DISAGREEMENT')
        states = _decisions(policy, users, closures)
        checks, extra = _properties(policy, users, states, closures)
        comparisons += len(users) + extra
        failures = []
        for check in checks:
            slot = coverage[check['id']]
            if not check['applicable']:
                slot['not_applicable'] += 1
            else:
                evaluations += 1
                slot['evaluated'] += 1
                if check['passed'] is False:
                    slot['failed'] += 1
                    failures.append(check['id'])
        failed_configs += bool(failures)
        if failures and len(witnesses) < MAX_WITNESSES:
            witnesses.append({'configuration_index': index, 'assignments': users,
                              'violated_properties': failures})
        row = {'index': index, 'assignment_sha256': _digest(canonical(users)),
               'decision_sha256': _digest(canonical(states)), 'checks_sha256': _digest(canonical(checks)),
               'failed_properties': len(failures)}
        chain = _digest(bytes.fromhex(chain) + canonical(row))
        records.append(row)
    complete = count == total
    nonvacuous = bool(ids) and all(x['evaluated'] > 0 for x in coverage.values())
    status = ('POLICY_DOMAIN_VIOLATION' if failed_configs else
              'POLICY_DOMAIN_VERIFIED' if complete and nonvacuous else 'POLICY_DOMAIN_INCONCLUSIVE')
    if not ids:
        reasons.append('NO_PROPERTIES')
    elif not nonvacuous:
        reasons.append('UNEXERCISED_PROPERTY')
    return {'schema_version': 1, 'model': MODEL, 'model_sha256': _digest(canonical(model)),
            'status': status, 'coverage_complete': complete, 'all_properties_exercised': nonvacuous,
            'proven_for_declared_domain': status == 'POLICY_DOMAIN_VERIFIED',
            'domain_configurations': total, 'examined_configurations': count,
            'unexamined_configurations': total - count, 'violating_configurations': failed_configs,
            'property_evaluations': evaluations, 'permission_reference_comparisons': comparisons,
            'assignment_reference_comparisons': count, 'coverage_chain_sha256': chain,
            'bound_reasons': reasons, 'property_coverage': coverage, 'witnesses': witnesses,
            'witnesses_truncated': failed_configs > len(witnesses), 'configurations': records,
            'live_enforcement_verified': False, 'production_reachability_verified': False,
            'vulnerability_confirmed': False, 'producer_authenticated': False,
            'smt_used': False, 'solidity_analyzed': False, 'manual_review_required': True}


def _code_digest() -> str:
    return _digest(canonical({name: _digest(read_artifact(ROOT, name)) for name in CODE_FILES}))


def _events(result: dict, run_id: str) -> list[tuple[str, dict]]:
    events = [('domain.start', {'run_id': run_id, 'model_sha256': result['model_sha256'], 'model': MODEL})]
    for offset in range(0, len(result['configurations']), CHUNK):
        rows = result['configurations'][offset:offset + CHUNK]
        events.append(('domain.coverage', {'first_index': offset, 'count': len(rows),
                                          'rows_sha256': _digest(canonical(rows))}))
    events.append(('domain.complete', {'run_id': run_id, 'analysis_sha256': _digest(canonical(result)),
                                       'status': result['status'], 'vulnerability_confirmed': False}))
    return events


def render_domain(result: dict) -> bytes:
    # Summary only: don't echo policy IDs, user IDs, role names or witness values.
    return (f"# Verificación de configuraciones de permisos\n\nEstado: **{result['status']}**.\n\n"
            f"Configuraciones: {result['examined_configurations']} examinadas de {result['domain_configurations']}. "
            f"Incumplimientos por configuración: {result['violating_configurations']}.\n\n"
            f"Evaluaciones de propiedades: {result['property_evaluations']}. "
            f"Comparaciones de decisiones: {result['permission_reference_comparisons']}.\n\n"
            "VERIFIED significa cobertura completa únicamente del dominio JSON declarado. "
            "INCONCLUSIVE no es aprobación; VIOLATION es un contraejemplo del modelo, no un exploit.\n\n"
            "No analiza Solidity, no usa SMT y no demuestra alcanzabilidad ni permisos de una aplicación real. "
            "Los dos algoritmos comparten especificaciones y validación; no garantizan ausencia universal de errores. "
            "Los originales y contraejemplos están en archivos privados; el resumen no los reproduce. "
            "Los hashes no autentican un productor remoto.\n").encode('utf-8')


def audit_domain(source: Path, out: Path) -> dict:
    _need(not out.exists() and not out.is_symlink(), 'DOMAIN_OUTPUT_EXISTS')
    _need(not out.resolve().is_relative_to(ROOT.parent), 'DOMAIN_OUTPUT_INSIDE_CHECKOUT')
    raw = read_artifact(source.parent, source.name)
    model = strict_json(raw)
    code = _code_digest()
    result = analyze_domain(model)
    _need(len(canonical(result)) <= MAX_BYTES, 'DOMAIN_OUTPUT_LIMIT')
    native = load_components()
    run_id = str(uuid.uuid4())
    audit = native.audit.AuditLog()
    for event, data in _events(result, run_id):
        audit.append(event, data)
    audit.assert_intact()
    _need(_code_digest() == code, 'DOMAIN_CODE_CHANGED')
    receipt = {'schema_version': 1, 'run_id': run_id, 'code_sha256': code,
               'audit_count': len(audit), 'audit_head': audit.head,
               'native_sources': list(native.provenance)}
    write_new_bundle(out, {'model.json': raw, 'analysis.json': canonical(result),
                          'audit.json': canonical({'entries': [asdict(e) for e in audit.entries]}),
                          'receipt.json': canonical(receipt), 'REVIEW.md': render_domain(result)})
    return verify_domain(out)


def verify_domain(root: Path) -> dict:
    before = _code_digest()
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    _need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
          marker['schema_version'] == 1 and type(marker['sha256']) is dict and
          set(marker['sha256']) == FILES, 'DOMAIN_MANIFEST')
    _need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'DOMAIN_FILE_SET')
    blobs = {name: read_artifact(root, name) for name in sorted(FILES)}
    _need(all(_digest(raw) == marker['sha256'][name] for name, raw in blobs.items()), 'DOMAIN_ARTIFACT_HASH')
    receipt = strict_json(blobs['receipt.json'])
    _need(set(receipt) == {'schema_version', 'run_id', 'code_sha256', 'audit_count', 'audit_head',
                            'native_sources'} and type(receipt['schema_version']) is int and
          receipt['schema_version'] == 1, 'DOMAIN_RECEIPT')
    _need(type(receipt['run_id']) is str and str(uuid.UUID(receipt['run_id'])) == receipt['run_id'], 'DOMAIN_RUN_ID')
    _need(receipt['code_sha256'] == before, 'DOMAIN_STALE_CODE')
    result = analyze_domain(strict_json(blobs['model.json']))
    _need(blobs['analysis.json'] == canonical(result), 'DOMAIN_RECALCULATION_MISMATCH')
    _need(blobs['REVIEW.md'] == render_domain(result), 'DOMAIN_REPORT_MISMATCH')
    native = load_components()
    _need(canonical(receipt['native_sources']) == canonical(list(native.provenance)), 'DOMAIN_NATIVE_SOURCE')
    journal = strict_json(blobs['audit.json'])
    _need(set(journal) == {'entries'}, 'DOMAIN_AUDIT_SCHEMA')
    rows, events = journal['entries'], _events(result, receipt['run_id'])
    _need(type(rows) is list and len(rows) == len(events) and
          type(receipt['audit_count']) is int and receipt['audit_count'] == len(rows), 'DOMAIN_AUDIT_COUNT')
    prev, time = '0' * 64, None
    for i, (row, (event, data)) in enumerate(zip(rows, events)):
        _need(type(row) is dict and set(row) == {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'}, 'DOMAIN_AUDIT_ROW')
        _need(type(row['index']) is int and row['index'] == i and row['event'] == event and
              canonical(row['data']) == canonical(data), 'DOMAIN_AUDIT_SEMANTICS')
        _need(type(row['timestamp']) is str, 'DOMAIN_AUDIT_TIME')
        now = datetime.fromisoformat(row['timestamp'])
        _need(now.tzinfo is not None and (time is None or now >= time), 'DOMAIN_AUDIT_TIME')
        _need(row['prev_hash'] == prev and native.audit.AuditEntry(**row).recompute() == row['hash'], 'DOMAIN_AUDIT_HASH')
        prev, time = row['hash'], now
    _need(prev == receipt['audit_head'], 'DOMAIN_AUDIT_HEAD')
    _need(_code_digest() == before, 'DOMAIN_CODE_CHANGED')
    return {key: result[key] for key in ('status', 'model_sha256', 'domain_configurations',
            'examined_configurations', 'violating_configurations', 'coverage_complete',
            'proven_for_declared_domain', 'vulnerability_confirmed', 'live_enforcement_verified')}


def example_model(*, corrected: bool = False) -> dict:
    policy = permissions.example_policy()
    if corrected:
        policy['roles']['preparer']['deny'] = ['approve']
    return {'schema_version': 1, 'model': MODEL, 'policy': policy,
            'variables': [{'user': 'alice', 'role': 'approver'}, {'user': 'bob', 'role': 'preparer'}],
            'max_states': 4}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Exhaustively check bounded local policy configurations, not deployed targets')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('check-permission-domain')
    make.add_argument('--model', type=Path, required=True)
    make.add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-permission-domain').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (audit_domain(args.model, args.out) if args.command == 'check-permission-domain'
                  else verify_domain(args.bundle))
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'POLICY_DOMAIN_VERIFIED' else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({'status': 'POLICY_DOMAIN_ERROR', 'error_code': 'INVALID_MODEL_OR_EVIDENCE',
                          'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
