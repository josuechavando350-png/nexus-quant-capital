"""Two-environment acceptance of QA and six fixed OWNED quota controls.

QA preparation uses its exact package versions. Completion and verification use
the separately pinned EELS environment and actually replay both EVMs. No source,
target, calldata, interpreter, RPC endpoint or transaction can be supplied.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from . import native_doctor as doctor, native_platform as inventory
from . import owned_quota_cross_evm as native, platform as local, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'whole-qa-and-owned-quota-two-environments-v1'
LOCAL_FILES = inventory.LOCAL_FILES
READY_FILES = {'readiness.json'}
REPORT_FILES = {'acceptance.json', 'REVIEW.md'}
WORKERS = {'qa_count': 8, 'wall_seconds': 180, 'cpu_seconds': 90,
           'address_space_bytes': 2 * 1024**3, 'file_bytes': 20 * 1024**2,
           'scope': 'per-worker-not-aggregate', 'qa_scheduling': 'sequential'}
need, sha = inventory.need, inventory.sha


def _source(expected: str) -> dict:
    need(type(expected) is str and re.fullmatch(r'[a-f0-9]{64}', expected) is not None,
         'OWNED_PLATFORM_EXPECTED_SOURCE_REQUIRED')
    snapshot = quality.source_snapshot()
    need(sha(canonical(snapshot)) == expected, 'OWNED_PLATFORM_SOURCE_MISMATCH')
    return snapshot


def _new_output(out: Path) -> None:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'OWNED_PLATFORM_NEW_PRIVATE_OUTPUT')


def _qa_runtime() -> dict:
    checks = [doctor._host(), doctor._sealed_memory(), doctor._qa_packages(),
              doctor._z3_fixture_library()]
    need(all(c['status'] == 'PASS' for c in checks), 'OWNED_PLATFORM_QA_PREREQUISITES')
    host = checks[0]
    return {'system': host['system'], 'architecture': host['architecture'],
            'python_version': host['python_version'], 'sealed_memory': True,
            'package_versions': dict(doctor.PACKAGES), 'z3_sha256': doctor.Z3_SHA256}


def _validate_runtime(runtime: dict) -> None:
    need(type(runtime) is dict and runtime.get('system') == 'Linux' and
         runtime.get('architecture') in ('x86_64', 'amd64') and
         type(runtime.get('python_version')) is str and
         re.fullmatch(r'3\.12\.\d+', runtime['python_version']) is not None,
         'OWNED_PLATFORM_RECORDED_HOST')
    expected = {'system': 'Linux', 'architecture': runtime['architecture'],
                'python_version': runtime['python_version'], 'sealed_memory': True,
                'package_versions': dict(doctor.PACKAGES), 'z3_sha256': doctor.Z3_SHA256}
    need(canonical(runtime) == canonical(expected), 'OWNED_PLATFORM_RECORDED_RUNTIME')


def _prepared_files() -> set[str]:
    return ({'local/' + n for n in LOCAL_FILES} |
            {'readiness/' + n for n in READY_FILES | {'COMPLETE.json'}})


def _manifest(root: Path, names: set[str]) -> dict[str, str]:
    hashes = inventory._tree(root, names | {'COMPLETE.json'})
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(canonical(marker) == canonical({'schema_version': 1,
         'sha256': {n: hashes[n] for n in sorted(names)}}), 'OWNED_PLATFORM_MANIFEST')
    return hashes


def _readiness(runtime: dict, digest: str, local_hashes: dict) -> dict:
    return {'schema_version': 1, 'profile': PROFILE, 'source_digest': digest,
            'status': 'OWNED_QA_PREPARED', 'qa_runtime': runtime,
            'worker_policy': WORKERS, 'local_sha256': local_hashes,
            'producer_authenticated': False, 'native_executed': False,
            'platform_complete': False, 'vulnerability_confirmed': False}


def _local_result(root: Path, expected: str) -> dict:
    checked = local.verify_platform(root)
    need(checked['status'] == 'LOCAL_DEFENSIVE_REVIEW_PASS' and
         checked['source_digest'] == expected and checked['platform_complete'] is False and
         checked['vulnerability_confirmed'] is False and
         checked['stages']['qa']['status'] == 'LOCAL_QA_PASS' and
         type(checked['stages']['qa']['tests_run']) is int and
         checked['stages']['qa']['tests_run'] > 0, 'OWNED_PLATFORM_LOCAL_STATUS')
    return checked


def verify_prepared(root: Path, expected: str) -> dict:
    """Verify recorded QA identity without requiring QA packages in EELS Python.

    This verifies current-source receipts, not an authenticated producer or a
    second execution of QA. Rehashed invented receipts are not attestation.
    """
    snapshot = _source(expected)
    hashes = inventory._tree(root, _prepared_files())
    _manifest(root / 'readiness', READY_FILES)
    record = strict_json(read_artifact(root, 'readiness/readiness.json'))
    runtime = record.get('qa_runtime')
    _validate_runtime(runtime)
    local_hashes = inventory._tree(root / 'local', LOCAL_FILES)
    need(canonical(record) == canonical(_readiness(runtime, expected, local_hashes)),
         'OWNED_PLATFORM_PREPARATION_CHANGED')
    checked = _local_result(root / 'local', expected)
    need(snapshot == quality.source_snapshot() and
         hashes == inventory._tree(root, _prepared_files()),
         'OWNED_PLATFORM_PREPARATION_CHANGED_DURING_VERIFICATION')
    return {'record': record, 'local': checked, 'files': hashes}


def prepare(out: Path) -> dict:
    _new_output(out)
    snapshot = quality.source_snapshot()
    digest = sha(canonical(snapshot))
    runtime = _qa_runtime()  # Wrong QA packages fail before output or execution.
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    result = local.run_platform(out / 'local')
    need(result['status'] == 'LOCAL_DEFENSIVE_REVIEW_PASS' and
         result['source_digest'] == digest, 'OWNED_PLATFORM_QA_NOT_APPROVED')
    _local_result(out / 'local', digest)
    hashes = inventory._tree(out / 'local', LOCAL_FILES)
    need(snapshot == quality.source_snapshot() and runtime == _qa_runtime(),
         'OWNED_PLATFORM_QA_ENVIRONMENT_CHANGED')
    record = _readiness(runtime, digest, hashes)
    write_new_bundle(out / 'readiness', {'readiness.json': canonical(record)})
    verify_prepared(out, digest)
    return record


def _native_preflight(solc: Path, evm: Path) -> None:
    checks = [doctor._host(), doctor._sealed_memory(), doctor._tool('solc', solc),
              doctor._tool('geth', evm), doctor._second_evm_packages('execution-specs')]
    need(all(c['status'] == 'PASS' for c in checks), 'OWNED_PLATFORM_NATIVE_PREREQUISITES')


def _copy_prepared(source: Path, dest: Path, expected_hashes: dict) -> None:
    # Snapshot bounded bytes first; never copy extras, symlinks or a live tree
    # using shutil.copytree. A concurrent replacement cannot gain new paths.
    files = {n: read_artifact(source, n) for n in sorted(expected_hashes)}
    need({n: sha(raw) for n, raw in files.items()} == expected_hashes and
         inventory._tree(source, _prepared_files()) == expected_hashes,
         'OWNED_PLATFORM_PREPARATION_CHANGED_DURING_COPY')
    dest.mkdir(mode=0o700)
    for name, raw in files.items():
        path = dest / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    need(inventory._tree(dest, _prepared_files()) == expected_hashes,
         'OWNED_PLATFORM_COPY_MISMATCH')


def _stage_hashes(root: Path, complete: bool) -> dict:
    wanted = {'prepared', 'native', 'review'} if complete else {'prepared', 'native'}
    need(root.is_dir() and not root.is_symlink() and
         {p.name for p in root.iterdir()} == wanted, 'OWNED_PLATFORM_STAGE_INVENTORY')
    return {'prepared': inventory._tree(root / 'prepared', _prepared_files()),
            'native': inventory._tree(root / 'native', native.FILES | {'COMPLETE.json'})}


def _collect(root: Path, solc: Path, evm: Path, expected: str, *, complete: bool) -> dict:
    snapshot = _source(expected)
    captured = _stage_hashes(root, complete)
    prepared = verify_prepared(root / 'prepared', expected)
    _native_preflight(solc, evm)
    replayed = native.verify(root / 'native', solc, evm, expected)
    need(canonical(replayed) == canonical({'status': 'OWNED_QUOTA_CROSS_EVM_REPLAY_VERIFIED',
         'cases': 6, 'runtime_calls_per_engine': 228, 'vulnerability_confirmed': False}),
         'OWNED_PLATFORM_NATIVE_REPLAY_REQUIRED')
    comparison = strict_json(read_artifact(root, 'native/comparison.json'))
    checked = prepared['local']
    receipt = strict_json(read_artifact(root, 'prepared/local/qa/receipt.json'))
    result = {
        'schema_version': 1, 'profile': PROFILE, 'status': 'OWNED_PLATFORM_REVIEW_PASS',
        'source_digest': expected, 'evidence_sha256': captured,
        'qa_runtime': prepared['record']['qa_runtime'], 'worker_policy': WORKERS,
        'qa': {'tests_run': checked['stages']['qa']['tests_run'],
               'inventory_sha256': sha(canonical(sorted(receipt['discovered']))),
               'tests_reexecuted_by_verifier': False},
        'local_controls': {'numerical_cases': checked['stages']['lab']['cases_passed'],
                           'fuzz_cases': checked['stages']['fuzz']['cases_verified'],
                           'accounting_cases': checked['stages']['economics']['cases_checked'],
                           'permission_cases': checked['stages']['benchmark_control']['cases'],
                           'sequence_cases': checked['stages']['sequence']['cases_checked']},
        'native_comparison': comparison,
        'plans': {'integration_ids': [x['id'] for x in checked['integration']['items']],
                  'capability_ids': [x['id'] for x in checked['capabilities']['items']],
                  'initiative_ids': [x['id'] for x in checked['research_initiatives']['items']]},
        'native_reexecuted_by_verifier': True, 'qa_and_eels_environments_separate': True,
        'fixed_owned_controls_only': True, 'producer_authenticated': False,
        'legacy_native_profile_recertified': False, 'aggregate_resource_budget_certified': False,
        'geth_image_staged_before_worker_file_limit': True,
        'platform_complete': False, 'vulnerability_confirmed': False,
        'external_targets_executed': False, 'network_used': False,
        'monetary_valuation_usd': None,
    }
    need(snapshot == quality.source_snapshot() and captured == _stage_hashes(root, complete),
         'OWNED_PLATFORM_SOURCE_OR_EVIDENCE_CHANGED')
    return result


def _documents(result: dict) -> dict[str, bytes]:
    report = ('# Revisión integral de controles propios\n\n'
        f"Perfil: `{PROFILE}`. Código: `{result['source_digest']}`.\n\n"
        f"QA: {result['qa']['tests_run']} pruebas. Se verifican recibos; el verificador no repite QA.\n"
        'La aceptación y cada verificación sí recompilan y repiten Geth y EELS.\n'
        'Son seis casos conocidos, cuatro defectos sembrados y dos controles correctos.\n'
        'Doce constructores y 228 llamadas por motor no son muestras independientes.\n'
        'QA conserva PyYAML 6.0.3 y cryptography 46.0.4; EELS usa sus 23 dependencias fijadas.\n'
        'Los límites son por trabajador, no un presupuesto agregado del árbol de procesos.\n'
        'La imagen Geth sellada se prepara antes del límite de archivos del trabajador.\n'
        'Compilador, casos, host y detector son compartidos. No hay benchmark ciego,\n'
        'autenticación del productor, recertificación del perfil histórico ni generalización.\n'
        'Sin objetivos externos, fondos, vulnerabilidades nuevas ni recompensas estimadas.\n'
        'Plataforma completa: NO. Avance global no determinado.\n').encode()
    return {'acceptance.json': canonical(result), 'REVIEW.md': report}


def finish(prepared: Path, out: Path, solc: Path, evm: Path, expected: str) -> dict:
    _new_output(out)
    need(not out.resolve().is_relative_to(prepared.resolve()) and
         not prepared.resolve().is_relative_to(out.resolve()), 'OWNED_PLATFORM_OVERLAPPING_OUTPUT')
    snapshot = _source(expected)
    verified = verify_prepared(prepared, expected)
    _native_preflight(solc, evm)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    _copy_prepared(prepared, out / 'prepared', verified['files'])
    verify_prepared(out / 'prepared', expected)
    native.create(out / 'native', solc, evm, expected)
    result = _collect(out, solc, evm, expected, complete=False)
    need(snapshot == quality.source_snapshot(), 'OWNED_PLATFORM_SOURCE_CHANGED_BEFORE_COMPLETION')
    write_new_bundle(out / 'review', _documents(result))
    return result


def verify(root: Path, solc: Path, evm: Path, expected: str) -> dict:
    _source(expected)
    _stage_hashes(root, complete=True)
    hashes = _manifest(root / 'review', REPORT_FILES)
    result = _collect(root, solc, evm, expected, complete=True)
    for name, raw in _documents(result).items():
        need(read_artifact(root / 'review', name) == raw, 'OWNED_PLATFORM_REPORT_DIFFERS_FROM_REPLAY')
    need(hashes == _manifest(root / 'review', REPORT_FILES), 'OWNED_PLATFORM_REPORT_CHANGED')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='QA and six OWNED controls in separate pinned environments')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('prepare-owned-platform')
    make.add_argument('--out', type=Path, required=True)
    ready = subs.add_parser('verify-owned-preparation')
    ready.add_argument('--bundle', type=Path, required=True)
    ready.add_argument('--expected-source', required=True)
    final = subs.add_parser('finish-owned-platform')
    final.add_argument('--prepared', type=Path, required=True)
    final.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-owned-platform')
    check.add_argument('--bundle', type=Path, required=True)
    for p in (final, check):
        p.add_argument('--solc', type=Path, required=True)
        p.add_argument('--evm', type=Path, required=True)
        p.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare-owned-platform':
            result = prepare(args.out)
        elif args.command == 'verify-owned-preparation':
            result = verify_prepared(args.bundle, args.expected_source)['record']
        elif args.command == 'finish-owned-platform':
            result = finish(args.prepared, args.out, args.solc, args.evm, args.expected_source)
        else:
            result = verify(args.bundle, args.solc, args.evm, args.expected_source)
        print(json.dumps({k: result[k] for k in ('status', 'source_digest', 'platform_complete',
                                                'vulnerability_confirmed')}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, RecursionError,
            OverflowError, subprocess.TimeoutExpired):
        print(json.dumps({'status': 'OWNED_PLATFORM_BLOCKED', 'platform_complete': False,
                          'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
