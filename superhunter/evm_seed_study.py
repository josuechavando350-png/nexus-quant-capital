"""Paired multi-seed EVM coverage study on fixed, *owned* arithmetic controls.

This is an executable laboratory experiment, not a vulnerability detector,
network client, or statistical superiority proof. It improves seed diversity
relative to the previous parity-only mutation recipe without replacing that
historical experiment. Every observation is obtained from pinned Geth execution
and checked against the existing exact-state/accounting oracles.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from . import evm_coverage_guidance as guidance, evm_sequence_fuzz as fuzz
from . import evm_execution as evm, native_compile as compiler, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = frozenset({'study.json', 'audit.json', 'REVIEW.md'})
PROFILE = 'owned-paired-multiseed-evm-v1'
DOMAIN = b'SUPERHUNTER-STUDY-RECIPE-V1\x00'
MIN_SEEDS, MAX_SEEDS = 2, 4
MIN_MUTATIONS, MAX_MUTATIONS = 2, 3


class StudyError(ValueError):
    """Private-safe, fixed diagnostics."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise StudyError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def mutation_plan(seed: int, mutations: int) -> list[dict]:
    """A full-64-bit-domain deterministic ordering over 8 independent toggles.

    A seed controls all 8 choices (unlike the earlier parity-only recipe).
    Mutations are without replacement, preventing duplicate fixed-parent cases.
    Plans are fixed BEFORE execution and cannot depend on observed outcomes.
    """
    require(type(seed) is int and 0 <= seed < 2**64, 'SEED_UINT64')
    require(type(mutations) is int and MIN_MUTATIONS <= mutations <= MAX_MUTATIONS,
            'MUTATION_BUDGET')
    positions = [(step, field) for step in range(fuzz.STEPS) for field in (0, 1)]
    positions.sort(key=lambda pair: hashlib.sha256(DOMAIN + seed.to_bytes(8, 'big') +
                                                    bytes(pair)).digest())
    return [{'step': step, 'field': 'quantity' if field == 0 else 'gas'}
            for step, field in positions[:mutations]]


def validate_parameters(seeds: object, mutations: object, source: object) -> list[int]:
    require(type(seeds) is list and MIN_SEEDS <= len(seeds) <= MAX_SEEDS and
            all(type(x) is int and 0 <= x < 2**64 for x in seeds) and
            seeds == sorted(set(seeds)), 'SEEDS_REQUIRE_SORTED_UNIQUE_UINT64')
    require(type(mutations) is int and MIN_MUTATIONS <= mutations <= MAX_MUTATIONS,
            'MUTATION_BUDGET')
    require(type(source) is str and re.fullmatch('[0-9a-f]{64}', source) is not None,
            'EXTERNAL_SOURCE_DIGEST_REQUIRED')
    signatures = {sha(canonical(mutation_plan(s, mutations))) for s in seeds}
    require(len(signatures) >= 2, 'DEGENERATE_SEED_SCHEDULES')
    return seeds


def mutate(parent: list[list[int]], recipe: dict) -> list[list[int]]:
    require(type(parent) is list and len(parent) == fuzz.STEPS and
            all(type(row) is list and len(row) == 2 and type(row[0]) is int and
                row[0] in (0,16) and type(row[1]) is int and row[1] in (1, evm.GAS)
                for row in parent), 'INVALID_OWNED_SEQUENCE')
    require(type(recipe) is dict and set(recipe) == {'step','field'} and
            type(recipe['step']) is int and 0 <= recipe['step'] < fuzz.STEPS and
            recipe['field'] in ('quantity','gas'), 'MUTATION_RECIPE')
    result = deepcopy(parent)
    idx = recipe['step']
    if recipe['field'] == 'quantity':
        result[idx][0] = 16 if result[idx][0] == 0 else 0
    else:
        result[idx][1] = 1 if result[idx][1] == evm.GAS else evm.GAS
    require(result != parent, 'MUTATION_DID_NOT_CHANGE_CASE')
    return result


def prepared_contracts(solc_image: bytes, evm_image: bytes) -> tuple[dict, dict]:
    """Compile four exact controls and execute their constructors, no RPC."""
    prepared, manifests = {}, {}
    for name in fuzz.CONTROLS:
        source, first = fuzz._compile(name, fuzz.PROFILES[0], solc_image, None)
        _, second = fuzz._compile(name, fuzz.PROFILES[1], solc_image, source)
        prepared[name], manifests[name] = {}, {}
        for profile, record in zip(fuzz.PROFILES, (first, second)):
            contract = record['contract']
            birth = evm._run(evm_image, prestate=evm.genesis(),
                             creation=contract['evm']['bytecode']['object'])
            observed = birth['observed']
            require(observed['error'] is None and observed['return_data'] ==
                    '0x' + contract['evm']['deployedBytecode']['object'] and
                    evm.decode_state(observed['alloc'],contract) ==
                    {'debit':15,'credit':0,'steps':0}, 'OWNED_CONSTRUCTOR_MISMATCH')
            prepared[name][profile] = (contract, observed['alloc'])
            manifests[name][profile] = {'creation_sha256':record['creation_sha256'],
                                         'runtime_sha256':record['runtime_sha256'],
                                         'state_root':observed['state_root']}
    return prepared, manifests


def execute_case(prepared: dict, image: bytes, sequence: list[list[int]]) -> dict:
    observations = {}
    for name in fuzz.CONTROLS:
        observations[name] = {}
        for profile in fuzz.PROFILES:
            contract, allocation = prepared[name][profile]
            observations[name][profile] = guidance._run_one(
                name,contract,image,contract['evm']['deployedBytecode']['object'],
                allocation,sequence)
    return observations


def run_arm(prepared: dict, evm_image: bytes, plan: list[dict], *, guided: bool) -> list[dict]:
    rows, history = [], []
    seen = set()
    for idx in range(len(plan)+1):
        if idx == 0:
            parent = None
            sequence = deepcopy(guidance.BASELINE)
            recipe = None
        else:
            parent = guidance.choose_parent(history) if guided else 0
            recipe = plan[idx-1]
            sequence = mutate(rows[parent]['sequence'], recipe)
        signature = sha(canonical(sequence))
        require(signature not in seen, 'REPEATED_SEQUENCE')
        seen.add(signature)
        observed = execute_case(prepared,evm_image,sequence)
        features = guidance.case_features(observed)
        prior = set().union(*(h['features'] for h in history)) if history else set()
        novelty = features - prior
        row = {'case_index':idx,'parent_index':parent,
               'sequence':sequence,'sequence_sha256':signature,
               'mutation':recipe,'observations':observed,
               'new_feature_count':len(novelty)}
        rows.append(row)
        history.append({'features':features,'new_features':novelty})
    return rows


def summarize(rows: list[dict]) -> dict:
    # Recompute from observations, never from claimed new_feature_count fields.
    require(type(rows) is list and len(rows) >= MIN_MUTATIONS+1,'STUDY_ROWS')
    seen, prior, counts = set(), set(), Counter()
    for idx,row in enumerate(rows):
        require(type(row) is dict and row['case_index']==idx and
                row['sequence_sha256']==sha(canonical(row['sequence'])) and
                row['sequence_sha256'] not in seen, 'STUDY_CASE_INVENTORY')
        seen.add(row['sequence_sha256'])
        features = guidance.case_features(row['observations'])
        require(row['new_feature_count']==len(features-prior),'NOVELTY_DISAGREEMENT')
        prior.update(features)
        for control in fuzz.CONTROLS:
            for profile in fuzz.PROFILES:
                counts.update(row['observations'][control][profile]['outcomes'])
    calls = len(rows)*fuzz.STEPS*len(fuzz.CONTROLS)*len(fuzz.PROFILES)
    require(sum(counts.values())==calls,'STUDY_CALL_BUDGET')
    return {'sequences':len(rows),'runtime_calls':calls,
            'observed_features':len(prior),'new_features_after_baseline':
            len(prior-guidance.case_features(rows[0]['observations'])),
            'outcomes':dict(sorted(counts.items()))}


def summarize_study(results: list[dict], source: str, mutations: int,
                    pins: dict, builds: dict) -> dict:
    require(type(results) is list and bool(results),'STUDY_EMPTY')
    pairs, guided_win, fixed_win, ties = [],0,0,0
    initial_baseline = None
    plans = []
    for result in results:
        seed,plan,ga,fa = (result[k] for k in ('seed','plan','guided','fixed_parent'))
        require(plan==mutation_plan(seed,mutations),'MUTATION_PLAN_CHANGED')
        require(len(ga)==len(fa)==mutations+1,'UNBALANCED_CASES')
        require(ga[0]['sequence']==fa[0]['sequence']==guidance.BASELINE and
                ga[0]['parent_index'] is fa[0]['parent_index'] is None and
                canonical(ga[0]['observations'])==canonical(fa[0]['observations']),
                'UNEQUAL_BASELINE')
        # Baselines must also be identical across seeds (same sources, fixed inputs).
        if initial_baseline is None:
            initial_baseline = canonical(ga[0]['observations'])
        require(canonical(ga[0]['observations']) == initial_baseline,'BASELINE_DRIFT')
        for i,recipe in enumerate(plan,1):
            require(ga[i]['mutation']==fa[i]['mutation']==recipe and
                    ga[i]['sequence']==mutate(ga[ga[i]['parent_index']]['sequence'],recipe) and
                    fa[i]['parent_index']==0 and
                    fa[i]['sequence']==mutate(fa[0]['sequence'],recipe) and
                    ga[i]['parent_index'] is not None and
                    type(ga[i]['parent_index']) is int and 0 <= ga[i]['parent_index'] < i,
                    'PARENT_OR_RECIPE_DISAGREEMENT')
        # Validate that guided parents were actually chosen based on prior traces.
        hist=[]
        for i,row in enumerate(ga):
            if i:
                require(row['parent_index'] == guidance.choose_parent(hist),
                        'FEEDBACK_NOT_USED')
            features = guidance.case_features(row['observations'])
            prior=set().union(*(h['features'] for h in hist)) if hist else set()
            hist.append({'features':features,'new_features':features-prior})
        a,b=summarize(ga),summarize(fa)
        require(a['runtime_calls']==b['runtime_calls'],'UNEQUAL_CALL_BUDGET')
        diff=a['observed_features']-b['observed_features']
        guided_win+=int(diff>0);fixed_win+=int(diff<0);ties+=int(diff==0)
        pairs.append({'seed':seed,'recipe_sha256':sha(canonical(plan)),
                      'guided':a,'fixed_parent':b,'coverage_delta':diff,
                      'complete_path_coverage_proven':False})
        plans.append(sha(canonical(plan)))
    total_calls=sum(pair['guided']['runtime_calls']+pair['fixed_parent']['runtime_calls'] for pair in pairs)
    return {'schema_version':1,'profile':PROFILE,
            'status':'OWNED_EVM_MULTISEED_OBSERVED',
            'source_digest':source,'seeds':[x['seed'] for x in results],
            'mutations_per_seed':mutations,'distinct_recipe_schedules':len(set(plans)),
            'per_seed':pairs,'total_runtime_calls':total_calls,
            'total_constructor_executions':len(fuzz.CONTROLS)*len(fuzz.PROFILES),
            'wins':{'guided':guided_win,'fixed_parent':fixed_win,'ties':ties},
            'engine_pins':pins,'compiled_controls':builds,
            'budget_fairness_checked':True,'same_baseline_per_arm_and_seed':True,
            'paired_observation_data':results,
            'full_instruction_coverage_proven':False,
            'statistical_superiority_proven':False,
            'vulnerability_discovered':False,'network_used':False,
            'external_programs_tested':False,
            'interpretation':'Owned arithmetic fixtures, few seeds; no population inference.'}


def execute(solc: Path, geth: Path, source: str, *, seeds: list[int],
            mutations: int=2) -> dict:
    validate_parameters(seeds,mutations,source)
    before=quality.source_snapshot()
    require(sha(canonical(before))==source,'SOURCE_DIGEST_MISMATCH')
    solc_image=compiler.read_pinned_binary(solc)
    evm_image=evm.read_evm(geth)
    prepared,builds=prepared_contracts(solc_image,evm_image)
    rows=[]
    for seed in seeds:
        plan=mutation_plan(seed,mutations)
        rows.append({'seed':seed,'plan':plan,
                     'guided':run_arm(prepared,evm_image,plan,guided=True),
                     'fixed_parent':run_arm(prepared,evm_image,plan,guided=False)})
    require(before==quality.source_snapshot(),'SOURCE_CHANGED_DURING_STUDY')
    return summarize_study(rows,source,mutations,
                           {'solc_sha256':sha(solc_image),'evm_sha256':sha(evm_image)},builds)


def _audit(result: dict,created: str) -> bytes:
    log=load_components().audit.AuditLog(clock=lambda:created)
    log.append('study.start',{'source_digest':result['source_digest'],
                               'seeds':result['seeds'],'mutations':result['mutations_per_seed']})
    for item in result['paired_observation_data']:
        log.append('study.seed',{'seed':item['seed'],
                                  'guided_sha256':sha(canonical(item['guided'])),
                                  'fixed_sha256':sha(canonical(item['fixed_parent']))})
    log.append('study.complete',{'result_sha256':sha(canonical(result))})
    log.assert_intact()
    return canonical({'created_at':created,'entries':[asdict(e) for e in log.entries],
                      'authenticated_producer':False})


def _render(result: dict) -> bytes:
    lines=['# SUPERHUNTER — estudio EVM pareado multisemilla', '',
           'Comparación de mutación guiada y control de padre fijo sobre contratos propios.',
           f"Semillas: {len(result['seeds'])}; planes de mutación distintos: {result['distinct_recipe_schedules']}.",
           f"Llamadas EVM observadas: {result['total_runtime_calls']}.",
           f"Victorias guiado/control/empates: {result['wins']['guided']}/{result['wins']['fixed_parent']}/{result['wins']['ties']}.", '',
           '| Semilla | Guiado | Control | Delta rasgos |', '|---|---:|---:|---:|']
    for pair in result['per_seed']:
        lines.append(f"| {pair['seed']} | {pair['guided']['observed_features']} | "
                     f"{pair['fixed_parent']['observed_features']} | {pair['coverage_delta']} |")
    lines += ['', 'Un rasgo PC/arista observado NO es un bug ni cobertura de rutas completa.',
              'Semillas y pocas mutaciones de contratos conocidos NO prueban superioridad estadística.',
              'No hubo ejecución contra terceros, RPC, transferencias ni descubrimientos originales.',
              'Los resultados se deben contrastar con un benchmark ciego antes de generalizarlos.', '']
    return ('\n'.join(lines)).encode()


def create(out: Path, solc: Path, geth: Path, source: str, *, seeds: list[int],
           mutations: int=2) -> dict:
    require(not out.exists() and not out.is_symlink() and
            not out.resolve().is_relative_to(ROOT.parent),'PRIVATE_NEW_DIRECTORY_REQUIRED')
    report=execute(solc,geth,source,seeds=seeds,mutations=mutations)
    created=datetime.now(timezone.utc).isoformat()
    write_new_bundle(out,{'study.json':canonical(report),'audit.json':_audit(report,created),
                          'REVIEW.md':_render(report)})
    return {'status':'OWNED_EVM_MULTISEED_CREATED','calls':report['total_runtime_calls'],
            'unique_plans':report['distinct_recipe_schedules'],
            'statistical_superiority_proven':False}


def verify(root: Path, solc: Path, geth: Path, source: str, *, seeds: list[int],
           mutations: int=2) -> dict:
    validate_parameters(seeds,mutations,source)
    require(root.is_dir() and not root.is_symlink(),'BUNDLE_DIR')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    require(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
            type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FILES and
            {p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILE_SET')
    blobs={n:read_artifact(root,n) for n in FILES}
    require(all(sha(blobs[n])==marker['sha256'][n] for n in FILES),'BUNDLE_DIGEST')
    claimed=strict_json(blobs['study.json'])
    require(claimed.get('seeds')==seeds and claimed.get('mutations_per_seed')==mutations and
            claimed.get('source_digest')==source,'EXTERNAL_CONTEXT_MISMATCH')
    audit=strict_json(blobs['audit.json']);created=audit.get('created_at')
    require(type(created) is str and len(created)<64,'AUDIT_TIMESTAMP')
    try:
        parsed=datetime.fromisoformat(created)
    except (ValueError,OverflowError) as exc:
        raise StudyError('AUDIT_TIMESTAMP') from exc
    require(parsed.tzinfo is not None,'AUDIT_TIMESTAMP')
    fresh=execute(solc,geth,source,seeds=seeds,mutations=mutations)
    require(blobs['study.json']==canonical(fresh) and
            blobs['audit.json']==_audit(fresh,created) and
            blobs['REVIEW.md']==_render(fresh),'NATIVE_MULTISEED_REPLAY_DISAGREEMENT')
    require(all(read_artifact(root,n)==blobs[n] for n in FILES),'BUNDLE_CHANGED_DURING_REPLAY')
    return {'status':'OWNED_EVM_MULTISEED_REPLAY_VERIFIED',
            'calls':fresh['total_runtime_calls'],
            'unique_plans':fresh['distinct_recipe_schedules'],
            'statistical_superiority_proven':False}


def main(argv: list[str] | None=None) -> int:
    p=PrivateArgumentParser(description='Owned EVM equal-budget paired multi-seed study, offline')
    sub=p.add_subparsers(dest='command',required=True)
    for command in ('study-owned-evm','verify-owned-evm-study'):
        q=sub.add_parser(command)
        for key in ('solc','evm'):
            q.add_argument('--'+key,type=Path,required=True)
        q.add_argument('--expected-source',required=True)
        q.add_argument('--seeds',required=True,help='Comma-separated sorted distinct uint64 seed integers')
        q.add_argument('--mutations',type=int,default=2)
        q.add_argument('--out' if command=='study-owned-evm' else '--bundle',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        parts=args.seeds.split(',')
        require(all(re.fullmatch(r'(0|[1-9][0-9]{0,19})',part) for part in parts),
                'SEED_LIST_FORMAT')
        seeds=[int(v) for v in parts]
        result=(create(args.out,args.solc,args.evm,args.expected_source,seeds=seeds,mutations=args.mutations)
                if args.command=='study-owned-evm' else
                verify(args.bundle,args.solc,args.evm,args.expected_source,seeds=seeds,mutations=args.mutations))
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,RecursionError,OverflowError):
        print(json.dumps({'status':'OWNED_EVM_MULTISEED_BLOCKED',
                          'statistical_superiority_proven':False}));return 2


if __name__=='__main__':
    raise SystemExit(main())
