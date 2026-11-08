"""Report temporal input coverage of the eleven existing OWNED sequences.

This describes which abstract conditions inputs exercise. It never executes a
model or EVM, generates test sequences, or infers a vulnerability from a gap.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import owned_authority_cases as corpus
from . import owned_authority_coverage_reference as reference
from . import quality
from .owned_authority_model import need, validate_events
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-temporal-input-coverage-v1'
CONDITIONS = (
    'use_without_control', 'current_grant_use', 'revoked_grant_use',
    'stale_grant_after_regrant_use', 'principal_mismatch_use',
    'scope_mismatch_use', 'repeated_current_grant_use',
    'current_grant_after_revocation_use')
FILES = {'inputs.json', 'coverage.json', 'REVIEW.md'}


def coverage(events: list) -> dict[str, list[int]]:
    """Incremental state per fixed principal/tenant/action; at most 64 events."""
    validate_events(events)
    states, uses = {}, set()
    hits = {name: [] for name in CONDITIONS}
    for index, event in enumerate(events):
        key = tuple(event[f] for f in ('principal', 'tenant', 'action'))
        state = states.setdefault(key, {'generation': 0, 'active': False,
                                        'issued': set(), 'revoked': set(),
                                        'had_revocation': False})
        if event['op'] != 'use':
            state['generation'] += 1
            state['active'] = event['op'] == 'grant'
            if state['active']:
                state['issued'].add(state['generation'])
            else:
                state['had_revocation'] = True
                state['revoked'].update(state['issued'])
            continue
        credential = event['credential']
        principal = credential['principal'] == event['principal']
        scope = (credential['tenant'], credential['action']) == (event['tenant'], event['action'])
        if not principal:
            hits['principal_mismatch_use'].append(index)
        if not scope:
            hits['scope_mismatch_use'].append(index)
        if not (principal and scope):
            continue
        generation = credential['generation']
        if state['generation'] == 0:
            hits['use_without_control'].append(index)
        if generation in state['revoked']:
            name = ('stale_grant_after_regrant_use' if state['active'] else 'revoked_grant_use')
            hits[name].append(index)
        if state['active'] and generation == state['generation']:
            hits['current_grant_use'].append(index)
            if state['had_revocation']:
                hits['current_grant_after_revocation_use'].append(index)
            identity = (*key, generation)
            if identity in uses:
                hits['repeated_current_grant_use'].append(index)
            uses.add(identity)
    return hits


def _inputs() -> dict:
    return {'schema_version': 1, 'profile': PROFILE, 'cases': [
        {'case_id': c['case_id'], 'events': c['events']} for c in corpus.cases()]}


def _report(inputs: dict, expected: str) -> dict:
    rows, groups = [], {}
    for case in inputs['cases']:
        events = case['events']
        result = coverage(events)
        need(canonical(result) == canonical(reference.coverage(events)),
             'AUTHORITY_COVERAGE_REFERENCE_DISAGREEMENT')
        digest = quality.sha(canonical(events))
        groups.setdefault(digest, []).append(case['case_id'])
        rows.append({'case_id': case['case_id'], 'events_sha256': digest,
                     'event_count': len(events), 'witness_indices': result,
                     'covered_conditions': [name for name in CONDITIONS if result[name]],
                     'uncovered_conditions': [name for name in CONDITIONS if not result[name]]})
    return {'schema_version': 1, 'profile': PROFILE,
            'status': 'OWNED_TEMPORAL_INPUT_COVERAGE_REVIEWED',
            'source_digest': expected, 'case_count': len(rows),
            'condition_count': len(CONDITIONS), 'conditions': list(CONDITIONS),
            'unique_event_sequences': len(groups), 'cases': rows,
            'duplicate_event_sequences': [
                {'events_sha256': digest, 'case_ids': ids}
                for digest, ids in sorted(groups.items()) if len(ids) > 1],
            'uncovered_in_all_cases': [name for name in CONDITIONS
                if not any(row['witness_indices'][name] for row in rows)],
            'input_only': True, 'synthetic_known_sequences': True,
            'native_execution_performed': False, 'vulnerability_confirmed': False,
            'producer_authenticated': False, 'global_progress': None,
            'historical_detection_metrics_modified': False}


def _render(report: dict) -> bytes:
    lines = ['# Cobertura temporal de entradas propias', '',
             'Once secuencias sintéticas conocidas; ocho condiciones explícitas.',
             'Los índices señalan eventos de entrada, no resultados de ejecución.',
             'Una condición ausente es un hueco de cobertura, no una vulnerabilidad.',
             'No se modifican secuencias, etiquetas ni métricas históricas.', '',
             '| Caso | Condiciones observadas | Condiciones ausentes |',
             '| --- | --- | --- |']
    for row in report['cases']:
        lines.append('| ' + row['case_id'] + ' | ' +
                     ', '.join(row['covered_conditions']) + ' | ' +
                     ', '.join(row['uncovered_conditions']) + ' |')
    lines += ['', 'Las secuencias repetidas no son muestras independientes.',
              'La coincidencia de dos algoritmos comparte especificación y datos;',
              'no demuestra completitud, autenticidad o generalización.']
    return ('\n'.join(lines) + '\n').encode()


def _execute(expected: str) -> dict[str, bytes]:
    before = quality.source_snapshot()
    need(quality.sha(canonical(before)) == expected, 'AUTHORITY_COVERAGE_SOURCE')
    inputs = _inputs()
    result = _report(inputs, expected)
    need(before == quality.source_snapshot(), 'AUTHORITY_COVERAGE_SOURCE_CHANGED')
    return {'inputs.json': canonical(inputs), 'coverage.json': canonical(result),
            'REVIEW.md': _render(result)}


def create(out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'AUTHORITY_COVERAGE_PRIVATE_OUTPUT')
    expected = quality.sha(canonical(quality.source_snapshot()))
    payload = _execute(expected)
    write_new_bundle(out, payload)
    return strict_json(payload['coverage.json'])


def _inventory(root: Path) -> set[str]:
    need(root.is_dir() and not root.is_symlink(), 'AUTHORITY_COVERAGE_DIRECTORY')
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index <= len(FILES), 'AUTHORITY_COVERAGE_INVENTORY')
        names.add(entry.name)
    need(names == FILES | {'COMPLETE.json'}, 'AUTHORITY_COVERAGE_INVENTORY')
    return names


def verify(root: Path, expected: str) -> dict:
    names = _inventory(root)
    marker_raw = read_artifact(root, 'COMPLETE.json')
    files = {name: read_artifact(root, name) for name in FILES}
    marker = {'schema_version': 1, 'sha256': {
        name: quality.sha(raw) for name, raw in files.items()}}
    need(canonical(strict_json(marker_raw)) == canonical(marker), 'AUTHORITY_COVERAGE_HASH')
    regenerated = _execute(expected)
    need(files == regenerated, 'AUTHORITY_COVERAGE_REPLAY_MISMATCH')
    need(all(read_artifact(root, name) == raw for name, raw in files.items()) and
         read_artifact(root, 'COMPLETE.json') == marker_raw and _inventory(root) == names,
         'AUTHORITY_COVERAGE_CHANGED_DURING_REPLAY')
    need(quality.sha(canonical(quality.source_snapshot())) == expected, 'AUTHORITY_COVERAGE_SOURCE')
    return strict_json(regenerated['coverage.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Review temporal input coverage of fixed OWNED records')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('review-owned-authority-coverage')
    make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-authority-coverage')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'review-owned-authority-coverage' else verify(
            args.bundle, args.expected_source)
        print(json.dumps({key: result[key] for key in (
            'status', 'source_digest', 'case_count', 'condition_count', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'OWNED_TEMPORAL_COVERAGE_BLOCKED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
