"""Evaluate fixed OWNED input counter-controls without executing a detector.

The historical corpus stays separate. Both algorithms receive events only;
authored expected indices are compared after calculation, never fed into it.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import owned_authority_cases as historical
from . import owned_authority_coverage as analyzer
from . import owned_authority_coverage_reference as reference
from . import owned_authority_coverage_cases as corpus
from . import quality
from .owned_authority_model import need, validate_events
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = corpus.PROFILE
CORPUS_SHA256 = 'eb2898a1714961bd4bf918ef096cb8cd8ee66622269284b4918a18ff6724261e'
HISTORICAL_CASES_SHA256 = 'a0c577c4cad38f8518dfafa1860e77415e1e94a69136ee5e1b2b7b8777e78c0c'
FILES = {'inputs.json', 'evaluation.json', 'REVIEW.md'}
CASE_KEYS = {'case_id', 'condition', 'role', 'events', 'expected_witness_indices'}


def _validate_cases(rows: list) -> None:
    need(type(rows) is list and len(rows) == 16, 'COVERAGE_SUITE_CASE_COUNT')
    identities = set()
    for row in rows:
        need(type(row) is dict and set(row) == CASE_KEYS, 'COVERAGE_SUITE_CASE_SCHEMA')
        condition, role = row['condition'], row['role']
        need(type(condition) is str and condition in analyzer.CONDITIONS and
             type(role) is str and role in ('present', 'absent'), 'COVERAGE_SUITE_PAIR')
        identity = condition + '--' + role
        need(row['case_id'] == identity and identity not in identities,
             'COVERAGE_SUITE_CASE_IDENTITY')
        identities.add(identity)
        events, expected = row['events'], row['expected_witness_indices']
        validate_events(events)
        need(type(expected) is dict and set(expected) == set(analyzer.CONDITIONS),
             'COVERAGE_SUITE_EXPECTATION_SCHEMA')
        for indices in expected.values():
            need(type(indices) is list and len(indices) <= len(events),
                 'COVERAGE_SUITE_WITNESS')
            need(all(type(i) is int and 0 <= i < len(events) and
                     events[i]['op'] == 'use' for i in indices), 'COVERAGE_SUITE_WITNESS')
            need(indices == sorted(set(indices)), 'COVERAGE_SUITE_WITNESS')
        need(bool(expected[condition]) == (role == 'present'), 'COVERAGE_SUITE_ROLE')
    need(identities == {condition + '--' + role for condition in analyzer.CONDITIONS
                        for role in ('present', 'absent')}, 'COVERAGE_SUITE_PAIR_INVENTORY')


def _evaluate(rows: list) -> list[dict]:
    _validate_cases(rows)
    results = []
    for row in rows:
        events = row['events']
        actual = analyzer.coverage(events)
        need(canonical(actual) == canonical(reference.coverage(events)),
             'COVERAGE_SUITE_REFERENCE_DISAGREEMENT')
        need(canonical(actual) == canonical(row['expected_witness_indices']),
             'COVERAGE_SUITE_EXPECTATION_DISAGREEMENT')
        results.append({'case_id': row['case_id'], 'condition': row['condition'],
                        'role': row['role'], 'event_count': len(events),
                        'events_sha256': quality.sha(canonical(events)),
                        'witness_indices': actual, 'all_expectations_matched': True})
    return results


def _sequence_groups(rows: list) -> dict[str, list[str]]:
    groups = {}
    for row in rows:
        groups.setdefault(quality.sha(canonical(row['events'])), []).append(row['case_id'])
    return groups


def _report(rows: list, old: list, expected: str) -> dict:
    results = _evaluate(rows)
    old_groups, new_groups = _sequence_groups(old), _sequence_groups(rows)
    old_coverage = []
    for row in old:
        hits = analyzer.coverage(row['events'])
        need(canonical(hits) == canonical(reference.coverage(row['events'])),
             'COVERAGE_SUITE_REFERENCE_DISAGREEMENT')
        old_coverage.append(hits)
    by_id = {row['case_id']: row for row in results}
    return {
        'schema_version': 1, 'profile': PROFILE, 'corpus_version': corpus.CORPUS_VERSION,
        'status': 'OWNED_INPUT_COUNTER_CONTROLS_VERIFIED', 'source_digest': expected,
        'corpus_sha256': CORPUS_SHA256, 'case_count': len(results),
        'condition_count': len(analyzer.CONDITIONS), 'pair_count': len(analyzer.CONDITIONS),
        'all_expectations_matched': True, 'cases': results,
        'pairs': [{'condition': condition,
                   'present_case_id': condition + '--present',
                   'absent_case_id': condition + '--absent',
                   'present_witness_indices': by_id[condition + '--present']['witness_indices'][condition],
                   'absent_witness_indices': by_id[condition + '--absent']['witness_indices'][condition]}
                  for condition in analyzer.CONDITIONS],
        'unique_event_sequences': len(new_groups),
        'duplicate_event_sequences': [{'events_sha256': digest, 'case_ids': ids}
            for digest, ids in sorted(new_groups.items()) if len(ids) > 1],
        'historical': {
            'cases_sha256': HISTORICAL_CASES_SHA256, 'case_count': len(old),
            'unique_event_sequences': len(old_groups),
            'uncovered_in_all_cases': [condition for condition in analyzer.CONDITIONS
                if not any(hits[condition] for hits in old_coverage)],
            'cases_and_labels_modified': False, 'detection_metrics_recomputed': False},
        'shared_event_sequences': [{'events_sha256': digest,
            'historical_case_ids': old_groups[digest], 'additional_case_ids': new_groups[digest]}
            for digest in sorted(set(old_groups) & set(new_groups))],
        'input_only': True, 'expected_witnesses_authored': True,
        'synthetic_known_sequences': True, 'blind_benchmark': False,
        'case_units_pooled': False, 'generalization_established': False,
        'model_or_native_execution_performed': False, 'detector_evaluated': False,
        'vulnerability_confirmed': False, 'producer_authenticated': False,
        'platform_complete': False, 'global_progress': None}


def _render(report: dict) -> bytes:
    lines = ['# Contra-controles de cobertura de entradas propias', '',
             '16 casos nuevos declarados; ocho pares, 13 secuencias distintas.',
             'Cada par exige presencia y ausencia de una condición de entrada.',
             'Las expectativas explícitas coinciden con ambos algoritmos.', '',
             '| Condición | Caso que la ejerce: índices | Contra-control: índices |',
             '| --- | --- | --- |']
    for pair in report['pairs']:
        lines.append('| ' + pair['condition'] + ' | ' +
                     str(pair['present_witness_indices']) + ' | ' +
                     str(pair['absent_witness_indices']) + ' |')
    lines += ['', 'El corpus histórico sigue separado: once casos, nueve secuencias.',
              'Su hueco use_without_control no se borra ni cambia su omisión conocida.',
              'Los casos repetidos y compartidos se enumeran en evaluation.json.',
              'Los ocho pares no representan cobertura universal ni detección de defectos.',
              'No se ejecutan modelos, contratos, motores nativos o destinos externos.']
    return ('\n'.join(lines) + '\n').encode()


def _execute(expected: str) -> dict[str, bytes]:
    before = quality.source_snapshot()
    need(quality.sha(canonical(before)) == expected, 'COVERAGE_SUITE_SOURCE')
    rows, old = corpus.cases(), historical.cases()
    need(quality.sha(canonical(rows)) == CORPUS_SHA256, 'COVERAGE_SUITE_CORPUS_IDENTITY')
    need(quality.sha(canonical(old)) == HISTORICAL_CASES_SHA256,
         'COVERAGE_SUITE_HISTORICAL_IDENTITY')
    report = _report(rows, old, expected)
    inputs = {'schema_version': 1, 'profile': PROFILE, 'corpus_version': corpus.CORPUS_VERSION,
              'corpus_sha256': CORPUS_SHA256, 'cases': rows}
    need(before == quality.source_snapshot(), 'COVERAGE_SUITE_SOURCE_CHANGED')
    return {'inputs.json': canonical(inputs), 'evaluation.json': canonical(report),
            'REVIEW.md': _render(report)}


def create(out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'COVERAGE_SUITE_PRIVATE_OUTPUT')
    payload = _execute(quality.sha(canonical(quality.source_snapshot())))
    write_new_bundle(out, payload)
    return strict_json(payload['evaluation.json'])


def _inventory(root: Path) -> set[str]:
    need(root.is_dir() and not root.is_symlink(), 'COVERAGE_SUITE_DIRECTORY')
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index <= len(FILES), 'COVERAGE_SUITE_INVENTORY')
        names.add(entry.name)
    need(names == FILES | {'COMPLETE.json'}, 'COVERAGE_SUITE_INVENTORY')
    return names


def verify(root: Path, expected: str) -> dict:
    names = _inventory(root)
    marker_raw = read_artifact(root, 'COMPLETE.json')
    files = {name: read_artifact(root, name) for name in FILES}
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(raw) for name, raw in files.items()}}
    need(canonical(strict_json(marker_raw)) == canonical(marker), 'COVERAGE_SUITE_HASH')
    regenerated = _execute(expected)
    need(files == regenerated, 'COVERAGE_SUITE_REPLAY_MISMATCH')
    need(all(read_artifact(root, name) == raw for name, raw in files.items()) and
         read_artifact(root, 'COMPLETE.json') == marker_raw and _inventory(root) == names,
         'COVERAGE_SUITE_CHANGED_DURING_REPLAY')
    need(quality.sha(canonical(quality.source_snapshot())) == expected, 'COVERAGE_SUITE_SOURCE')
    return strict_json(regenerated['evaluation.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Evaluate fixed OWNED input counter-controls')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('review-owned-coverage-suite')
    make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-coverage-suite')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'review-owned-coverage-suite' else verify(
            args.bundle, args.expected_source)
        print(json.dumps({key: result[key] for key in (
            'status', 'source_digest', 'corpus_sha256', 'case_count', 'pair_count',
            'all_expectations_matched', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'OWNED_INPUT_COUNTER_CONTROLS_BLOCKED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
