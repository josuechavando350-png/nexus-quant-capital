"""Defensive invariant review of fixed OWNED quota-ledger observations.

The detector accepts observations, never a variant or truth label. Known source
mutations evaluate that detector; two compiler outputs remain one grouped case.
Only fixed local contracts run. No arbitrary source, network or signing API.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from . import benchmark, evm_execution as evm, native_compile as compiler, quality
from . import owned_quota_cases as cases, owned_process
from . import owned_quota_execution as quota_execution
from .owned_quota_cases import need, sha
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'owned-quota-invariants-cancun-v1'
FILES = {'execution.json','evaluation.json','REVIEW.md'}
WALL_SECONDS, OUTPUT_LIMIT = 180, 4*1024**2
TRUTH = {'correct':'negative','reconciled':'negative','quota_not_charged':'positive',
         'strict_boundary':'positive','double_debit':'positive','extra_credit':'positive'}
POLICIES = ('full','status_only','state_only')


def _state(value: dict) -> None:
    need(type(value) is dict and set(value) == set(cases.INITIAL) and
         all(type(v) is int and 0 <= v <= 65535 for v in value.values()),'QUOTA_STATE')


def detect(call: dict, policy: str = 'full') -> dict:
    """Observe status and unit changes; neither labels nor variant IDs are read."""
    need(type(policy) is str and policy in POLICIES,'QUOTA_POLICY')
    need(type(call) is dict and set(call) ==
         {'before','after','amount','gas','status','return_data'},'QUOTA_OBSERVATION')
    before,after = call['before'],call['after']; _state(before); _state(after)
    amount,gas,status = call['amount'],call['gas'],call['status']
    need(type(amount) is int and 0 <= amount <= 255 and type(gas) is int and
         gas in (1,evm.GAS) and type(status) is str and
         status in ('COMMITTED','REVERTED','OUT_OF_GAS') and call['return_data'] == '0x',
         'QUOTA_CALL_PROFILE')
    if status != 'COMMITTED':
        need(before == after,'QUOTA_FAILED_CALL_CHANGED_STATE')
    expected = ('OUT_OF_GAS' if gas == 1 else
                'REVERTED' if amount > min(before['quota'],before['remaining']) else 'COMMITTED')
    status_reasons,state_reasons = [],[]
    if status != expected:
        status_reasons.append('VALID_REQUEST_REJECTED' if expected == 'COMMITTED'
                              else 'INVALID_REQUEST_COMMITTED' if status == 'COMMITTED'
                              else 'UNEXPECTED_EXECUTION_STATUS')
    if status == 'COMMITTED':
        for field,wanted,code in (
            ('quota',before['quota']-amount,'QUOTA_DEBIT_MISMATCH'),
            ('remaining',before['remaining']-amount,'BALANCE_DEBIT_MISMATCH'),
            ('distributed',before['distributed']+amount,'DISTRIBUTION_CREDIT_MISMATCH')):
            if after[field] != wanted:
                state_reasons.append(code)
        if before['remaining']+before['distributed'] != after['remaining']+after['distributed']:
            state_reasons.append('TOTAL_UNITS_CHANGED')
    reasons = ((status_reasons if policy != 'state_only' else []) +
               (state_reasons if policy != 'status_only' else []))
    return {'decision':'positive' if reasons else 'negative','reasons':reasons}


def execute_native(solc: Path, geth: Path, digest: str, sealed_geth_fd: int | None = None) -> dict:
    need(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest),'QUOTA_SOURCE_REFERENCE')
    snapshot = quality.source_snapshot()
    need(sha(canonical(snapshot)) == digest,'QUOTA_SOURCE_CHANGED')
    solc_image,geth_image = compiler.read_pinned_binary(solc),evm.read_evm(geth)
    builds,rows = [],[]
    for variant in cases.VARIANTS:
        for codegen in cases.CODEGEN:
            built = cases.compile_owned(solc_image,variant,codegen)
            contract = built['contract']
            birth = quota_execution.run(geth_image,prestate=evm.genesis(),sealed_fd=sealed_geth_fd,
                            creation=contract['evm']['bytecode']['object'])['observed']
            need(birth['error'] is None and birth['return_data'] ==
                 '0x'+contract['evm']['deployedBytecode']['object'] and
                 cases.decode(birth['alloc'],contract) == cases.INITIAL,'QUOTA_CONSTRUCTOR')
            builds.append({**built['record'],'initial_state':dict(cases.INITIAL)})
            for scenario,sequence in enumerate(cases.SEQUENCES):
                alloc = deepcopy(birth['alloc'])
                for step,(amount,gas) in enumerate(sequence):
                    before = cases.decode(alloc,contract)
                    result = quota_execution.run(geth_image,prestate=evm.genesis(alloc,gas=gas),gas=gas,
                        sealed_fd=sealed_geth_fd,
                        calldata=contract['evm']['methodIdentifiers']['release(uint8)']+format(amount,'064x'))
                    actual = result['observed']
                    need(actual['error'] in (None,'execution reverted','out of gas'),
                         'QUOTA_UNEXPECTED_EVM_ERROR')
                    status = {None:'COMMITTED','execution reverted':'REVERTED',
                              'out of gas':'OUT_OF_GAS'}[actual['error']]
                    if status != 'COMMITTED':
                        need(canonical(alloc) == canonical(actual['alloc']),'QUOTA_REVERT_PERSISTED')
                    rows.append({'variant':variant,'codegen':codegen,'scenario':scenario,'step':step,
                        'observation':{'before':before,'after':cases.decode(actual['alloc'],contract),
                        'amount':amount,'gas':gas,'status':status,'return_data':actual['return_data']},
                        'state_root':actual['state_root'],'stdout_sha256':sha(result['stdout_utf8'].encode())})
                    alloc = actual['alloc']
    need(quality.source_snapshot() == snapshot,'QUOTA_SOURCE_CHANGED_DURING_EXECUTION')
    return {'schema_version':1,'profile':PROFILE,'source_digest':digest,'fork':'Cancun',
        'solc_sha256':sha(solc_image),'geth_sha256':sha(geth_image),
        'builds':builds,'rows':rows,'constructor_executions':len(builds),'runtime_calls':len(rows)}


def analyze(execution: dict, digest: str) -> dict:
    need(type(execution) is dict and set(execution) == {'schema_version','profile','source_digest',
         'fork','solc_sha256','geth_sha256','builds','rows','constructor_executions','runtime_calls'},
         'QUOTA_EXECUTION_SCHEMA')
    need(type(execution['schema_version']) is int and execution['schema_version'] == 1 and
         execution['profile'] == PROFILE and execution['source_digest'] == digest and
         type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest) and execution['fork'] == 'Cancun',
         'QUOTA_EXECUTION_IDENTITY')
    for name in ('solc_sha256','geth_sha256'):
        need(type(execution[name]) is str and re.fullmatch('[0-9a-f]{64}',execution[name]),'QUOTA_TOOL_HASH')
    expected = [(v,c,s,t) for v in cases.VARIANTS for c in cases.CODEGEN
                for s,seq in enumerate(cases.SEQUENCES) for t in range(len(seq))]
    rows,builds = execution['rows'],execution['builds']
    need(type(rows) is list and type(builds) is list and len(rows) == len(expected) and
         type(execution['runtime_calls']) is int and execution['runtime_calls'] == len(expected) and
         type(execution['constructor_executions']) is int and
         execution['constructor_executions'] == len(builds) == 12,'QUOTA_COVERAGE')
    for built,(variant,codegen) in zip(builds,[(v,c) for v in cases.VARIANTS for c in cases.CODEGEN]):
        need(type(built) is dict and set(built) == {'variant','codegen','source_sha256','input_sha256',
             'output_sha256','creation_sha256','runtime_sha256','initial_state'} and
             built['variant'] == variant and built['codegen'] == codegen and
             canonical(built['initial_state']) == canonical(cases.INITIAL) and
             built['source_sha256'] == sha(cases.owned_source(variant).encode()) and
             built['input_sha256'] == sha(canonical(cases.compile_input(variant,codegen))),
             'QUOTA_BUILD_IDENTITY')
        need(all(type(built[k]) is str and re.fullmatch('[0-9a-f]{64}',built[k])
                 for k in ('output_sha256','creation_sha256','runtime_sha256')),'QUOTA_BUILD_HASH')
    observed = {v:{c:[] for c in cases.CODEGEN} for v in cases.VARIANTS}
    previous = None
    for row,(variant,codegen,scenario,step) in zip(rows,expected):
        need(type(row) is dict and set(row) == {'variant','codegen','scenario','step','observation',
             'state_root','stdout_sha256'} and row['variant'] == variant and row['codegen'] == codegen and
             type(row['scenario']) is int and row['scenario'] == scenario and
             type(row['step']) is int and row['step'] == step,'QUOTA_ROW_ORDER')
        call = row['observation']; detect(call)
        need((call['amount'],call['gas']) == cases.SEQUENCES[scenario][step],'QUOTA_FIXED_INPUT')
        need(call['before'] == (cases.INITIAL if step == 0 else previous),'QUOTA_STATE_CHAIN')
        need(type(row['state_root']) is str and re.fullmatch('[0-9a-f]{64}',row['state_root']) and
             type(row['stdout_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['stdout_sha256']),
             'QUOTA_OBSERVATION_HASH')
        observed[variant][codegen].append(call)
        previous = call['after']
    decisions = {p:[] for p in POLICIES}; witnesses = []
    for variant in cases.VARIANTS:
        calls = observed[variant][cases.CODEGEN[0]]
        need(canonical(calls) == canonical(observed[variant][cases.CODEGEN[1]]),
             'QUOTA_CODEGEN_DISAGREEMENT')
        for policy in POLICIES:
            alarms = [detect(call,policy) for call in calls]
            decisions[policy].append({'case_id':variant,'decision':
                'positive' if any(a['decision'] == 'positive' for a in alarms) else 'negative'})
        witnesses.append({'case_id':variant,'violations':[
            {'observation_index':i,'reasons':detect(call)['reasons'],'sha256':sha(canonical(call))}
            for i,call in enumerate(calls) if detect(call)['decision'] == 'positive']})
    # Labels are applied only after all detector decisions have been computed.
    corpus = [{'case_id':v,'family':'quota-ledger','truth':TRUTH[v]} for v in cases.VARIANTS]
    metrics = {}
    for policy in POLICIES:
        pairs = list(zip(corpus,decisions[policy]))
        score = benchmark._section(pairs)
        need(score['counts'] == benchmark._reference_counts(pairs),'QUOTA_COUNTER_DISAGREEMENT')
        metrics[policy] = score
    return {'schema_version':1,'status':'OWNED_QUOTA_EVALUATED','profile':PROFILE,
        'source_digest':digest,'case_count':6,'family':'quota-ledger','compiler_runs_per_case':2,
        'constructor_executions':12,'runtime_calls':len(rows),'predictions':decisions,
        'metrics':metrics,'witnesses':witnesses,'corpus':corpus,
        'known_seeded_defects':4,'known_correct_controls':2,'labels_known_to_developers':True,
        'case_unit':'one-source-variant; compiler runs and calls are correlated observations',
        'detector_uses_variant_or_truth':False,'native_execution_regenerated_here':False,
        'blind_benchmark':False,'generalization_established':False,'vulnerability_confirmed':False}


def _run_worker(solc: Path, geth: Path, digest: str) -> dict:
    # Seal the 42 MB pinned executable before entering the child's 20 MiB
    # file-write budget. The child rechecks the exact immutable descriptor;
    # native execution output keeps its existing 2 MB child limit.
    with compiler._sealed_executable(evm.read_evm(geth)) as geth_fd, \
         tempfile.TemporaryDirectory(prefix='owned-quota-') as directory:
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            try:
                proc = owned_process.run([sys.executable,'-I','-B','-X',
                    'pycache_prefix='+str(Path(directory)/'cache'),str(ROOT/'owned_quota_worker.py'),
                    '--solc',str(solc.resolve()),'--evm',str(geth.resolve()),'--source-digest',digest,
                    '--geth-fd',str(geth_fd)],stdout=output,stderr=errors,cwd=directory,
                    pass_fds=(geth_fd,),timeout=WALL_SECONDS,
                    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':directory})
            except subprocess.TimeoutExpired:
                raise ValueError('QUOTA_WORKER_TIMEOUT') from None
            output.seek(0); errors.seek(0)
            raw,err = output.read(OUTPUT_LIMIT+1),errors.read(OUTPUT_LIMIT+1)
            need(proc.returncode == 0 and not err and 0 < len(raw) <= OUTPUT_LIMIT,'QUOTA_WORKER_FAILED')
            return strict_json(raw)


def _execute(solc: Path, geth: Path, digest: str) -> dict[str,bytes]:
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest,'QUOTA_SOURCE_CHANGED')
    execution = _run_worker(solc,geth,digest)
    report = analyze(execution,digest)
    need(quality.source_snapshot() == before,'QUOTA_SOURCE_CHANGED_DURING_REVIEW')
    review = ('# Evaluación defensiva de cuotas propias\n\n'
        'Seis variantes conocidas: dos controles correctos y cuatro defectos sembrados.\n'
        'Cada variante se compila de dos formas; las llamadas y compilaciones no son nuevas muestras.\n'
        'El detector observa estado, resultado y cantidad, sin recibir etiquetas o variantes.\n'
        'Se miden además dos ablaciones: solo resultado y solo estado.\n'
        'No es evaluación ciega, hallazgo original ni evidencia de generalización.\n'
        'Geth y solc son compartidos; el replay es otro proceso, no otro motor.\n').encode()
    return {'execution.json':canonical(execution),'evaluation.json':canonical(report),'REVIEW.md':review}


def create(out: Path, solc: Path, geth: Path, digest: str) -> dict:
    need(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.parent),
         'QUOTA_NEW_PRIVATE_OUTPUT_REQUIRED')
    files = _execute(solc,geth,digest)
    write_new_bundle(out,files)
    return {'status':'OWNED_QUOTA_CREATED','cases':6,'counts':strict_json(files['evaluation.json'])[
        'metrics']['full']['counts'],'vulnerability_confirmed':False}


def verify(root: Path, solc: Path, geth: Path, digest: str) -> dict:
    need(root.is_dir() and not root.is_symlink(),'QUOTA_BUNDLE_DIRECTORY')
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES and
         {p.name for p in root.iterdir()} == FILES|{'COMPLETE.json'},'QUOTA_BUNDLE_MANIFEST')
    files = {n:read_artifact(root,n) for n in FILES}
    need(all(sha(raw) == marker['sha256'][n] for n,raw in files.items()),'QUOTA_BUNDLE_HASH')
    need(strict_json(files['evaluation.json'])['source_digest'] == digest,'QUOTA_WRONG_CODE_REFERENCE')
    need(files == _execute(solc,geth,digest),'QUOTA_REPLAY_MISMATCH')
    return {'status':'OWNED_QUOTA_REPLAY_VERIFIED','cases':6,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Evaluate fixed owned quota-ledger controls only')
    subs = parser.add_subparsers(dest='command',required=True)
    make,check = subs.add_parser('evaluate-owned-quota'),subs.add_parser('verify-owned-quota')
    for p in (make,check):
        p.add_argument('--solc',type=Path,required=True); p.add_argument('--evm',type=Path,required=True)
        p.add_argument('--source-digest',required=True)
    make.add_argument('--out',type=Path,required=True); check.add_argument('--bundle',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        result = (create(args.out,args.solc,args.evm,args.source_digest) if
                  args.command == 'evaluate-owned-quota' else
                  verify(args.bundle,args.solc,args.evm,args.source_digest))
        print(json.dumps(result,sort_keys=True)); return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError,OverflowError):
        print(json.dumps({'status':'OWNED_QUOTA_BLOCKED','vulnerability_confirmed':False})); return 2
