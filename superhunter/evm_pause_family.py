"""Two real, fixed OWNED Solidity pause-guard regressions on the pinned Geth EVM.

This module expands lab *behavioral diversity*, not discovery capability:
intentionally faulty code is known before testing. No external code, calldata,
program, RPC, deployment, exploit, or account can be supplied to the executor.
A replay recompiles and reexecutes the same fixed source; it does not authenticate
an independent EVM or imply a real bug-bounty finding.
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

from . import evm_execution as evm, native_compile as compiler, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SOURCE_FILE, CONTRACT = 'OwnedPause.sol', 'PauseLedger'
PROFILE = 'owned-pause-guard-native-evm-v1'
FILES = {'execution.json', 'audit.json', 'REVIEW.md'}
VARIANTS = ('guarded', 'guard_missing')
CODEGEN = ('legacy', 'ir_optimized')

# This is an intentionally limited, OWNED regression contract, not a target.
# The only variant difference is the requirement guarding paused releases.
HEADER = '''// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
contract PauseLedger {
    uint16 public remaining = 15;
    uint16 public distributed;
    uint8 public paused;
    function setPaused(uint8 state) external {
        require(state <= 1);
        paused = state;
    }
    function release(uint8 amount) external {
'''
FOOTER = '''        require(amount <= remaining);
        remaining -= amount;
        distributed += amount;
    }
}
'''
GUARD = '        require(paused == 0);\n'
SEQUENCES = (
    (('pause',1,evm.GAS),('release',2,evm.GAS),('pause',0,evm.GAS),('release',3,evm.GAS)),
    (('release',2,evm.GAS),('pause',1,evm.GAS),('release',1,evm.GAS),('pause',0,evm.GAS)),
    (('pause',1,evm.GAS),('pause',1,evm.GAS),('release',0,evm.GAS),('release',1,evm.GAS)),
    (('pause',2,evm.GAS),('release',16,evm.GAS),('pause',1,evm.GAS),('release',1,evm.GAS)),
    (('pause',1,evm.GAS),('release',4,1),('release',4,evm.GAS),('pause',0,evm.GAS)),
)
STORAGE = [('remaining','0',0,'uint16'),('distributed','0',2,'uint16'),('paused','0',4,'uint8')]


class PauseLabError(ValueError):
    """Fixed error codes; no user-controlled source text in diagnostics."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise PauseLabError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def owned_source(variant: str) -> str:
    require(type(variant) is str and variant in VARIANTS, 'VARIANT_NOT_ALLOWED')
    return HEADER + (GUARD if variant == 'guarded' else '') + FOOTER


def compile_input(variant: str, codegen: str) -> dict:
    require(type(codegen) is str and codegen in CODEGEN, 'CODEGEN_NOT_ALLOWED')
    settings = {'optimizer': {'enabled':codegen!='legacy', 'runs':200},
                'evmVersion':'cancun','modelChecker':{'engine':'none'},
                'outputSelection':{'*':{'':['ast'],'*':['abi','storageLayout',
                    'evm.bytecode','evm.deployedBytecode','evm.methodIdentifiers']}}}
    if codegen == 'ir_optimized':
        settings['viaIR'] = True
    return {'language':'Solidity','sources':{SOURCE_FILE:{'content':owned_source(variant)}},
            'settings':settings}


def compile_owned(image: bytes, variant: str, codegen: str) -> dict:
    inp = compile_input(variant,codegen)
    output, stderr = compiler._execute(image, 'compile', canonical(inp))
    require(stderr == b'' and compiler.classify_output(inp,output)['status'] ==
            'SOLC_COMPILATION_COMPLETED', 'OWNED_COMPILATION_FAILED')
    obj = strict_json(output)
    require(set(obj['contracts']) == {SOURCE_FILE} and
            set(obj['contracts'][SOURCE_FILE]) == {CONTRACT}, 'UNEXPECTED_CONTRACT')
    contract = obj['contracts'][SOURCE_FILE][CONTRACT]
    expected = [(r['label'],r['slot'],r['offset'],contract['storageLayout']['types'][r['type']]['label'])
                for r in contract['storageLayout']['storage']]
    require(expected == STORAGE, 'OWNED_LAYOUT_CHANGED')
    methods = contract['evm']['methodIdentifiers']
    require(type(methods) is dict and set(methods) ==
            {'remaining()','distributed()','paused()','release(uint8)','setPaused(uint8)'} and
            all(re.fullmatch('[0-9a-f]{8}',v) is not None for v in methods.values()),
            'OWNED_SELECTORS_CHANGED')
    creation = contract['evm']['bytecode']['object']
    runtime = contract['evm']['deployedBytecode']['object']
    require(all(type(v) is str and bool(v) and len(v)%2==0 and re.fullmatch('[0-9a-f]+',v)
                for v in (creation,runtime)), 'INVALID_OWNED_BYTECODE')
    require(contract['evm']['bytecode']['linkReferences'] == {} and
            contract['evm']['deployedBytecode']['linkReferences'] == {} and
            contract['evm']['deployedBytecode']['immutableReferences'] == {},
            'UNRESOLVED_OWNED_LINK')
    return {'contract':contract,'record':{'variant':variant,'codegen':codegen,
           'source_sha256':sha(owned_source(variant).encode()),
           'input_sha256':sha(canonical(inp)),'output_sha256':sha(output),
           'creation_sha256':sha(bytes.fromhex(creation)),
           'runtime_sha256':sha(bytes.fromhex(runtime))}}


def decode(alloc: dict, contract: dict) -> dict:
    require(type(alloc) is dict and evm.RECEIVER in alloc, 'CONTRACT_MISSING')
    require(alloc[evm.RECEIVER]['code'] ==
            '0x'+contract['evm']['deployedBytecode']['object'], 'OWNED_RUNTIME_CHANGED')
    fields = [(r['label'],r['slot'],r['offset'],contract['storageLayout']['types'][r['type']]['label'])
              for r in contract['storageLayout']['storage']]
    require(fields == STORAGE, 'OWNED_LAYOUT_CHANGED')
    word = int(alloc[evm.RECEIVER]['storage'].get(evm.SLOT, '0x0'),16)
    require(word >> 40 == 0, 'UNEXPECTED_OWNED_STORAGE')
    return {'remaining':word&65535, 'distributed':(word>>16)&65535, 'paused':(word>>32)&255}


def reference(variant: str, before: dict, operation: str, amount: int, gas: int) -> dict:
    """Deterministic transition model, independent of the compiler and EVM."""
    require(variant in VARIANTS and operation in ('pause','release') and
            type(amount) is int and 0 <= amount <= 255 and
            type(gas) is int and gas in (1,evm.GAS) and
            type(before) is dict and set(before) == {'remaining','distributed','paused'} and
            all(type(v) is int for v in before.values()), 'OWNED_REFERENCE_INPUT')
    after = dict(before)
    if gas == 1:
        status,error = 'OUT_OF_GAS','out of gas'
    elif operation == 'pause' and amount > 1:
        status,error = 'REVERTED','execution reverted'
    elif operation == 'release' and (amount > before['remaining'] or
         (before['paused']==1 and variant=='guarded')):
        status,error = 'REVERTED','execution reverted'
    else:
        status,error='COMMITTED',None
        if operation == 'pause':
            after['paused'] = amount
        else:
            after['remaining'] -= amount
            after['distributed'] += amount
    return {'status':status,'state':after,'error':error,'return_data':'0x'}


def unauthorized_effect(before: dict, after: dict, operation: str, amount: int, status: str) -> bool:
    """Separate *observed-property* checker, not an alias of reference()."""
    return (operation == 'release' and amount > 0 and before['paused'] == 1 and
            status == 'COMMITTED' and after['remaining'] < before['remaining'] and
            after['distributed'] > before['distributed'])


def execute(solc: Path, evm_path: Path, expected_source: str) -> dict:
    require(type(expected_source) is str and re.fullmatch('[0-9a-f]{64}', expected_source),
            'EXTERNAL_SOURCE_DIGEST_REQUIRED')
    before = quality.source_snapshot()
    require(sha(canonical(before)) == expected_source, 'SOURCE_DIGEST_MISMATCH')
    solc_image=compiler.read_pinned_binary(solc)
    evm_image=evm.read_evm(evm_path)
    results, builds = {}, {}
    for variant in VARIANTS:
        results[variant],builds[variant]={},{}
        for codegen in CODEGEN:
            compiled=compile_owned(solc_image,variant,codegen)
            contract=compiled['contract']
            build=compiled['record']
            creation=evm._run(evm_image,prestate=evm.genesis(),creation=contract['evm']['bytecode']['object'])
            require(creation['observed']['error'] is None and
                    creation['observed']['return_data'] == '0x'+contract['evm']['deployedBytecode']['object'],
                    'OWNED_CONSTRUCTOR_FAILED')
            initial=decode(creation['observed']['alloc'], contract)
            require(initial=={'remaining':15,'distributed':0,'paused':0}, 'OWNED_CONSTRUCTOR_STATE')
            builds[variant][codegen]={**build,'constructor_state_root':creation['observed']['state_root']}
            rows=[]
            for case,scenario in enumerate(SEQUENCES):
                alloc=deepcopy(creation['observed']['alloc'])
                current=dict(initial)
                calls=[]
                for step,(operation,amount,gas) in enumerate(scenario):
                    expected=reference(variant,current,operation,amount,gas)
                    selector=contract['evm']['methodIdentifiers'][
                        'setPaused(uint8)' if operation=='pause' else 'release(uint8)']
                    observed=evm._run(evm_image,prestate=evm.genesis(alloc,gas=gas),
                                      calldata=selector+format(amount,'064x'),gas=gas)
                    actual=observed['observed'];following=decode(actual['alloc'],contract)
                    status=('OUT_OF_GAS' if actual['error']=='out of gas' else
                            'REVERTED' if actual['error']=='execution reverted' else 'COMMITTED')
                    require(status == expected['status'] and actual['error']==expected['error'] and
                            actual['return_data']==expected['return_data'] and following==expected['state'],
                            'OWNED_NATIVE_ORACLE_DISAGREEMENT')
                    require(following['remaining']+following['distributed']==15,
                            'OWNED_TOTAL_INVARIANT')
                    if status != 'COMMITTED':
                        require(canonical(actual['alloc'])==canonical(alloc),
                                'REVERT_CHANGED_STATE')
                    calls.append({'step':step,'operation':operation,'amount':amount,'gas':gas,
                                  'status':status,'before':current,'after':following,
                                  'paused_release_persisted':unauthorized_effect(
                                      current,following,operation,amount,status),
                                  'state_root':actual['state_root'],
                                  'stdout_sha256':sha(observed['stdout_utf8'].encode())})
                    current,alloc=following,actual['alloc']
                rows.append({'case':case,'calls':calls,'final_state':current})
            results[variant][codegen]=rows
    require(quality.source_snapshot()==before,'SOURCE_CHANGED_DURING_EXECUTION')
    baseline=results['guarded']['legacy']; faulty=results['guard_missing']['legacy']
    for variant in VARIANTS:
        require(results[variant]['legacy']==results[variant]['ir_optimized'] or all(
            [(a['case']==b['case'] and a['final_state']==b['final_state'] and
              [{k:x[k] for k in ('step','operation','amount','gas','status','before','after','paused_release_persisted')}
               for x in a['calls']] ==
              [{k:x[k] for k in ('step','operation','amount','gas','status','before','after','paused_release_persisted')}
               for x in b['calls']]) for a,b in zip(results[variant]['legacy'],results[variant]['ir_optimized'])]),
              'OWNED_CODEGEN_SEMANTICS_MISMATCH')
    observed_violations={variant:sum(c['paused_release_persisted'] for row in results[variant]['legacy']
                                     for c in row['calls']) for variant in VARIANTS}
    require(observed_violations['guarded']==0 and observed_violations['guard_missing']>0,
            'FIXTURE_DETECTION_CONTROL_MISSING')
    require(baseline[0]['calls'][1]['status']=='REVERTED' and
            faulty[0]['calls'][1]['status']=='COMMITTED', 'CRITICAL_PAUSE_NEGATIVE_CONTROL')
    totals={variant:dict(sorted(Counter(c['status'] for row in results[variant]['legacy']
                                          for c in row['calls']).items())) for variant in VARIANTS}
    return {'schema_version':1,'profile':PROFILE,'status':'OWNED_PAUSE_FIXTURE_COMPARISON',
            'source_digest':expected_source,'solc_sha256':sha(solc_image),
            'evm_sha256':sha(evm_image),'builds':builds,'cases':results,
            'case_count':len(SEQUENCES),'total_native_runtime_calls':len(SEQUENCES)*len(SEQUENCES[0])*len(VARIANTS)*len(CODEGEN),
            'paused_release_violations_in_known_fixture':observed_violations,
            'outcomes_by_variant_one_profile':totals,
            'separate_property_watcher_used':True,'known_intentional_fixture':True,
            'unknown_vulnerability_found':False,'external_programs_executed':0,
            'network_used':False,'economic_loss_demonstrated':False,
            'benchmark_blind':False,'vulnerability_confirmed':False,
            'all_paths_covered':False,'other_compilers_or_evms_verified':False}


def render(report: dict) -> bytes:
    return ('# Prueba nativa de una familia distinta: pausa y distribución\n\n'
            f"Llamadas EVM: {report['total_native_runtime_calls']}; escenarios: {report['case_count']}.\n"
            f"Operaciones durante pausa que persistieron (control correcto): {report['paused_release_violations_in_known_fixture']['guarded']}.\n"
            f"Operaciones durante pausa que persistieron (mutante conocido): {report['paused_release_violations_in_known_fixture']['guard_missing']}.\n\n"
            'Solo código propio intencionadamente alterado, compilado y ejecutado con herramientas fijadas.\n'
            'Una infracción de esta propiedad declarada NO demuestra un hallazgo nuevo ni un bounty.\n'
            'El replay utiliza los mismos motores; no hay objetivos externos ni ejecución de red.\n').encode()


def _audit(report: dict, at: str) -> bytes:
    log=load_components().audit.AuditLog(clock=lambda: at)
    log.append('owned.pause.start',{'source_digest':report['source_digest'],
                                    'solc_sha256':report['solc_sha256'],
                                    'evm_sha256':report['evm_sha256']})
    for variant in VARIANTS:
        for codegen in CODEGEN:
            for row in report['cases'][variant][codegen]:
                log.append('owned.pause.case',{'variant':variant,'codegen':codegen,
                    'case':row['case'],'case_sha256':sha(canonical(row))})
    log.append('owned.pause.complete',{'result_sha256':sha(canonical(report))})
    log.assert_intact()
    return canonical({'entries':[asdict(e) for e in log.entries],
                      'producer_authenticated':False})


def create(out: Path, solc: Path, evm_path: Path, expected_source: str) -> dict:
    require(not out.exists() and not out.is_symlink() and
            not out.resolve().is_relative_to(ROOT.parent), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    result=execute(solc,evm_path,expected_source)
    at=datetime.now(timezone.utc).isoformat()
    write_new_bundle(out,{'execution.json':canonical(result),
                          'audit.json':_audit(result,at),'REVIEW.md':render(result)})
    return {'status':'OWNED_PAUSE_EVM_CREATED','native_calls':result['total_native_runtime_calls'],
            'known_violations':result['paused_release_violations_in_known_fixture']}


def replay(bundle: Path, solc: Path, evm_path: Path, expected_source: str) -> dict:
    require(bundle.is_dir() and not bundle.is_symlink(),'BUNDLE_DIRECTORY')
    marker=strict_json(read_artifact(bundle,'COMPLETE.json'))
    require(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
            type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FILES,
            'BUNDLE_MANIFEST')
    require({p.name for p in bundle.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILES')
    original={k:read_artifact(bundle,k) for k in FILES}
    require(all(sha(original[k])==marker['sha256'][k] for k in FILES),'BUNDLE_HASH')
    saved=strict_json(original['execution.json'])
    require(saved.get('source_digest')==expected_source,'EXTERNAL_CODE_MISMATCH')
    run=execute(solc,evm_path,expected_source)
    require(original['execution.json']==canonical(run), 'OWNED_PAUSE_NATIVE_REPLAY_DISAGREEMENT')
    # Audit record uses an explicit creation timestamp. It is not a time authority.
    claimed=strict_json(original['audit.json'])
    require(type(claimed) is dict and type(claimed.get('entries')) is list and bool(claimed['entries']),
            'AUDIT_FORMAT')
    timestamp=claimed['entries'][0].get('timestamp')
    require(type(timestamp) is str and datetime.fromisoformat(timestamp).tzinfo is not None,
            'AUDIT_TIME_FORMAT')
    require(original['audit.json']==_audit(run,timestamp) and original['REVIEW.md']==render(run),
            'AUDIT_OR_REVIEW_MISMATCH')
    return {'status':'OWNED_PAUSE_EVM_REPLAY_VERIFIED','native_calls':run['total_native_runtime_calls'],
            'known_violations':run['paused_release_violations_in_known_fixture']}


def main(argv: list[str] | None = None) -> int:
    parser=PrivateArgumentParser(description='Compile and execute fixed owned pause-regression controls only')
    sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('run-owned-pause-lab')
    verify=sub.add_parser('verify-owned-pause-lab')
    for p in (make,verify):
        p.add_argument('--solc',type=Path,required=True)
        p.add_argument('--evm',type=Path,required=True)
        p.add_argument('--source-digest',required=True)
    make.add_argument('--out',type=Path,required=True)
    verify.add_argument('--bundle',type=Path,required=True)
    a=parser.parse_args(argv)
    try:
        if a.command=='run-owned-pause-lab':
            res=create(a.out,a.solc,a.evm,a.source_digest)
        else:
            res=replay(a.bundle,a.solc,a.evm,a.source_digest)
        print(json.dumps(res,sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError,OverflowError):
        print(json.dumps({'status':'OWNED_PAUSE_EVM_BLOCKED','vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
