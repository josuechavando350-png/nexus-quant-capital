"""Equal-budget EVM experiment: observed-PC feedback vs fixed-parent mutation.

Both arms execute the SAME bounded mutation recipes on owned, pinned Solidity
controls. Only the parent selection differs. Outcomes and coverage come from
real Geth traces and two concrete accounting oracles. No external source or
transaction input, live target, exploit, or generalized security claim.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from . import evm_coverage_guidance as guided, evm_sequence_fuzz as fuzz
from . import evm_execution as evm, native_compile as compiler, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-equal-budget-feedback-comparison-v1'
FILES = {'comparison.json', 'audit.json', 'REVIEW.md'}
MAX_CANDIDATES = guided.MAX_CANDIDATES


class ComparisonError(ValueError):
    """Fixed error codes only: avoid leaking input paths in shared logs."""


def require(check: bool, reason: str) -> None:
    if not check:
        raise ComparisonError(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_parameters(seed: object, candidates: object, source: object) -> None:
    guided.validate(seed, candidates)
    require(type(source) is str and re.fullmatch('[0-9a-f]{64}', source) is not None,
            'EXTERNAL_SOURCE_DIGEST_REQUIRED')


def fixed_parent_proposal(iteration: int, seed: int) -> tuple[list[list[int]], dict]:
    """Same mutation recipe, but no trace feedback or parent selection.

    Both arms share an identical baseline and deterministic mutation operators.
    This comparison isolates the parent-choice heuristic on this small corpus;
    it is NOT a random-fuzzer benchmark or a representative efficacy estimate.
    """
    guided.validate(seed, iteration)
    row, recipe = guided.next_mutation(deepcopy(guided.BASELINE), iteration, seed)
    return row, {**recipe, 'origin': 'fixed-initial-parent-without-feedback'}


def summarize_arm(rows: list[dict], *, calls_per_case: int) -> dict:
    require(type(rows) is list and len(rows) >= 2 and type(calls_per_case) is int and
            calls_per_case > 0, 'ARM_SCHEMA')
    all_features: set[str] = set()
    counts = Counter()
    baseline_features = None
    for i, row in enumerate(rows):
        require(type(row) is dict and row.get('case_index') == i and
                type(row.get('observations')) is dict, 'CASE_IDENTITY')
        current = guided.case_features(row['observations'])
        if i == 0:
            baseline_features = set(current)
        all_features.update(current)
        for ctrl in fuzz.CONTROLS:
            for profile in fuzz.PROFILES:
                counts.update(row['observations'][ctrl][profile]['outcomes'])
    require(baseline_features is not None and sum(counts.values()) == len(rows)*calls_per_case,
            'ARM_CALL_BUDGET_MISMATCH')
    return {
        'cases_executed': len(rows), 'runtime_calls': len(rows)*calls_per_case,
        'baseline_features': len(baseline_features), 'observed_features': len(all_features),
        'new_features_after_baseline': len(all_features-baseline_features),
        'outcomes': dict(sorted(counts.items())),
    }


def _fixed_arm(solc_image: bytes, evm_image: bytes, builds: dict, *, seed: int,
               candidates: int) -> list[dict]:
    """Recompile pinned code and actually execute the non-guided controls."""
    prepared = {}
    for name in fuzz.CONTROLS:
        first_input, first = fuzz._compile(name, fuzz.PROFILES[0], solc_image, None)
        _, second = fuzz._compile(name, fuzz.PROFILES[1], solc_image, first_input)
        prepared[name] = {}
        for profile, record in zip(fuzz.PROFILES, (first, second)):
            require(record['creation_sha256'] == builds[name][profile]['creation_sha256'] and
                    record['runtime_sha256'] == builds[name][profile]['runtime_sha256'],
                    'COMPILER_ARMS_DIFFER')
            contract = record['contract']
            birth = evm._run(evm_image, prestate=evm.genesis(),
                             creation=contract['evm']['bytecode']['object'])
            observed = birth['observed']
            require(observed['error'] is None and observed['return_data'] ==
                    '0x'+contract['evm']['deployedBytecode']['object'] and
                    evm.decode_state(observed['alloc'],contract) ==
                    {'debit':15,'credit':0,'steps':0}, 'CONTROL_CONSTRUCTOR_MISMATCH')
            prepared[name][profile] = (contract, observed['alloc'])
    rows = []
    seen: set[bytes] = set()
    for i in range(candidates+1):
        if i == 0:
            sequence = deepcopy(guided.BASELINE)
            mutation = None
        else:
            sequence, mutation = fixed_parent_proposal(i, seed)
        identity = canonical(sequence)
        require(identity not in seen, 'DUPLICATE_FIXED_PARENT_CASE')
        seen.add(identity)
        observations = {}
        for name in fuzz.CONTROLS:
            observations[name] = {}
            for profile in fuzz.PROFILES:
                contract, allocation = prepared[name][profile]
                observations[name][profile] = guided._run_one(
                    name, contract, evm_image, contract['evm']['deployedBytecode']['object'],
                    allocation, sequence)
        rows.append({'case_index': i, 'parent_index': None if i == 0 else 0,
                     'sequence': sequence, 'sequence_sha256': digest(identity),
                     'mutation': mutation, 'observations': observations})
    return rows


def compare_reports(guided_report: dict, fixed_rows: list[dict], *,
                    expected_source: str, seed: int, candidates: int) -> dict:
    """Compute outcomes/novelty strictly from the observed per-call traces."""
    validate_parameters(seed,candidates,expected_source)
    require(type(guided_report) is dict and guided_report.get('profile') == guided.PROFILE and
            guided_report.get('status') == 'OWNED_EVM_GUIDANCE_OBSERVED' and
            guided_report.get('source_digest') == expected_source and
            guided_report.get('seed') == seed and guided_report.get('candidates') == candidates and
            guided_report.get('vulnerability_confirmed') is False,
            'GUIDED_EVIDENCE_PROFILE')
    cases = guided_report.get('cases')
    require(type(cases) is list and len(cases) == len(fixed_rows) == candidates+1,
            'UNEQUAL_CASE_BUDGET')
    calls = fuzz.STEPS*len(fuzz.CONTROLS)*len(fuzz.PROFILES)
    a = summarize_arm(cases, calls_per_case=calls)
    b = summarize_arm(fixed_rows, calls_per_case=calls)
    require(a['runtime_calls'] == b['runtime_calls'] == guided_report['runtime_calls'] and
            a['baseline_features'] == b['baseline_features'] and
            canonical(cases[0]['observations']) == canonical(fixed_rows[0]['observations']) and
            cases[0]['sequence'] == fixed_rows[0]['sequence'] == guided.BASELINE and
            cases[0]['parent_index'] is None and fixed_rows[0]['parent_index'] is None,
            'BASELINE_OR_BUDGET_MISMATCH')
    for i in range(1, len(cases)):
        fixed = fixed_rows[i]
        planned, _ = fixed_parent_proposal(i, seed)
        require(fixed['sequence'] == planned and fixed['parent_index'] == 0 and
                fixed['sequence_sha256'] == digest(canonical(planned)),
                'FIXED_CONTROL_NOT_REPRODUCIBLE')
        require(cases[i]['mutation']['operation_index'] == fixed['mutation']['operation_index'] and
                cases[i]['mutation']['field'] == fixed['mutation']['field'],
                'UNEQUAL_MUTATION_RECIPES')
    require(a['observed_features'] == guided_report['observed_feature_count'] and
            a['new_features_after_baseline'] == guided_report['novel_features_after_baseline'],
            'GUIDED_COVERAGE_MISMATCH')
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'OWNED_EVM_COMPARISON_OBSERVED',
        'source_digest': expected_source, 'seed': seed, 'candidates': candidates,
        'programs_executed': 0, 'controls': list(fuzz.CONTROLS),
        'compiler_profiles': list(fuzz.PROFILES),
        'budget': {'calls_per_arm':a['runtime_calls'], 'total_calls': a['runtime_calls']+b['runtime_calls'],
                   'sequences_per_arm': candidates+1, 'calls_per_sequence': calls},
        'guided': {'summary':a, 'cases':cases},
        'fixed_parent': {'summary':b, 'cases':fixed_rows},
        'guided_minus_fixed_features': a['observed_features']-b['observed_features'],
        'fairness': {'same_baseline': True, 'same_mutation_recipe_per_iteration': True,
                     'same_evm_call_budget': True, 'same_compiler_and_evm': True,
                     'different_parent_selection': True,
                     'baseline_reexecuted_per_arm':True},
        'exhaustive_path_coverage_proven': False,
        'improved_detection_proven': False,
        'statistical_superiority_proven': False,
        'new_vulnerability_confirmed': False,
        'network_used': False, 'external_programs_executed': False,
        'note': 'Single-seed owned-fixture paired comparison; no general efficacy inference.',
    }


def execute(solc_path: Path, evm_path: Path, expected_source: str, *,
            seed: int = 20261105, candidates: int = 2) -> dict:
    validate_parameters(seed,candidates,expected_source)
    snapshot = quality.source_snapshot()
    require(digest(canonical(snapshot))==expected_source,'SOURCE_DIGEST_MISMATCH')
    # Executed by the original feedback engine; do not substitute its observations.
    directed = guided.execute(solc_path,evm_path,expected_source,seed=seed,candidates=candidates)
    image_solc = compiler.read_pinned_binary(solc_path)
    image_evm = evm.read_evm(evm_path)
    require(directed['engine_pins'] == {
        'solc_sha256':digest(image_solc), 'evm_sha256':digest(image_evm)},'ENGINE_IDENTITY_CHANGED')
    controls = _fixed_arm(image_solc,image_evm,directed['builds'],seed=seed,candidates=candidates)
    out = compare_reports(directed,controls,expected_source=expected_source,
                          seed=seed,candidates=candidates)
    out['engine_pins'] = deepcopy(directed['engine_pins'])
    require(snapshot == quality.source_snapshot(),'CODE_CHANGED_DURING_COMPARISON')
    return out


def _audit(report: dict, created: str) -> bytes:
    log = load_components().audit.AuditLog(clock=lambda:created)
    log.append('benchmark.evm.start', {
        'source_digest':report['source_digest'],'seed':report['seed'],
        'candidates':report['candidates'], 'total_calls':report['budget']['total_calls']})
    for arm_name in ('guided','fixed_parent'):
        for row in report[arm_name]['cases']:
            log.append('benchmark.evm.case', {'arm':arm_name,'index':row['case_index'],
                   'sequence_sha256':row['sequence_sha256'],
                   'observations_sha256':digest(canonical(row['observations']))})
    log.append('benchmark.evm.complete',{'result_sha256':digest(canonical(report))})
    log.assert_intact()
    return canonical({'created_at': created, 'entries':[asdict(e) for e in log.entries],
                      'producer_authenticated':False})


def _render(report: dict) -> bytes:
    a,b = report['guided']['summary'],report['fixed_parent']['summary']
    return ('# Comparación EVM con presupuesto idéntico\n\n'
            f"Casos por brazo: {a['cases_executed']}. Llamadas EVM por brazo: {a['runtime_calls']}.\n"
            f"Cobertura observable guiada: {a['observed_features']} rasgos; nuevos tras base: {a['new_features_after_baseline']}.\n"
            f"Cobertura observable sin feedback: {b['observed_features']} rasgos; nuevos tras base: {b['new_features_after_baseline']}.\n"
            f"Diferencia (guiado menos control): {report['guided_minus_fixed_features']} rasgos.\n\n"
            'La base, las recetas de mutación, las fuentes, el compilador, la EVM y el número de llamadas son iguales.\n'
            'Solo cambia qué secuencia sirve como padre de la siguiente mutación.\n'
            'Un solo seed y controles propios: NO mide recall, precisión, exploits ni superioridad estadística.\n'
            'No hay objetivos externos, redes ni recompensas. Los paquetes deben permanecer privados.\n').encode()


def create(out: Path, solc: Path, evm_binary: Path, source: str,
           *, seed: int=20261105, candidates: int=2) -> dict:
    require(not out.exists() and not out.is_symlink() and
            not out.resolve().is_relative_to(ROOT.parent),'PRIVATE_NEW_DIRECTORY_REQUIRED')
    result = execute(solc,evm_binary,source,seed=seed,candidates=candidates)
    created = datetime.now().astimezone().isoformat()
    write_new_bundle(out,{'comparison.json':canonical(result),
                          'audit.json':_audit(result,created),
                          'REVIEW.md':_render(result)})
    return {'status':'OWNED_EVM_COMPARISON_CREATED',
            'calls':result['budget']['total_calls'],
            'guided_features':result['guided']['summary']['observed_features'],
            'control_features':result['fixed_parent']['summary']['observed_features'],
            'superiority_proven':False}


def verify(bundle: Path, solc: Path, evm_binary: Path, source: str,
           *, expected_seed: int, expected_candidates: int) -> dict:
    validate_parameters(expected_seed,expected_candidates,source)
    require(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    marker = strict_json(read_artifact(bundle,'COMPLETE.json'))
    require(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
            type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FILES and
            {p.name for p in bundle.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILE_SET')
    saved={n:read_artifact(bundle,n) for n in FILES}
    require(all(digest(saved[n]) == marker['sha256'][n] for n in FILES),'BUNDLE_HASH_MISMATCH')
    asserted=strict_json(saved['comparison.json'])
    require(asserted.get('source_digest')==source and
            asserted.get('seed')==expected_seed and
            asserted.get('candidates')==expected_candidates,'EXPECTED_CONTEXT_MISMATCH')
    audit=strict_json(saved['audit.json']);created=audit.get('created_at')
    require(type(created) is str and len(created)<64,'AUDIT_DATE_SCHEMA')
    try:
        t=datetime.fromisoformat(created)
    except (ValueError,OverflowError) as exc:
        raise ComparisonError('AUDIT_DATE_SCHEMA') from exc
    require(t.tzinfo is not None,'AUDIT_DATE_SCHEMA')
    fresh=execute(solc,evm_binary,source,seed=expected_seed,candidates=expected_candidates)
    require(saved['comparison.json']==canonical(fresh) and
            saved['audit.json']==_audit(fresh,created) and
            saved['REVIEW.md']==_render(fresh),'NATIVE_REPLAY_DISAGREEMENT')
    require(all(read_artifact(bundle,n)==saved[n] for n in FILES),'BUNDLE_CHANGED_DURING_REPLAY')
    return {'status':'OWNED_EVM_COMPARISON_REPLAY_VERIFIED',
            'calls':fresh['budget']['total_calls'],
            'guided_features':fresh['guided']['summary']['observed_features'],
            'control_features':fresh['fixed_parent']['summary']['observed_features'],
            'superiority_proven':False}


def main(argv: list[str] | None=None) -> int:
    p=PrivateArgumentParser(description='Compare owned fixed EVM feedback and no-feedback under equal budgets')
    sub=p.add_subparsers(dest='command', required=True)
    for command in ('compare-owned-evm','verify-owned-evm-comparison'):
        q=sub.add_parser(command)
        for key in ('solc','evm'):
            q.add_argument('--'+key,type=Path,required=True)
        q.add_argument('--expected-source',required=True)
        if command=='compare-owned-evm':
            q.add_argument('--out',type=Path,required=True)
            q.add_argument('--seed',type=int,default=20261105)
            q.add_argument('--candidates',type=int,default=2)
        else:
            q.add_argument('--bundle',type=Path,required=True)
            q.add_argument('--expected-seed',type=int,required=True)
            q.add_argument('--expected-candidates',type=int,required=True)
    args=p.parse_args(argv)
    try:
        result=(create(args.out,args.solc,args.evm,args.expected_source,
                      seed=args.seed,candidates=args.candidates)
                if args.command=='compare-owned-evm' else
                verify(args.bundle,args.solc,args.evm,args.expected_source,
                       expected_seed=args.expected_seed,
                       expected_candidates=args.expected_candidates))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,RuntimeError,RecursionError,OverflowError):
        print(json.dumps({'status':'OWNED_EVM_COMPARISON_BLOCKED',
                          'superiority_proven':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
