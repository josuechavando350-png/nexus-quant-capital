"""Temporal defensive observation review over a closed OWNED synthetic corpus.

The detector sees only events and observations, never variants or truth labels.
Absence of an observed violation never certifies absence of a latent defect.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from . import benchmark, quality, owned_authority_model as model
from . import owned_authority_cases as corpus, owned_authority_reference as reference
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = model.PROFILE
POLICIES = ('full', 'decision_only', 'issued_snapshot')
FILES = {'corpus.json', 'traces.json', 'evaluation.json', 'REVIEW.md'}
need, sha = model.need, quality.sha


def _validate_trace(trace: dict) -> None:
    need(type(trace) is dict and set(trace) ==
         {'schema_version', 'profile', 'events', 'observations'}, 'AUTHORITY_TRACE_SCHEMA')
    need(type(trace['schema_version']) is int and trace['schema_version'] == 1 and
         trace['profile'] == PROFILE, 'AUTHORITY_TRACE_PROFILE')
    model.validate_events(trace['events'])
    rows = trace['observations']
    need(type(rows) is list and len(rows) == len(trace['events']), 'AUTHORITY_TRACE_COVERAGE')
    previous = {key: 0 for key in model.EFFECT_KEYS}
    for index, row in enumerate(rows):
        need(type(row) is dict and set(row) ==
             {'index', 'accepted', 'effects_before', 'effects_after'}, 'AUTHORITY_OBSERVATION_SCHEMA')
        need(type(row['index']) is int and row['index'] == index and type(row['accepted']) is bool,
             'AUTHORITY_OBSERVATION_ORDER_OR_STATUS')
        for name in ('effects_before', 'effects_after'):
            counters = row[name]
            need(type(counters) is dict and set(counters) == set(model.EFFECT_KEYS) and
                 all(type(v) is int and 0 <= v <= 2 * model.MAX_EVENTS for v in counters.values()),
                 'AUTHORITY_EFFECT_BOUNDS')
        need(row['effects_before'] == previous, 'AUTHORITY_DISCONTINUOUS_OBSERVATIONS')
        previous = row['effects_after']


def detect(trace: dict, policy: str = 'full') -> dict:
    need(type(policy) is str and policy in POLICIES, 'AUTHORITY_DETECTOR_POLICY')
    _validate_trace(trace)
    trace = deepcopy(trace)
    events = trace['events']
    oracle = reference.expected_decisions(events) if policy == 'full' else None
    if policy == 'full':
        need(type(oracle) is list and len(oracle) == len(events) and
             all(type(value) is bool for value in oracle), 'AUTHORITY_REFERENCE_SCHEMA')
    active, issued, revoked = set(), set(), set()
    generations, violations = {}, []
    coverage = {'grant_commands': 0, 'revoke_commands': 0, 'use_requests': 0,
                'uses_after_a_revocation': 0, 'principal_mismatch_requests': 0,
                'scope_mismatch_requests': 0}
    for index, (event, row) in enumerate(zip(events, trace['observations'])):
        key = (event['principal'], event['tenant'], event['action'])
        expected = True
        if event['op'] in ('grant', 'revoke'):
            generations[key] = generations.get(key, 0) + 1
            if event['op'] == 'grant':
                coverage['grant_commands'] += 1
                active.add(key)
                issued.add((*key, generations[key]))
            else:
                coverage['revoke_commands'] += 1
                active.discard(key)
                revoked.add(key)
        else:
            coverage['use_requests'] += 1
            coverage['uses_after_a_revocation'] += int(key in revoked)
            credential = event['credential']
            principal_bound = credential['principal'] == event['principal']
            scope_bound = (credential['tenant'], credential['action']) == (event['tenant'], event['action'])
            coverage['principal_mismatch_requests'] += int(not principal_bound)
            coverage['scope_mismatch_requests'] += int(not scope_bound)
            bound = principal_bound and scope_bound
            expected = (bound and ((*key, credential['generation']) in issued
                if policy == 'issued_snapshot' else
                key in active and credential['generation'] == generations.get(key, 0)))
        if oracle is not None:
            need(type(oracle[index]) is bool and expected == oracle[index], 'AUTHORITY_REFERENCE_DISAGREEMENT')
        reasons = []
        if row['accepted'] != expected:
            reasons.append('CONTROL_COMMAND_REJECTED' if event['op'] != 'use' else
                           'UNAUTHORIZED_USE_ACCEPTED' if row['accepted'] else 'VALID_USE_REJECTED')
        wanted_effects = dict(row['effects_before'])
        if event['op'] == 'use' and row['accepted']:
            wanted_effects[event['tenant'] + '.' + event['action']] += 1
        if policy != 'decision_only' and row['effects_after'] != wanted_effects:
            reasons.append('EFFECT_DELTA_MISMATCH')
        if reasons:
            violations.append({'index': index, 'reasons': reasons,
                               'expected_accepted': expected, 'observed_accepted': row['accepted'],
                               'observation_sha256': sha(canonical(row))})
    return {'decision': 'positive' if violations else 'negative', 'policy': policy,
            'events_checked': len(events), 'trace_sha256': sha(canonical(trace)),
            'violations': violations, 'coverage': coverage,
            'history_reference_checked': policy == 'full', 'absence_of_defect_proved': False}


def _source(expected: str) -> dict:
    need(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected) is not None,
         'AUTHORITY_EXPECTED_SOURCE_REQUIRED')
    before = quality.source_snapshot()
    need(sha(canonical(before)) == expected, 'AUTHORITY_SOURCE_MISMATCH')
    return before


def _corpus() -> dict:
    return {'schema_version': 1, 'profile': PROFILE,
            'unit': 'one-own-model-and-sequence-case; observations and ablations are correlated',
            'labels_known_to_developers': True,
            'cases': [{'case_id': c['case_id'], 'variant': c['variant'], 'truth': c['truth'],
                       'seeded_defect_exercised': c['seeded_defect_exercised'],
                       'configuration_sha256': sha(canonical({'variant': c['variant'], 'events': c['events']}))}
                      for c in corpus.cases()]}


def evaluate(execution: dict, expected: str) -> dict:
    _source(expected)
    need(type(execution) is dict and set(execution) ==
         {'schema_version', 'profile', 'source_digest', 'cases'} and
         type(execution['schema_version']) is int and execution['schema_version'] == 1 and
         execution['profile'] == PROFILE and execution['source_digest'] == expected,
         'AUTHORITY_EXECUTION_IDENTITY')
    fixed = corpus.cases()
    rows = execution['cases']
    need(type(rows) is list and len(rows) == len(fixed), 'AUTHORITY_CASE_INVENTORY')
    decisions = {policy: [] for policy in POLICIES}
    trace_groups = {}
    for row, case in zip(rows, fixed):
        need(type(row) is dict and set(row) == {'case_id', 'trace'} and
             row['case_id'] == case['case_id'], 'AUTHORITY_CASE_ORDER')
        _validate_trace(row['trace'])
        need(canonical(row['trace']['events']) == canonical(case['events']), 'AUTHORITY_FIXED_SEQUENCE')
        # Classification happens before labels are paired with decisions.
        for policy in POLICIES:
            decisions[policy].append({'case_id': row['case_id'], **detect(row['trace'], policy)})
        trace_groups.setdefault(sha(canonical(row['trace'])), []).append(row['case_id'])
    labels = [{'case_id': case['case_id'], 'truth': case['truth']} for case in fixed]
    metrics = {policy: benchmark._section(list(zip(labels, decisions[policy]))) for policy in POLICIES}
    missed = [case['case_id'] for case, result in zip(labels, decisions['full'])
              if case['truth'] == 'positive' and result['decision'] != 'positive']
    equal_groups = [{'trace_sha256': digest, 'case_ids': names}
                    for digest, names in sorted(trace_groups.items()) if len(names) > 1]
    return {'schema_version': 1, 'profile': PROFILE, 'status': 'OWNED_TEMPORAL_AUTHORITY_EVALUATED',
            'source_digest': expected, 'case_count': len(fixed),
            'observation_count': sum(len(case['events']) for case in fixed),
            'known_correct_controls': sum(c['truth'] == 'negative' for c in fixed),
            'known_defective_cases': sum(c['truth'] == 'positive' for c in fixed),
            'unique_seeded_mutations': len({c['variant'] for c in fixed if c['truth'] == 'positive'}),
            'activated_defect_cases': sum(c['seeded_defect_exercised'] for c in fixed),
            'latent_defect_cases': sum(c['truth'] == 'positive' and not c['seeded_defect_exercised'] for c in fixed),
            'predictions': decisions, 'metrics': metrics, 'missed_case_ids': missed,
            'all_seeded_cases_detected': not missed, 'observationally_equal_case_groups': equal_groups,
            'labels_known_to_developers': True, 'detector_receives_variant_or_truth': False,
            'history_reference_uses_producer_state': False, 'shared_policy_specification': True,
            'producer_authenticated': False, 'native_evm_executed': False,
            'cryptographic_credential_authentication_implemented': False,
            'blind_benchmark': False, 'generalization_established': False,
            'absence_of_defect_proved': False, 'platform_complete': False,
            'vulnerability_confirmed': False, 'external_targets_executed': 0}


def render(result: dict) -> bytes:
    lines = ['# Permisos temporales: controles propios', '',
             f"Código: `{result['source_digest']}`.", '',
             'Once casos conocidos de modelo y secuencia, cuatro controles correctos y siete casos',
             'con defectos sembrados; seis mutaciones distintas. Una no se activa en su secuencia.',
             'Las 42 observaciones y las tres políticas no son muestras independientes.', '',
             '| Detector | TP | TN | FP | FN |', '|---|---:|---:|---:|---:|']
    for policy in POLICIES:
        c = result['metrics'][policy]['counts']
        lines.append(f"| {policy} | {c['tp']} | {c['tn']} | {c['fp']} | {c['fn']} |")
    lines += ['', 'Omisiones del detector completo: ' + ', '.join(result['missed_case_ids']) + '.', '',
              'El control limpio clean_repeat y el modelo defectuoso latent_revocation producen',
              'exactamente la misma traza: sin ejercer revocación, este observador no los distingue.',
              'La omisión permanece en el denominador; no se convierte en aprobado ni se elimina.',
              'La referencia consulta el historial por separado; comparte especificación e inputs.',
              'La verificación vuelve a ejecutar los modelos propios y recalcula toda la evaluación.', '',
              'Solo registros abstractos propios: no credenciales reales, autenticación criptográfica,',
              'contratos de terceros, ejecución EVM, firmas ni transacciones. No es benchmark ciego,',
              'prueba de generalización, autenticación del productor ni descubrimiento original.',
              'Ausencia de defectos probada: NO. Plataforma completa: NO. Avance global no determinado.', '']
    return '\n'.join(lines).encode()


def _execute(expected: str) -> dict[str, bytes]:
    before = _source(expected)
    execution = {'schema_version': 1, 'profile': PROFILE, 'source_digest': expected,
                 'cases': [{'case_id': case['case_id'], 'trace': model.simulate(case['variant'], case['events'])}
                           for case in corpus.cases()]}
    result = evaluate(execution, expected)
    need(before == quality.source_snapshot(), 'AUTHORITY_SOURCE_CHANGED_DURING_RUN')
    return {'corpus.json': canonical(_corpus()), 'traces.json': canonical(execution),
            'evaluation.json': canonical(result), 'REVIEW.md': render(result)}


def create(out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'AUTHORITY_NEW_PRIVATE_OUTPUT')
    expected = sha(canonical(quality.source_snapshot()))
    files = _execute(expected)
    write_new_bundle(out, files)
    return strict_json(files['evaluation.json'])


def _inventory(root: Path) -> set[str]:
    need(root.is_dir() and not root.is_symlink(), 'AUTHORITY_BUNDLE_DIRECTORY')
    names = []
    for index, entry in enumerate(root.iterdir()):
        need(index < len(FILES) + 1, 'AUTHORITY_BUNDLE_INVENTORY')
        names.append(entry.name)
    need(set(names) == FILES | {'COMPLETE.json'}, 'AUTHORITY_BUNDLE_INVENTORY')
    return set(names)


def verify(root: Path, expected: str) -> dict:
    _source(expected)
    names = _inventory(root)
    marker_raw = read_artifact(root, 'COMPLETE.json')
    marker = strict_json(marker_raw)
    files = {name: read_artifact(root, name) for name in FILES}
    wanted = {'schema_version': 1, 'sha256': {name: sha(raw) for name, raw in files.items()}}
    need(canonical(marker) == canonical(wanted), 'AUTHORITY_BUNDLE_HASH')
    regenerated = _execute(expected)
    need(files == regenerated, 'AUTHORITY_REPLAY_MISMATCH')
    need(all(read_artifact(root, name) == raw for name, raw in files.items()) and
         read_artifact(root, 'COMPLETE.json') == marker_raw and
         _inventory(root) == names, 'AUTHORITY_EVIDENCE_CHANGED_DURING_REPLAY')
    _source(expected)
    return strict_json(regenerated['evaluation.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Evaluate fixed OWNED temporal authority observations')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('evaluate-owned-authority')
    make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-authority')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'evaluate-owned-authority' else verify(args.bundle, args.expected_source)
        print(json.dumps({'status': result['status'], 'source_digest': result['source_digest'],
                          'cases': result['case_count'], 'counts': result['metrics']['full']['counts'],
                          'all_seeded_cases_detected': result['all_seeded_cases_detected'],
                          'vulnerability_confirmed': False}, sort_keys=True))
        return 0  # Evaluation completed; FN/FP remain explicit, never an all-cases-PASS claim.
    except (ValueError, OSError, KeyError, TypeError, RecursionError, OverflowError):
        print(json.dumps({'status': 'OWNED_TEMPORAL_AUTHORITY_BLOCKED', 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
