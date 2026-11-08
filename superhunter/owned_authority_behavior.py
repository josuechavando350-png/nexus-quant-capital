"""Correct-model behavior for sixteen fixed synthetic input counter-controls.

Only the correct abstract implementation runs. No native engine, injected
variant, detector, arbitrary source, target or network is accepted.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from . import owned_authority_cases as historical
from . import owned_authority_coverage_cases as corpus
from . import owned_authority_coverage_suite as coverage_suite
from . import owned_authority_model as model
from . import owned_authority_reference as reference
from . import quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-correct-model-counter-control-behavior-v1'
FILES = {'inputs.json', 'traces.json', 'evaluation.json', 'REVIEW.md'}
# Independently authored decisions and cumulative north.read effects by event.
# All other effects remain zero. Expectations are not derived from execution.
EXPECTATIONS = {
    'use_without_control--present': ((False,), (0,)),
    'use_without_control--absent': ((True, True), (0, 1)),
    'current_grant_use--present': ((True, True), (0, 1)),
    'current_grant_use--absent': ((True, False), (0, 0)),
    'revoked_grant_use--present': ((True, True, False), (0, 0, 0)),
    'revoked_grant_use--absent': ((True, True, False), (0, 0, 0)),
    'stale_grant_after_regrant_use--present': ((True, True, True, False), (0, 0, 0, 0)),
    'stale_grant_after_regrant_use--absent': ((True, True, True, True), (0, 0, 0, 1)),
    'principal_mismatch_use--present': ((True, False), (0, 0)),
    'principal_mismatch_use--absent': ((True, True), (0, 1)),
    'scope_mismatch_use--present': ((True, False), (0, 0)),
    'scope_mismatch_use--absent': ((True, True), (0, 1)),
    'repeated_current_grant_use--present': ((True, True, True), (0, 1, 2)),
    'repeated_current_grant_use--absent': ((True, True, True, True), (0, 1, 1, 2)),
    'current_grant_after_revocation_use--present': ((True, True, True), (0, 0, 1)),
    'current_grant_after_revocation_use--absent': ((True, True, True), (0, 0, 1)),
}


def expected_trace(case: dict) -> dict:
    decisions, counts = EXPECTATIONS[case['case_id']]
    events = case['events']
    model.need(len(events) == len(decisions) == len(counts) and
               all(type(v) is bool for v in decisions) and
               all(type(v) is int and 0 <= v <= len(events) for v in counts),
               'BEHAVIOR_AUTHORED_EXPECTATION_SCHEMA')
    observations = []
    effects = dict.fromkeys(model.EFFECT_KEYS, 0)
    for index, (decision, count) in enumerate(zip(decisions, counts)):
        following = {**dict.fromkeys(model.EFFECT_KEYS, 0), 'north.read': count}
        observations.append({'index': index, 'accepted': decision,
                             'effects_before': dict(effects), 'effects_after': following})
        effects = following
    return {'schema_version': 1, 'profile': model.PROFILE,
            'events': deepcopy(events), 'observations': observations}


def _evaluate(rows: list) -> tuple[list[dict], list[dict]]:
    model.need(quality.sha(canonical(rows)) == coverage_suite.CORPUS_SHA256,
               'BEHAVIOR_FIXED_CORPUS')
    model.need(set(EXPECTATIONS) == {row['case_id'] for row in rows},
               'BEHAVIOR_EXPECTATION_INVENTORY')
    traces, summaries = [], []
    for case in rows:
        events = deepcopy(case['events'])
        unchanged = canonical(events)
        # Each implementation receives a fresh copy of event records only.
        actual = model.simulate('correct', deepcopy(events))
        decisions = reference.expected_decisions(deepcopy(events))
        authored = expected_trace(case)
        model.need(canonical(decisions) == canonical(list(EXPECTATIONS[case['case_id']][0])),
                   'BEHAVIOR_REFERENCE_DISAGREEMENT')
        model.need(canonical(actual) == canonical(authored), 'BEHAVIOR_MODEL_DISAGREEMENT')
        model.need(canonical(events) == unchanged and canonical(case['events']) == unchanged,
                   'BEHAVIOR_INPUT_CHANGED')
        observations = actual['observations']
        uses = [i for i, event in enumerate(events) if event['op'] == 'use']
        traces.append({'case_id': case['case_id'], 'trace': actual})
        summaries.append({'case_id': case['case_id'], 'event_count': len(events),
            'events_sha256': quality.sha(unchanged),
            'use_events': len(uses),
            'accepted_use_indices': [i for i in uses if observations[i]['accepted']],
            'rejected_use_indices': [i for i in uses if not observations[i]['accepted']],
            'final_effects': observations[-1]['effects_after'],
            'all_decisions_and_effects_matched': True})
    return traces, summaries


def _render(report: dict) -> bytes:
    lines = ['# Comportamiento del modelo correcto en los contra-controles', '',
        'Se ejecuta únicamente el modelo abstracto correcto sobre las 16 entradas fijas.',
        'Decisiones y efectos coinciden con expectativas escritas; una referencia de',
        'historial comprueba las decisiones por separado.', '',
        '| Caso | Usos aceptados: índices | Usos rechazados: índices |',
        '| --- | --- | --- |']
    for row in report['cases']:
        lines.append(f"| {row['case_id']} | {row['accepted_use_indices']} | {row['rejected_use_indices']} |")
    lines += ['', 'Son 16 casos declarados y 13 secuencias distintas; las repeticiones se conservan.',
        'Los controles grant/revoke se aceptan sin producir efectos de uso.',
        'Un uso rechazado tampoco produce efectos. Repetir un uso vigente es permitido',
        'por esta política abstracta: cada uso aceptado incrementa exactamente un contador.',
        'No se ejecuta un detector, contrato, variante defectuosa ni motor nativo.',
        'La omisión histórica latent_revocation no cambia. No se recalculan TP/FP/FN.',
        'Las coincidencias no prueban una política universal, autenticación real o cobertura general.']
    return ('\n'.join(lines) + '\n').encode()


def _execute(expected: str) -> dict[str, bytes]:
    before = quality.source_snapshot()
    model.need(quality.sha(canonical(before)) == expected, 'BEHAVIOR_SOURCE')
    rows = corpus.cases()
    model.need(quality.sha(canonical(historical.cases())) == coverage_suite.HISTORICAL_CASES_SHA256,
               'BEHAVIOR_HISTORICAL_IDENTITY')
    traces, cases = _evaluate(rows)
    report = {'schema_version': 1, 'profile': PROFILE,
        'status': 'OWNED_CORRECT_MODEL_BEHAVIOR_VERIFIED', 'source_digest': expected,
        'corpus_sha256': coverage_suite.CORPUS_SHA256,
        'expectations_sha256': quality.sha(canonical(EXPECTATIONS)),
        'case_count': len(cases), 'unique_event_sequences': len({row['events_sha256'] for row in cases}),
        'event_executions': sum(row['event_count'] for row in cases),
        'use_events': sum(row['use_events'] for row in cases),
        'accepted_uses': sum(len(row['accepted_use_indices']) for row in cases),
        'rejected_uses': sum(len(row['rejected_use_indices']) for row in cases),
        'cases': cases, 'model_variant': 'correct', 'expectations_authored': True,
        'reference_shares_abstract_policy': True, 'case_units_pooled': False,
        'native_execution_performed': False, 'detector_evaluated': False,
        'injected_variants_executed': False, 'historical_detection_metrics_recomputed': False,
        'historical_cases_sha256': coverage_suite.HISTORICAL_CASES_SHA256,
        'historical_cases_and_labels_modified': False, 'vulnerability_confirmed': False,
        'producer_authenticated': False, 'generalization_established': False,
        'platform_complete': False, 'global_progress': None}
    model.need(before == quality.source_snapshot(), 'BEHAVIOR_SOURCE_CHANGED')
    return {'inputs.json': canonical({'profile': PROFILE, 'cases': rows, 'expectations': EXPECTATIONS}),
            'traces.json': canonical({'profile': PROFILE, 'cases': traces}),
            'evaluation.json': canonical(report), 'REVIEW.md': _render(report)}


def create(out: Path) -> dict:
    model.need(not out.exists() and not out.is_symlink() and
               not out.resolve().is_relative_to(ROOT.parent), 'BEHAVIOR_PRIVATE_OUTPUT')
    payload = _execute(quality.sha(canonical(quality.source_snapshot())))
    write_new_bundle(out, payload)
    return strict_json(payload['evaluation.json'])


def _capture(root: Path) -> dict[str, bytes]:
    model.need(root.is_dir() and not root.is_symlink(), 'BEHAVIOR_DIRECTORY')
    names = set()
    for index, entry in enumerate(root.iterdir()):
        model.need(index <= len(FILES), 'BEHAVIOR_FILES')
        names.add(entry.name)
    model.need(names == FILES | {'COMPLETE.json'}, 'BEHAVIOR_FILES')
    return {name: read_artifact(root, name) for name in sorted(names)}


def verify(root: Path, expected: str) -> dict:
    saved = _capture(root)
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(saved[name]) for name in FILES}}
    model.need(canonical(strict_json(saved['COMPLETE.json'])) == canonical(marker), 'BEHAVIOR_HASH')
    fresh = _execute(expected)
    model.need(all(saved[name] == raw for name, raw in fresh.items()), 'BEHAVIOR_REPLAY_MISMATCH')
    model.need(saved == _capture(root), 'BEHAVIOR_REPORT_CHANGED')
    model.need(quality.sha(canonical(quality.source_snapshot())) == expected, 'BEHAVIOR_SOURCE')
    return strict_json(fresh['evaluation.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Check the correct own model on fixed counter-controls')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('review-owned-correct-behavior'); make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-correct-behavior')
    check.add_argument('--bundle', type=Path, required=True); check.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'review-owned-correct-behavior' else verify(args.bundle, args.expected_source)
        print(json.dumps({key: result[key] for key in ('status', 'source_digest', 'case_count',
            'event_executions', 'accepted_uses', 'rejected_uses', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'OWNED_CORRECT_MODEL_BEHAVIOR_BLOCKED'})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
