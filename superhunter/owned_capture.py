"""Capture one fixed own process; offline verification is consistency, not attestation.

The producer observes a real child. Saved bytes cannot prove that execution to
an independent party. No remote target, arbitrary command or journald export.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from . import owned_process, quality, repository_boundary
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'superhunter-owned-boundary-capture-v1'
FILES = {'observation.json', 'boundary.stdout', 'REVIEW.md'}
WALL_SECONDS = 30
OUTPUT_BYTES = 65536
LIMITS = {'independent_execution_authenticated': False, 'host_authenticated': False,
          'utc_accuracy_authenticated': False, 'journald_acquisition': False,
          'runtime_isolation_proved': False, 'incident_confirmed': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _digest(value) -> None:
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'CAPTURE_DIGEST')


def _path(path: Path, *, new: bool) -> None:
    need(not path.resolve().is_relative_to(ROOT) and not ROOT.is_relative_to(path.resolve()),
         'CAPTURE_REPOSITORY_OVERLAP')
    for parent in (path.absolute(), *path.absolute().parents):
        need(not parent.is_symlink(), 'CAPTURE_SYMLINK')
    need(not path.exists() if new else path.is_dir(), 'CAPTURE_DIRECTORY')


def _read(root: Path) -> dict[str, bytes]:
    _path(root, new=False)
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index < len(FILES) + 1, 'CAPTURE_INVENTORY')
        names.add(entry.name)
    need(names == FILES | {'COMPLETE.json'}, 'CAPTURE_INVENTORY')
    raw = {name: read_artifact(root, name) for name in names}
    need(all(len(value) <= OUTPUT_BYTES for value in raw.values()), 'CAPTURE_BYTES')
    expected = {'schema_version': 1, 'sha256': {name: quality.sha(raw[name]) for name in FILES}}
    need(raw['COMPLETE.json'] == canonical(expected), 'CAPTURE_MANIFEST')
    return raw


def _runtime() -> dict:
    # Identify only the executable's bytes, not its shared libraries or host.
    executable = Path(sys.executable).resolve(strict=True)
    fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 64 * 1024**2, 'CAPTURE_RUNTIME')
        digest = hashlib.sha256()
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            for _ in range(65):
                block = stream.read(1024**2)
                if not block:
                    break
                digest.update(block)
            else:
                raise ValueError('CAPTURE_RUNTIME_BYTES')
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'CAPTURE_RUNTIME_CHANGED')
    finally:
        os.close(fd)
    return {'executable_sha256': digest.hexdigest(), 'python': '.'.join(map(str, sys.version_info[:3]))}


def _clock_check(clock: dict) -> None:
    fields = {'monotonic_start_ns', 'monotonic_end_ns', 'realtime_start_ns', 'realtime_end_ns',
              'elapsed_ns', 'realtime_delta_ns', 'realtime_moved_backwards'}
    need(type(clock) is dict and set(clock) == fields, 'CAPTURE_CLOCK_SCHEMA')
    for key in fields - {'realtime_delta_ns', 'realtime_moved_backwards'}:
        need(type(clock[key]) is int and 0 <= clock[key] < 2**63, 'CAPTURE_CLOCK_INTEGER')
    need(type(clock['realtime_delta_ns']) is int and -(2**63) < clock['realtime_delta_ns'] < 2**63,
         'CAPTURE_CLOCK_INTEGER')
    elapsed = clock['monotonic_end_ns'] - clock['monotonic_start_ns']
    delta = clock['realtime_end_ns'] - clock['realtime_start_ns']
    need(elapsed >= 0 and clock['elapsed_ns'] == elapsed and clock['realtime_delta_ns'] == delta,
         'CAPTURE_CLOCK_ARITHMETIC')
    need(type(clock['realtime_moved_backwards']) is bool and clock['realtime_moved_backwards'] == (delta < 0),
         'CAPTURE_CLOCK_ROLLBACK')


def _check(observation: dict, stdout: bytes, *, source_digest: str, boundary: dict) -> None:
    fields = {'schema_version', 'profile', 'capture_id', 'origin', 'source_digest', 'worker_sha256',
              'runtime', 'exit_code', 'wall_budget_seconds', 'stdout_sha256', 'stdout_bytes',
              'stderr_bytes', 'clock', 'limitations'}
    need(type(observation) is dict and set(observation) == fields, 'CAPTURE_SCHEMA')
    need(type(observation['schema_version']) is int and observation['schema_version'] == 1 and
         observation['profile'] == PROFILE and observation['origin'] == 'own_parent_process_observation',
         'CAPTURE_ORIGIN')
    capture_id = observation['capture_id']
    need(type(capture_id) is str and str(uuid.UUID(capture_id)) == capture_id and
         uuid.UUID(capture_id).version == 4, 'CAPTURE_ID')
    need(observation['source_digest'] == source_digest and
         observation['worker_sha256'] == quality.sha(read_artifact(ROOT / 'superhunter', 'owned_boundary_worker.py')),
         'CAPTURE_SOURCE')
    runtime = observation['runtime']
    need(type(runtime) is dict and set(runtime) == {'executable_sha256', 'python'}, 'CAPTURE_RUNTIME_SCHEMA')
    _digest(runtime['executable_sha256'])
    need(type(runtime['python']) is str and re.fullmatch(r'3\.\d{1,3}\.\d{1,3}', runtime['python']) is not None,
         'CAPTURE_PYTHON')
    for name, expected in (('exit_code', 0), ('wall_budget_seconds', WALL_SECONDS),
                           ('stdout_bytes', len(stdout)), ('stderr_bytes', 0)):
        need(type(observation[name]) is int and observation[name] == expected, 'CAPTURE_PROCESS_RESULT')
    need(len(stdout) <= OUTPUT_BYTES and stdout == canonical(boundary) and
         observation['stdout_sha256'] == quality.sha(stdout), 'CAPTURE_BOUNDARY_RESULT')
    need(canonical(observation['limitations']) == canonical(LIMITS), 'CAPTURE_LIMITATIONS')
    _clock_check(observation['clock'])


def render(observation: dict) -> bytes:
    clock = observation['clock']
    return (f'# Captura de proceso propio\n\nFormato: {PROFILE}.\n'
            f"Captura: {observation['capture_id']}; salida: 0.\n"
            f"Intervalo observado: {clock['elapsed_ns']} ns; retroceso UTC: {clock['realtime_moved_backwards']}.\n\n"
            'El productor supervisa una revisión fija y de solo lectura de este repositorio.\n'
            'El intervalo monotónico incluye lanzamiento, espera y limpieza; no es tiempo de CPU.\n'
            'Los relojes y el proceso pertenecen al mismo host. No se acredita exactitud UTC.\n'
            'El expediente no es una exportación journald ni una atestación independiente.\n'
            'Verificarlo comprueba bytes, aritmética y resultado frente al repositorio vigente;\n'
            'no vuelve a ejecutar el worker ni demuestra que se ejecutó históricamente.\n').encode()


def create(out: Path, *, source_digest: str) -> dict:
    _digest(source_digest); _path(out, new=True)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'CAPTURE_SOURCE')
    before = repository_boundary.review(ROOT)
    runtime = _runtime()
    with tempfile.TemporaryDirectory(prefix='superhunter-owned-capture-') as name:
        work = Path(name)
        with (work / 'stdout').open('w+b') as stdout, (work / 'stderr').open('w+b') as stderr:
            mono_start = time.monotonic_ns(); real_start = time.time_ns()
            result = owned_process.run(
                [sys.executable, '-I', '-B', str(ROOT / 'superhunter' / 'owned_boundary_worker.py')],
                cwd=work, env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=WALL_SECONDS,
                stdout=stdout, stderr=stderr)
            real_end = time.time_ns(); mono_end = time.monotonic_ns()
            stdout.seek(0); raw = stdout.read(OUTPUT_BYTES + 1)
            stderr.seek(0); error = stderr.read(OUTPUT_BYTES + 1)
    need(type(result.returncode) is int and result.returncode == 0 and not error, 'CAPTURE_PROCESS_FAILED')
    need(len(raw) <= OUTPUT_BYTES, 'CAPTURE_OUTPUT_BUDGET')
    after = repository_boundary.review(ROOT)
    need(before == after and quality.source_snapshot() == snapshot and _runtime() == runtime,
         'CAPTURE_INPUT_CHANGED')
    observation = {'schema_version': 1, 'profile': PROFILE, 'capture_id': str(uuid.uuid4()),
                   'origin': 'own_parent_process_observation', 'source_digest': source_digest,
                   'worker_sha256': snapshot['owned_boundary_worker.py'], 'runtime': runtime,
                   'exit_code': result.returncode, 'wall_budget_seconds': WALL_SECONDS,
                   'stdout_sha256': quality.sha(raw), 'stdout_bytes': len(raw), 'stderr_bytes': 0,
                   'clock': {'monotonic_start_ns': mono_start, 'monotonic_end_ns': mono_end,
                             'realtime_start_ns': real_start, 'realtime_end_ns': real_end,
                             'elapsed_ns': mono_end - mono_start, 'realtime_delta_ns': real_end - real_start,
                             'realtime_moved_backwards': real_end < real_start}, 'limitations': dict(LIMITS)}
    _check(observation, raw, source_digest=source_digest, boundary=after)
    write_new_bundle(out, {'observation.json': canonical(observation), 'boundary.stdout': raw,
                           'REVIEW.md': render(observation)})
    return {'status': 'OWNED_CAPTURE_CREATED', 'capture_id': observation['capture_id'],
            'capture_anchor': quality.sha(read_artifact(out, 'COMPLETE.json')),
            'source_digest': source_digest, 'historical_files_checked': after['historical_files_checked'],
            'elapsed_ns': observation['clock']['elapsed_ns'], 'limitations': dict(LIMITS)}


def verify(bundle: Path, *, source_digest: str, capture_anchor: str) -> dict:
    _digest(source_digest); _digest(capture_anchor)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'CAPTURE_SOURCE')
    raw = _read(bundle)
    need(quality.sha(raw['COMPLETE.json']) == capture_anchor, 'CAPTURE_ANCHOR')
    observation = strict_json(raw['observation.json'])
    boundary = repository_boundary.review(ROOT)
    _check(observation, raw['boundary.stdout'], source_digest=source_digest, boundary=boundary)
    need(raw['observation.json'] == canonical(observation) and raw['REVIEW.md'] == render(observation),
         'CAPTURE_REPORT')
    need(_read(bundle) == raw and quality.source_snapshot() == snapshot and
         repository_boundary.review(ROOT) == boundary, 'CAPTURE_EVIDENCE_CHANGED')
    return {'status': 'OWNED_CAPTURE_CONSISTENT', 'capture_id': observation['capture_id'],
            'capture_anchor': capture_anchor, 'source_digest': source_digest,
            'historical_files_checked': boundary['historical_files_checked'],
            'elapsed_ns': observation['clock']['elapsed_ns'], 'limitations': dict(LIMITS)}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Capture or verify one fixed own repository review process')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('capture-owned-boundary'); check = sub.add_parser('verify-owned-boundary-capture')
    for command in (make, check):
        command.add_argument('--source-digest', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--capture-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'capture-owned-boundary' else verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
        print(json.dumps({'status': 'OWNED_CAPTURE_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
