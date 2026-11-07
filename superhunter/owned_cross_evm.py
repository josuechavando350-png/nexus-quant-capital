"""Compare fixed OWNED Cancun controls across Geth and py-evm implementations.

Shared compiler/source/host: this is bounded execution corroboration, not
independent producers, a blind benchmark, a scanner or a vulnerability claim.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from . import owned_mutation_evaluation as score, quality
from . import evm_pause_family as pause, evm_access_family as access
from .owned_cross_evm_pins import PINS
from .owned_cross_evm_worker import PROFILE
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = {'geth-pause.json', 'geth-access.json', 'python.json', 'comparison.json', 'REVIEW.md'}
WALL_SECONDS = 180
OUTPUT_LIMIT = 4*1024**2


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _python_command(fresh_cache: Path) -> list[str]:
    # -B prevents cache writes, not reads. A fresh private prefix prevents an
    # old bytecode cache from replacing the source bytes checked by the worker.
    return [sys.executable, '-I', '-B', '-X', 'pycache_prefix=' + str(fresh_cache)]


def _run_python(solc: Path, digest: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='owned-second-evm-') as directory:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen(_python_command(Path(directory)/'bytecode') + [
                str(ROOT/'owned_cross_evm_worker.py'), '--solc', str(solc.resolve()),
                '--source-digest', digest], stdin=subprocess.DEVNULL, stdout=output,
                stderr=errors, cwd=directory, start_new_session=True,
                env={'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'HOME':directory})
            try:
                proc.wait(timeout=WALL_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise ValueError('SECOND_EVM_TIMEOUT') from None
            output.seek(0); errors.seek(0)
            raw, err = output.read(OUTPUT_LIMIT+1), errors.read(OUTPUT_LIMIT+1)
            need(proc.returncode == 0 and not err and 0 < len(raw) <= OUTPUT_LIMIT,
                 'SECOND_EVM_WORKER_FAILED')
            result = strict_json(raw)
            need(type(result) is dict, 'SECOND_EVM_RESULT')
            return result


def _geth_rows(pause_result: dict, access_result: dict) -> tuple[list, list]:
    rows, builds = [], []
    for family, module, result in (('pause', pause, pause_result),
                                    ('access', access, access_result)):
        initial = ({'remaining':15, 'distributed':0, 'paused':0} if family == 'pause'
                   else {'admin':access.evm.SENDER, 'remaining':10, 'distributed':0})
        for variant in module.VARIANTS:
            for codegen in module.CODEGEN:
                # Constructor return bytes and all call return data have already
                # been checked by each fixed native producer. Roots are excluded:
                # this comparison does not compare gas or account trie roots.
                built = result['builds'][variant][codegen]
                builds.append({'family':family, 'variant':variant, 'codegen':codegen,
                    **{k:built[k] for k in ('source_sha256','input_sha256','output_sha256',
                                           'creation_sha256','runtime_sha256')},
                    'initial_state':initial})
                for scenario, row in enumerate(result['cases'][variant][codegen]):
                    for step, call in enumerate(row['calls']):
                        rows.append({'family':family,'variant':variant,'codegen':codegen,
                            'scenario':scenario,'step':step,
                            'input':list(module.SEQUENCES[scenario][step]),
                            'status':call['status'],'before':call['before'],'after':call['after'],
                            'return_data':'0x'})
    return rows, builds


def compare(pause_result: dict, access_result: dict, python_result: dict, digest: str) -> dict:
    scored = score.analyze(pause_result, access_result, digest)
    rows, builds = _geth_rows(pause_result, access_result)
    expected_dependencies = {k:{f:v[f] for f in ('version','runtime_sha256','files')}
                             for k,v in PINS.items()}
    need(set(python_result) == {'profile','source_digest','engine','fork','dependencies',
                                'builds','rows','constructor_executions','runtime_calls'},
         'SECOND_EVM_SCHEMA')
    need(python_result['profile'] == PROFILE and python_result['source_digest'] == digest and
         python_result['engine'] == 'py-evm' and python_result['fork'] == 'Cancun' and
         canonical(python_result['dependencies']) == canonical(expected_dependencies),
         'SECOND_EVM_IDENTITY')
    need(type(python_result['constructor_executions']) is int and
         python_result['constructor_executions'] == len(builds) == 8 and
         type(python_result['runtime_calls']) is int and
         python_result['runtime_calls'] == len(rows) == 144, 'SECOND_EVM_COVERAGE')
    # Canonical bytes distinguish bool/int and reject extras, omissions, duplicate
    # cases, reordering, altered status, output or any observed storage field.
    need(canonical(python_result['builds']) == canonical(builds), 'SECOND_EVM_BUILD_MISMATCH')
    need(canonical(python_result['rows']) == canonical(rows), 'SECOND_EVM_SEMANTICS_MISMATCH')
    return {'schema_version':1,'profile':PROFILE,'status':'OWNED_CROSS_EVM_MATCH',
        'source_digest':digest,'solc_sha256':scored['solc_sha256'],
        'geth_sha256':scored['evm_sha256'],'python_dependencies':expected_dependencies,
        'fork':'Cancun','implementation_count':2,'constructor_builds_per_engine':8,
        'runtime_calls_per_engine':144,'known_cases':4,'compiler_runs_per_case':2,
        'semantic_rows_sha256':sha(canonical(rows)), 'builds_sha256':sha(canonical(builds)),
        'counts':scored['metrics']['overall']['counts'],
        'comparison_dimensions':['constructor_runtime','constructor_storage','call_status',
                                 'persisted_storage','return_data'],
        'distinct_evm_implementations_executed':True,
        'shared_compiler_and_inputs':True,'independent_producers_proved':False,
        'gas_costs_compared':False,'account_state_roots_compared':False,
        'blind_benchmark':False,'all_evm_semantics_certified':False,
        'generalization_established':False,'external_programs_executed':0,
        'vulnerability_confirmed':False}


def _execute(solc: Path, evm: Path, digest: str) -> dict[str, bytes]:
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest, 'SOURCE_CHANGED')
    p, a = score._run_native(solc, evm, digest)
    second = _run_python(solc, digest)
    report = compare(p, a, second, digest)
    need(quality.source_snapshot() == before, 'SOURCE_CHANGED_DURING_COMPARISON')
    review = ('# Comparación de dos implementaciones EVM\n\n'
        'Geth y py-evm ejecutaron los mismos cuatro controles propios conocidos.\n'
        'Ocho constructores y 144 llamadas por motor; dos compilaciones por caso.\n'
        'Coinciden estado persistente, éxito/reversión/gas agotado y retorno.\n'
        'Los dos motores comparten solc, entradas y host. No se comparan costes\n'
        'de gas ni raíces de cuentas. No es certificación general del protocolo.\n'
        'py-evm 0.12.1b1 está archivado: este perfil queda fijado a Cancun.\n'
        'No es benchmark ciego, hallazgo nuevo ni validación de objetivos externos.\n').encode()
    return {'geth-pause.json':canonical(p), 'geth-access.json':canonical(a),
            'python.json':canonical(second), 'comparison.json':canonical(report),
            'REVIEW.md':review}


def create(out: Path, solc: Path, evm: Path, digest: str) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    files = _execute(solc, evm, digest)
    write_new_bundle(out, files)
    return {'status':'OWNED_CROSS_EVM_CREATED','known_cases':4,
            'runtime_calls_per_engine':144,'vulnerability_confirmed':False}


def verify(root: Path, solc: Path, evm: Path, digest: str) -> dict:
    need(root.is_dir() and not root.is_symlink(), 'BUNDLE_DIRECTORY')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES and
         {p.name for p in root.iterdir()} == FILES|{'COMPLETE.json'}, 'BUNDLE_MANIFEST')
    files = {n:read_artifact(root, n) for n in FILES}
    need(all(sha(raw) == marker['sha256'][n] for n,raw in files.items()), 'BUNDLE_HASH')
    original = strict_json(files['comparison.json'])
    need(original.get('source_digest') == digest, 'WRONG_EXTERNAL_CODE_REFERENCE')
    regenerated = _execute(solc, evm, digest)
    need(files == regenerated, 'CROSS_EVM_REPLAY_MISMATCH')
    return {'status':'OWNED_CROSS_EVM_REPLAY_VERIFIED','known_cases':4,
            'runtime_calls_per_engine':144,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Compare fixed owned Cancun controls across two EVMs')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('compare-owned-evm-engines')
    check = subs.add_parser('verify-owned-evm-engines')
    for p in (make, check):
        p.add_argument('--solc', type=Path, required=True)
        p.add_argument('--evm', type=Path, required=True)
        p.add_argument('--source-digest', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (create(args.out, args.solc, args.evm, args.source_digest)
                  if args.command == 'compare-owned-evm-engines' else
                  verify(args.bundle, args.solc, args.evm, args.source_digest))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'status':'OWNED_CROSS_EVM_BLOCKED','vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
