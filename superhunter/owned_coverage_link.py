"""Link only the fixed historical and additional OWNED coverage profiles.

Both input reports are regenerated. External anchors select exact bundles;
they do not authenticate a producer or turn input coverage into detection.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from . import owned_authority_coverage as historical
from . import owned_authority_coverage_suite as additional
from . import quality
from .owned_authority_model import need
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'owned-temporal-coverage-linked-evidence-v1'
FILES = {'link.json', 'REVIEW.md'}
HEX64 = re.compile(r'[a-f0-9]{64}\Z')


def _anchors(source: str, first: str, second: str) -> None:
    need(all(type(value) is str and HEX64.fullmatch(value) for value in (source, first, second)),
         'COVERAGE_LINK_EXTERNAL_ANCHORS_REQUIRED')
    need(first != second, 'COVERAGE_LINK_DISTINCT_ANCHORS_REQUIRED')


def _distinct(first: Path, second: Path) -> None:
    need(not first.is_symlink() and first.is_dir() and
         not second.is_symlink() and second.is_dir(), 'COVERAGE_LINK_INPUT_DIRECTORIES')
    a, b = first.resolve(), second.resolve()
    need(a != b and not a.is_relative_to(b) and not b.is_relative_to(a),
         'COVERAGE_LINK_DISTINCT_INPUTS_REQUIRED')


def _capture(root: Path, required: set[str]) -> dict[str, bytes]:
    need(root.is_dir() and not root.is_symlink(), 'COVERAGE_LINK_DIRECTORY')
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index < len(required), 'COVERAGE_LINK_INVENTORY')
        names.add(entry.name)
    need(names == required, 'COVERAGE_LINK_INVENTORY')
    return {name: read_artifact(root, name) for name in sorted(required)}


def _same_bytes(root: Path, previous: dict[str, bytes]) -> bool:
    return _capture(root, set(previous)) == previous


def collect(first: Path, second: Path, source: str, first_anchor: str, second_anchor: str) -> dict:
    _anchors(source, first_anchor, second_anchor)
    _distinct(first, second)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source, 'COVERAGE_LINK_SOURCE')
    captured = {'historical': _capture(first, historical.FILES | {'COMPLETE.json'}),
                'additional': _capture(second, additional.FILES | {'COMPLETE.json'})}
    need(quality.sha(captured['historical']['COMPLETE.json']) == first_anchor and
         quality.sha(captured['additional']['COMPLETE.json']) == second_anchor,
         'COVERAGE_LINK_ANCHOR_MISMATCH')
    old = historical.verify(first, source)
    new = additional.verify(second, source)
    need(old['profile'] == historical.PROFILE and new['profile'] == additional.PROFILE and
         old['source_digest'] == new['source_digest'] == source,
         'COVERAGE_LINK_PROFILE_IDENTITY')
    need(new['historical']['case_count'] == old['case_count'] and
         new['historical']['unique_event_sequences'] == old['unique_event_sequences'] and
         new['historical']['uncovered_in_all_cases'] == old['uncovered_in_all_cases'],
         'COVERAGE_LINK_HISTORICAL_BINDING')
    conditions = old['conditions']
    witnesses = {condition: [{'case_id': row['case_id'],
                             'witness_indices': row['witness_indices'][condition]}
                            for row in new['cases'] if row['witness_indices'][condition]]
                 for condition in conditions}
    result = {
        'schema_version': 1, 'profile': PROFILE, 'status': 'OWNED_COVERAGE_EVIDENCE_LINKED',
        'source_digest': source,
        'anchors': {'historical_complete_sha256': first_anchor, 'additional_complete_sha256': second_anchor},
        'evidence_sha256': {stage: {name: quality.sha(raw) for name, raw in files.items()}
                           for stage, files in captured.items()},
        'historical': {'profile': old['profile'], 'case_count': old['case_count'],
                       'unique_event_sequences': old['unique_event_sequences'],
                       'uncovered_conditions': old['uncovered_in_all_cases'],
                       'duplicate_event_sequences': old['duplicate_event_sequences']},
        'additional': {'profile': new['profile'], 'corpus_sha256': new['corpus_sha256'],
                       'case_count': new['case_count'], 'pair_count': new['pair_count'],
                       'unique_event_sequences': new['unique_event_sequences'],
                       'covered_conditions': [c for c in conditions if witnesses[c]],
                       'uncovered_conditions': [c for c in conditions if not witnesses[c]],
                       'duplicate_event_sequences': new['duplicate_event_sequences']},
        'additional_witnesses_for_historical_gaps': {
            condition: witnesses[condition] for condition in old['uncovered_in_all_cases']},
        'shared_event_sequences': new['shared_event_sequences'],
        'input_reports_regenerated': True, 'external_anchors_rechecked': True,
        'same_source_identity_required': True, 'historical_gap_erased': False,
        'historical_detection_metrics_modified': False, 'case_units_pooled': False,
        'model_or_native_execution_performed': False, 'detector_evaluated': False,
        'producer_authenticated': False, 'independent_producers_proved': False,
        'vulnerability_confirmed': False, 'platform_complete': False, 'global_progress': None}
    need(_same_bytes(first, captured['historical']) and _same_bytes(second, captured['additional']),
         'COVERAGE_LINK_INPUT_CHANGED_DURING_REVIEW')
    need(snapshot == quality.source_snapshot(), 'COVERAGE_LINK_SOURCE_CHANGED')
    return result


def _render(result: dict) -> bytes:
    old, new = result['historical'], result['additional']
    lines = ['# Expedientes de cobertura vinculados', '',
             'Ambos perfiles se regeneraron con el mismo código y sus anclas externas.', '',
             '| Corpus | Casos | Secuencias distintas | Condiciones ausentes |',
             '| --- | ---: | ---: | --- |',
             f"| Histórico | {old['case_count']} | {old['unique_event_sequences']} | {', '.join(old['uncovered_conditions'])} |",
             f"| Adicional | {new['case_count']} | {new['unique_event_sequences']} | {', '.join(new['uncovered_conditions']) or 'Ninguna de las ocho declaradas'} |", '',
             'El corpus adicional tiene testigos para estas condiciones ausentes en el histórico:',
             ', '.join(result['additional_witnesses_for_historical_gaps']), '',
             'El hueco histórico permanece. Los denominadores no se suman.',
             'Las secuencias duplicadas y compartidas se enumeran en link.json.',
             'Las anclas seleccionan bytes; no autentican productores independientes.',
             'No se ejecutaron detectores, modelos o EVM ni se confirmó una vulnerabilidad.']
    return ('\n'.join(lines) + '\n').encode()


def _output_location(out: Path, first: Path, second: Path, new: bool) -> None:
    resolved = out.resolve()
    need(not out.is_symlink() and (not new or not out.exists()) and
         not resolved.is_relative_to(ROOT), 'COVERAGE_LINK_OUTPUT_LOCATION')
    for input_root in (first, second):
        other = input_root.resolve()
        need(not resolved.is_relative_to(other) and not other.is_relative_to(resolved),
             'COVERAGE_LINK_OVERLAPPING_OUTPUT')


def create(first: Path, second: Path, source: str, first_anchor: str,
           second_anchor: str, out: Path) -> dict:
    _output_location(out, first, second, new=True)
    result = collect(first, second, source, first_anchor, second_anchor)
    write_new_bundle(out, {'link.json': canonical(result), 'REVIEW.md': _render(result)})
    return result


def verify(out: Path, first: Path, second: Path, source: str,
           first_anchor: str, second_anchor: str) -> dict:
    _output_location(out, first, second, new=False)
    saved = _capture(out, FILES | {'COMPLETE.json'})
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(saved[name]) for name in FILES}}
    need(canonical(strict_json(saved['COMPLETE.json'])) == canonical(marker), 'COVERAGE_LINK_HASH')
    result = collect(first, second, source, first_anchor, second_anchor)
    need(saved['link.json'] == canonical(result) and saved['REVIEW.md'] == _render(result),
         'COVERAGE_LINK_REPLAY_MISMATCH')
    need(_same_bytes(out, saved), 'COVERAGE_LINK_OUTPUT_CHANGED_DURING_REPLAY')
    need(quality.sha(canonical(quality.source_snapshot())) == source, 'COVERAGE_LINK_SOURCE')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Link two fixed OWNED input coverage profiles')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('link-owned-coverage')
    make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-coverage-link')
    check.add_argument('--bundle', type=Path, required=True)
    for sub in (make, check):
        sub.add_argument('--historical', type=Path, required=True)
        sub.add_argument('--additional', type=Path, required=True)
        sub.add_argument('--expected-source', required=True)
        sub.add_argument('--historical-anchor', required=True)
        sub.add_argument('--additional-anchor', required=True)
    args = parser.parse_args(argv)
    try:
        common = (args.historical, args.additional, args.expected_source,
                  args.historical_anchor, args.additional_anchor)
        result = create(*common, args.out) if args.command == 'link-owned-coverage' else verify(args.bundle, *common)
        print(json.dumps({key: result[key] for key in (
            'status', 'source_digest', 'input_reports_regenerated', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'OWNED_COVERAGE_LINK_BLOCKED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
