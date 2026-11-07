"""Bounded two-implementation comparison of the six OWNED quota controls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from . import owned_quota_review as quota, owned_cross_evm as previous, quality
from .owned_quota_cases import need,sha
from .owned_quota_spec_worker import PROFILE
from .owned_spec_evm_pins import PINS
from .privacy import PrivateArgumentParser
from .safe_io import canonical,read_artifact,strict_json,write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = {'geth.json','eels.json','comparison.json','REVIEW.md'}
WALL_SECONDS,OUTPUT_LIMIT = 180,4*1024**2


def _run_eels(solc: Path, digest: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='owned-quota-eels-') as directory:
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen(previous._python_command(Path(directory)/'cache')+[
                str(ROOT/'owned_quota_spec_worker.py'),'--solc',str(solc.resolve()),
                '--source-digest',digest],stdin=subprocess.DEVNULL,stdout=output,stderr=errors,
                cwd=directory,start_new_session=True,
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':directory})
            try: proc.wait(timeout=WALL_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                raise ValueError('QUOTA_EELS_TIMEOUT') from None
            output.seek(0);errors.seek(0)
            raw,err = output.read(OUTPUT_LIMIT+1),errors.read(OUTPUT_LIMIT+1)
            need(proc.returncode == 0 and not err and 0 < len(raw) <= OUTPUT_LIMIT,
                 'QUOTA_EELS_WORKER_FAILED')
            result = strict_json(raw);need(type(result) is dict,'QUOTA_EELS_RESULT')
            return result


def compare(geth: dict,eels: dict,digest: str) -> dict:
    score = quota.analyze(geth,digest)
    need(geth['solc_sha256'] == quota.compiler.PIN['sha256'] and
         geth['geth_sha256'] == quota.evm.PIN['sha256'],'QUOTA_CROSS_TOOL_IDENTITY')
    dependencies = {name:{k:pin[k] for k in ('version','files','runtime_sha256')}
                    for name,pin in PINS.items()}
    need(type(eels) is dict and set(eels) == {'profile','source_digest','engine','fork',
        'solc_sha256','dependencies','builds','rows','constructor_executions','runtime_calls'},
        'QUOTA_CROSS_SCHEMA')
    need(eels['profile'] == PROFILE and eels['source_digest'] == digest and
         eels['engine'] == 'execution-specs' and eels['fork'] == 'Cancun' and
         eels['solc_sha256'] == geth['solc_sha256'] and
         canonical(eels['dependencies']) == canonical(dependencies),'QUOTA_CROSS_IDENTITY')
    need(type(eels['constructor_executions']) is int and eels['constructor_executions'] == 12 and
         type(eels['runtime_calls']) is int and eels['runtime_calls'] == 228,'QUOTA_CROSS_COVERAGE')
    rows = [{k:v for k,v in row.items() if k not in ('state_root','stdout_sha256')}
            for row in geth['rows']]
    need(canonical(eels['builds']) == canonical(geth['builds']),'QUOTA_CROSS_BUILD_MISMATCH')
    need(canonical(eels['rows']) == canonical(rows),'QUOTA_CROSS_SEMANTICS_MISMATCH')
    return {'schema_version':1,'status':'OWNED_QUOTA_CROSS_EVM_MATCH','profile':PROFILE,
        'source_digest':digest,'solc_sha256':geth['solc_sha256'],'geth_sha256':geth['geth_sha256'],
        'eels_dependencies':dependencies,'fork':'Cancun','implementation_count':2,
        'known_cases':6,'constructor_executions_per_engine':12,'runtime_calls_per_engine':228,
        'semantic_rows_sha256':sha(canonical(rows)),'builds_sha256':sha(canonical(geth['builds'])),
        'counts':score['metrics']['full']['counts'],'ablation_metrics':score['metrics'],
        'comparison_dimensions':['constructor_runtime','constructor_storage','call_status',
                                 'persisted_storage','return_data'],
        'distinct_evm_implementations_executed':True,'shared_compiler_and_inputs':True,
        'independent_producers_proved':False,'gas_costs_compared':False,
        'account_state_roots_compared':False,'blind_benchmark':False,
        'generalization_established':False,'all_evm_semantics_certified':False,
        'external_programs_executed':0,'vulnerability_confirmed':False}


def _execute(solc: Path,geth: Path,digest: str) -> dict[str,bytes]:
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest,'QUOTA_CROSS_SOURCE_CHANGED')
    first = quota._run_worker(solc,geth,digest);second = _run_eels(solc,digest)
    report = compare(first,second,digest)
    need(quality.source_snapshot() == before,'QUOTA_CROSS_SOURCE_CHANGED_DURING_RUN')
    review = ('# Cuotas propias: Geth y EELS\n\n'
        'Seis variantes conocidas, dos controles correctos y cuatro defectos sembrados.\n'
        'Doce constructores y 228 llamadas por implementación, dos compilaciones por caso.\n'
        'Se comparan bytecode construido, estado inicial, estado persistido, resultado y retorno.\n'
        'Los motores comparten compilador, fuentes, entradas, host y detector.\n'
        'No se comparan costes de gas ni raíces de cuentas; no se certifica toda la EVM.\n'
        'Los mismos seis casos se corroboran: no son doce casos ni un benchmark ciego.\n'
        'Sin programas externos, vulnerabilidades nuevas ni recompensas estimadas.\n').encode()
    return {'geth.json':canonical(first),'eels.json':canonical(second),
            'comparison.json':canonical(report),'REVIEW.md':review}


def create(out: Path,solc: Path,geth: Path,digest: str) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent),'QUOTA_CROSS_NEW_PRIVATE_OUTPUT')
    write_new_bundle(out,_execute(solc,geth,digest))
    return {'status':'OWNED_QUOTA_CROSS_EVM_CREATED','cases':6,'runtime_calls_per_engine':228,
            'vulnerability_confirmed':False}


def verify(root: Path,solc: Path,geth: Path,digest: str) -> dict:
    need(root.is_dir() and not root.is_symlink(),'QUOTA_CROSS_BUNDLE_DIRECTORY')
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES and
         {p.name for p in root.iterdir()} == FILES|{'COMPLETE.json'},'QUOTA_CROSS_MANIFEST')
    files = {n:read_artifact(root,n) for n in FILES}
    need(all(sha(raw) == marker['sha256'][n] for n,raw in files.items()),'QUOTA_CROSS_BUNDLE_HASH')
    report = strict_json(files['comparison.json'])
    need(type(report) is dict and report.get('source_digest') == digest,'QUOTA_CROSS_EXTERNAL_SOURCE')
    need(files == _execute(solc,geth,digest),'QUOTA_CROSS_REPLAY_MISMATCH')
    return {'status':'OWNED_QUOTA_CROSS_EVM_REPLAY_VERIFIED','cases':6,
            'runtime_calls_per_engine':228,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Compare six fixed own quota cases in Geth and EELS')
    subs = parser.add_subparsers(dest='command',required=True)
    make = subs.add_parser('compare-owned-quota-engines');check = subs.add_parser('verify-owned-quota-engines')
    for p in (make,check):
        p.add_argument('--solc',type=Path,required=True);p.add_argument('--evm',type=Path,required=True)
        p.add_argument('--source-digest',required=True)
    make.add_argument('--out',type=Path,required=True);check.add_argument('--bundle',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        result = (create(args.out,args.solc,args.evm,args.source_digest)
                  if args.command == 'compare-owned-quota-engines' else
                  verify(args.bundle,args.solc,args.evm,args.source_digest))
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError,OverflowError):
        print(json.dumps({'status':'OWNED_QUOTA_CROSS_EVM_BLOCKED','vulnerability_confirmed':False}));return 2


if __name__ == '__main__':
    raise SystemExit(main())
