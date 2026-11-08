"""Five fixed own-copy trials with a restricted in-memory policy reviewer.

The acquisition phase precedes restriction. This profile preserves the actual
new worker identity and never relabels historical unfiltered-worker receipts.
Verification checks evidence consistency; it does not replay native execution.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from . import (owned_boundary_diagnosis as lab, owned_capture as capture,
               owned_compute_guard as guard, owned_process, owned_workspace,
               quality, repository_boundary as boundary)
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'owned-restricted-boundary-lab-v1'
WORKER = 'owned_restricted_worker.py'
LIMITS = {**capture.LIMITS, 'input_acquisition_inside_filter': False,
          'general_hostile_code_sandbox_proved': False, 'memory_integrity_proved': False,
          'general_causation_proved': False, 'vulnerability_confirmed': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _matched(stdout: bytes, expected: dict, inventory_digest: str, clock: dict) -> bool:
    """An unexpected worker response is retained as inconclusive, never promoted."""
    try:
        value = strict_json(stdout)
        need(type(value) is dict and set(value) == {
            'schema_version', 'profile', 'status', 'input_inventory_sha256',
            'filter_proof', 'boundary_result', 'phase_clocks'}, 'RESTRICTED_WORKER_SCHEMA')
        need(type(value['schema_version']) is int and value['schema_version'] == 1 and
             value['profile'] == 'owned-preloaded-boundary-review-v1' and
             value['status'] == 'OWNED_RESTRICTED_REVIEW_OBSERVED', 'RESTRICTED_WORKER_PROFILE')
        need(value['input_inventory_sha256'] == inventory_digest and
             canonical(value['boundary_result']) == canonical(expected), 'RESTRICTED_WORKER_RESULT')
        proof = value['filter_proof']
        need(type(proof) is dict and canonical(proof) == canonical(
            guard.expected_proof(proof['socket_controls_before_filter'])), 'RESTRICTED_FILTER_PROOF')
        phases = value['phase_clocks']
        keys = ('input_capture_finished_monotonic_ns', 'filter_controls_finished_monotonic_ns',
                'review_finished_monotonic_ns')
        need(type(phases) is dict and set(phases) == set(keys), 'RESTRICTED_PHASE_SCHEMA')
        stamps = [clock['monotonic_start_ns'], *(phases[key] for key in keys), clock['monotonic_end_ns']]
        need(all(type(stamp) is int and 0 <= stamp < 2**63 for stamp in stamps) and
             stamps == sorted(stamps), 'RESTRICTED_PHASE_ORDER')
        need(stdout == canonical(value), 'RESTRICTED_WORKER_ENCODING')
        return True
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def analyze(observation: dict, raw: dict[str, bytes], original: dict,
            baseline: dict, *, source_digest: str) -> dict:
    fields = {'schema_version', 'profile', 'experiment_id', 'origin', 'source_digest',
              'source_inventory_sha256', 'worker_sha256', 'runtime', 'trials', 'limitations'}
    need(type(observation) is dict and set(observation) == fields, 'RESTRICTED_SCHEMA')
    need(type(observation['schema_version']) is int and observation['schema_version'] == 1 and
         observation['profile'] == PROFILE and observation['origin'] == 'own_parent_process_observation',
         'RESTRICTED_PROFILE')
    identifier = observation['experiment_id']
    need(type(identifier) is str and str(uuid.UUID(identifier)) == identifier and
         uuid.UUID(identifier).version == 4, 'RESTRICTED_ID')
    need(observation['source_digest'] == source_digest and
         observation['source_inventory_sha256'] == quality.sha(canonical(original)) and
         observation['worker_sha256'] == quality.sha(read_artifact(ROOT/'superhunter', WORKER)),
         'RESTRICTED_SOURCE')
    runtime = observation['runtime']
    need(type(runtime) is dict and set(runtime) == {'executable_sha256', 'python'}, 'RESTRICTED_RUNTIME')
    capture._digest(runtime['executable_sha256'])
    need(type(runtime['python']) is str and len(runtime['python']) <= 16 and
         len(runtime['python'].split('.')) == 3 and
         all(p.isascii() and p.isdigit() for p in runtime['python'].split('.')), 'RESTRICTED_RUNTIME')
    need(canonical(observation['limitations']) == canonical(LIMITS), 'RESTRICTED_LIMITATIONS')
    trials = observation['trials']
    need(type(trials) is list and 1 <= len(trials) <= len(lab.PLAN), 'RESTRICTED_TRIAL_COUNT')
    checks = []
    previous_end = None
    for index, trial in enumerate(trials):
        label, kind = lab.PLAN[index]
        fields = {'index', 'label', 'intervention', 'inventory_before_sha256', 'inventory_after_sha256',
                  'delta', 'returncode', 'timed_out', 'stdout_sha256', 'stderr_sha256', 'stdout_bytes',
                  'stderr_bytes', 'wall_budget_seconds', 'clock'}
        need(type(trial) is dict and set(trial) == fields, 'RESTRICTED_TRIAL_SCHEMA')
        need(type(trial['index']) is int and trial['index'] == index and trial['label'] == label and
             trial['intervention'] == kind, 'RESTRICTED_TRIAL_ORDER')
        state = lab._state(original, kind)
        digest = quality.sha(canonical(state))
        need(trial['inventory_before_sha256'] == digest == trial['inventory_after_sha256'] and
             canonical(trial['delta']) == canonical(lab._delta(original, state)), 'RESTRICTED_INTERVENTION')
        need(type(trial['timed_out']) is bool and
             ((trial['timed_out'] and trial['returncode'] is None) or
              (not trial['timed_out'] and type(trial['returncode']) is int and
               -64 <= trial['returncode'] <= 255)), 'RESTRICTED_EXIT')
        need(type(trial['wall_budget_seconds']) is int and trial['wall_budget_seconds'] == capture.WALL_SECONDS,
             'RESTRICTED_WALL_BUDGET')
        capture._clock_check(trial['clock'])
        need(previous_end is None or previous_end <= trial['clock']['monotonic_start_ns'], 'RESTRICTED_CLOCK_ORDER')
        previous_end = trial['clock']['monotonic_end_ns']
        for stream in ('stdout', 'stderr'):
            value = raw[f'trial-{index}.{stream}']
            need(type(value) is bytes and len(value) <= capture.OUTPUT_BYTES and
                 trial[stream+'_sha256'] == quality.sha(value) and type(trial[stream+'_bytes']) is int and
                 trial[stream+'_bytes'] == len(value), 'RESTRICTED_STREAM')
        expected = baseline if kind == 'original' else {
            'status': 'REPOSITORY_BOUNDARY_BLOCKED', 'reason': 'HISTORICAL_TREE_CHANGED'}
        match = (not trial['timed_out'] and trial['returncode'] == (0 if kind == 'original' else 2) and
                 raw[f'trial-{index}.stderr'] == b'' and
                 _matched(raw[f'trial-{index}.stdout'], expected, digest, trial['clock']))
        checks.append({'label': label, 'expected_restricted_observation_matched': match,
                       'returncode': trial['returncode'], 'timed_out': trial['timed_out']})
        need(match or index == len(trials)-1, 'RESTRICTED_CONTINUED_AFTER_FAILURE')
    complete = len(trials) == len(lab.PLAN) and all(row['expected_restricted_observation_matched'] for row in checks)
    return {'schema_version': 1, 'profile': PROFILE, 'experiment_id': identifier,
            'status': 'OWNED_RESTRICTED_LAB_PASS' if complete else 'OWNED_RESTRICTED_LAB_INCONCLUSIVE',
            'source_digest': source_digest, 'trials_observed': len(trials), 'trials_required': len(lab.PLAN),
            'restricted_trials_matched': sum(int(row['expected_restricted_observation_matched']) for row in checks),
            'checks': checks, 'declared_integrity_controls_supported': ['missing-fixed-file', 'changed-fixed-mode'] if complete else [],
            'operational_findings_created': 0, 'repairs_executed_outside_disposable_copy': 0,
            'input_acquisition_inside_filter': False, 'limitations': dict(LIMITS)}


def render(result: dict) -> bytes:
    return (f"# Verificación propia con cómputo restringido\n\nEstado: {result['status']}.\n"
            f"Ensayos: {result['trials_observed']}/{result['trials_required']}; "
            f"respuestas restringidas coincidentes: {result['restricted_trials_matched']}.\n\n"
            'Se revisan bytes de una copia propia. La adquisición doble y la carga de módulos '
            'ocurren antes del filtro; la política de integridad se calcula en memoria después. '
            'No se ejecuta código de la copia. El worker no admite destinos ni comandos.\n\n'
            'La biblioteca fijada se carga bajo un límite de archivo de 128 KiB; después se reduce '
            'a 64 KiB. CPU: 15 s; memoria virtual: 256 MiB; espera del padre: 30 s por ensayo. '
            'El padre comprueba entradas, salidas y limpieza. Un filtro no disponible, timeout '
            'o respuesta inesperada detiene los ensayos y conserva INCONCLUSIVE.\n\n'
            'Para contar un ensayo como coincidente, sus controles de archivo deben funcionar antes '
            'del filtro y ser denegados después. Un resultado inconcluso no acredita controles '
            'no completados. La disponibilidad previa de cada tipo de socket se registra por separado: un bloqueo '
            'preexistente no se atribuye a este filtro. Solo se mantienen los descriptores 0, 1 y 2; '
            'entrada /dev/null y salida regular o pipe.\n\n'
            'Son dos condiciones de integridad declaradas, no descubrimientos de vulnerabilidades. '
            'La verificación del expediente no vuelve a ejecutar el filtro ni autentica ejecución, '
            'host, UTC o integridad de memoria. No acredita sandbox general ni cierre de M1.\n').encode()


def create(out: Path, *, source_digest: str) -> dict:
    capture._digest(source_digest)
    capture._path(out, new=True)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'RESTRICTED_SOURCE')
    before = boundary.review(ROOT)
    files, _ = boundary._capture(ROOT)
    original = lab.inventory(files)
    need(quality.sha(canonical(original)) == before['source_inventory_sha256'] and
         original[lab.FIXED_FILE]['mode'] == '100644', 'RESTRICTED_ORIGINAL_INVENTORY')
    baseline = {**before, 'ignored_python_cache_files': 0}
    runtime = capture._runtime()
    observation = {'schema_version': 1, 'profile': PROFILE, 'experiment_id': str(uuid.uuid4()),
                   'origin': 'own_parent_process_observation', 'source_digest': source_digest,
                   'source_inventory_sha256': before['source_inventory_sha256'],
                   'worker_sha256': snapshot[WORKER], 'runtime': runtime,
                   'trials': [], 'limitations': dict(LIMITS)}
    streams = {}
    with owned_workspace.Workspace('diagnosis', excluded=(ROOT, out)) as workspace:
        work = workspace.path
        copied = work/'owned-checkout'
        lab._copy(files, copied)
        marker = work/'owned-compute-control'
        marker.write_bytes(guard.MARKER_BYTES)
        for index, (label, kind) in enumerate(lab.PLAN):
            lab._intervene(copied, files[lab.FIXED_FILE]['bytes'], kind)
            actual, _ = boundary._capture(copied)
            seen = lab.inventory(actual)
            need(seen == lab._state(original, kind), 'RESTRICTED_COPY_BEFORE')
            with (work/'stdout').open('w+b') as stdout, (work/'stderr').open('w+b') as stderr:
                mono_start, real_start = time.monotonic_ns(), time.time_ns()
                timed_out = False
                try:
                    process = owned_process.run([sys.executable, '-I', '-B', str(ROOT/'superhunter'/WORKER)],
                        cwd=work, env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=capture.WALL_SECONDS,
                        stdout=stdout, stderr=stderr)
                    returncode = process.returncode
                except subprocess.TimeoutExpired:
                    timed_out, returncode = True, None
                real_end, mono_end = time.time_ns(), time.monotonic_ns()
                for stream, file in (('stdout', stdout), ('stderr', stderr)):
                    file.seek(0)
                    value = file.read(capture.OUTPUT_BYTES+1)
                    need(len(value) <= capture.OUTPUT_BYTES, 'RESTRICTED_OUTPUT_BUDGET')
                    streams[f'trial-{index}.{stream}'] = value
            after, _ = boundary._capture(copied)
            need(lab.inventory(after) == seen and marker.read_bytes() == guard.MARKER_BYTES and
                 not (work/'owned-compute-directory-control').exists(), 'RESTRICTED_COPY_CHANGED')
            digest = quality.sha(canonical(seen))
            trial = {'index': index, 'label': label, 'intervention': kind,
                     'inventory_before_sha256': digest, 'inventory_after_sha256': digest,
                     'delta': lab._delta(original, seen), 'returncode': returncode, 'timed_out': timed_out,
                     'wall_budget_seconds': capture.WALL_SECONDS,
                     'clock': {'monotonic_start_ns': mono_start, 'monotonic_end_ns': mono_end,
                               'realtime_start_ns': real_start, 'realtime_end_ns': real_end,
                               'elapsed_ns': mono_end-mono_start, 'realtime_delta_ns': real_end-real_start,
                               'realtime_moved_backwards': real_end < real_start}}
            for stream in ('stdout', 'stderr'):
                value = streams[f'trial-{index}.{stream}']
                trial[stream+'_sha256'], trial[stream+'_bytes'] = quality.sha(value), len(value)
            observation['trials'].append(trial)
            result = analyze(observation, streams, original, baseline, source_digest=source_digest)
            if not result['checks'][-1]['expected_restricted_observation_matched']:
                break
    need(boundary.review(ROOT) == before and quality.source_snapshot() == snapshot and
         capture._runtime() == runtime, 'RESTRICTED_ORIGINAL_CHANGED')
    workspace.confirm_removed()
    write_new_bundle(out, {**streams, 'observation.json': canonical(observation),
                           'diagnosis.json': canonical(result), 'REVIEW.md': render(result)})
    return {**result, 'experiment_anchor': quality.sha(read_artifact(out, 'COMPLETE.json'))}


def verify(bundle: Path, *, source_digest: str, experiment_anchor: str) -> dict:
    capture._digest(source_digest)
    capture._digest(experiment_anchor)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'RESTRICTED_SOURCE')
    raw = lab._read(bundle)
    need(quality.sha(raw['COMPLETE.json']) == experiment_anchor, 'RESTRICTED_ANCHOR')
    before = boundary.review(ROOT)
    files, _ = boundary._capture(ROOT)
    original = lab.inventory(files)
    need(quality.sha(canonical(original)) == before['source_inventory_sha256'], 'RESTRICTED_ORIGINAL_INVENTORY')
    observation = strict_json(raw['observation.json'])
    result = analyze(observation, raw, original, {**before, 'ignored_python_cache_files': 0}, source_digest=source_digest)
    need(raw['observation.json'] == canonical(observation) and raw['diagnosis.json'] == canonical(result) and
         raw['REVIEW.md'] == render(result), 'RESTRICTED_REPORT')
    need(lab._read(bundle) == raw and quality.source_snapshot() == snapshot and boundary.review(ROOT) == before,
         'RESTRICTED_EVIDENCE_CHANGED')
    return {**result, 'experiment_anchor': experiment_anchor}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Review five fixed own snapshots under a compute syscall filter')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('check-owned-restricted-boundary')
    check = sub.add_parser('verify-owned-restricted-boundary')
    for command in (make, check):
        command.add_argument('--source-digest', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--experiment-anchor', required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    try:
        result = create(**args) if command == 'check-owned-restricted-boundary' else verify(**args)
        print(json.dumps({key: result[key] for key in (
            'status', 'source_digest', 'trials_observed', 'restricted_trials_matched', 'experiment_anchor')}, sort_keys=True))
        return 0 if result['status'] == 'OWNED_RESTRICTED_LAB_PASS' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
        print(json.dumps({'status': 'OWNED_RESTRICTED_LAB_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
