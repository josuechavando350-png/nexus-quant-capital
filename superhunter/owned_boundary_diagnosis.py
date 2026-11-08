"""Contrast two fixed operational faults and repairs in a disposable own copy.

Real subprocess outputs and failed attempts are retained. Verification checks
consistency, not independent execution, host attestation or general causation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from . import owned_capture as capture, owned_process, quality, repository_boundary as boundary
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'owned-boundary-fault-repair-experiment-v2'
FIXED_FILE = 'migration/source-manifest.json'
PLAN = (('baseline', 'original'), ('missing-file', 'missing'), ('restored-file', 'original'),
        ('changed-mode', 'executable'), ('restored-mode', 'original'))
REJECTION = {'status': 'OWNED_BOUNDARY_TRIAL_REJECTED', 'reason': 'HISTORICAL_TREE_CHANGED'}
BASE_FILES = {'observation.json', 'diagnosis.json', 'REVIEW.md'}
LIMITS = {**capture.LIMITS, 'general_causation_proved': False, 'vulnerability_confirmed': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def inventory(files: dict) -> dict:
    return {name: {'mode': item['mode'], 'sha256': quality.sha(item['bytes'])}
            for name, item in sorted(files.items())}


def _state(original: dict, kind: str) -> dict:
    result = dict(original)
    if kind == 'missing':
        del result[FIXED_FILE]
    elif kind == 'executable':
        result[FIXED_FILE] = {**result[FIXED_FILE], 'mode': '100755'}
    else:
        need(kind == 'original', 'DIAGNOSIS_FIXED_STATE')
    return result


def _delta(original: dict, current: dict) -> list[dict]:
    return [{'path': name, 'before': original.get(name), 'after': current.get(name)}
            for name in sorted(set(original) | set(current)) if original.get(name) != current.get(name)]


def _copy(files: dict, destination: Path) -> None:
    destination.mkdir(mode=0o700)
    for name, item in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(item['bytes'])
        path.chmod(0o755 if item['mode'] == '100755' else 0o644)


def _intervene(root: Path, original: bytes, kind: str) -> None:
    # Only this hard-coded file in our newly created private copy is changed.
    path = root / FIXED_FILE
    if path.exists() or path.is_symlink():
        need(stat.S_ISREG(path.lstat().st_mode), 'DIAGNOSIS_COPY_FILE_TYPE')
        path.unlink()
    if kind != 'missing':
        need(kind in ('original', 'executable'), 'DIAGNOSIS_FIXED_STATE')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(original)
        path.chmod(0o755 if kind == 'executable' else 0o644)


def _files(count: int) -> set[str]:
    return BASE_FILES | {f'trial-{index}.{stream}' for index in range(count) for stream in ('stdout', 'stderr')}


def _read(root: Path) -> dict[str, bytes]:
    capture._path(root, new=False)
    names = set()
    allowed = _files(len(PLAN)) | {'COMPLETE.json'}
    for index, entry in enumerate(root.iterdir()):
        need(index < len(allowed) and entry.name in allowed, 'DIAGNOSIS_INVENTORY')
        names.add(entry.name)
    need(BASE_FILES | {'COMPLETE.json'} <= names, 'DIAGNOSIS_INVENTORY')
    raw = {name: read_artifact(root, name) for name in names}
    observation = strict_json(raw['observation.json'])
    trials = observation.get('trials')
    need(type(trials) is list and 1 <= len(trials) <= len(PLAN), 'DIAGNOSIS_TRIAL_COUNT')
    need(names == _files(len(trials)) | {'COMPLETE.json'}, 'DIAGNOSIS_INVENTORY')
    for name in names - BASE_FILES - {'COMPLETE.json'}:
        need(len(raw[name]) <= capture.OUTPUT_BYTES, 'DIAGNOSIS_STREAM_BUDGET')
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(raw[name]) for name in names - {'COMPLETE.json'}}}
    need(raw['COMPLETE.json'] == canonical(marker), 'DIAGNOSIS_MANIFEST')
    return raw


def analyze(observation: dict, raw: dict[str, bytes], original: dict, baseline: dict, *, source_digest: str) -> dict:
    fields = {'schema_version', 'profile', 'experiment_id', 'origin', 'source_digest',
              'source_inventory_sha256', 'worker_sha256', 'runtime', 'trials', 'limitations'}
    need(type(observation) is dict and set(observation) == fields, 'DIAGNOSIS_SCHEMA')
    need(type(observation['schema_version']) is int and observation['schema_version'] == 2 and
         observation['profile'] == PROFILE and observation['origin'] == 'own_parent_process_observation', 'DIAGNOSIS_ORIGIN')
    identity = observation['experiment_id']
    need(type(identity) is str and str(uuid.UUID(identity)) == identity and uuid.UUID(identity).version == 4,
         'DIAGNOSIS_ID')
    need(observation['source_digest'] == source_digest and
         observation['source_inventory_sha256'] == quality.sha(canonical(original)) and
         observation['worker_sha256'] == quality.sha(read_artifact(ROOT / 'superhunter', 'owned_boundary_trial_worker.py')),
         'DIAGNOSIS_SOURCE')
    runtime = observation['runtime']
    need(type(runtime) is dict and set(runtime) == {'executable_sha256', 'python'}, 'DIAGNOSIS_RUNTIME')
    capture._digest(runtime['executable_sha256'])
    need(type(runtime['python']) is str and len(runtime['python']) <= 16 and
         len(runtime['python'].split('.')) == 3 and all(p.isascii() and p.isdigit() for p in runtime['python'].split('.')),
         'DIAGNOSIS_RUNTIME')
    need(canonical(observation['limitations']) == canonical(LIMITS), 'DIAGNOSIS_LIMITATIONS')
    trials = observation['trials']
    need(type(trials) is list and 1 <= len(trials) <= len(PLAN), 'DIAGNOSIS_TRIAL_COUNT')
    checks = []; previous_end = None
    for index, trial in enumerate(trials):
        label, kind = PLAN[index]
        fields = {'index', 'label', 'intervention', 'inventory_before_sha256', 'inventory_after_sha256',
                  'delta', 'returncode', 'timed_out', 'stdout_sha256', 'stderr_sha256', 'stdout_bytes',
                  'stderr_bytes', 'wall_budget_seconds', 'clock'}
        need(type(trial) is dict and set(trial) == fields, 'DIAGNOSIS_TRIAL_SCHEMA')
        need(type(trial['index']) is int and trial['index'] == index and trial['label'] == label and
             trial['intervention'] == kind, 'DIAGNOSIS_TRIAL_ORDER')
        state = _state(original, kind); digest = quality.sha(canonical(state))
        need(trial['inventory_before_sha256'] == digest == trial['inventory_after_sha256'] and
             canonical(trial['delta']) == canonical(_delta(original, state)), 'DIAGNOSIS_INTERVENTION')
        need(type(trial['timed_out']) is bool and
             ((trial['timed_out'] and trial['returncode'] is None) or
              (not trial['timed_out'] and type(trial['returncode']) is int and -64 <= trial['returncode'] <= 255)),
             'DIAGNOSIS_EXIT')
        need(type(trial['wall_budget_seconds']) is int and trial['wall_budget_seconds'] == capture.WALL_SECONDS,
             'DIAGNOSIS_BUDGET')
        capture._clock_check(trial['clock'])
        need(previous_end is None or previous_end <= trial['clock']['monotonic_start_ns'], 'DIAGNOSIS_CLOCK_ORDER')
        previous_end = trial['clock']['monotonic_end_ns']
        for stream in ('stdout', 'stderr'):
            value = raw[f'trial-{index}.{stream}']
            need(len(value) <= capture.OUTPUT_BYTES and trial[stream + '_sha256'] == quality.sha(value) and
                 type(trial[stream + '_bytes']) is int and trial[stream + '_bytes'] == len(value), 'DIAGNOSIS_STREAM')
        expected = canonical(baseline if kind == 'original' else REJECTION)
        match = (not trial['timed_out'] and trial['returncode'] == (0 if kind == 'original' else 2) and
                 raw[f'trial-{index}.stdout'] == expected and raw[f'trial-{index}.stderr'] == b'')
        checks.append({'label': label, 'expected_observation_matched': match,
                       'returncode': trial['returncode'], 'timed_out': trial['timed_out']})
        # Acquisition stops at the first unexpected result. No later repair can hide it.
        need(match or index == len(trials) - 1, 'DIAGNOSIS_CONTINUED_AFTER_FAILURE')
    complete = len(trials) == len(PLAN) and all(row['expected_observation_matched'] for row in checks)
    findings, remediation = _remediation(trials, original) if complete else ([], [])
    return {'schema_version': 2, 'profile': PROFILE, 'experiment_id': identity,
            'status': 'OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB' if complete else 'OWNED_FAULT_DIAGNOSIS_INCONCLUSIVE',
            'source_digest': source_digest, 'trials_observed': len(trials), 'trials_required': len(PLAN),
            'checks': checks, 'hypotheses': {
                'missing_file_rejection_reversed_by_restoration': 'SUPPORTED_IN_FIXED_LAB' if complete else 'INCONCLUSIVE',
                'mode_rejection_reversed_by_restoration': 'SUPPORTED_IN_FIXED_LAB' if complete else 'INCONCLUSIVE',
                'error_code_alone_identifies_missing_file': 'REFUTED_IN_FIXED_LAB' if complete else 'INCONCLUSIVE',
                'content_change_required_for_rejection': 'REFUTED_IN_FIXED_LAB' if complete else 'INCONCLUSIVE'},
            'operational_findings': findings, 'remediation_plan': remediation,
            'remediation_execution_enabled': False, 'current_target_state_checked': False,
            'human_approval_recorded': False, 'limitations': dict(LIMITS)}


def _remediation(trials: list[dict], original: dict) -> tuple[list[dict], list[dict]]:
    """Derive two bounded operational findings only after all five checks pass.

    This is a plan for a fresh own lab copy. It contains no runnable commands,
    target path argument, repair executor or assertion about a live filesystem.
    """
    expected = dict(original[FIXED_FILE])
    findings = []; actions = []
    for number, identity, cause, operation in (
        (1, 'missing-fixed-manifest', 'EXPECTED_FILE_ABSENT', 'RESTORE_REVIEWED_FILE_BYTES_AND_MODE'),
        (3, 'changed-fixed-mode', 'EXPECTED_GIT_MODE_CHANGED', 'RESTORE_REVIEWED_GIT_MODE'),
    ):
        fault, restored = trials[number], trials[number + 1]
        evidence = []
        for row in (trials[0], fault, restored):
            evidence.append({key: row[key] for key in (
                'index', 'label', 'returncode', 'stdout_sha256', 'stderr_sha256',
                'inventory_before_sha256', 'inventory_after_sha256', 'clock')})
        findings.append({'id': identity, 'kind': 'OWNED_OPERATIONAL_INTEGRITY_FAILURE',
                         'subject': {'relative_path': FIXED_FILE, 'expected': dict(expected)},
                         'cause_supported_in_fixed_lab': cause, 'observed_delta': fault['delta'],
                         'effect': 'HISTORICAL_BOUNDARY_REVIEW_REJECTED', 'evidence': evidence,
                         'restoration_observed_in_same_lab': True, 'security_severity': None,
                         'incident_confirmed': False, 'vulnerability_confirmed': False})
        actions.append({'finding_id': identity, 'scope': 'FRESH_OWNED_LAB_COPY_ONLY',
                        'operation': operation, 'relative_path': FIXED_FILE,
                        'expected_after': dict(expected), 'execution_enabled': False,
                        'human_review_required': True, 'live_preconditions_checked': False,
                        'preconditions': ['RECHECK_CURRENT_COPY_IDENTITY', 'PRESERVE_CURRENT_COPY_BEFORE_CHANGE',
                                          'VERIFY_REVIEWED_BASELINE_BYTES_AND_MODE', 'RECONFIRM_SPECIFIC_DELTA'],
                        'postconditions': {'full_inventory_sha256': restored['inventory_after_sha256'],
                                           'boundary_stdout_sha256': restored['stdout_sha256'],
                                           'returncode': 0, 'no_unrelated_inventory_delta': True},
                        'stop_if': ['CURRENT_STATE_DIFFERS_FROM_REVIEWED_DELTA', 'BASELINE_NOT_VERIFIABLE',
                                    'UNRELATED_FILE_OR_MODE_CHANGES', 'BOUNDARY_REVIEW_DOES_NOT_MATCH_BASELINE'],
                        'on_failure': 'STOP_AND_RETAIN_NEW_EVIDENCE_WITHOUT_PROMOTING_SUCCESS'})
    return findings, actions


def render(result: dict) -> bytes:
    text = (f"# Diagnóstico operativo propio\n\nEstado: {result['status']}.\n"
            f"Ensayos observados: {result['trials_observed']}/{result['trials_required']}.\n\n"
            'Se interviene solo una copia temporal propia; nunca se ejecuta código copiado.\n'
            'Se conserva stdout, stderr privado, terminación y reloj de cada proceso.\n'
            'Un resultado inesperado o timeout detiene el experimento y conserva INCONCLUSIVE.\n'
            'Los dos fallos esperados comparten código de error: el código solo no identifica la causa.\n'
            'Las conclusiones dependen de intervenciones y controles de restauración de este laboratorio.\n'
            'Verificar bytes no autentica productor, ejecución, host, UTC ni causalidad general.\n')
    if not result['operational_findings']:
        text += '\nEl diagnóstico está inconcluso: no se emiten findings operativos ni planes de corrección.\n'
    else:
        text += '\n## Findings operativos y corrección propuesta\n\n'
        for finding, action in zip(result['operational_findings'], result['remediation_plan']):
            expected = finding['subject']['expected']
            trial_ids = ', '.join(str(row['index']) for row in finding['evidence'])
            text += (f"- {finding['id']}: {finding['cause_supported_in_fixed_lab']}. "
                     f"Evidencia en ensayos {trial_ids}. Archivo relativo: {FIXED_FILE}. "
                     f"Referencia SHA256 {expected['sha256']}, modo Git {expected['mode']}. "
                     f"Operación propuesta: {action['operation']}.\n")
        text += ('\nAntes de actuar: revisar una copia propia nueva, preservar su estado y verificar la referencia. '
                 'Una diferencia distinta de la observada exige detenerse y adquirir evidencia nueva. '
                 'Después: inventario completo y salida del revisor deben coincidir con el baseline, '
                 'sin cambios ajenos. La restauración observada pertenece solo al experimento temporal.\n'
                 'El plan requiere revisión humana y no ejecuta correcciones. No comprueba el estado actual '
                 'de ningún destino ni autoriza cambios en el checkout original. '
                 'Estos findings son fallos operativos de laboratorio, sin severidad de seguridad ni incidente confirmado.\n')
    return text.encode()


def create(out: Path, *, source_digest: str) -> dict:
    capture._digest(source_digest); capture._path(out, new=True)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'DIAGNOSIS_SOURCE')
    before = boundary.review(ROOT); files, _ = boundary._capture(ROOT)
    original = inventory(files)
    need(quality.sha(canonical(original)) == before['source_inventory_sha256'] and
         original[FIXED_FILE]['mode'] == '100644', 'DIAGNOSIS_ORIGINAL_INVENTORY')
    baseline = {**before, 'ignored_python_cache_files': 0}
    runtime = capture._runtime()
    observation = {'schema_version': 2, 'profile': PROFILE, 'experiment_id': str(uuid.uuid4()),
                   'origin': 'own_parent_process_observation', 'source_digest': source_digest,
                   'source_inventory_sha256': before['source_inventory_sha256'],
                   'worker_sha256': snapshot['owned_boundary_trial_worker.py'], 'runtime': runtime,
                   'trials': [], 'limitations': dict(LIMITS)}
    streams = {}
    with tempfile.TemporaryDirectory(prefix='superhunter-owned-fault-') as name:
        work = Path(name); copied = work / 'owned-checkout'; _copy(files, copied)
        for index, (label, kind) in enumerate(PLAN):
            _intervene(copied, files[FIXED_FILE]['bytes'], kind)
            actual, _ = boundary._capture(copied); seen = inventory(actual)
            need(seen == _state(original, kind), 'DIAGNOSIS_COPY_BEFORE')
            with (work / 'stdout').open('w+b') as stdout, (work / 'stderr').open('w+b') as stderr:
                mono_start = time.monotonic_ns(); real_start = time.time_ns()
                timed_out = False
                try:
                    process = owned_process.run([sys.executable, '-I', '-B', str(ROOT / 'superhunter' / 'owned_boundary_trial_worker.py')],
                        cwd=work, env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=capture.WALL_SECONDS,
                        stdout=stdout, stderr=stderr)
                    returncode = process.returncode
                except subprocess.TimeoutExpired:
                    timed_out = True; returncode = None
                real_end = time.time_ns(); mono_end = time.monotonic_ns()
                for stream, file in (('stdout', stdout), ('stderr', stderr)):
                    file.seek(0); value = file.read(capture.OUTPUT_BYTES + 1)
                    need(len(value) <= capture.OUTPUT_BYTES, 'DIAGNOSIS_OUTPUT_BUDGET')
                    streams[f'trial-{index}.{stream}'] = value
            after_files, _ = boundary._capture(copied)
            need(inventory(after_files) == seen, 'DIAGNOSIS_COPY_CHANGED')
            digest = quality.sha(canonical(seen))
            trial = {'index': index, 'label': label, 'intervention': kind,
                     'inventory_before_sha256': digest, 'inventory_after_sha256': digest,
                     'delta': _delta(original, seen), 'returncode': returncode, 'timed_out': timed_out,
                     'wall_budget_seconds': capture.WALL_SECONDS,
                     'clock': {'monotonic_start_ns': mono_start, 'monotonic_end_ns': mono_end,
                               'realtime_start_ns': real_start, 'realtime_end_ns': real_end,
                               'elapsed_ns': mono_end - mono_start, 'realtime_delta_ns': real_end - real_start,
                               'realtime_moved_backwards': real_end < real_start}}
            for stream in ('stdout', 'stderr'):
                value = streams[f'trial-{index}.{stream}']
                trial[stream + '_sha256'] = quality.sha(value); trial[stream + '_bytes'] = len(value)
            observation['trials'].append(trial)
            result = analyze(observation, streams, original, baseline, source_digest=source_digest)
            if not result['checks'][-1]['expected_observation_matched']:
                break
    need(boundary.review(ROOT) == before and quality.source_snapshot() == snapshot and capture._runtime() == runtime,
         'DIAGNOSIS_ORIGINAL_CHANGED')
    write_new_bundle(out, {**streams, 'observation.json': canonical(observation),
                           'diagnosis.json': canonical(result), 'REVIEW.md': render(result)})
    return {**result, 'experiment_anchor': quality.sha(read_artifact(out, 'COMPLETE.json'))}


def verify(bundle: Path, *, source_digest: str, experiment_anchor: str) -> dict:
    capture._digest(source_digest); capture._digest(experiment_anchor)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'DIAGNOSIS_SOURCE')
    raw = _read(bundle)
    need(quality.sha(raw['COMPLETE.json']) == experiment_anchor, 'DIAGNOSIS_ANCHOR')
    before = boundary.review(ROOT); files, _ = boundary._capture(ROOT)
    original = inventory(files)
    need(quality.sha(canonical(original)) == before['source_inventory_sha256'], 'DIAGNOSIS_ORIGINAL_INVENTORY')
    observation = strict_json(raw['observation.json'])
    result = analyze(observation, raw, original, {**before, 'ignored_python_cache_files': 0}, source_digest=source_digest)
    need(raw['observation.json'] == canonical(observation) and raw['diagnosis.json'] == canonical(result) and
         raw['REVIEW.md'] == render(result), 'DIAGNOSIS_REPORT')
    need(_read(bundle) == raw and quality.source_snapshot() == snapshot and boundary.review(ROOT) == before,
         'DIAGNOSIS_EVIDENCE_CHANGED')
    return {**result, 'experiment_anchor': experiment_anchor}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Observe two fixed own operational faults and repairs')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('diagnose-owned-boundary'); check = sub.add_parser('verify-owned-boundary-diagnosis')
    for command in (make, check): command.add_argument('--source-digest', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True); check.add_argument('--experiment-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'diagnose-owned-boundary' else verify(**args)
        summary = {key: result[key] for key in ('status', 'trials_observed', 'experiment_anchor')}
        summary.update(operational_findings=len(result['operational_findings']),
                       remediation_actions=len(result['remediation_plan']), remediation_execution_enabled=False)
        print(json.dumps(summary, sort_keys=True))
        return 0 if result['status'] == 'OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError, subprocess.SubprocessError):
        print(json.dumps({'status': 'OWNED_FAULT_DIAGNOSIS_REJECTED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
