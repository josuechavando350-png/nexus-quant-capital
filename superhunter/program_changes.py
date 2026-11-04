"""Compare verified LOCAL program snapshots and the impact on unchanged cases.

No accounts, crawling, target execution or disclosure. This describes differences
between supplied policies; it does not authenticate permission or current rules.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from . import program_registry as registry
from .native_runtime import load_components, source_inventory
from .program_registry import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_SNAPSHOT_BYTES = 20_000_000
OUTPUT_FILES = {'comparison.json', 'audit.json', 'REVIEW.md'}


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _now(value: datetime | None) -> datetime:
    value = registry.clock() if value is None else value
    need(isinstance(value, datetime) and value.tzinfo is not None, 'AWARE_TIME_REQUIRED')
    return value.astimezone(timezone.utc)


def _snapshot_names(manifest: dict) -> tuple[list[str], set[str]]:
    data = registry.validate(manifest)
    documents = sorted({p['document']['file'] for p in data['programs']})
    names = registry.FIXED_FILES | {'COMPLETE.json'} | {
        f'policy-{i:03d}.txt' for i in range(len(documents))}
    return documents, names


def capture(root: Path) -> dict[str, bytes]:
    """Capture only the exact files defined by the original registry schema."""
    need(not root.is_symlink(), 'SNAPSHOT_ROOT_SYMLINK')
    manifest = read_artifact(root, 'registry.json')
    _, names = _snapshot_names(strict_json(manifest))
    need({p.name for p in root.iterdir()} == names, 'SNAPSHOT_FILE_SET')
    data, total = {}, 0
    for name in sorted(names):
        raw = read_artifact(root, name)
        total += len(raw)
        need(total <= MAX_SNAPSHOT_BYTES, 'SNAPSHOT_SIZE_LIMIT')
        data[name] = raw
    need(data['registry.json'] == manifest, 'SNAPSHOT_CHANGED_DURING_CAPTURE')
    return data


def _restore_validate(data: dict[str, bytes], now: datetime) -> dict:
    """Verify captured bytes, not a second read of a mutable source directory."""
    need(type(data) is dict, 'SNAPSHOT_SCHEMA')
    policy = strict_json(data['registry.json'])
    documents, names = _snapshot_names(policy)
    need(set(data) == names, 'SNAPSHOT_FILE_SET')
    need(all(type(b) is bytes and len(b) <= MAX_BYTES for b in data.values()) and
         sum(map(len, data.values())) <= MAX_SNAPSHOT_BYTES, 'SNAPSHOT_SIZE_LIMIT')
    with tempfile.TemporaryDirectory(prefix='sh-policy-capture-') as temp:
        root = Path(temp)
        for name in sorted(names):
            # All names derive from fixed constants or generated numeric names.
            path = root / name
            with path.open('xb') as out:
                out.write(data[name])
            path.chmod(0o600)
        registry.verify(root, now=now)
    return {'registry': policy, 'requests': strict_json(data['requests.json']),
            'result': strict_json(data['decision.json']),
            'documents': {name: data[f'policy-{i:03d}.txt'] for i, name in enumerate(documents)}}


def _engine() -> dict:
    names = ('program_changes.py', 'program_registry.py', 'safe_io.py', 'native_runtime.py')
    return {'sources': {name: hashlib.sha256(read_artifact(ROOT, name)).hexdigest() for name in names},
            'native_sources': source_inventory()}


def _assets(program: dict | None, field: str) -> set[str]:
    return {registry.digest(registry.asset(a)) for a in program[field]} if program else set()


def compare(before: dict[str, bytes], after: dict[str, bytes], *, now: datetime | None = None) -> tuple[dict, dict]:
    """Keep case identity fixed; distinguish clock expiry from policy changes."""
    now = _now(now)
    engine_before = _engine()
    old, new = (_restore_validate(data, now) for data in (before, after))
    old_time = registry.utc(old['result']['checked_at'])
    new_time = registry.utc(new['result']['checked_at'])
    need(old_time <= new_time <= now, 'SNAPSHOT_ORDER')
    old_cases = {c['id']: c for c in registry.validate_requests(old['requests'])['cases']}
    new_cases = {c['id']: c for c in registry.validate_requests(new['requests'])['cases']}
    # A renamed/removed case must not make a loss of eligibility disappear.
    need(canonical(old_cases) == canonical(new_cases), 'CASE_IDENTITY_SET_CHANGED')
    controlled, _ = registry.evaluate(old['registry'], old['documents'], old['requests'], now=new_time)
    controlled_map = {d['case_id']: d for d in controlled['decisions']}
    old_map = {d['case_id']: d for d in old['result']['decisions']}
    new_map = {d['case_id']: d for d in new['result']['decisions']}
    programs_old = {registry.program_key(p): p for p in old['registry']['programs']}
    programs_new = {registry.program_key(p): p for p in new['registry']['programs']}
    changes = []
    for key in sorted(set(programs_old) | set(programs_new)):
        a, b = programs_old.get(key), programs_new.get(key)
        if a is None or b is None:
            fields = ['PROGRAM_ADDED' if a is None else 'PROGRAM_REMOVED']
        else:
            fields = [k for k in sorted(a) if canonical(a[k]) != canonical(b[k])]
        doc_old = old['documents'][a['document']['file']] if a else None
        doc_new = new['documents'][b['document']['file']] if b else None
        if a is not None and b is not None and doc_old != doc_new and 'document' not in fields:
            fields.append('DOCUMENT_BYTES_CHANGED_WITHOUT_METADATA')
        if not fields:
            continue
        changes.append({'program_key_sha256': registry.digest(key), 'changed_fields': fields,
                        'before_revision': registry.revision(a) if a else None,
                        'after_revision': registry.revision(b) if b else None,
                        'document_bytes_changed': doc_old != doc_new,
                        'assets_added_sha256': sorted(_assets(b, 'assets') - _assets(a, 'assets')),
                        'assets_removed_sha256': sorted(_assets(a, 'assets') - _assets(b, 'assets')),
                        'exclusions_added_sha256': sorted(_assets(b, 'excluded') - _assets(a, 'excluded')),
                        'exclusions_removed_sha256': sorted(_assets(a, 'excluded') - _assets(b, 'excluded'))})
    effects = []
    for case_id in sorted(old_cases):
        a, control, b = old_map[case_id], controlled_map[case_id], new_map[case_id]
        was, is_now = a['status'] == 'ELIGIBLE_LOCAL_REVIEW', b['status'] == 'ELIGIBLE_LOCAL_REVIEW'
        transition = ('LOST_LOCAL_ELIGIBILITY' if was and not is_now else
                      'GAINED_LOCAL_ELIGIBILITY' if is_now and not was else
                      'STILL_ELIGIBLE_LOCAL_REVIEW' if is_now else 'STILL_BLOCKED')
        effects.append({'case_id': case_id, 'case_sha256': registry.digest(old_cases[case_id]),
                        'transition': transition, 'before_status': a['status'], 'after_status': b['status'],
                        'before_reasons': a['reasons'], 'after_reasons': b['reasons'],
                        'old_policy_at_after_time_status': control['status'],
                        'old_policy_at_after_time_reasons': control['reasons'],
                        'clock_changes_decision': (a['status'], a['reasons']) != (control['status'], control['reasons']),
                        'snapshot_changes_decision': (control['status'], control['reasons']) != (b['status'], b['reasons']),
                        'human_review_required': True, 'live_testing_authorized': False})
    evidence = {label: {n: hashlib.sha256(raw).hexdigest() for n, raw in sorted(data.items())}
                for label, data in (('before', before), ('after', after))}
    result = {'schema_version': 1, 'status': 'LOCAL_POLICY_CHANGE_REVIEW',
              'compared_at': now.isoformat(), 'before_checked_at': old_time.isoformat(),
              'after_checked_at': new_time.isoformat(), 'evidence_sha256': evidence,
              'engine_identity': engine_before, 'case_count': len(effects),
              'transition_counts': dict(sorted(Counter(e['transition'] for e in effects).items())),
              'program_changes': changes, 'case_effects': effects,
              'same_case_identities': True, 'source_order_authenticated': False,
              'authorization_authenticated': False, 'latest_remote_policy_verified': False,
              'network_used': False, 'live_testing_authorized': False,
              'submission_enabled': False, 'vulnerability_confirmed': False}
    audit = load_components().audit.AuditLog(clock=lambda: now.isoformat())
    audit.append('programs.change.start', {'evidence_sha256': evidence})
    for change in changes:
        audit.append('programs.change.policy', change)
    for effect in effects:
        audit.append('programs.change.case', effect)
    audit.append('programs.change.complete', {'result_sha256': registry.digest(result)})
    audit.assert_intact()
    need(_engine() == engine_before, 'ENGINE_CHANGED_DURING_COMPARISON')
    return result, {'entries': [asdict(e) for e in audit.entries]}


def render(result: dict) -> bytes:
    text = ['# Cambios de alcance — revisión local', '',
            f"Expedientes idénticos comparados: {result['case_count']}.",
            f"Programas con cambios: {len(result['program_changes'])}."]
    text += [f'{key}: {value}' for key, value in sorted(result['transition_counts'].items())]
    text += ['', 'Se comparan dos instantáneas aportadas. No se verificaron reglas actuales por red,',
             'cuentas, permisos del titular, ni elegibilidad para pago. No se ejecutó ningún objetivo.',
             'Un cambio favorable solo admite revisión local; requiere revisión humana.',
             'El paquete completo contiene documentos privados y no debe publicarse.', '']
    return '\n'.join(text).encode()


def create(before: Path, after: Path, out: Path, *, now: datetime | None = None) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    need(not any(out.resolve().is_relative_to(p.resolve()) for p in (before, after)), 'OUTPUT_INSIDE_INPUT')
    captured = {'before': capture(before), 'after': capture(after)}
    now = _now(now)
    result, audit = compare(captured['before'], captured['after'], now=now)
    # Capture remains the source of truth; reject mutation before publishing.
    need(capture(before) == captured['before'] and capture(after) == captured['after'], 'SOURCE_CHANGED')
    files = {f'{side}--{name}': raw for side, data in captured.items() for name, raw in data.items()}
    files.update({'comparison.json': canonical(result), 'audit.json': canonical(audit), 'REVIEW.md': render(result)})
    need(all(len(raw) <= MAX_BYTES for raw in files.values()), 'OUTPUT_SIZE_LIMIT')
    write_new_bundle(out, files)
    return verify(out, now=now)


def verify(root: Path, *, now: datetime | None = None) -> dict:
    now = _now(now)
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict, 'MANIFEST_SCHEMA')
    packed = {}
    expected = set(OUTPUT_FILES)
    for side in ('before', 'after'):
        policy = strict_json(read_artifact(root, side+'--registry.json'))
        _, names = _snapshot_names(policy)
        expected.update(side+'--'+n for n in names)
        packed[side], total = {}, 0
        for name in sorted(names):
            raw = read_artifact(root, side+'--'+name)
            total += len(raw)
            need(total <= MAX_SNAPSHOT_BYTES, 'SNAPSHOT_SIZE_LIMIT')
            packed[side][name] = raw
    need(set(marker['sha256']) == expected and {p.name for p in root.iterdir()} == expected | {'COMPLETE.json'}, 'BUNDLE_FILE_SET')
    stored = {n: read_artifact(root, n) for n in OUTPUT_FILES}
    all_data = {**stored, **{s+'--'+n: raw for s,d in packed.items() for n,raw in d.items()}}
    need(all(hashlib.sha256(raw).hexdigest() == marker['sha256'][n] for n,raw in all_data.items()), 'BUNDLE_HASH')
    statement = strict_json(stored['comparison.json'])
    at = registry.utc(statement['compared_at'])
    need(at <= now, 'FUTURE_COMPARISON')
    result, audit = compare(packed['before'], packed['after'], now=at)
    need(stored['comparison.json'] == canonical(result) and stored['audit.json'] == canonical(audit) and
         stored['REVIEW.md'] == render(result), 'COMPARISON_REPLAY_DISAGREEMENT')
    current = _restore_validate(packed['after'], now)
    fresh, _ = registry.evaluate(current['registry'], current['documents'], current['requests'], now=now)
    return {'status': 'LOCAL_POLICY_CHANGE_REVIEW_VERIFIED', 'transition_counts': result['transition_counts'],
            'case_count': result['case_count'], 'current_after_counts': fresh['counts'],
            'current_after_decisions': fresh['decisions'], 'current_at': now.isoformat(),
            'historical_compared_at': result['compared_at'], 'authorization_authenticated': False,
            'latest_remote_policy_verified': False, 'live_testing_authorized': False,
            'submission_enabled': False, 'vulnerability_confirmed': False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Compare local program-policy snapshots; never test targets')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('compare-programs')
    for name in ('before', 'after', 'out'):
        make.add_argument('--'+name, type=Path, required=True)
    sub.add_parser('verify-program-changes').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.before, args.after, args.out) if args.command == 'compare-programs' else verify(args.bundle)
        print(json.dumps({k: result[k] for k in ('status', 'case_count', 'transition_counts',
                           'current_after_counts', 'live_testing_authorized')}))
        return 1 if result['current_after_counts'].get('BLOCKED') else 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError):
        print(json.dumps({'status': 'POLICY_CHANGE_REVIEW_ERROR', 'live_testing_authorized': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
