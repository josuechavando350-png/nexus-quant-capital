"""Accept QA and both closed OWNED native cohorts under one source identity.

Completion means the prescribed evaluation finished. It does not erase known
omissions, pool incompatible sample units or certify the wider platform.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from . import owned_platform as quota, owned_authority_cross_evm as authority
from . import native_platform as inventory, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'whole-qa-quota-and-temporal-authority-v1'
REPORT_FILES = {'acceptance.json', 'REVIEW.md'}
need, sha = quota.need, quota.sha


def _quota_files() -> set[str]:
    return ({'prepared/' + name for name in quota._prepared_files()} |
            {'native/' + name for name in quota.native.FILES | {'COMPLETE.json'}} |
            {'review/' + name for name in quota.REPORT_FILES | {'COMPLETE.json'}})


def _stage_hashes(root: Path, complete: bool) -> dict:
    wanted = {'quota', 'authority', 'review'} if complete else {'quota', 'authority'}
    need(root.is_dir() and not root.is_symlink(), 'DEFENSIVE_ACCEPTANCE_ROOT')
    names = []
    for index, path in enumerate(root.iterdir()):
        need(index < len(wanted), 'DEFENSIVE_ACCEPTANCE_STAGE_INVENTORY'); names.append(path.name)
    need(set(names) == wanted, 'DEFENSIVE_ACCEPTANCE_STAGE_INVENTORY')
    return {'quota': inventory._tree(root / 'quota', _quota_files()),
            'authority': inventory._tree(root / 'authority', authority.FILES | {'COMPLETE.json'})}


def _counts(counts: dict, positives: int, negatives: int) -> dict:
    names = {'tp', 'tn', 'fp', 'fn', 'abstain_positive', 'abstain_negative', 'error_positive', 'error_negative'}
    need(type(counts) is dict and set(counts) == names and
         all(type(v) is int and v >= 0 for v in counts.values()), 'DEFENSIVE_ACCEPTANCE_COUNTS_SCHEMA')
    need(counts['tp'] + counts['fn'] + counts['abstain_positive'] + counts['error_positive'] == positives and
         counts['tn'] + counts['fp'] + counts['abstain_negative'] + counts['error_negative'] == negatives,
         'DEFENSIVE_ACCEPTANCE_COUNTS_DENOMINATOR')
    return counts


def _assemble(root: Path, qa_quota: dict, temporal: dict, expected: str, evidence: dict) -> dict:
    need(type(qa_quota) is dict and qa_quota.get('status') == 'OWNED_PLATFORM_REVIEW_PASS' and
         qa_quota.get('profile') == quota.PROFILE and qa_quota.get('source_digest') == expected and
         qa_quota.get('platform_complete') is False and qa_quota.get('vulnerability_confirmed') is False and
         qa_quota.get('native_reexecuted_by_verifier') is True, 'DEFENSIVE_ACCEPTANCE_QUOTA_REQUIRED')
    need(type(temporal) is dict and temporal.get('status') == 'OWNED_AUTHORITY_CROSS_EVM_MATCH' and
         temporal.get('profile') == authority.cases.PROFILE and temporal.get('source_digest') == expected and
         temporal.get('platform_complete') is False and temporal.get('vulnerability_confirmed') is False and
         temporal.get('distinct_evm_implementations_executed') is True,
         'DEFENSIVE_ACCEPTANCE_AUTHORITY_REQUIRED')
    need(read_artifact(root, 'quota/review/acceptance.json') == canonical(qa_quota) and
         read_artifact(root, 'authority/comparison.json') == canonical(temporal),
         'DEFENSIVE_ACCEPTANCE_REPORT_BINDING')
    comparison = qa_quota['native_comparison']
    need(type(comparison) is dict and comparison.get('status') == 'OWNED_QUOTA_CROSS_EVM_MATCH' and
         comparison.get('source_digest') == expected and type(comparison.get('known_cases')) is int and
         comparison['known_cases'] == 6 and type(temporal.get('known_case_count')) is int and
         temporal['known_case_count'] == 11, 'DEFENSIVE_ACCEPTANCE_COHORT_IDENTITY')
    quota_counts = _counts(comparison['counts'], 4, 2)
    temporal_counts = _counts(temporal['metrics']['full']['counts'], 7, 4)
    need(qa_quota['worker_policy'] == quota.WORKERS and
         type(qa_quota['qa']['tests_run']) is int and qa_quota['qa']['tests_run'] > 0 and
         qa_quota['qa']['tests_reexecuted_by_verifier'] is False,
         'DEFENSIVE_ACCEPTANCE_QA_CONTRACT')
    quota._validate_runtime(qa_quota['qa_runtime'])
    cohorts = {
        'quota': {'case_unit': 'one-known-own-source-variant', 'known_cases': 6,
                  'known_defective_cases': 4, 'known_correct_controls': 2,
                  'counts': quota_counts, 'metrics': comparison['ablation_metrics']},
        'temporal_authority': {'case_unit': 'one-known-own-model-and-sequence-case', 'known_cases': 11,
                  'known_defective_cases': 7, 'known_correct_controls': 4,
                  'counts': temporal_counts, 'metrics': temporal['metrics'],
                  'vm_success_as_authorization_metrics': temporal['vm_success_as_authorization_metrics'],
                  'missed_case_ids': temporal['missed_case_ids'],
                  'observationally_equal_case_groups': temporal['observationally_equal_case_groups']}}
    return {'schema_version': 1, 'status': 'OWNED_DEFENSIVE_ACCEPTANCE_COMPLETE', 'profile': PROFILE,
        'source_digest': expected, 'evidence_sha256': evidence, 'qa': qa_quota['qa'],
        'qa_runtime': qa_quota['qa_runtime'], 'worker_policy': quota.WORKERS,
        'cohorts': cohorts, 'pooled_performance_score': None, 'case_units_pooled': False,
        'all_seeded_cases_detected': quota_counts['tp'] == 4 and temporal_counts['tp'] == 7,
        'all_known_controls_clean': quota_counts['tn'] == 2 and temporal_counts['tn'] == 4,
        'local_controls': qa_quota['local_controls'], 'plans': qa_quota['plans'],
        'native_reexecution_required_for_each_cohort': True,
        'qa_and_eels_environments_separate': True, 'same_source_identity_required': True,
        'separate_process_acceptance_verification_required': True,
        'independent_producers_proved': False, 'producer_authenticated': False,
        'legacy_native_profile_recertified': False, 'aggregate_resource_budget_certified': False,
        'caller_identity_authenticated': False, 'blind_benchmark': False,
        'generalization_established': False, 'platform_complete': False,
        'vulnerability_confirmed': False, 'external_targets_executed': 0, 'network_used': False,
        'global_progress': 'not determined', 'monetary_valuation_usd': None}


def _documents(result: dict) -> dict[str, bytes]:
    lines = ['# Aceptación conjunta de controles propios', '',
        f"Perfil: `{PROFILE}`. Código: `{result['source_digest']}`.", '',
        f"QA: {result['qa']['tests_run']} pruebas. El verificador comprueba recibos, no repite QA.",
        'Sí recompila y repite Geth/EELS para cada grupo de controles nativos.', '',
        '| Grupo conocido | Unidad | Casos | TP | TN | FP | FN |',
        '|---|---|---:|---:|---:|---:|---:|']
    for name, cohort in result['cohorts'].items():
        c = cohort['counts']
        lines.append(f"| {name} | {cohort['case_unit']} | {cohort['known_cases']} | {c['tp']} | {c['tn']} | {c['fp']} | {c['fn']} |")
    lines += ['', 'Se conservan denominadores y métricas separados; no se calcula una precisión global.',
        'Las ejecuciones, compilaciones y observaciones correlacionadas no añaden muestras independientes.',
        'latent_revocation sigue siendo una omisión: su secuencia no ejerce el defecto.',
        'El éxito EVM no equivale a autorización de aplicación; su ablación permanece en el informe.',
        'Completar la aceptación no significa detectar todos los defectos sembrados.',
        'QA y EELS conservan sus entornos exactos separados. Límites por trabajador sin ampliación.',
        'No hay autenticación del productor/caller, benchmark ciego, prueba de generalización o recertificación histórica.',
        'Sin objetivos externos, red, fondos, firmas o transacciones operativas.',
        'Plataforma completa: NO. Avance global no determinado. Vulnerabilidades originales confirmadas: ninguna.', '']
    return {'acceptance.json': canonical(result), 'REVIEW.md': '\n'.join(lines).encode()}


def finish(prepared: Path, out: Path, solc: Path, evm: Path, expected: str) -> dict:
    quota._new_output(out)
    need(not out.resolve().is_relative_to(prepared.resolve()) and
         not prepared.resolve().is_relative_to(out.resolve()), 'DEFENSIVE_ACCEPTANCE_OVERLAPPING_OUTPUT')
    snapshot = quota._source(expected)
    quota.verify_prepared(prepared, expected)
    quota._native_preflight(solc, evm)
    out.parent.mkdir(parents=True, exist_ok=True); out.mkdir(mode=0o700)
    qa_quota = quota.finish(prepared, out / 'quota', solc, evm, expected)
    quota_hashes = inventory._tree(out / 'quota', _quota_files())
    authority.create(out / 'authority', solc, evm, expected)
    temporal = authority.verify(out / 'authority', solc, evm, expected)
    evidence = _stage_hashes(out, complete=False)
    need(evidence['quota'] == quota_hashes, 'DEFENSIVE_ACCEPTANCE_QUOTA_CHANGED_DURING_AUTHORITY')
    result = _assemble(out, qa_quota, temporal, expected, evidence)
    files = _documents(result)
    need(snapshot == quality.source_snapshot() and evidence == _stage_hashes(out, complete=False),
         'DEFENSIVE_ACCEPTANCE_CHANGED_BEFORE_COMPLETION')
    write_new_bundle(out / 'review', files)
    return result


def verify(root: Path, solc: Path, evm: Path, expected: str) -> dict:
    snapshot = quota._source(expected)
    evidence = _stage_hashes(root, complete=True)
    review_hashes = quota._manifest(root / 'review', REPORT_FILES)
    qa_quota = quota.verify(root / 'quota', solc, evm, expected)
    temporal = authority.verify(root / 'authority', solc, evm, expected)
    result = _assemble(root, qa_quota, temporal, expected, evidence)
    for name, raw in _documents(result).items():
        need(read_artifact(root / 'review', name) == raw, 'DEFENSIVE_ACCEPTANCE_REPORT_DIFFERS_FROM_REPLAY')
    need(snapshot == quality.source_snapshot() and evidence == _stage_hashes(root, complete=True) and
         review_hashes == quota._manifest(root / 'review', REPORT_FILES),
         'DEFENSIVE_ACCEPTANCE_SOURCE_OR_EVIDENCE_CHANGED')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Require QA and both fixed own native cohorts')
    subs = parser.add_subparsers(dest='command', required=True)
    final = subs.add_parser('finish-owned-defensive')
    final.add_argument('--prepared', type=Path, required=True); final.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-defensive'); check.add_argument('--bundle', type=Path, required=True)
    for p in (final, check):
        p.add_argument('--solc', type=Path, required=True); p.add_argument('--evm', type=Path, required=True)
        p.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = (finish(args.prepared, args.out, args.solc, args.evm, args.expected_source)
                  if args.command == 'finish-owned-defensive' else
                  verify(args.bundle, args.solc, args.evm, args.expected_source))
        print(json.dumps({k: result[k] for k in ('status', 'source_digest', 'all_seeded_cases_detected',
                                                'platform_complete', 'vulnerability_confirmed')}, sort_keys=True)); return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, RecursionError,
            OverflowError, subprocess.TimeoutExpired):
        print(json.dumps({'status': 'OWNED_DEFENSIVE_ACCEPTANCE_BLOCKED',
                          'platform_complete': False, 'vulnerability_confirmed': False})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
