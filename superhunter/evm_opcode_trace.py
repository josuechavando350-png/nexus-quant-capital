"""Real EVM PC/opcode and JUMPI-outcome observations on OWNED fixed controls.

Each report requires replay of the complete earlier sequence-fuzz evidence
and fresh pinned-Geth traces on selected observed cases. It proves only which
instructions/edges were OBSERVED on a bounded subset, never total branch
coverage, reachable-code completeness, exploitability or unknown vulnerabilities.
Nothing evaluates remote programs, deploys, broadcasts or accepts their bytecode.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

from . import evm_execution as evm, evm_feedback as feedback
from . import evm_sequence_fuzz as fuzz, native_compile as compiler, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'pinned-owned-evm-pc-branch-observations-v1'
FILES = {'opcode-observations.json', 'source-binding.json', 'audit.json', 'REVIEW.md'}
MAX_TRACE_BYTES = 2_000_000
MAX_STEPS = 20_000
TRACE_KEYS = {'pc','op','gas','gasCost','memSize','stack','depth','refund','opName'}
EXIT_OPS = {0x00,0xf3,0xfd,0xfe,0xff}


class OpcodeTraceError(ValueError):
    """Fixed diagnostics avoid echoing source, policy, or path data."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise OpcodeTraceError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hex_number(value: object) -> int:
    need(type(value) is str and re.fullmatch(r'0x[0-9a-f]+',value) is not None,
         'NONCANONICAL_TRACE_NUMBER')
    return int(value[2:],16)


def instruction_positions(bytecode: str) -> dict[int,int]:
    """Decode PUSH immediates so a data byte can never masquerade as an opcode."""
    need(type(bytecode) is str and 0 < len(bytecode) <= 64000 and len(bytecode)%2 == 0 and
         re.fullmatch('[0-9a-f]+',bytecode) is not None,'CODE_HEX')
    raw=bytes.fromhex(bytecode)
    offsets={}
    pc=0
    while pc < len(raw):
        op=raw[pc]
        offsets[pc]=op
        pc += 1 + (op-0x5f if 0x60 <= op <= 0x7f else 0)
    return offsets


def _line(raw: str) -> dict:
    def unique(pairs):
        result={}
        for k,v in pairs:
            need(k not in result,'DUPLICATE_TRACE_KEY')
            result[k]=v
        return result
    def disallow_constant(_):
        raise OpcodeTraceError('NONFINITE_TRACE_JSON')
    try:
        return json.loads(raw,object_pairs_hook=unique,parse_constant=disallow_constant)
    except (ValueError,TypeError,RecursionError) as exc:
        raise OpcodeTraceError('TRACE_JSON') from exc


def decode_trace(raw: bytes, bytecode: str, observed: dict, *, budget: int,
                 creation_mode: bool = False) -> dict:
    """Strictly bind real Geth JSON traces to their EVM bytecode and final output.

    The EVM logs the last faulting opcode twice on some failures. A duplicate
    fault row is accepted ONLY if every original field matches the prior row.
    """
    need(type(raw) is bytes and 0 < len(raw) <= MAX_TRACE_BYTES,'TRACE_SIZE')
    need(type(budget) is int and budget in (evm.GAS,1),'GAS_PROFILE')
    code=instruction_positions(bytecode)
    try:
        rows=raw.decode('utf-8',errors='strict').splitlines()
    except UnicodeError as exc:
        raise OpcodeTraceError('TRACE_NOT_UTF8') from exc
    need(2 <= len(rows) <= MAX_STEPS+2,'TRACE_ROW_LIMIT')
    terminal=_line(rows[-1])
    need(type(terminal) is dict and set(terminal) in ({'output','gasUsed'}, {'output','gasUsed','error'})
         and type(terminal['output']) is str and
         re.fullmatch('[0-9a-f]*',terminal['output']) is not None and
         len(terminal['output'])%2 == 0,'TRACE_TERMINAL')
    gas_used=_hex_number(terminal['gasUsed'])
    expected_output = (observed.get('alloc',{}).get(evm.RECEIVER,{}).get('code')
                       if creation_mode and terminal.get('error') is None else
                       observed.get('return_data'))
    need(gas_used<=budget and expected_output=='0x'+terminal['output'] and
         observed.get('error')==terminal.get('error'),'TRACE_TERMINAL_DISAGREEMENT')
    steps=[]; faults=0
    for text in rows[:-1]:
        item=_line(text)
        need(type(item) is dict and set(item) in (TRACE_KEYS,TRACE_KEYS|{'error'}),
             'TRACE_STEP_SCHEMA')
        pc,op=item['pc'],item['op']
        need(type(pc) is int and type(op) is int and code.get(pc)==op and
             type(item['depth']) is int and item['depth']==1 and
             type(item['memSize']) is int and 0<=item['memSize']<MAX_TRACE_BYTES and
             item['stack'] is None and type(item['refund']) is int and item['refund']>=0 and
             type(item['opName']) is str and re.fullmatch(r'[A-Z0-9_]+',item['opName']) is not None,
             'TRACE_OPCODE_OR_PC_MISMATCH')
        gas,charge=_hex_number(item['gas']),_hex_number(item['gasCost'])
        need(gas<=budget and charge<2**64 and
             (not steps or gas<=steps[-1]['gas_before']), 'TRACE_GAS_PROFILE')
        step={'pc':pc,'op':op,'name':item['opName'],'gas_before':gas,'gas_cost':charge}
        if 'error' in item:
            need(faults==0 and type(item['error']) is str and
                 0 < len(item['error'])<=128 and
                 terminal.get('error')==item['error'], 'TRACE_FAULT_DISAGREEMENT')
            faults += 1
            if steps and all(item[key]==rows_prev[key] for key in TRACE_KEYS):
                # Duplicate Geth fault line, not another EVM step.
                continue
        else:
            need(faults==0,'STEP_AFTER_FAULT')
        steps.append(step)
        rows_prev={k:item[k] for k in TRACE_KEYS}
    need(bool(steps),'EMPTY_TRACE')
    transitions=[]; conditional=[]
    for left,right in zip(steps,steps[1:]):
        pc,op=left['pc'],left['op']
        next_pc=pc + 1+(op-0x5f if 0x60<=op<=0x7f else 0)
        if op in EXIT_OPS:
            raise OpcodeTraceError('STEP_AFTER_TERMINATOR')
        if op in (0x56,0x57):
            jumped_to_other_pc=right['pc']!=next_pc
            if jumped_to_other_pc:
                need(code.get(right['pc'])==0x5b,'JUMP_NOT_TO_JUMPDEST')
            elif op==0x56:
                # A JUMP to the immediately following JUMPDEST is legal.
                # PC equality alone cannot prove that JUMP did not execute.
                need(code.get(next_pc)==0x5b,'UNCONDITIONAL_JUMP_NOT_TO_JUMPDEST')
            if op==0x57:
                # Without stack values the successor PC cannot distinguish a
                # taken jump to the immediately following JUMPDEST from an
                # untaken conditional. Preserve this as UNKNOWN, not false.
                outcome=('taken' if jumped_to_other_pc else
                         'indeterminate' if code.get(next_pc)==0x5b else
                         'fallthrough')
                conditional.append({'pc':pc,'outcome':outcome})
        else:
            need(right['pc']==next_pc,'NON_JUMP_PC_DISCONTINUITY')
        transitions.append({'from_pc':pc,'to_pc':right['pc']})
    return {
        'trace_raw_sha256':sha(raw),
        'steps':len(steps),
        'instruction_sites':sorted({s['pc'] for s in steps}),
        'opcode_counts':dict(sorted(Counter(s['name'] for s in steps).items())),
        'pc_opcode_sha256':sha(canonical([(s['pc'],s['op']) for s in steps])),
        'observed_conditional_branches':conditional,
        'conditional_edge_set':sorted({f"{c['pc']}:{c['outcome']}" for c in conditional}),
        'jump_transitions_sha256':sha(canonical(transitions)),
        'gas_used':gas_used,
        'terminal_error':terminal.get('error'),
        'terminal_output':terminal['output'],
        'syntactic_instruction_site_count_in_bytecode':len(code),
        'all_reachable_sites_enumerated':False,
    }


def _run_traced(image: bytes, *, prestate: dict, creation: str | None = None,
                calldata: str = '', gas: int = evm.GAS, bytecode: str) -> dict:
    """Execute actual pinned EVM with --trace, compare trace and state dump.

    Called only with freshly compiled fixed contracts and generated inputs.
    """
    need(type(image) is bytes and sha(image)==evm.PIN['sha256'],'EVM_BINARY_HASH')
    need(type(gas) is int and gas in (1,evm.GAS) and
         prestate.get('gasLimit')==hex(gas),'GENESIS_GAS_DISAGREEMENT')
    mode='create' if creation is not None else 'call'
    need((mode=='create' and type(creation) is str and creation==bytecode and
          0<len(creation)<=64000 and re.fullmatch('[0-9a-f]+',creation) is not None and len(creation)%2==0) or
         (mode=='call' and type(calldata) is str and re.fullmatch('[0-9a-f]{72}',calldata) is not None),
         'EVM_TRACE_CALL_PROFILE')
    with compiler._sealed_executable(image) as fd, tempfile.TemporaryDirectory(prefix='sh-evm-pcs-') as tmp:
        directory=Path(tmp)
        (directory/'prestate.json').write_bytes(canonical(prestate))
        if creation is not None:
            (directory/'creation.hex').write_text(creation)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            command=[sys.executable,'-I','-B',str(ROOT/'evm_trace_worker.py'),mode,str(fd),
                     '-' if mode=='create' else calldata,str(gas)]
            proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout_file,stderr=stderr_file,
                                   cwd=directory,env={'LANG':'C','LC_ALL':'C'},pass_fds=(fd,),
                                   start_new_session=True)
            try:
                rc=proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
                raise OpcodeTraceError('EVM_TRACE_TIMEOUT') from None
            need(stdout_file.seek(0,os.SEEK_END)<2_000_000 and
                 stderr_file.seek(0,os.SEEK_END)<=MAX_TRACE_BYTES,'EVM_TRACE_OUTPUT_LIMIT')
            stdout_file.seek(0);stderr_file.seek(0)
            stdout,stderr=stdout_file.read(),stderr_file.read()
            need(rc==0,'EVM_TRACE_PROCESS_FAILED')
    # With --trace Geth moves returned data to the stderr trace's terminal
    # record and writes only its state dump to stdout. Independently rerun
    # the identical pinned execution WITHOUT tracing; its stdout is the same
    # representation committed by the existing native-fuzz evidence.
    traced_state=evm.parse_run(stdout)
    untraced=evm._run(image,prestate=prestate,creation=creation,
                      calldata=calldata,gas=gas)
    state=untraced['observed']
    # Geth --trace places revert/error details in the trace terminal on
    # stderr, rather than the stdout tail. Compare the state dump here;
    # decode_trace below matches the terminal error/output to untraced.
    need(traced_state['state_root']==state['state_root'] and
         canonical(traced_state['alloc'])==canonical(state['alloc']),
         'TRACE_STATE_VS_UNTRACED_DISAGREEMENT')
    trace=decode_trace(stderr,bytecode,state,budget=gas,creation_mode=(mode=='create'))
    return {'observed':state,'stdout_sha256':sha(untraced['stdout_utf8'].encode()),
            'traced_dump_sha256':sha(stdout), 'trace':trace,
            'prestate_sha256':sha(canonical(prestate))}


def _source_binding(native_root: Path, expected: str) -> dict:
    names=sorted(fuzz.FILES|{'COMPLETE.json'})
    return {'schema_version':1,'native_source_digest':expected,
            'native_artifact_sha256':{name:sha(read_artifact(native_root,name)) for name in names}}


def gather(native_root: Path, solc: Path, evm_binary: Path, expected: str,
           *, run_native_replay: bool = True) -> tuple[dict,dict]:
    """Reproduce complete original fuzzy run, then trace greedy-selected cases.

    The optional replay bypass is ONLY for testing pure orchestration. Public
    create/verify always set it to True. This is never a remote scanning API.
    """
    need(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None,
         'EXTERNAL_CODE_REFERENCE')
    before=quality.source_snapshot()
    need(sha(canonical(before))==expected,'SOURCE_SNAPSHOT_CHANGED')
    binding_before=_source_binding(native_root,expected)
    if run_native_replay:
        fuzz.replay(native_root,solc,evm_binary,expected)
    native_run=strict_json(read_artifact(native_root,'sequences.json'))
    need(native_run.get('source_digest')==expected,'NATIVE_SOURCE_REFERENCE_MISMATCH')
    chosen=feedback.features(native_run)
    selected=chosen['selected_indices']
    # The preceding pure reducer is not a code-coverage oracle. This run really
    # traces exactly the selected cases and labels every other case untraced.
    image_solc=compiler.read_pinned_binary(solc)
    image_evm=evm.read_evm(evm_binary)
    results={};totals=Counter();all_edges=set();all_pcs=0;ctor_count=0
    for name in fuzz.CONTROLS:
        initial,first=fuzz._compile(name,fuzz.PROFILES[0],image_solc,None)
        _,second=fuzz._compile(name,fuzz.PROFILES[1],image_solc,initial)
        results[name]={}
        for profile,parts in ((fuzz.PROFILES[0],first),(fuzz.PROFILES[1],second)):
            contract=parts['contract'];stored=native_run['controls'][name]
            build=stored['builds'][profile]
            need(build['creation_sha256']==parts['creation_sha256'] and
                 build['runtime_sha256']==parts['runtime_sha256'] and
                 build['source_sha256']==parts['summary']['source_sha256'],
                 'CODEGEN_FINGERPRINT_DISAGREEMENT')
            image=contract['evm']['bytecode']['object']
            runtime=contract['evm']['deployedBytecode']['object']
            birth=_run_traced(image_evm,prestate=evm.genesis(),creation=image,bytecode=image)
            reference=stored['profiles'][profile]
            need(birth['stdout_sha256']==reference['constructor_stdout_sha256'] and
                 birth['observed']['state_root']==reference['constructor_state_root'],
                 'TRACED_CONSTRUCTOR_DISAGREEMENT')
            initial_alloc=birth['observed']['alloc']
            need(evm.decode_state(initial_alloc,contract)=={'debit':15,'credit':0,'steps':0},
                 'CONSTRUCTOR_STORAGE')
            ctor_count+=1
            coverage=set();edges=set();per_case=[];statuses=Counter()
            for i in selected:
                current=deepcopy(initial_alloc)
                case=reference['runs'][i]
                for pos,(quantity,gas) in enumerate(native_run['sequences'][i]):
                    prestate=evm.genesis(current,gas=gas)
                    calldata=contract['evm']['methodIdentifiers']['move(uint8)']+format(quantity,'064x')
                    trace=_run_traced(image_evm,prestate=prestate,calldata=calldata,gas=gas,bytecode=runtime)
                    original=case['steps'][pos]
                    need(trace['stdout_sha256']==original['stdout_sha256'] and
                         trace['prestate_sha256']==original['prestate_sha256'] and
                         trace['observed']['state_root']==original['observed_state_root'] and
                         trace['observed']['error']==original['error'] and
                         trace['observed']['return_data']==original['return_data'] and
                         evm.decode_state(trace['observed']['alloc'],contract)==original['state_after'],
                         'TRACE_VS_UNTRACED_NATIVE_DISAGREEMENT')
                    coverage.update(trace['trace']['instruction_sites'])
                    edges.update(trace['trace']['conditional_edge_set'])
                    statuses[original['outcome']]+=1
                    per_case.append({'case_index':i,'step_index':pos,
                                     'sequence_sha256':case['sequence_sha256'],
                                     'outcome':original['outcome'],
                                     'stdout_sha256':trace['stdout_sha256'],
                                     'trace':trace['trace']})
                    current=trace['observed']['alloc']
            all_edges.update(f'{name}|{profile}|{edge}' for edge in edges)
            all_pcs += len(coverage)
            totals.update(statuses)
            results[name][profile]={
                'runtime_sha256':sha(bytes.fromhex(runtime)),
                'creation_sha256':sha(bytes.fromhex(image)),
                'creation_trace':birth['trace'],
                'syntactic_runtime_instruction_positions':len(instruction_positions(runtime)),
                'observed_unique_runtime_pcs':sorted(coverage),
                'observed_conditional_edges':sorted(edges),
                'traced_calls':len(per_case),
                'outcomes':dict(sorted(statuses.items())),
                'observations':per_case}
    need(binding_before==_source_binding(native_root,expected) and
         before==quality.source_snapshot(),'INPUT_CHANGED_DURING_TRACE')
    report={'schema_version':1,'profile':PROFILE,'status':'OWNED_EVM_OPCODE_TRACES_RECORDED',
            'source_digest':expected,'native_source_run_sha256':sha(canonical(native_run)),
            'case_count_available':native_run['cases_per_control'],
            'case_indices_traced':selected,
            'cases_not_traced':[i for i in range(native_run['cases_per_control']) if i not in selected],
            'trace_selection_basis':'observable-feature-greedy-not-code-coverage-guided',
            'controls':list(fuzz.CONTROLS),'codegen_profiles':list(fuzz.PROFILES),
            'constructor_traces':ctor_count,
            'traced_runtime_calls':sum(totals.values()),
            'traced_runtime_unique_pcs_summed_per_control_profile':all_pcs,
            'observed_conditional_edges_across_profiles':len(all_edges),
            'runtime_outcomes':dict(sorted(totals.items())),'trace_groups':results,
            'verified_against_untraced_genuine_evm_output':True,
            'pc_and_jumpi_edge_observations_measured':True,
            'complete_instruction_or_branch_coverage_proven':False,
            'all_possible_paths_enumerated':False,
            'unseen_vulnerabilities_found':False,
            'vulnerability_confirmed':False,'externally_authorized_targets_executed':False,
            'second_evm_implementation_used':False}
    need(len(canonical(report))<=2_000_000,'REPORT_SIZE')
    return report,binding_before


def _audit(report: dict, binding: dict, created: str) -> bytes:
    log=load_components().audit.AuditLog(clock=lambda:created)
    log.append('evm.opcodes.begin',{'source_binding_sha256':sha(canonical(binding))})
    for name,group in report['trace_groups'].items():
        for profile,details in group.items():
            log.append('evm.opcodes.profile',{'name':name,'profile':profile,
                                             'details_sha256':sha(canonical(details))})
    log.append('evm.opcodes.finish',{'report_sha256':sha(canonical(report))})
    log.assert_intact()
    return canonical({'created_at':created,'entries':[asdict(e) for e in log.entries],
                      'producer_authenticated':False})


def _render(report: dict) -> bytes:
    return ('# Cobertura de PCs y resultados de JUMPI observados en Geth\n\n'
            f"Estado: {report['status']}; constructor traces: {report['constructor_traces']}.\n"
            f"Secuencias trazadas: {len(report['case_indices_traced'])} de {report['case_count_available']}.\n"
            f"Llamadas EVM trazadas: {report['traced_runtime_calls']}.\n"
            f"Total de PCs únicos por pareja contrato/configuración: "
            f"{report['traced_runtime_unique_pcs_summed_per_control_profile']}.\n"
            f"Aristas condicionales observadas por pareja: "
            f"{report['observed_conditional_edges_across_profiles']}.\n\n"
            'PCs y aristas indican ejecución observada SOLO en las secuencias seleccionadas.\n'
            'El total de instrucciones decodificadas incluye datos potencialmente inaccesibles.\n'
            'No se infiere cobertura porcentual del espacio alcanzable ni del bytecode completo.\n'
            'No se utilizó cobertura para dirigir el corpus existente; se midió después.\n'
            'Contratos propios, sin programas externos, hallazgos desconocidos ni fondos.\n'
            'Una reversión no representa pérdidas persistentes.\n').encode()


def create(native_root: Path, solc: Path, evm_binary: Path, expected: str, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent) and
         not out.resolve().is_relative_to(native_root.resolve()), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    report,binding=gather(native_root,solc,evm_binary,expected)
    created=datetime.now(timezone.utc).isoformat()
    files={'opcode-observations.json':canonical(report),'source-binding.json':canonical(binding),
           'audit.json':_audit(report,binding,created),'REVIEW.md':_render(report)}
    write_new_bundle(out,files)
    return {'status':'OWNED_EVM_OPCODE_TRACES_CREATED',
            'traced_calls':report['traced_runtime_calls'],
            'observed_pc_sites':report['traced_runtime_unique_pcs_summed_per_control_profile'],
            'vulnerability_confirmed':False}


def verify(root: Path, native_root: Path, solc: Path, evm_binary: Path, expected: str) -> dict:
    need(not root.is_symlink() and root.is_dir(),'BUNDLE_ROOT')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version']==1 and
         type(marker['sha256']) is dict and set(marker['sha256'])==FILES and
         {p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_INVENTORY')
    existing={name:read_artifact(root,name) for name in FILES}
    need(all(sha(existing[name])==marker['sha256'][name] for name in FILES),'BUNDLE_HASH')
    saved_audit=strict_json(existing['audit.json'])
    created=saved_audit.get('created_at')
    need(type(created) is str and len(created)<=40,'AUDIT_TIME')
    try:
        value=datetime.fromisoformat(created)
        need(value.tzinfo is not None,'AUDIT_TIMEZONE')
    except (ValueError,TypeError) as exc:
        raise OpcodeTraceError('AUDIT_TIME') from exc
    report,binding=gather(native_root,solc,evm_binary,expected)
    need(existing['opcode-observations.json']==canonical(report) and
         existing['source-binding.json']==canonical(binding) and
         existing['audit.json']==_audit(report,binding,created) and
         existing['REVIEW.md']==_render(report),'OPCODE_REPLAY_DISAGREEMENT')
    need(all(read_artifact(root,name)==existing[name] for name in FILES),'BUNDLE_CHANGED')
    return {'status':'OWNED_EVM_OPCODE_TRACES_REPLAY_VERIFIED',
            'traced_calls':report['traced_runtime_calls'],
            'observed_pc_sites':report['traced_runtime_unique_pcs_summed_per_control_profile'],
            'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser=PrivateArgumentParser(description='Measure genuine EVM opcode/PC traces on local fixed owned contracts')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('review-opcode-traces','verify-opcode-traces'):
        q=sub.add_parser(name)
        q.add_argument('--native-bundle',type=Path,required=True)
        q.add_argument('--solc',type=Path,required=True)
        q.add_argument('--evm',type=Path,required=True)
        q.add_argument('--expected-source',required=True)
        q.add_argument('--out' if name=='review-opcode-traces' else '--bundle',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=(create(args.native_bundle,args.solc,args.evm,args.expected_source,args.out)
                if args.command=='review-opcode-traces' else
                verify(args.bundle,args.native_bundle,args.solc,args.evm,args.expected_source))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,OverflowError,RecursionError):
        print(json.dumps({'status':'OWNED_EVM_OPCODE_TRACES_BLOCKED',
                          'vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
