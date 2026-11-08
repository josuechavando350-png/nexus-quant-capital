"""Offline review of an explicitly supplied RBAC configuration, not live access.

Custom bounded model sh-rbac-v1: all assigned roles are active, hierarchy is a
DAG, denies override allows, disabled users have no effective permissions.
Separation rules constrain effective *permissions*, not a NIST conformance claim.
Two different closure algorithms must agree before any report is emitted.
No source-code execution, network, credentials, probing or policy changes.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import uuid

from .native_runtime import load_components
from .privacy import PrivateArgumentParser, redact_text
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

MODEL = 'sh-rbac-v1'
IDENTIFIER = re.compile(r'[a-z][a-z0-9_.:-]{0,63}\Z')
MAX_ROLES, MAX_USERS, MAX_PERMISSIONS, MAX_CHECKS = 64, 128, 128, 128
FILES = {'policy.json', 'analysis.json', 'graph.json', 'audit.json', 'receipt.json', 'REVIEW.md'}
CODE_FILES = ('permissions.py', 'native_runtime.py', 'safe_io.py', 'privacy.py')
ROOT = Path(__file__).resolve().parent


class PolicyError(ValueError):
    """Safe errors contain a fixed code, never input values or identifiers."""


def _need(condition: bool, code: str = 'INVALID_POLICY') -> None:
    if not condition:
        raise PolicyError(code)


def _fields(value: object, keys: set[str]) -> None:
    _need(type(value) is dict and set(value) == keys, 'SCHEMA_MISMATCH')


def _id(value: object) -> None:
    _need(type(value) is str and IDENTIFIER.fullmatch(value) is not None, 'INVALID_IDENTIFIER')


def _ids(value: object, limit: int, *, nonempty: bool = False) -> None:
    _need(type(value) is list and int(nonempty) <= len(value) <= limit, 'INVALID_LIST')
    for item in value:
        _id(item)
    _need(len(value) == len(set(value)), 'DUPLICATE_IDENTIFIER')


def validate_policy(policy: object) -> dict:
    """Validate a bounded JSON-only schema, including all references and the DAG."""
    _fields(policy, {'schema_version', 'model', 'policy_id', 'permissions', 'roles',
                     'users', 'separation_rules', 'assertions', 'revocations'})
    _need(type(policy['schema_version']) is int and policy['schema_version'] == 1, 'SCHEMA_VERSION')
    _need(policy['model'] == MODEL, 'MODEL_UNSUPPORTED')
    _id(policy['policy_id'])
    _ids(policy['permissions'], MAX_PERMISSIONS, nonempty=True)
    roles, users = policy['roles'], policy['users']
    _need(type(roles) is dict and 1 <= len(roles) <= MAX_ROLES, 'ROLE_LIMIT')
    _need(type(users) is dict and 1 <= len(users) <= MAX_USERS, 'USER_LIMIT')
    permissions, role_ids = set(policy['permissions']), set(roles)
    edges = bindings = 0
    for name, role in roles.items():
        _id(name); _fields(role, {'inherits', 'allow', 'deny'})
        _ids(role['inherits'], MAX_ROLES); _ids(role['allow'], MAX_PERMISSIONS); _ids(role['deny'], MAX_PERMISSIONS)
        _need(set(role['inherits']) <= role_ids, 'UNKNOWN_ROLE')
        _need(set(role['allow']) | set(role['deny']) <= permissions, 'UNKNOWN_PERMISSION')
        edges += len(role['inherits']); bindings += len(role['allow']) + len(role['deny'])
    for name, user in users.items():
        _id(name); _fields(user, {'roles', 'disabled'})
        _ids(user['roles'], MAX_ROLES)
        _need(set(user['roles']) <= role_ids, 'UNKNOWN_ROLE')
        _need(type(user['disabled']) is bool, 'DISABLED_MUST_BE_BOOLEAN')
        bindings += len(user['roles'])
    _need(edges <= 512 and bindings <= 8192, 'MODEL_SIZE_LIMIT')
    _topological(roles)  # Cyclic input is invalid, not an exploitable finding.
    for category in ('separation_rules', 'assertions', 'revocations'):
        entries = policy[category]
        _need(type(entries) is list and len(entries) <= MAX_CHECKS, 'CHECK_LIMIT')
        seen = set()
        for item in entries:
            keys = ({'id', 'permissions', 'max_allowed'} if category == 'separation_rules' else
                    {'id', 'user', 'permission', 'expected'} if category == 'assertions' else
                    {'id', 'user', 'remove_roles', 'must_deny'})
            _fields(item, keys); _id(item['id'])
            _need(item['id'] not in seen, 'DUPLICATE_CHECK'); seen.add(item['id'])
            if category == 'separation_rules':
                _ids(item['permissions'], MAX_PERMISSIONS, nonempty=True)
                _need(set(item['permissions']) <= permissions, 'UNKNOWN_PERMISSION')
                _need(type(item['max_allowed']) is int and 0 <= item['max_allowed'] < len(item['permissions']), 'INVALID_MAXIMUM')
            else:
                _id(item['user']); _need(item['user'] in users, 'UNKNOWN_USER')
                if category == 'assertions':
                    _id(item['permission']); _need(item['permission'] in permissions, 'UNKNOWN_PERMISSION')
                    _need(item['expected'] in ('ALLOW', 'DENY'), 'INVALID_EXPECTATION')
                else:
                    _ids(item['remove_roles'], MAX_ROLES, nonempty=True)
                    _ids(item['must_deny'], MAX_PERMISSIONS, nonempty=True)
                    _need(set(item['remove_roles']) <= set(users[item['user']]['roles']), 'REMOVE_UNASSIGNED_ROLE')
                    _need(set(item['must_deny']) <= permissions, 'UNKNOWN_PERMISSION')
    return deepcopy(policy)


def _topological(roles: dict) -> list[str]:
    remaining = {name: len(role['inherits']) for name, role in roles.items()}
    children = {name: [] for name in roles}
    for name, role in roles.items():
        for parent in role['inherits']:
            children[parent].append(name)
    queue = deque(sorted(name for name in roles if not remaining[name]))
    order = []
    while queue:
        role = queue.popleft(); order.append(role)
        for child in sorted(children[role]):
            remaining[child] -= 1
            if remaining[child] == 0:
                queue.append(child)
    _need(len(order) == len(roles), 'ROLE_HIERARCHY_CYCLE')
    return order


def _closures(roles: dict) -> dict[str, set[str]]:
    """Primary algorithm: propagation in a parent-first topological order."""
    closures = {}
    for name in _topological(roles):
        reachable = {name}
        for parent in roles[name]['inherits']:
            reachable.update(closures[parent])
        closures[name] = reachable
    return closures


def _primary(policy: dict, user: dict, closures: dict) -> dict:
    inherited = set().union(*(closures[role] for role in user['roles']))
    allow, deny = set(), set()
    for role in inherited:
        allow.update(policy['roles'][role]['allow']); deny.update(policy['roles'][role]['deny'])
    effective = set() if user['disabled'] else allow - deny
    return {'roles': sorted(inherited), 'allowed': sorted(effective),
            'explicitly_denied': sorted(deny), 'disabled': user['disabled']}


def _reference(policy: dict, user: dict) -> dict:
    """Independent algorithm: per-user graph traversal and permission bit masks.

    Does not call the primary closure or decision functions. Input validation
    and the declared model semantics are shared, so this is not a formal proof.
    """
    names = sorted(policy['permissions']); bits = {p: 1 << i for i, p in enumerate(names)}
    visited, todo = set(), list(user['roles'])
    grant_mask = deny_mask = 0
    while todo:
        role_name = todo.pop()
        if role_name in visited:
            continue
        visited.add(role_name); role = policy['roles'][role_name]
        todo.extend(role['inherits'])
        for permission in role['allow']:
            grant_mask |= bits[permission]
        for permission in role['deny']:
            deny_mask |= bits[permission]
    effective = 0 if user['disabled'] else grant_mask & ~deny_mask
    return {'roles': sorted(visited), 'allowed': [p for p in names if effective & bits[p]],
            'explicitly_denied': [p for p in names if deny_mask & bits[p]], 'disabled': user['disabled']}


def _checked_state(policy: dict, user: dict, closures: dict) -> dict:
    actual, reference = _primary(policy, user, closures), _reference(policy, user)
    _need(canonical(actual) == canonical(reference), 'REFERENCE_DISAGREEMENT')
    return actual


def analyze_policy(raw_policy: dict) -> dict:
    """Compute effective access and evaluate only explicitly supplied checks."""
    policy = validate_policy(raw_policy)
    closures = _closures(policy['roles'])
    states = {u: _checked_state(policy, spec, closures) for u, spec in sorted(policy['users'].items())}
    checks = []
    for assertion in sorted(policy['assertions'], key=lambda x: x['id']):
        actual = 'ALLOW' if assertion['permission'] in states[assertion['user']]['allowed'] else 'DENY'
        checks.append({'kind': 'assertion', 'id': assertion['id'], 'user': assertion['user'],
                       'permission': assertion['permission'], 'expected': assertion['expected'],
                       'observed_in_model': actual, 'passed': actual == assertion['expected']})
    for rule in sorted(policy['separation_rules'], key=lambda x: x['id']):
        for user, state in states.items():
            held = sorted(set(rule['permissions']) & set(state['allowed']))
            checks.append({'kind': 'separation', 'id': rule['id'], 'user': user,
                           'held_permissions': held, 'max_allowed': rule['max_allowed'],
                           'passed': len(held) <= rule['max_allowed']})
    revocations = []
    for change in sorted(policy['revocations'], key=lambda x: x['id']):
        user = deepcopy(policy['users'][change['user']])
        user['roles'] = sorted(set(user['roles']) - set(change['remove_roles']))
        after = _checked_state(policy, user, closures)
        before_permissions = set(states[change['user']]['allowed'])
        remaining = sorted(set(change['must_deny']) & set(after['allowed']))
        revocations.append({'id': change['id'], 'user': change['user'], 'after': after,
                            'unexpected_retained': remaining,
                            'gained_permissions': sorted(set(after['allowed']) - before_permissions),
                            'lost_permissions': sorted(before_permissions - set(after['allowed']))})
        checks.append({'kind': 'revocation', 'id': change['id'], 'user': change['user'],
                       'expected_denied': sorted(change['must_deny']), 'retained': remaining,
                       'passed': not remaining})
    failed = sum(check['passed'] is False for check in checks)
    status = 'POLICY_ASSERTIONS_FAIL' if failed else 'POLICY_ASSERTIONS_PASS' if checks else 'POLICY_REVIEW_ONLY'
    return {'schema_version': 1, 'model': MODEL, 'policy_id': policy['policy_id'],
            'policy_sha256': _digest(canonical(policy)), 'status': status,
            'states': states, 'checks': checks, 'revocations': revocations,
            'counts': {'users': len(states), 'roles': len(policy['roles']), 'permissions': len(policy['permissions']),
                       'checks': len(checks), 'failed': failed,
                       'reference_comparisons': len(states) + len(revocations)},
            'model_consistency_checked': True, 'live_enforcement_verified': False,
            'vulnerability_confirmed': False, 'producer_authenticated': False, 'manual_review_required': True}


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _graph(policy: dict) -> dict:
    return {'model': MODEL, 'nodes': sorted(policy['roles']),
            'edges': sorted([[role, parent] for role, spec in policy['roles'].items() for parent in spec['inherits']]),
            'edge_meaning': 'child inherits parent permissions and denies', 'acyclic': True}


def _code_digest() -> str:
    return _digest(canonical({name: _digest(read_artifact(ROOT, name)) for name in CODE_FILES}))


def render_analysis(result: dict) -> str:
    lines = ['# SUPERHUNTER — revisión de permisos declarados', '',
             f"Estado: **{result['status']}**. Modelo: `{MODEL}`.",
             'Se ha analizado una configuración JSON, no los permisos efectivos de una aplicación desplegada.',
             'La coincidencia de dos algoritmos no demuestra que la aplicación aplique esta política.', '',
             f"Usuarios: {result['counts']['users']}. Roles: {result['counts']['roles']}. "
             f"Comprobaciones declaradas: {result['counts']['checks']}. Incumplimientos: {result['counts']['failed']}.", '',
             '## Comprobaciones', '']
    for check in result['checks']:
        lines.append(f"{'✓' if check['passed'] else '✗'} {check['kind']} / {check['id']} / {check['user']}")
    if not result['checks']:
        lines.append('No se declararon propiedades esperadas: no se afirma que la política sea correcta.')
    lines += ['', '## Límites', '', 'Denegación explícita prevalece; usuario deshabilitado no obtiene permisos. '
              'Todas las asignaciones declaradas están activas. La separación se evalúa por permisos efectivos. '
              'Las revocaciones son casos suministrados, no secuencias de ataque generadas. '
              'No se incluyen ABAC, condiciones de sesión, código Solidity, permisos cloud ni sincronización externa.',
              'El paquete contiene configuración privada y debe revisarse antes de compartir.', '']
    return redact_text('\n'.join(lines)).text


def audit_policy(source: Path, out: Path) -> dict:
    _need(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    _need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CHECKOUT')
    policy = strict_json(read_artifact(source.parent, source.name))
    before = _code_digest()
    result = analyze_policy(policy)
    native = load_components()
    run_id = str(uuid.uuid4()); audit = native.audit.AuditLog()
    audit.append('permissions.start', {'run_id': run_id, 'policy_sha256': result['policy_sha256'], 'model': MODEL})
    for index, check in enumerate(result['checks']):
        audit.append('permissions.check', {'index': index, 'check_sha256': _digest(canonical(check)), 'passed': check['passed']})
    audit.append('permissions.complete', {'run_id': run_id, 'analysis_sha256': _digest(canonical(result)),
                                          'status': result['status'], 'vulnerability_confirmed': False})
    audit.assert_intact()
    _need(before == _code_digest(), 'CODE_CHANGED')
    receipt = {'schema_version': 1, 'run_id': run_id, 'code_sha256': before,
               'audit_head': audit.head, 'audit_count': len(audit), 'native_sources': list(native.provenance)}
    write_new_bundle(out, {'policy.json': canonical(policy), 'analysis.json': canonical(result),
                          'graph.json': canonical(_graph(policy)),
                          'audit.json': canonical({'entries': [asdict(e) for e in audit.entries]}),
                          'receipt.json': canonical(receipt), 'REVIEW.md': render_analysis(result).encode()})
    return verify_permissions(out)


def verify_permissions(root: Path) -> dict:
    """Recompute all model results and bind each DIABLO audit event to a check."""
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    _fields(marker, {'schema_version', 'sha256'})
    _need(type(marker['schema_version']) is int and marker['schema_version'] == 1, 'SCHEMA_VERSION')
    _fields(marker['sha256'], FILES)
    blobs = {name: read_artifact(root, name) for name in sorted(FILES)}
    _need(all(_digest(raw) == marker['sha256'][name] for name, raw in blobs.items()), 'ARTIFACT_CHANGED')
    receipt = strict_json(blobs['receipt.json'])
    _fields(receipt, {'schema_version', 'run_id', 'code_sha256', 'audit_head', 'audit_count', 'native_sources'})
    _need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1, 'SCHEMA_VERSION')
    _need(type(receipt['run_id']) is str, 'RUN_ID')
    try:
        _need(str(uuid.UUID(receipt['run_id'])) == receipt['run_id'], 'RUN_ID')
    except (ValueError, AttributeError):
        raise PolicyError('RUN_ID') from None
    _need(receipt['code_sha256'] == _code_digest(), 'STALE_CODE')
    policy = strict_json(blobs['policy.json']); result = analyze_policy(policy)
    _need(blobs['analysis.json'] == canonical(result), 'RESULT_MISMATCH')
    _need(blobs['graph.json'] == canonical(_graph(policy)), 'GRAPH_MISMATCH')
    _need(blobs['REVIEW.md'] == render_analysis(result).encode(), 'REPORT_MISMATCH')
    native = load_components()
    _need(canonical(receipt['native_sources']) == canonical(list(native.provenance)), 'SOURCE_MISMATCH')
    journal = strict_json(blobs['audit.json']); _fields(journal, {'entries'})
    entries = journal['entries']
    expected = [('permissions.start', {'run_id': receipt['run_id'], 'policy_sha256': result['policy_sha256'], 'model': MODEL})]
    expected += [('permissions.check', {'index': i, 'check_sha256': _digest(canonical(c)), 'passed': c['passed']})
                 for i, c in enumerate(result['checks'])]
    expected += [('permissions.complete', {'run_id': receipt['run_id'], 'analysis_sha256': _digest(canonical(result)),
                                           'status': result['status'], 'vulnerability_confirmed': False})]
    _need(type(entries) is list and len(entries) == len(expected), 'AUDIT_COUNT')
    _need(type(receipt['audit_count']) is int and receipt['audit_count'] == len(entries), 'AUDIT_COUNT')
    previous, timestamp = '0' * 64, None
    for index, (entry, (event, data)) in enumerate(zip(entries, expected)):
        _fields(entry, {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'})
        _need(type(entry['index']) is int and entry['index'] == index, 'AUDIT_INDEX')
        _need(entry['event'] == event and canonical(entry['data']) == canonical(data), 'AUDIT_SEMANTICS')
        _need(entry['prev_hash'] == previous, 'AUDIT_CHAIN')
        _need(type(entry['timestamp']) is str, 'AUDIT_TIME')
        try:
            current = datetime.fromisoformat(entry['timestamp'])
            _need(current.tzinfo is not None and (timestamp is None or current >= timestamp), 'AUDIT_TIME')
        except (ValueError, TypeError):
            raise PolicyError('AUDIT_TIME') from None
        _need(native.audit.AuditEntry(**entry).recompute() == entry['hash'], 'AUDIT_HASH')
        previous, timestamp = entry['hash'], current
    _need(previous == receipt['audit_head'], 'AUDIT_HEAD')
    return {'status': result['status'], 'checks': result['counts']['checks'], 'failed': result['counts']['failed'],
            'reference_comparisons': result['counts']['reference_comparisons'],
            'policy_sha256': result['policy_sha256'], 'live_enforcement_verified': False,
            'vulnerability_confirmed': False, 'producer_authenticated': False}


def example_policy() -> dict:
    """Small benign configuration illustrating approval separation and revocation."""
    return {'schema_version': 1, 'model': MODEL, 'policy_id': 'local.approval',
            'permissions': ['read', 'prepare', 'approve'],
            'roles': {'reader': {'inherits': [], 'allow': ['read'], 'deny': []},
                      'preparer': {'inherits': ['reader'], 'allow': ['prepare'], 'deny': []},
                      'approver': {'inherits': ['reader'], 'allow': ['approve'], 'deny': []}},
            'users': {'alice': {'roles': ['preparer'], 'disabled': False},
                      'bob': {'roles': ['approver'], 'disabled': False}},
            'separation_rules': [{'id': 'two.person', 'permissions': ['prepare', 'approve'], 'max_allowed': 1}],
            'assertions': [{'id': 'preparer.cannot.approve', 'user': 'alice', 'permission': 'approve', 'expected': 'DENY'},
                           {'id': 'approver.can.read', 'user': 'bob', 'permission': 'read', 'expected': 'ALLOW'}],
            'revocations': [{'id': 'remove.approver', 'user': 'bob', 'remove_roles': ['approver'], 'must_deny': ['approve']}]}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Review a local declarative permission policy; never probe an application')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('audit-permissions'); make.add_argument('--policy', type=Path, required=True)
    make.add_argument('--out', type=Path, required=True)
    verify = sub.add_parser('verify-permissions'); verify.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit_policy(args.policy, args.out) if args.command == 'audit-permissions' else verify_permissions(args.bundle)
        print(json.dumps(result, sort_keys=True))
        return 1 if result['status'] == 'POLICY_ASSERTIONS_FAIL' else 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({'status': 'POLICY_REVIEW_ERROR', 'error_code': 'INVALID_POLICY_OR_EVIDENCE'}))
        return 2
