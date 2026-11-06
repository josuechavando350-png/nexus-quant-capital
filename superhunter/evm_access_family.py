"""Fixed, owned EVM access-control regression using actual msg.sender identity.

Two callers are hardcoded synthetic addresses. The known mutation removes one
authorization check; this is NOT an original vulnerability, third-party scan,
exploit, live transaction, generic EVM runner, or proof of bounty eligibility.
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

from . import evm_execution as evm, evm_access_runner as guest_runner, native_compile as compiler, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-two-caller-authorization-evm-v1'
GUEST = guest_runner.GUEST
SOURCE_FILE, CONTRACT = 'OwnedAccess.sol', 'AccessLedger'
VARIANTS = ('protected', 'missing_auth_guard')
CODEGEN = ('legacy', 'ir_optimized')
FILES = {'execution.json', 'audit.json', 'REVIEW.md'}
SLOT_STORAGE = [('admin','0',0,'address'),('remaining','0',20,'uint16'),
                ('distributed','0',22,'uint16')]
SOURCE_TOP = '''// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
contract AccessLedger {
    address public admin;
    uint16 public remaining = 10;
    uint16 public distributed;
    constructor() { admin = msg.sender; }
    function payout(uint8 amount) external {
'''
SOURCE_BOTTOM = '''        require(amount <= remaining);
        remaining -= amount;
        distributed += amount;
    }
}
'''
AUTH_GUARD = '        require(msg.sender == admin);\n'
# Only two fixed, owned-test callers; no untrusted source, target or calldata.
SEQUENCES = (
    ((GUEST,2,evm.GAS),(evm.SENDER,3,evm.GAS),(GUEST,1,evm.GAS),(evm.SENDER,7,evm.GAS)),
    ((evm.SENDER,4,evm.GAS),(GUEST,3,evm.GAS),(evm.SENDER,0,evm.GAS),(GUEST,9,evm.GAS)),
    ((GUEST,0,evm.GAS),(GUEST,1,evm.GAS),(evm.SENDER,1,evm.GAS),(GUEST,2,evm.GAS)),
    ((evm.SENDER,11,evm.GAS),(GUEST,11,evm.GAS),(evm.SENDER,2,1),(GUEST,4,evm.GAS)),
)


class AccessLabError(ValueError):
    """Fixed diagnostics; never echo untrusted evidence or private paths."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise AccessLabError(code)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def owned_source(variant: str) -> str:
    need(type(variant) is str and variant in VARIANTS, 'UNKNOWN_OWNED_VARIANT')
    return SOURCE_TOP + (AUTH_GUARD if variant == 'protected' else '') + SOURCE_BOTTOM


def compile_input(variant: str, codegen: str) -> dict:
    need(type(codegen) is str and codegen in CODEGEN, 'UNKNOWN_CODEGEN')
    settings = {'optimizer':{'enabled':codegen!='legacy','runs':200},
                'evmVersion':'cancun','modelChecker':{'engine':'none'},
                'outputSelection':{'*':{'':['ast'],'*':['abi','storageLayout',
                   'evm.bytecode','evm.deployedBytecode','evm.methodIdentifiers']}}}
    if codegen == 'ir_optimized':
        settings['viaIR'] = True
    return {'language':'Solidity','sources':{SOURCE_FILE:{'content':owned_source(variant)}},
            'settings':settings}


def compile_owned(image: bytes, variant: str, codegen: str) -> dict:
    inp = compile_input(variant, codegen)
    output, err = compiler._execute(image, 'compile', canonical(inp))
    need(err == b'' and compiler.classify_output(inp, output)['status'] ==
         'SOLC_COMPILATION_COMPLETED', 'OWNED_COMPILATION_FAILED')
    root = strict_json(output)
    need(set(root['contracts']) == {SOURCE_FILE} and
         set(root['contracts'][SOURCE_FILE]) == {CONTRACT}, 'CONTRACT_SET_CHANGED')
    contract = root['contracts'][SOURCE_FILE][CONTRACT]
    layout = contract['storageLayout']
    actual = [(r['label'],r['slot'],r['offset'],layout['types'][r['type']]['label'])
              for r in layout['storage']]
    need(actual == SLOT_STORAGE, 'ACCESS_STORAGE_LAYOUT_CHANGED')
    methods = contract['evm']['methodIdentifiers']
    need(set(methods) == {'admin()','remaining()','distributed()','payout(uint8)'} and
         all(type(v) is str and re.fullmatch('[0-9a-f]{8}', v) for v in methods.values()),
         'ACCESS_ABI_CHANGED')
    creation = contract['evm']['bytecode']['object']
    runtime = contract['evm']['deployedBytecode']['object']
    need(all(type(v) is str and bool(v) and len(v)%2==0 and
             re.fullmatch('[0-9a-f]+',v) for v in (creation,runtime)),
         'ACCESS_BYTECODE_PROFILE')
    need(contract['evm']['bytecode']['linkReferences'] == {} and
         contract['evm']['deployedBytecode']['linkReferences'] == {} and
         contract['evm']['deployedBytecode']['immutableReferences'] == {},
         'UNRESOLVED_LINK')
    return {'contract':contract,'record':{'variant':variant,'codegen':codegen,
            'source_sha256':sha(owned_source(variant).encode()),
            'input_sha256':sha(canonical(inp)),'output_sha256':sha(output),
            'creation_sha256':sha(bytes.fromhex(creation)),
            'runtime_sha256':sha(bytes.fromhex(runtime))}}


def decode(alloc: dict, contract: dict) -> dict:
    need(type(alloc) is dict and evm.RECEIVER in alloc, 'ACCESS_CONTRACT_NOT_FOUND')
    need(alloc[evm.RECEIVER]['code'] ==
         '0x'+contract['evm']['deployedBytecode']['object'], 'ACCESS_RUNTIME_CHANGED')
    layout = contract['storageLayout']
    actual = [(r['label'],r['slot'],r['offset'],layout['types'][r['type']]['label'])
              for r in layout['storage']]
    need(actual == SLOT_STORAGE, 'ACCESS_LAYOUT_CHANGED')
    word = int(alloc[evm.RECEIVER]['storage'].get(evm.SLOT,'0x0'),16)
    need(word >> 192 == 0 and (word & ((1<<160)-1)) == int(evm.SENDER,16),
         'ACCESS_ADMIN_NOT_FROM_CONSTRUCTOR')
    return {'admin':evm.SENDER,'remaining':(word>>160)&65535,
            'distributed':(word>>176)&65535}


def reference(variant: str, before: dict, caller: str, amount: int, gas: int) -> dict:
    need(variant in VARIANTS and caller in (evm.SENDER,GUEST) and
         type(amount) is int and 0 <= amount <= 255 and
         type(gas) is int and gas in (1,evm.GAS) and
         type(before) is dict and set(before) == {'admin','remaining','distributed'} and
         before['admin'] == evm.SENDER and all(type(before[k]) is int for k in ('remaining','distributed')),
         'ACCESS_REFERENCE_PROFILE')
    after=dict(before)
    if gas == 1:
        status,error = 'OUT_OF_GAS','out of gas'
    elif ((variant == 'protected' and caller != before['admin']) or
          amount > before['remaining']):
        status,error='REVERTED','execution reverted'
    else:
        status,error='COMMITTED',None
        after['remaining']-=amount
        after['distributed']+=amount
    return {'status':status,'state':after,'error':error,'return_data':'0x'}


def unauthorized_effect(caller: str, amount: int, status: str, before: dict, after: dict) -> bool:
    """Observed committed effect, not a prediction of the contract behavior."""
    return (caller == GUEST and amount > 0 and status == 'COMMITTED' and
            before['remaining'] - after['remaining'] == amount and
            after['distributed'] - before['distributed'] == amount)


def _semantic_rows(rows: list[dict]) -> list[dict]:
    return [{'case':r['case'],'calls':[{k:c[k] for k in ('step','caller','amount','gas',
               'status','before','after','unauthorized_effect')} for c in r['calls']],
             'final_state':r['final_state']} for r in rows]


def execute(solc: Path, evm_binary: Path, expected_source: str) -> dict:
    need(type(expected_source) is str and re.fullmatch('[0-9a-f]{64}',expected_source),
         'SOURCE_DIGEST_REQUIRED')
    before=quality.source_snapshot()
    need(sha(canonical(before)) == expected_source, 'SOURCE_DIGEST_CHANGED')
    image=compiler.read_pinned_binary(solc)
    native=evm.read_evm(evm_binary)
    cases, builds={},{}
    for variant in VARIANTS:
        cases[variant],builds[variant]={},{}
        for codegen in CODEGEN:
            built=compile_owned(image,variant,codegen)
            contract=built['contract']
            birth=evm._run(native,prestate=evm.genesis(),creation=contract['evm']['bytecode']['object'])
            observed=birth['observed']
            need(observed['error'] is None and observed['return_data'] ==
                 '0x'+contract['evm']['deployedBytecode']['object'], 'ACCESS_CONSTRUCTOR_FAILED')
            state=decode(observed['alloc'],contract)
            need(state=={'admin':evm.SENDER,'remaining':10,'distributed':0},'ACCESS_INITIAL_STATE')
            builds[variant][codegen]={**built['record'],
                                      'constructor_state_root':observed['state_root']}
            rows=[]
            for index,scenario in enumerate(SEQUENCES):
                alloc=deepcopy(observed['alloc'])
                current=dict(state);calls=[]
                for step,(caller,amount,gas) in enumerate(scenario):
                    wanted=reference(variant,current,caller,amount,gas)
                    calldata=contract['evm']['methodIdentifiers']['payout(uint8)']+format(amount,'064x')
                    if caller == evm.SENDER:
                        output=evm._run(native,prestate=evm.genesis(alloc,gas=gas),
                                        calldata=calldata,gas=gas)
                    else:
                        output=guest_runner.run_guest(native,prestate=evm.genesis(alloc,gas=gas),
                                                      calldata=calldata,gas=gas)
                    actual=output['observed'];following=decode(actual['alloc'],contract)
                    status=('OUT_OF_GAS' if actual['error']=='out of gas' else
                            'REVERTED' if actual['error']=='execution reverted' else 'COMMITTED')
                    need(status==wanted['status'] and actual['error']==wanted['error'] and
                         actual['return_data']==wanted['return_data'] and following==wanted['state'],
                         'ACCESS_NATIVE_REFERENCE_DISAGREEMENT')
                    need(following['remaining']+following['distributed']==10,'ACCESS_TOTAL_INVARIANT')
                    if status != 'COMMITTED':
                        need(actual['alloc'][evm.RECEIVER]==alloc[evm.RECEIVER],
                             'ACCESS_REVERT_CHANGED_CONTRACT')
                    calls.append({'step':step,'caller':caller,'amount':amount,'gas':gas,
                       'status':status,'before':current,'after':following,
                       'unauthorized_effect':unauthorized_effect(caller,amount,status,current,following),
                       'state_root':actual['state_root'],
                       'stdout_sha256':sha(output['stdout_utf8'].encode())})
                    alloc,current=actual['alloc'],following
                rows.append({'case':index,'calls':calls,'final_state':current})
            cases[variant][codegen]=rows
        need(_semantic_rows(cases[variant]['legacy'])==
             _semantic_rows(cases[variant]['ir_optimized']), 'ACCESS_CODEGEN_BEHAVIOR_DISAGREEMENT')
    need(quality.source_snapshot()==before,'SOURCES_CHANGED_DURING_ACCESS_LAB')
    known={v:sum(call['unauthorized_effect'] for r in cases[v]['legacy'] for call in r['calls'])
           for v in VARIANTS}
    need(known['protected']==0 and known['missing_auth_guard']>0,'ACCESS_CONTROL_NOT_DISCRIMINATING')
    need(cases['protected']['legacy'][0]['calls'][0]['status']=='REVERTED' and
         cases['missing_auth_guard']['legacy'][0]['calls'][0]['status']=='COMMITTED',
         'ACCESS_CONTROL_DIFFERENTIAL_FAILED')
    return {'schema_version':1,'profile':PROFILE,'status':'OWNED_ACCESS_FIXTURE_COMPARISON',
            'source_digest':expected_source,'solc_sha256':sha(image),'evm_sha256':sha(native),
            'builds':builds,'cases':cases,'scenario_count':len(SEQUENCES),
            'native_constructor_calls':len(VARIANTS)*len(CODEGEN),
            'native_runtime_calls':len(VARIANTS)*len(CODEGEN)*sum(map(len,SEQUENCES)),
            'known_unauthorized_persistent_effects_one_profile':known,
            'outcomes_by_variant_one_profile':{v:dict(sorted(Counter(c['status']
                for r in cases[v]['legacy'] for c in r['calls']).items())) for v in VARIANTS},
            'sender_identities_are_fixed_synthetic':True,
            'known_intentional_mutation':True,'unknown_vulnerability_found':False,
            'network_used':False,'real_assets_executed':False,'economic_loss_demonstrated':False,
            'blind_benchmark':False,'vulnerability_confirmed':False,
            'all_paths_proven':False,'independent_evm_verified':False}


def render(result: dict) -> bytes:
    return ('# Control de dos remitentes sobre contratos de prueba\n\n'
            f"Constructores nativos: {result['native_constructor_calls']}; "
            f"llamadas: {result['native_runtime_calls']}.\n"
            f"Efectos no autorizados persistentes en el protegido: {result['known_unauthorized_persistent_effects_one_profile']['protected']}.\n"
            f"Efectos persistentes del mutante conocido: {result['known_unauthorized_persistent_effects_one_profile']['missing_auth_guard']}.\n\n"
            'Se ejecutaron dos identidades FIJAS sobre contratos PROPIOS. '
            'No hay hallazgo externo, permisos reales, dinero, RPC o envío de reportes.\n'
            'El replay usa los mismos solc y Geth, no otro compilador/EVM.\n').encode()


def _audit(result: dict, at: str) -> bytes:
    log=load_components().audit.AuditLog(clock=lambda:at)
    log.append('owned.access.start',{'source_digest':result['source_digest'],
              'solc_sha256':result['solc_sha256'],'evm_sha256':result['evm_sha256']})
    for variant in VARIANTS:
        for codegen in CODEGEN:
            for row in result['cases'][variant][codegen]:
                log.append('owned.access.case',{'variant':variant,'codegen':codegen,
                     'case':row['case'],'case_sha256':sha(canonical(row))})
    log.append('owned.access.complete',{'result_sha256':sha(canonical(result))})
    log.assert_intact()
    return canonical({'entries':[asdict(e) for e in log.entries],
                      'producer_authenticated':False})


def create(out: Path, solc: Path, evm_binary: Path, expected_source: str) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent),'OUTPUT_DIRECTORY_NOT_NEW')
    result=execute(solc,evm_binary,expected_source)
    at=datetime.now(timezone.utc).isoformat()
    write_new_bundle(out,{'execution.json':canonical(result),
                  'audit.json':_audit(result,at),'REVIEW.md':render(result)})
    return {'status':'OWNED_ACCESS_EVM_CREATED','native_calls':result['native_runtime_calls'],
            'known_effects':result['known_unauthorized_persistent_effects_one_profile']}


def replay(root: Path, solc: Path, evm_binary: Path, expected_source: str) -> dict:
    need(root.is_dir() and not root.is_symlink(),'EVIDENCE_DIR_REQUIRED')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version']==1 and
         type(marker['sha256']) is dict and set(marker['sha256'])==FILES,'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()} == FILES|{'COMPLETE.json'},'BUNDLE_FILES')
    original={name:read_artifact(root,name) for name in FILES}
    need(all(sha(original[name])==marker['sha256'][name] for name in FILES),'BUNDLE_HASH')
    saved=strict_json(original['execution.json'])
    need(saved.get('source_digest')==expected_source,'WRONG_EXTERNAL_CODE_REFERENCE')
    actual=execute(solc,evm_binary,expected_source)
    need(original['execution.json']==canonical(actual),'ACCESS_NATIVE_REPLAY_DISAGREEMENT')
    audit=strict_json(original['audit.json'])
    need(type(audit) is dict and type(audit.get('entries')) is list and audit['entries'],
         'AUDIT_MISSING')
    timestamp=audit['entries'][0].get('timestamp')
    need(type(timestamp) is str and datetime.fromisoformat(timestamp).tzinfo is not None,
         'AUDIT_TIME')
    need(original['audit.json']==_audit(actual,timestamp) and
         original['REVIEW.md']==render(actual),'AUDIT_OR_REPORT_MISMATCH')
    return {'status':'OWNED_ACCESS_EVM_REPLAY_VERIFIED','native_calls':actual['native_runtime_calls'],
            'known_effects':actual['known_unauthorized_persistent_effects_one_profile']}


def main(argv: list[str] | None = None) -> int:
    parser=PrivateArgumentParser(description='Two FIXED caller identities, owned Solidity controls only')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run-owned-access-lab');check=sub.add_parser('verify-owned-access-lab')
    for p in (run,check):
        p.add_argument('--solc',type=Path,required=True)
        p.add_argument('--evm',type=Path,required=True)
        p.add_argument('--source-digest',required=True)
    run.add_argument('--out',type=Path,required=True)
    check.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=(create(args.out,args.solc,args.evm,args.source_digest) if
                args.command=='run-owned-access-lab' else
                replay(args.bundle,args.solc,args.evm,args.source_digest))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,OverflowError,RecursionError):
        print(json.dumps({'status':'OWNED_ACCESS_EVM_BLOCKED','vulnerability_confirmed':False}))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
