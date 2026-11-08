"""Bounded, trace-feedback-directed mutation of fixed OWNED Solidity controls.

Observed EVM PC/conditional-edge novelty chooses which input to mutate next.
Only two internal arithmetic controls and two pinned codegen configurations are
permitted. This is NOT generalized security scanning, exploit development,
coverage of reachable code, or evidence of a previously unknown vulnerability.
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

from . import evm_execution as evm, evm_sequence_fuzz as fuzz
from . import evm_opcode_trace as opcode, native_compile as compiler, quality
from . import balance_reconciliation as accounting
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-trace-feedback-mutation-v1'
FILES = {'guided-observations.json', 'audit.json', 'REVIEW.md'}
MAX_CANDIDATES = 3
# Fixed reference seed. No external bytecode, calldata, ABI, path or target input.
BASELINE = [[0, evm.GAS] for _ in range(fuzz.STEPS)]


class GuidanceError(ValueError):
    """Non-sensitive fixed error codes."""


def require(value: bool, code: str) -> None:
    if not value:
        raise GuidanceError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate(seed: object, candidates: object) -> None:
    require(type(seed) is int and 0 <= seed < 2**64, 'SEED_UINT64')
    require(type(candidates) is int and 1 <= candidates <= MAX_CANDIDATES, 'CANDIDATE_LIMIT')


def case_features(summaries: dict) -> set[str]:
    """Domain-separate PC and JUMPI features by control AND compiler profile."""
    require(type(summaries) is dict and set(summaries)==set(fuzz.CONTROLS), 'CONTROL_INVENTORY')
    result = set()
    for control in fuzz.CONTROLS:
        profiles=summaries[control]
        require(type(profiles) is dict and set(profiles)==set(fuzz.PROFILES), 'PROFILE_INVENTORY')
        for profile in fuzz.PROFILES:
            row=profiles[profile]
            require(type(row) is dict and set(row)=={'pcs','edges','outcomes','trace_sha256','final_state'},
                    'OBSERVATION_SCHEMA')
            require(type(row['pcs']) is list and all(type(v) is int and v>=0 for v in row['pcs']) and
                    row['pcs']==sorted(set(row['pcs'])),'OBSERVED_PC_SCHEMA')
            require(type(row['edges']) is list and all(type(e) is str and re.fullmatch(r'[0-9]+:(taken|fallthrough|indeterminate)',e) for e in row['edges']) and
                    row['edges']==sorted(set(row['edges'])),'OBSERVED_EDGE_SCHEMA')
            result.update(f'{control}|{profile}|pc:{v}' for v in row['pcs'])
            result.update(f'{control}|{profile}|jumpi:{v}' for v in row['edges'])
    return result


def choose_parent(history: list[dict]) -> int:
    """Choose observed novel traces before rare features, stable index tie-break.

    This is a selection heuristic, not a claim of maximizing future coverage.
    """
    require(type(history) is list and bool(history),'EMPTY_FEEDBACK')
    require(all(type(case) is dict and type(case.get('features')) is set and
                type(case.get('new_features')) is set and
                all(type(f) is str for f in case['features'] | case['new_features'])
                for case in history),'FEEDBACK_SCHEMA')
    frequency=Counter(feature for case in history for feature in case['features'])
    scores=[]
    for index,case in enumerate(history):
        rarity=sum(1/frequency[f] for f in case['features'])
        # A fresh mutation that discovered any site/edge outranks the baseline.
        # Otherwise the seed's large initial coverage would dominate forever.
        scores.append((int(index>0 and bool(case['new_features'])),
                       len(case['new_features']) if index>0 else 0,rarity,-index))
    return max(range(len(history)),key=lambda i:scores[i])


def next_mutation(parent: list[list[int]], iteration: int, seed: int) -> tuple[list[list[int]],dict]:
    """Restricted boundary mutations, scheduled after observing preceding traces.

    On iterations 1..3: first transfer beyond initial balance, then force one
    low-gas attempt, then test maximal uint8. Determinism is explicitly seeded.
    """
    validate(seed, iteration)
    require(type(parent) is list and len(parent)==fuzz.STEPS and
            all(type(row) is list and len(row)==2 and type(row[0]) is int and 0<=row[0]<=255 and
                type(row[1]) is int and row[1] in (1,evm.GAS) for row in parent),'PARENT_CASE')
    candidate=deepcopy(parent)
    if iteration==1:
        position=0;field='quantity';value=16
    elif iteration==2:
        position=2+(seed % 2);field='gas';value=1
    else:
        position=1;field='quantity';value=255
    index=0 if field=='quantity' else 1
    # Ensure actual mutation when the chosen parent already has the sentinel.
    if candidate[position][index]==value:
        value=15 if field=='quantity' else evm.GAS
    candidate[position][index]=value
    require(candidate!=parent,'MUTATION_NOT_CHANGED')
    return candidate,{'operation_index':position,'field':field,'new_value':value,
                      'origin':'bounded-boundary-proposal-selected-from-trace-feedback'}


def _run_one(name: str, contract: dict, image: bytes, bytecode: str,
             initial_alloc: dict, sequence: list[list[int]]) -> dict:
    """Fresh constructor state for each sequence; verify every call against 2 oracles."""
    require(name in fuzz.CONTROLS,'UNKNOWN_CONTROL')
    require(len(sequence)==fuzz.STEPS,'WRONG_SEQUENCE_SIZE')
    selector=contract['evm']['methodIdentifiers']['move(uint8)']
    allocation=deepcopy(initial_alloc)
    state={'debit':15,'credit':0,'steps':0}
    pcs, edges = set(), set()
    outcomes=Counter(); traces=[]
    for position,(quantity,gas) in enumerate(sequence):
        expected=fuzz.verify_oracles(name,state,quantity,gas)
        calldata=selector+format(quantity,'064x')
        traced=opcode._run_traced(image,prestate=evm.genesis(allocation,gas=gas),
                                  calldata=calldata,gas=gas,bytecode=bytecode)
        observed=traced['observed']
        after=evm.decode_state(observed['alloc'],contract)
        require(after==expected['state'] and observed['error']==expected['error'] and
                observed['return_data']==expected['return_data'],'EVM_ORACLE_DISAGREEMENT')
        if expected['status']!='COMMITTED':
            require(canonical(allocation)==canonical(observed['alloc']),'REVERT_MUTATED_STATE')
        flow=[] if expected['status']!='COMMITTED' or quantity==0 else [
            {'id':f'step-{position}','from':'debit','to':'credit','amount_units':str(quantity)}]
        balances={k:str(state[k]) for k in ('debit','credit')}
        finals={k:str(after[k]) for k in ('debit','credit')}
        require(accounting.reconcile_internal_units(balances,finals,flow)['status']==
                'UNIT_BALANCES_RECONCILED','EVM_ACCOUNTING_DISAGREEMENT')
        trace=traced['trace'];pcs.update(trace['instruction_sites']);edges.update(trace['conditional_edge_set'])
        outcomes[expected['status']]+=1
        traces.append({'step':position,'quantity':quantity,'gas':gas,
                       'status':expected['status'],'state_after':after,
                       'stdout_sha256':traced['stdout_sha256'],
                       'trace_raw_sha256':trace['trace_raw_sha256'],
                       'pc_opcode_sha256':trace['pc_opcode_sha256'],
                       'state_root':observed['state_root']})
        state,allocation=after,observed['alloc']
    return {'pcs':sorted(pcs),'edges':sorted(edges),'outcomes':dict(sorted(outcomes.items())),
            'trace_sha256':sha(canonical(traces)),'final_state':state}


def execute(solc: Path, evm_binary: Path, expected: str, *, seed: int=20261105,
            candidates: int=2) -> dict:
    """Compile fixed sources and evaluate a baseline + sequential mutations.

    Each candidate is proposed using the actual coverage of earlier runs. No
    result is adopted solely from a Python oracle or an untrusted bundle.
    """
    validate(seed,candidates)
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None,
            'EXTERNAL_SOURCE_DIGEST_REQUIRED')
    before=quality.source_snapshot()
    require(sha(canonical(before))==expected,'SOURCE_DIGEST_MISMATCH')
    image_solc=compiler.read_pinned_binary(solc)
    image_evm=evm.read_evm(evm_binary)
    contracts={};constructors={}
    for control in fuzz.CONTROLS:
        initial, first=fuzz._compile(control,fuzz.PROFILES[0],image_solc,None)
        _,second=fuzz._compile(control,fuzz.PROFILES[1],image_solc,initial)
        contracts[control]={}
        constructors[control]={}
        for profile,compiled in zip(fuzz.PROFILES,(first,second)):
            contract=compiled['contract']
            birth=evm._run(image_evm,prestate=evm.genesis(),
                           creation=contract['evm']['bytecode']['object'])
            observed=birth['observed']
            require(observed['error'] is None and observed['return_data']==
                    '0x'+contract['evm']['deployedBytecode']['object'],'CONSTRUCTOR_RUNTIME')
            require(evm.decode_state(observed['alloc'],contract)==
                    {'debit':15,'credit':0,'steps':0},'CONSTRUCTOR_STORAGE')
            contracts[control][profile]=(contract,compiled,observed['alloc'])
            constructors[control][profile]={
                'creation_sha256':compiled['creation_sha256'],
                'runtime_sha256':compiled['runtime_sha256'],
                'constructor_state_root':observed['state_root']}
    report_rows=[];history=[];all_seen=set()
    for idx in range(candidates+1):
        if idx==0:
            sequence=deepcopy(BASELINE);parent=None;mutation=None
        else:
            parent=choose_parent(history)
            sequence,mutation=next_mutation(report_rows[parent]['sequence'],idx,seed)
            require(sequence not in [row['sequence'] for row in report_rows],
                    'DUPLICATE_MUTATION_CASE')
        observations={}
        for control in fuzz.CONTROLS:
            observations[control]={}
            for profile in fuzz.PROFILES:
                contract,compiled,allocation=contracts[control][profile]
                observations[control][profile]=_run_one(
                    control,contract,image_evm,contract['evm']['deployedBytecode']['object'],
                    allocation,sequence)
        current=case_features(observations)
        novel=current-all_seen
        report_rows.append({'case_index':idx,'parent_index':parent,'mutation':mutation,
                            'sequence':sequence,'sequence_sha256':sha(canonical(sequence)),
                            'observations':observations,'feature_count':len(current),
                            'new_feature_count':len(novel),
                            'new_features':sorted(novel)})
        history.append({'features':current,'new_features':novel})
        all_seen.update(current)
    require(before==quality.source_snapshot(),'SOURCE_CHANGED_DURING_EXECUTION')
    total=Counter()
    for row in report_rows:
        for control in fuzz.CONTROLS:
            for profile in fuzz.PROFILES:
                total.update(row['observations'][control][profile]['outcomes'])
    return {'schema_version':1,'profile':PROFILE,
            'status':'OWNED_EVM_GUIDANCE_OBSERVED','source_digest':expected,
            'seed':seed,'candidates':candidates,'baseline_cases':1,
            'contracts':list(fuzz.CONTROLS),'codegen_profiles':list(fuzz.PROFILES),
            'constructor_count':len(fuzz.CONTROLS)*len(fuzz.PROFILES),
            'runtime_calls':len(report_rows)*fuzz.STEPS*len(fuzz.CONTROLS)*len(fuzz.PROFILES),
            'builds':constructors,'cases':report_rows,'observed_feature_count':len(all_seen),
            'novel_features_after_baseline':sum(x['new_feature_count'] for x in report_rows[1:]),
            'runtime_outcomes':dict(sorted(total.items())),
            'selection_method':'actual-observed-pc-and-jumpi-novelty-then-rarity',
            'mutation_strategy':'bounded-boundary-variants-iterative-parent-choice',
            'engine_pins':{'solc_sha256':sha(image_solc),'evm_sha256':sha(image_evm)},
            'baseline_is_freshly_executed':True,'candidate_cases_executed':True,
            'full_instruction_coverage_proven':False,'full_branch_coverage_proven':False,
            'previously_unknown_vulnerability_found':False,'vulnerability_confirmed':False,
            'external_programs_executed':False,'network_used':False,'second_evm_used':False}


def _audit(report: dict, created: str) -> bytes:
    log=load_components().audit.AuditLog(clock=lambda:created)
    log.append('evm.guided.start',{'source_sha256':report['source_digest'],
                                   'seed':report['seed'],'candidates':report['candidates']})
    for row in report['cases']:
        log.append('evm.guided.case',{'index':row['case_index'],
                                      'sequence_sha256':row['sequence_sha256'],
                                      'observations_sha256':sha(canonical(row['observations']))})
    log.append('evm.guided.complete',{'report_sha256':sha(canonical(report))})
    log.assert_intact()
    return canonical({'created_at':created,'entries':[asdict(e) for e in log.entries],
                      'producer_authenticated':False})


def _render(report: dict) -> bytes:
    return ('# SUPERHUNTER: mutación dirigida por PCs realmente ejecutados\n\n'
            f"Casos: {len(report['cases'])} (una base + {report['candidates']} mutaciones).\n"
            f"Llamadas EVM con trazas: {report['runtime_calls']}.\n"
            f"Rasgos PC/arista observados: {report['observed_feature_count']}.\n"
            f"Rasgos adicionales tras la base: {report['novel_features_after_baseline']}.\n"
            'Se comparan los dos perfiles y los estados/retornos con dos modelos.\n'
            'Se comprueban MOVIMIENTOS PERSISTENTES; reversiones no se cuentan.\n'
            'Se registra la selección siguiente a partir de las trazas previas.\n'
            'No se demuestra cobertura completa, detección de bugs nuevos, explotación ni dinero.\n'
            'Solo contratos de prueba propios, sin RPC ni datos de programas externos.\n').encode()


def create(out: Path, solc: Path, evm_binary: Path, expected: str, *,
           seed: int=20261105, candidates: int=2) -> dict:
    require(not out.exists() and not out.is_symlink() and
            not out.resolve().is_relative_to(ROOT.parent),'PRIVATE_NEW_DIRECTORY_REQUIRED')
    report=execute(solc,evm_binary,expected,seed=seed,candidates=candidates)
    created=datetime.now(timezone.utc).isoformat()
    write_new_bundle(out,{'guided-observations.json':canonical(report),
                          'audit.json':_audit(report,created),'REVIEW.md':_render(report)})
    return {'status':'OWNED_EVM_GUIDANCE_CREATED','observed_features':report['observed_feature_count'],
            'new_features':report['novel_features_after_baseline'],
            'runtime_calls':report['runtime_calls'],'vulnerability_confirmed':False}


def verify(root: Path, solc: Path, evm_binary: Path, expected: str) -> dict:
    require(root.is_dir() and not root.is_symlink(),'BUNDLE_DIRECTORY')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    require(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
            type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FILES and
            {p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILES')
    files={name:read_artifact(root,name) for name in FILES}
    require(all(sha(files[name])==marker['sha256'][name] for name in FILES),'BUNDLE_HASH')
    claimed=strict_json(files['guided-observations.json'])
    require(type(claimed) is dict and type(claimed.get('seed')) is int and
            type(claimed.get('candidates')) is int,'BUNDLE_PARAMETERS')
    audit=strict_json(files['audit.json'])
    created=audit.get('created_at')
    require(type(created) is str and len(created)<64,'AUDIT_TIMESTAMP')
    try:
        parsed=datetime.fromisoformat(created)
        require(parsed.tzinfo is not None,'AUDIT_TIMESTAMP')
    except (TypeError, ValueError) as exc:
        raise GuidanceError('AUDIT_TIMESTAMP') from exc
    report=execute(solc,evm_binary,expected,seed=claimed['seed'],candidates=claimed['candidates'])
    require(files['guided-observations.json']==canonical(report) and
            files['audit.json']==_audit(report,created) and
            files['REVIEW.md']==_render(report),'REPLAY_DISAGREEMENT')
    require(all(read_artifact(root,n)==files[n] for n in FILES),'BUNDLE_CHANGED')
    return {'status':'OWNED_EVM_GUIDANCE_REPLAY_VERIFIED',
            'runtime_calls':report['runtime_calls'],
            'observed_features':report['observed_feature_count'],
            'new_features':report['novel_features_after_baseline'],
            'vulnerability_confirmed':False}


def main(argv: list[str] | None=None) -> int:
    p=PrivateArgumentParser(description='Run only own fixed contract mutation using pinned local EVM')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('guide-owned-evm','verify-guided-evm'):
        q=sub.add_parser(name)
        q.add_argument('--solc',required=True,type=Path)
        q.add_argument('--evm',required=True,type=Path)
        q.add_argument('--expected-source',required=True)
        q.add_argument('--out' if name=='guide-owned-evm' else '--bundle',required=True,type=Path)
        if name=='guide-owned-evm':
            q.add_argument('--seed',default=20261105,type=int)
            q.add_argument('--candidates',default=2,type=int)
    args=p.parse_args(argv)
    try:
        result=(create(args.out,args.solc,args.evm,args.expected_source,
                       seed=args.seed,candidates=args.candidates)
                if args.command=='guide-owned-evm' else
                verify(args.bundle,args.solc,args.evm,args.expected_source))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,RuntimeError,OverflowError,RecursionError):
        print(json.dumps({'status':'OWNED_EVM_GUIDANCE_BLOCKED',
                          'vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
