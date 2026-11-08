"""One fixed own-repository review using a sealed data-only stdin channel.

Verification rechecks consistency and source identity, not native execution or
host authenticity. Unexpected worker output remains inconclusive.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from . import (owned_capture as capture, owned_compute_guard as guard, owned_process,
               owned_sealed_input as sealed, owned_workspace, quality, repository_boundary as boundary)
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'owned-sealed-boundary-lab-v1'
WORKER = 'owned_sealed_worker.py'
FILES = {'observation.json', 'result.json', 'worker.stdout', 'worker.stderr', 'REVIEW.md'}
LIMITS = {**capture.LIMITS, 'parent_filesystem_acquisition_inside_filter': False,
          'module_loading_inside_filter': False, 'general_hostile_code_sandbox_proved': False,
          'memory_integrity_proved': False, 'vulnerability_confirmed': False}


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _source(source_digest: str) -> tuple[dict, dict, bytes, dict]:
    capture._digest(source_digest)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'SEALED_REVIEW_SOURCE')
    files, _ = boundary._capture(ROOT)
    after, _ = boundary._capture(ROOT)
    need(files == after, 'SEALED_REVIEW_INPUT_CHANGED')
    baseline = boundary._review_captured(files, 0)
    return snapshot, files, sealed.encode(files), baseline


def _matched(raw: bytes, baseline: dict, frame: bytes, clock: dict) -> bool:
    try:
        value = strict_json(raw)
        need(set(value) == {'schema_version', 'profile', 'status', 'input_inventory_sha256',
             'input_frame_sha256', 'filter_proof', 'boundary_result', 'phase_clocks'}, 'SEALED_WORKER_SCHEMA')
        need(type(value['schema_version']) is int and value['schema_version'] == 1 and
             value['profile'] == 'owned-sealed-boundary-review-v1' and
             value['status'] == 'OWNED_SEALED_REVIEW_OBSERVED', 'SEALED_WORKER_PROFILE')
        need(value['input_inventory_sha256'] == baseline['source_inventory_sha256'] and
             value['input_frame_sha256'] == quality.sha(frame) and
             canonical(value['boundary_result']) == canonical(baseline), 'SEALED_WORKER_RESULT')
        proof = value['filter_proof']
        need(type(proof) is dict and canonical(proof) == canonical(guard.sealed_expected_proof(
             proof['socket_controls_before_filter'], len(frame))), 'SEALED_WORKER_PROOF')
        phases = value['phase_clocks']
        keys = ('filter_controls_finished_monotonic_ns', 'sealed_input_finished_monotonic_ns',
                'review_finished_monotonic_ns')
        need(type(phases) is dict and set(phases) == set(keys), 'SEALED_PHASE_SCHEMA')
        stamps = [clock['monotonic_start_ns'], *(phases[key] for key in keys), clock['monotonic_end_ns']]
        need(all(type(stamp) is int and 0 <= stamp < 2**63 for stamp in stamps) and
             stamps == sorted(stamps), 'SEALED_PHASE_ORDER')
        need(raw == canonical(value), 'SEALED_WORKER_ENCODING')
        return True
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return False


def analyze(observation: dict, raw: dict, *, source_digest: str, frame: bytes, baseline: dict) -> dict:
    fields = {'schema_version', 'profile', 'experiment_id', 'origin', 'source_digest',
              'worker_sha256', 'runtime', 'input_frame_sha256', 'input_frame_bytes',
              'input_inventory_sha256', 'returncode', 'timed_out', 'wall_budget_seconds',
              'stdout_sha256', 'stderr_sha256', 'stdout_bytes', 'stderr_bytes', 'clock', 'limitations'}
    need(type(observation) is dict and set(observation) == fields, 'SEALED_REVIEW_SCHEMA')
    need(type(observation['schema_version']) is int and observation['schema_version'] == 1 and
         observation['profile'] == PROFILE and observation['origin'] == 'own_parent_process_observation',
         'SEALED_REVIEW_PROFILE')
    identifier = observation['experiment_id']
    need(type(identifier) is str and str(uuid.UUID(identifier)) == identifier and
         uuid.UUID(identifier).version == 4, 'SEALED_REVIEW_ID')
    need(observation['source_digest'] == source_digest and
         observation['worker_sha256'] == quality.sha(read_artifact(ROOT/'superhunter', WORKER)),
         'SEALED_REVIEW_SOURCE')
    runtime = observation['runtime']
    need(type(runtime) is dict and set(runtime) == {'executable_sha256', 'python'}, 'SEALED_REVIEW_RUNTIME')
    capture._digest(runtime['executable_sha256'])
    need(type(runtime['python']) is str and len(runtime['python']) <= 16 and
         len(runtime['python'].split('.')) == 3 and
         all(p.isascii() and p.isdigit() for p in runtime['python'].split('.')), 'SEALED_REVIEW_RUNTIME')
    need(observation['input_frame_sha256'] == quality.sha(frame) and
         type(observation['input_frame_bytes']) is int and observation['input_frame_bytes'] == len(frame) and
         observation['input_inventory_sha256'] == baseline['source_inventory_sha256'], 'SEALED_REVIEW_FRAME')
    need(canonical(observation['limitations']) == canonical(LIMITS), 'SEALED_REVIEW_LIMITS')
    need(type(observation['timed_out']) is bool and
         ((observation['timed_out'] and observation['returncode'] is None) or
          (not observation['timed_out'] and type(observation['returncode']) is int and
           -64 <= observation['returncode'] <= 255)), 'SEALED_REVIEW_EXIT')
    need(type(observation['wall_budget_seconds']) is int and
         observation['wall_budget_seconds'] == capture.WALL_SECONDS, 'SEALED_REVIEW_BUDGET')
    capture._clock_check(observation['clock'])
    for stream in ('stdout', 'stderr'):
        value = raw[f'worker.{stream}']
        need(type(value) is bytes and len(value) <= capture.OUTPUT_BYTES and
             observation[stream+'_sha256'] == quality.sha(value) and
             type(observation[stream+'_bytes']) is int and observation[stream+'_bytes'] == len(value),
             'SEALED_REVIEW_STREAM')
    matched = (not observation['timed_out'] and observation['returncode'] == 0 and
               raw['worker.stderr'] == b'' and _matched(raw['worker.stdout'], baseline, frame, observation['clock']))
    return {'schema_version': 1, 'profile': PROFILE, 'experiment_id': identifier,
            'source_digest': source_digest,
            'status': 'OWNED_SEALED_LAB_PASS' if matched else 'OWNED_SEALED_LAB_INCONCLUSIVE',
            'restricted_observation_matched': matched, 'worker_payload_read_inside_filter_observed': matched,
            'input_frame_sha256': quality.sha(frame), 'input_frame_bytes': len(frame),
            'operational_findings_created': 0, 'limitations': dict(LIMITS)}


def render(result: dict) -> bytes:
    return (f"# Lectura propia desde entrada sellada\n\nEstado: {result['status']}.\n\n"
            f"Entrada: {result['input_frame_bytes']} bytes; SHA-256 {result['input_frame_sha256']}.\n\n"
            'El padre captura dos veces la fuente propia y sella un paquete de datos. '
            'El worker comprueba metadatos, activa el filtro y después lee el paquete por FD 0. '
            'No abre un checkout ni ejecuta los bytes recibidos. Solo conserva FD 0, 1 y 2. '
            'Una entrada sin sellos, un filtro no disponible o una respuesta inesperada no tiene '
            'cálculo alternativo sin filtro; conserva INCONCLUSIVE.\n\n'
            'La adquisición del padre y la carga de módulos preceden el filtro. Los sellos '
            'cubren el archivo de entrada, no la memoria del intérprete ni el host. '
            'La verificación coteja evidencia y fuente; no vuelve a ejecutar el worker ni '
            'autentica host, productor o relojes. No acredita sandbox general, cierre de M1, '
            'vulnerabilidad externa ni operación 24/7.\n').encode()


def _read(bundle: Path) -> dict:
    capture._path(bundle, new=False)
    names = set()
    for index, entry in enumerate(bundle.iterdir()):
        need(index <= len(FILES), 'SEALED_REVIEW_INVENTORY')
        names.add(entry.name)
    need(names == FILES | {'COMPLETE.json'}, 'SEALED_REVIEW_INVENTORY')
    raw = {name: read_artifact(bundle, name) for name in names}
    need(all(len(value) <= capture.OUTPUT_BYTES for value in raw.values()), 'SEALED_REVIEW_BYTES')
    need(raw['COMPLETE.json'] == canonical({'schema_version': 1,
         'sha256': {name: quality.sha(raw[name]) for name in FILES}}), 'SEALED_REVIEW_MANIFEST')
    return raw


def create(out: Path, *, source_digest: str) -> dict:
    capture._path(out, new=True)
    snapshot, files, frame, baseline = _source(source_digest)
    runtime = capture._runtime()
    observation = {'schema_version': 1, 'profile': PROFILE, 'experiment_id': str(uuid.uuid4()),
                   'origin': 'own_parent_process_observation', 'source_digest': source_digest,
                   'worker_sha256': snapshot[WORKER], 'runtime': runtime,
                   'input_inventory_sha256': baseline['source_inventory_sha256'],
                   'input_frame_sha256': quality.sha(frame), 'input_frame_bytes': len(frame),
                   'wall_budget_seconds': capture.WALL_SECONDS, 'limitations': dict(LIMITS)}
    streams = {}
    with owned_workspace.Workspace('diagnosis', excluded=(ROOT, out)) as workspace:
        work = workspace.path
        marker = work/'owned-compute-control'
        marker.write_bytes(guard.MARKER_BYTES)
        with sealed.sealed_bytes(frame) as descriptor, (work/'stdout').open('w+b') as stdout, \
             (work/'stderr').open('w+b') as stderr:
            mono_start, real_start = time.monotonic_ns(), time.time_ns()
            timed_out = False
            try:
                process = owned_process.run([sys.executable, '-I', '-B', str(ROOT/'superhunter'/WORKER)],
                    cwd=work, env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=capture.WALL_SECONDS,
                    stdout=stdout, stderr=stderr, sealed_stdin=descriptor)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                timed_out, returncode = True, None
            real_end, mono_end = time.time_ns(), time.monotonic_ns()
            for stream, file in (('stdout', stdout), ('stderr', stderr)):
                file.seek(0)
                value = file.read(capture.OUTPUT_BYTES+1)
                need(len(value) <= capture.OUTPUT_BYTES, 'SEALED_REVIEW_OUTPUT_BUDGET')
                streams[f'worker.{stream}'] = value
                observation[stream+'_sha256'], observation[stream+'_bytes'] = quality.sha(value), len(value)
        need(marker.read_bytes() == guard.MARKER_BYTES and
             not (work/'owned-compute-directory-control').exists(), 'SEALED_REVIEW_CONTROL_CHANGED')
        observation.update(returncode=returncode, timed_out=timed_out,
            clock={'monotonic_start_ns': mono_start, 'monotonic_end_ns': mono_end,
                   'realtime_start_ns': real_start, 'realtime_end_ns': real_end,
                   'elapsed_ns': mono_end-mono_start, 'realtime_delta_ns': real_end-real_start,
                   'realtime_moved_backwards': real_end < real_start})
        result = analyze(observation, streams, source_digest=source_digest, frame=frame, baseline=baseline)
    workspace.confirm_removed()
    after, _ = boundary._capture(ROOT)
    need(after == files and quality.source_snapshot() == snapshot and capture._runtime() == runtime,
         'SEALED_REVIEW_ORIGINAL_CHANGED')
    write_new_bundle(out, {**streams, 'observation.json': canonical(observation),
                          'result.json': canonical(result), 'REVIEW.md': render(result)})
    return {**result, 'experiment_anchor': quality.sha(read_artifact(out, 'COMPLETE.json'))}


def verify(bundle: Path, *, source_digest: str, experiment_anchor: str) -> dict:
    capture._digest(experiment_anchor)
    snapshot, files, frame, baseline = _source(source_digest)
    raw = _read(bundle)
    need(quality.sha(raw['COMPLETE.json']) == experiment_anchor, 'SEALED_REVIEW_ANCHOR')
    observation = strict_json(raw['observation.json'])
    result = analyze(observation, raw, source_digest=source_digest, frame=frame, baseline=baseline)
    need(raw['observation.json'] == canonical(observation) and raw['result.json'] == canonical(result) and
         raw['REVIEW.md'] == render(result), 'SEALED_REVIEW_REPORT')
    after, _ = boundary._capture(ROOT)
    need(after == files and _read(bundle) == raw and quality.source_snapshot() == snapshot,
         'SEALED_REVIEW_EVIDENCE_CHANGED')
    return {**result, 'experiment_anchor': experiment_anchor}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Review fixed own source through sealed stdin after restriction')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('check-owned-sealed-boundary')
    check = sub.add_parser('verify-owned-sealed-boundary')
    for command in (make, check):
        command.add_argument('--source-digest', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--experiment-anchor', required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    try:
        result = create(**args) if command == 'check-owned-sealed-boundary' else verify(**args)
        print(json.dumps({key: result[key] for key in ('status', 'source_digest', 'experiment_anchor')}, sort_keys=True))
        return 0 if result['status'] == 'OWNED_SEALED_LAB_PASS' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
        print(json.dumps({'status': 'OWNED_SEALED_LAB_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
