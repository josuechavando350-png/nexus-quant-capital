"""Bind an existing own operational diagnosis to restricted-compute evidence.

Read-only consumers of two fixed local profiles. No worker launch, target
selection, repair, network, new vulnerability finding or host authentication.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from . import owned_boundary_diagnosis as diagnosis, owned_restricted_review as restricted
from . import owned_capture as capture, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'owned-restricted-diagnosis-corroboration-v1'
FILES = {'inputs.json', 'comparison.json', 'REVIEW.md'}
LIMITS = {'new_findings_created': 0, 'new_executions_performed': 0,
          'input_acquisition_inside_filter': False, 'general_hostile_code_sandbox_proved': False,
          'independent_execution_authenticated': False, 'independent_host_proved': False,
          'current_target_state_checked': False, 'repairs_executed': 0,
          'human_approval_recorded': False, 'security_vulnerability_confirmed': False}


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _paths(*paths: Path) -> None:
    resolved = [p.resolve() for p in paths]
    for index, path in enumerate(resolved):
        for other in resolved[index+1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path), 'CORROBORATION_PATH_OVERLAP')


def _context(source_digest: str, diagnosis_anchor: str, restricted_anchor: str) -> dict:
    for value in (source_digest, diagnosis_anchor, restricted_anchor):
        capture._digest(value)
    need(diagnosis_anchor != restricted_anchor, 'CORROBORATION_DISTINCT_ANCHORS')
    return {'schema_version': 1, 'profile': PROFILE, 'source_digest': source_digest,
            'diagnosis_anchor': diagnosis_anchor, 'restricted_anchor': restricted_anchor}


def _input(module, path: Path, source_digest: str, anchor: str):
    verified = module.verify(path, source_digest=source_digest, experiment_anchor=anchor)
    raw = diagnosis._read(path)
    need(quality.sha(raw['COMPLETE.json']) == anchor, 'CORROBORATION_INPUT_CHANGED')
    return verified, strict_json(raw['observation.json']), raw


def compare(diagnosis_bundle: Path, restricted_bundle: Path, *, source_digest: str,
            diagnosis_anchor: str, restricted_anchor: str) -> dict:
    context = _context(source_digest, diagnosis_anchor, restricted_anchor)
    _paths(diagnosis_bundle, restricted_bundle)
    before = quality.source_snapshot()
    need(quality.sha(canonical(before)) == source_digest, 'CORROBORATION_SOURCE')
    ordinary, ordinary_observation, ordinary_raw = _input(diagnosis, diagnosis_bundle, source_digest, diagnosis_anchor)
    native, native_observation, native_raw = _input(restricted, restricted_bundle, source_digest, restricted_anchor)
    need(ordinary['experiment_id'] != native['experiment_id'], 'CORROBORATION_DUPLICATE_EXPERIMENT_ID')
    need(ordinary_observation['source_inventory_sha256'] == native_observation['source_inventory_sha256'],
         'CORROBORATION_SOURCE_INVENTORY')
    need(ordinary_observation['worker_sha256'] != native_observation['worker_sha256'], 'CORROBORATION_DISTINCT_WORKERS')
    pairs = []
    for index, (left, right) in enumerate(zip(ordinary_observation['trials'], native_observation['trials'])):
        comparable = (ordinary['checks'][index]['expected_observation_matched'] and
                      native['checks'][index]['expected_restricted_observation_matched'])
        equal = False
        proof_hash = None
        raw_equal = False
        rule = left_status = right_status = None
        if comparable:
            value = strict_json(native_raw[f'trial-{index}.stdout'])
            left_result = strict_json(ordinary_raw[f'trial-{index}.stdout'])
            right_result = value['boundary_result']
            raw_equal = ordinary_raw[f'trial-{index}.stdout'] == canonical(right_result)
            left_status, right_status = left_result['status'], right_result['status']
            if left['intervention'] == 'original':
                equivalent = raw_equal
                rule = 'EXACT_BASELINE_BYTES'
            else:
                equivalent = (ordinary_raw[f'trial-{index}.stdout'] == canonical(diagnosis.REJECTION) and
                              canonical(right_result) == canonical({
                                  'status': 'REPOSITORY_BOUNDARY_BLOCKED', 'reason': 'HISTORICAL_TREE_CHANGED'}))
                rule = 'FIXED_REJECTION_REASON_WITH_PROFILE_LABELS'
            equal = (equivalent and
                     left['returncode'] == right['returncode'] and
                     left['inventory_before_sha256'] == right['inventory_before_sha256'] and
                     left['inventory_after_sha256'] == right['inventory_after_sha256'] and
                     canonical(left['delta']) == canonical(right['delta']))
            proof_hash = quality.sha(canonical(value['filter_proof']))
        pairs.append({'trial_index': index, 'label': left['label'],
                      'both_expected_observations_matched': comparable,
                      'equivalent_review_outcome_and_inventory': equal,
                      'raw_boundary_results_equal': raw_equal, 'comparison_rule': rule,
                      'diagnosis_result_status': left_status, 'restricted_result_status': right_status,
                      'diagnosis_stdout_sha256': left['stdout_sha256'],
                      'restricted_stdout_sha256': right['stdout_sha256'],
                      'filter_proof_sha256': proof_hash})
    complete = (ordinary['status'] == 'OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB' and
                native['status'] == 'OWNED_RESTRICTED_LAB_PASS' and len(pairs) == 5 and
                all(pair['equivalent_review_outcome_and_inventory'] for pair in pairs))
    corroborated = []
    if complete:
        need(len(ordinary['operational_findings']) == len(ordinary['remediation_plan']) == 2,
             'CORROBORATION_FINDING_COUNT')
        for finding, plan in zip(ordinary['operational_findings'], ordinary['remediation_plan']):
            need(finding['id'] == plan['finding_id'] and plan['execution_enabled'] is False and
                 plan['human_review_required'] is True, 'CORROBORATION_PLAN')
            indices = [row['index'] for row in finding['evidence']]
            corroborated.append({'existing_finding_id': finding['id'],
                                 'existing_finding_sha256': quality.sha(canonical(finding)),
                                 'existing_plan_sha256': quality.sha(canonical(plan)),
                                 'paired_trial_indices': indices,
                                 'paired_evidence_sha256': quality.sha(canonical([pairs[i] for i in indices])),
                                 'scope': 'SAME_FIXED_OWNED_INVENTORY_AND_INTEGRITY_CONTROL',
                                 'new_finding_created': False, 'execution_enabled': False})
    intervals = []
    for label, observed in (('diagnosis', ordinary_observation), ('restricted', native_observation)):
        intervals.append({'profile': label, 'experiment_id': observed['experiment_id'],
                          'worker_sha256': observed['worker_sha256'],
                          'reported_monotonic_start_ns': observed['trials'][0]['clock']['monotonic_start_ns'],
                          'reported_monotonic_end_ns': observed['trials'][-1]['clock']['monotonic_end_ns']})
    left, right = intervals
    relation = ('DIAGNOSIS_BEFORE_RESTRICTED' if left['reported_monotonic_end_ns'] <= right['reported_monotonic_start_ns']
                else 'RESTRICTED_BEFORE_DIAGNOSIS' if right['reported_monotonic_end_ns'] <= left['reported_monotonic_start_ns']
                else 'REPORTED_INTERVALS_OVERLAP')
    result = {'schema_version': 1, 'profile': PROFILE,
              'status': 'OWNED_CORROBORATION_MATCH' if complete else 'OWNED_CORROBORATION_INCONCLUSIVE',
              'input_context': context, 'source_inventory_sha256': ordinary_observation['source_inventory_sha256'],
              'diagnosis_status': ordinary['status'], 'restricted_status': native['status'],
              'paired_trials_observed': len(pairs), 'pairs': pairs,
              'existing_findings_corroborated': corroborated,
              'reported_intervals': intervals, 'reported_interval_relationship': relation,
              'clock_domain_authenticated': False, 'causal_independence_proved': False,
              'limitations': dict(LIMITS)}
    need(diagnosis._read(diagnosis_bundle) == ordinary_raw and diagnosis._read(restricted_bundle) == native_raw and
         quality.source_snapshot() == before, 'CORROBORATION_INPUT_CHANGED')
    return result


def render(result: dict) -> bytes:
    count = len(result['existing_findings_corroborated'])
    return (f"# Contraste de diagnóstico propio y cómputo restringido\n\nEstado: {result['status']}.\n"
            f"Pares observados: {result['paired_trials_observed']}/5. Findings existentes corroborados: {count}.\n\n"
            'Se vuelven a verificar ambos expedientes y se comparan sus inventarios, resultados, '
            'retornos y deltas. Las referencias a finding y plan pertenecen al diagnóstico original. '
            'El baseline exige igualdad de bytes. Los dos controles de fallo admiten únicamente '
            'el motivo HISTORICAL_TREE_CHANGED con la etiqueta cerrada de cada perfil, que se '
            'conserva por separado. No se exige ni se afirma igualdad de esas etiquetas. '
            'Este contraste no crea otros findings ni ejecuta el plan. Solo cinco pares completos '
            'pueden corroborar los dos controles de integridad declarados.\n\n'
            'Los perfiles corresponden a workers distintos. Sus IDs y anclas diferentes no autentican '
            'dos ejecuciones independientes ni otro host. Los intervalos son declarados por el mismo '
            'tipo de reloj, sin autenticación de dominio temporal. La adquisición de archivos ocurre '
            'antes del filtro del worker restringido. No se acredita sandbox general, vulnerabilidad, '
            'estado actual del destino ni aprobación humana. No se inicia ningún proceso.\n').encode()


def _read(root: Path) -> dict[str, bytes]:
    capture._path(root, new=False)
    names = set()
    for index, path in enumerate(root.iterdir()):
        need(index < len(FILES)+1, 'CORROBORATION_INVENTORY')
        names.add(path.name)
    need(names == FILES | {'COMPLETE.json'}, 'CORROBORATION_INVENTORY')
    raw = {name: read_artifact(root, name) for name in FILES | {'COMPLETE.json'}}
    need(all(len(value) <= capture.OUTPUT_BYTES for value in raw.values()), 'CORROBORATION_BYTES')
    need(raw['COMPLETE.json'] == canonical({'schema_version': 1, 'sha256': {
        name: quality.sha(raw[name]) for name in FILES}}), 'CORROBORATION_MANIFEST')
    return raw


def create(out: Path, diagnosis_bundle: Path, restricted_bundle: Path, *, source_digest: str,
           diagnosis_anchor: str, restricted_anchor: str) -> dict:
    capture._path(out, new=True)
    _paths(out, diagnosis_bundle, restricted_bundle)
    result = compare(diagnosis_bundle, restricted_bundle, source_digest=source_digest,
                     diagnosis_anchor=diagnosis_anchor, restricted_anchor=restricted_anchor)
    write_new_bundle(out, {'inputs.json': canonical(result['input_context']),
                           'comparison.json': canonical(result), 'REVIEW.md': render(result)})
    return {**result, 'corroboration_anchor': quality.sha(read_artifact(out, 'COMPLETE.json'))}


def verify(bundle: Path, diagnosis_bundle: Path, restricted_bundle: Path, *, source_digest: str,
           diagnosis_anchor: str, restricted_anchor: str, corroboration_anchor: str) -> dict:
    capture._digest(corroboration_anchor)
    _paths(bundle, diagnosis_bundle, restricted_bundle)
    raw = _read(bundle)
    need(quality.sha(raw['COMPLETE.json']) == corroboration_anchor, 'CORROBORATION_ANCHOR')
    context = _context(source_digest, diagnosis_anchor, restricted_anchor)
    need(raw['inputs.json'] == canonical(context), 'CORROBORATION_CONTEXT')
    result = compare(diagnosis_bundle, restricted_bundle, **{k:context[k] for k in (
        'source_digest', 'diagnosis_anchor', 'restricted_anchor')})
    need(raw['comparison.json'] == canonical(result) and raw['REVIEW.md'] == render(result), 'CORROBORATION_REPORT')
    need(_read(bundle) == raw, 'CORROBORATION_CHANGED')
    return {**result, 'corroboration_anchor': corroboration_anchor}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Corroborate two existing fixed own evidence profiles')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('corroborate-owned-restricted-diagnosis')
    check = sub.add_parser('verify-owned-restricted-corroboration')
    for command in (make, check):
        command.add_argument('--diagnosis-bundle', type=Path, required=True)
        command.add_argument('--restricted-bundle', type=Path, required=True)
        command.add_argument('--source-digest', required=True)
        command.add_argument('--diagnosis-anchor', required=True)
        command.add_argument('--restricted-anchor', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--corroboration-anchor', required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    try:
        result = create(**args) if command == 'corroborate-owned-restricted-diagnosis' else verify(**args)
        print(json.dumps({'status': result['status'], 'source_digest': result['input_context']['source_digest'],
                          'paired_trials_observed': result['paired_trials_observed'],
                          'existing_findings_corroborated': len(result['existing_findings_corroborated']),
                          'new_findings_created': 0, 'corroboration_anchor': result['corroboration_anchor']}, sort_keys=True))
        return 0 if result['status'] == 'OWNED_CORROBORATION_MATCH' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'status': 'OWNED_CORROBORATION_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
