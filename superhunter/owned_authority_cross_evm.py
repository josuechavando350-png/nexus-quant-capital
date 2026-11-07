"""Corroborate fixed own temporal observations in Geth and pinned EELS.

Execution success is not application authorization. A committed call can return
false, while a one-gas probe must leave every observed state field unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from . import owned_authority_evm_cases as cases, owned_authority_review as review
from . import owned_cross_evm as previous, owned_process, quality
from .owned_spec_evm_pins import PINS
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
need, sha = cases.need, cases.sha
FILES = {'geth.json', 'eels.json', 'comparison.json', 'traces.json', 'REVIEW.md'}
WALL_SECONDS, OUTPUT_LIMIT = 180, 2 * 1024**2


def _source(digest: str) -> dict:
    need(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'AUTHORITY_CROSS_SOURCE_REFERENCE')
    snapshot = quality.source_snapshot()
    need(sha(canonical(snapshot)) == digest, 'AUTHORITY_CROSS_SOURCE_MISMATCH')
    return snapshot


def _run_worker(engine: str, solc: Path, geth: Path, digest: str) -> dict:
    need(engine in ('geth', 'execution-specs'), 'AUTHORITY_CROSS_ENGINE')
    # Only the pinned image is staged before the child enters its 20 MiB limit.
    # The existing sealed-image transport and historical engines are unchanged.
    with tempfile.TemporaryDirectory(prefix='owned-authority-') as directory:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            args = ['--solc', str(solc.resolve()), '--source-digest', digest]
            env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': directory}

            def execute(command, fds=()):
                try:
                    return owned_process.run(command, stdout=output, stderr=errors,
                        cwd=directory, env=env, pass_fds=fds, timeout=WALL_SECONDS)
                except subprocess.TimeoutExpired:
                    raise ValueError('AUTHORITY_CROSS_WORKER_TIMEOUT') from None

            cache = Path(directory) / 'cache'
            if engine == 'geth':
                with cases.compiler._sealed_executable(cases.evm.read_evm(geth)) as fd:
                    command = [sys.executable, '-I', '-B', '-X', 'pycache_prefix=' + str(cache),
                        str(ROOT / 'owned_authority_evm_worker.py'), *args,
                        '--evm', str(geth.resolve()), '--geth-fd', str(fd)]
                    proc = execute(command, (fd,))
            else:
                command = previous._python_command(cache) + [str(ROOT / 'owned_authority_spec_worker.py'), *args]
                proc = execute(command)
            output.seek(0); errors.seek(0)
            raw, err = output.read(OUTPUT_LIMIT + 1), errors.read(OUTPUT_LIMIT + 1)
            need(proc.returncode == 0 and not err and 0 < len(raw) <= OUTPUT_LIMIT,
                 'AUTHORITY_CROSS_WORKER_FAILED')
            result = strict_json(raw)
            need(type(result) is dict, 'AUTHORITY_CROSS_WORKER_SCHEMA')
            return result


def _hash(value) -> bool:
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def _execution(execution: dict, engine: str, digest: str) -> tuple[dict, dict]:
    need(type(execution) is dict and set(execution) == {'schema_version', 'profile', 'source_digest',
         'engine', 'fork', 'solc_sha256', 'builds', 'constructors', 'rows', 'compiler_runs',
         'constructor_executions', 'runtime_calls', 'geth_sha256' if engine == 'geth' else 'dependencies'},
         'AUTHORITY_CROSS_EXECUTION_SCHEMA')
    need(type(execution['schema_version']) is int and execution['schema_version'] == 1 and
         execution['profile'] == cases.PROFILE and execution['source_digest'] == digest and
         execution['engine'] == engine and execution['fork'] == 'Cancun' and
         execution['solc_sha256'] == cases.compiler.PIN['sha256'], 'AUTHORITY_CROSS_EXECUTION_IDENTITY')
    if engine == 'geth':
        need(execution['geth_sha256'] == cases.evm.PIN['sha256'], 'AUTHORITY_CROSS_TOOL_IDENTITY')
    else:
        dependencies = {name: {k: pin[k] for k in ('version', 'files', 'runtime_sha256')}
                        for name, pin in PINS.items()}
        need(canonical(execution['dependencies']) == canonical(dependencies), 'AUTHORITY_CROSS_DEPENDENCIES')
    for key, count in (('compiler_runs', 14), ('constructor_executions', 22), ('runtime_calls', 106)):
        need(type(execution[key]) is int and execution[key] == count, 'AUTHORITY_CROSS_COUNTS')
    builds, constructors, rows = execution['builds'], execution['constructors'], execution['rows']
    need(type(builds) is list and len(builds) == 14 and type(constructors) is list and
         len(constructors) == 22 and type(rows) is list and len(rows) == 106, 'AUTHORITY_CROSS_INVENTORY')
    compiled = {}
    for built, (variant, codegen) in zip(builds, [(v, c) for v in cases.model.VARIANTS for c in cases.CODEGEN]):
        need(type(built) is dict and set(built) == {'variant', 'codegen', 'source_sha256',
             'input_sha256', 'output_sha256', 'creation_sha256', 'runtime_sha256'} and
             built['variant'] == variant and built['codegen'] == codegen and
             built['source_sha256'] == sha(cases.owned_source(variant).encode()) and
             built['input_sha256'] == sha(canonical(cases.compile_input(variant, codegen))) and
             all(_hash(built[k]) for k in ('output_sha256', 'creation_sha256', 'runtime_sha256')),
             'AUTHORITY_CROSS_BUILD_IDENTITY')
        compiled[variant, codegen] = built
    projected, wrong_projection, cursor = {}, {}, 0
    for constructor, (case, codegen) in zip(constructors, cases.inventory()):
        need(type(constructor) is dict and set(constructor) ==
             {'case_id', 'codegen', 'initial_state', 'runtime_sha256'} and
             constructor['case_id'] == case['case_id'] and constructor['codegen'] == codegen and
             canonical(constructor['initial_state']) == canonical(cases.INITIAL) and
             constructor['runtime_sha256'] == compiled[case['variant'], codegen]['runtime_sha256'],
             'AUTHORITY_CROSS_CONSTRUCTOR_IDENTITY')
        previous_state = deepcopy(cases.INITIAL)
        observations, wrong = [], []
        for call_index, item in enumerate(cases.schedule(case['events'])):
            row = rows[cursor]; cursor += 1
            fields = {'case_id', 'codegen', 'call_index', 'event_index', 'probe', 'observation'}
            if engine == 'geth': fields |= {'state_root', 'stdout_sha256'}
            need(type(row) is dict and set(row) == fields and row['case_id'] == case['case_id'] and
                 row['codegen'] == codegen and type(row['call_index']) is int and row['call_index'] == call_index and
                 type(row['event_index']) is int and row['event_index'] == item['event_index'] and
                 type(row['probe']) is bool and row['probe'] == item['probe'], 'AUTHORITY_CROSS_ROW_ORDER')
            if engine == 'geth':
                need(_hash(row['state_root']) and _hash(row['stdout_sha256']), 'AUTHORITY_CROSS_OBSERVATION_HASH')
            call = row['observation']
            need(type(call) is dict and set(call) ==
                 {'before', 'after', 'word', 'gas', 'status', 'return_data'}, 'AUTHORITY_CROSS_CALL_SCHEMA')
            cases.validate_state(call['before']); cases.validate_state(call['after'])
            need(type(call['word']) is int and call['word'] == item['word'] and
                 type(call['gas']) is int and call['gas'] == item['gas'], 'AUTHORITY_CROSS_FIXED_INPUT')
            need(canonical(call['before']) == canonical(previous_state), 'AUTHORITY_CROSS_STATE_CHAIN')
            if item['probe']:
                need(call['status'] == 'OUT_OF_GAS' and call['return_data'] == '0x' and
                     canonical(call['before']) == canonical(call['after']), 'AUTHORITY_CROSS_PROBE_PERSISTED')
            else:
                accepted = call['after']['accepted'] == 1
                need(call['status'] == 'COMMITTED' and call['return_data'] == '0x' + format(int(accepted), '064x') and
                     call['before']['phase'] == item['event_index'] and
                     call['after']['phase'] == item['event_index'] + 1, 'AUTHORITY_CROSS_APPLICATION_RETURN')
                observed = {'index': item['event_index'], 'accepted': accepted,
                    'effects_before': dict(zip(cases.model.EFFECT_KEYS, call['before']['effects'])),
                    'effects_after': dict(zip(cases.model.EFFECT_KEYS, call['after']['effects']))}
                observations.append(observed)
                wrong.append({**deepcopy(observed), 'accepted': call['status'] == 'COMMITTED'})
            previous_state = call['after']
        trace = {'schema_version': 1, 'profile': cases.model.PROFILE,
                 'events': deepcopy(case['events']), 'observations': observations}
        projected[case['case_id'], codegen] = trace
        wrong_projection[case['case_id'], codegen] = {**deepcopy(trace), 'observations': wrong}
    need(cursor == len(rows), 'AUTHORITY_CROSS_UNCONSUMED_ROWS')

    def assemble(source):
        result = []
        for case in cases.corpus.cases():
            first, second = (source[case['case_id'], codegen] for codegen in cases.CODEGEN)
            need(canonical(first) == canonical(second), 'AUTHORITY_CROSS_CODEGEN_DISAGREEMENT')
            result.append({'case_id': case['case_id'], 'trace': first})
        return {'schema_version': 1, 'profile': cases.model.PROFILE, 'source_digest': digest, 'cases': result}
    return assemble(projected), assemble(wrong_projection)


def compare(geth: dict, eels: dict, digest: str) -> tuple[dict, dict]:
    _source(digest)
    traces, wrong = _execution(geth, 'geth', digest)
    other, wrong_other = _execution(eels, 'execution-specs', digest)
    semantic_rows = [{k: v for k, v in row.items() if k not in ('state_root', 'stdout_sha256')}
                     for row in geth['rows']]
    need(canonical(geth['builds']) == canonical(eels['builds']) and
         canonical(geth['constructors']) == canonical(eels['constructors']), 'AUTHORITY_CROSS_BUILD_DISAGREEMENT')
    need(canonical(semantic_rows) == canonical(eels['rows']) and canonical(traces) == canonical(other) and
         canonical(wrong) == canonical(wrong_other), 'AUTHORITY_CROSS_ENGINE_DISAGREEMENT')
    model_traces = {'schema_version': 1, 'profile': cases.model.PROFILE, 'source_digest': digest,
        'cases': [{'case_id': c['case_id'], 'trace': cases.model.simulate(c['variant'], c['events'])}
                  for c in cases.corpus.cases()]}
    need(canonical(traces) == canonical(model_traces), 'AUTHORITY_CROSS_PYTHON_MODEL_DISAGREEMENT')
    assessment, ablation = review.evaluate(traces, digest), review.evaluate(wrong, digest)
    return {'schema_version': 1, 'status': 'OWNED_AUTHORITY_CROSS_EVM_MATCH', 'profile': cases.PROFILE,
        'source_digest': digest, 'known_case_count': 11, 'known_correct_controls': 4,
        'known_defective_cases': 7, 'unique_seeded_mutations': 6, 'model_observations': 42,
        'compiler_runs_per_engine': 14, 'constructor_executions_per_engine': 22,
        'runtime_calls_per_engine': 106, 'out_of_gas_probes_per_engine': 22,
        'metrics': assessment['metrics'], 'vm_success_as_authorization_metrics': ablation['metrics']['full'],
        'missed_case_ids': assessment['missed_case_ids'],
        'all_seeded_cases_detected': assessment['all_seeded_cases_detected'],
        'observationally_equal_case_groups': assessment['observationally_equal_case_groups'],
        'semantic_rows_sha256': sha(canonical(semantic_rows)), 'traces_sha256': sha(canonical(traces)),
        'builds_sha256': sha(canonical(geth['builds'])), 'constructors_sha256': sha(canonical(geth['constructors'])),
        'solc_sha256': geth['solc_sha256'], 'geth_sha256': geth['geth_sha256'],
        'eels_dependencies': eels['dependencies'], 'fork': 'Cancun',
        'comparison_dimensions': ['constructor_runtime', 'constructor_storage', 'call_status',
                                 'persisted_storage', 'return_data', 'abstract_model_observations'],
        'distinct_evm_implementations_executed': True, 'shared_compiler_inputs_host_and_policy': True,
        'independent_producers_proved': False, 'gas_costs_compared': False, 'account_state_roots_compared': False,
        'all_evm_semantics_certified': False, 'caller_identity_authenticated': False,
        'cryptographic_credential_authentication_implemented': False,
        'labels_known_to_developers': True, 'blind_benchmark': False, 'generalization_established': False,
        'external_targets_executed': 0, 'platform_complete': False, 'vulnerability_confirmed': False}, traces


def _execute(solc: Path, geth: Path, digest: str) -> dict[str, bytes]:
    before = _source(digest)
    first = _run_worker('geth', solc, geth, digest)
    second = _run_worker('execution-specs', solc, geth, digest)
    result, traces = compare(first, second, digest)
    need(quality.source_snapshot() == before, 'AUTHORITY_CROSS_SOURCE_CHANGED_DURING_RUN')
    rows = ['# Permisos temporales propios: dos EVM', '',
        f'Código: `{digest}`.', '',
        'Once casos conocidos; cuatro controles correctos y siete casos con defectos sembrados.',
        'Las dos EVM, compilaciones, llamadas y repeticiones no amplían el número de muestras.', '',
        '| Detector | TP | TN | FP | FN |', '|---|---:|---:|---:|---:|']
    metrics = {**result['metrics'], 'vm_success_as_authorization': result['vm_success_as_authorization_metrics']}
    for name, metric in metrics.items():
        c = metric['counts']; rows.append(f"| {name} | {c['tp']} | {c['tn']} | {c['fp']} | {c['fn']} |")
    rows += ['', 'Una llamada puede terminar COMMITTED y devolver false: eso no concede autorización.',
        'Las sondas de un gas conservan estado; el siguiente intento consume el evento una sola vez.',
        'La omisión latent_revocation permanece: su secuencia no ejerce el defecto.',
        'Principales y registros abstractos: no autenticación de caller, firmas o credenciales reales.',
        'Ambas EVM comparten compilador, entradas, host y política. No se comparan gas ni raíces de cuentas.',
        'El verificador repite las dos implementaciones y compara todos los artefactos.',
        'Sin objetivos externos. Plataforma completa: NO. Avance global no determinado.', '']
    return {'geth.json': canonical(first), 'eels.json': canonical(second), 'comparison.json': canonical(result),
            'traces.json': canonical(traces), 'REVIEW.md': '\n'.join(rows).encode()}


def create(out: Path, solc: Path, geth: Path, digest: str) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'AUTHORITY_CROSS_NEW_PRIVATE_OUTPUT')
    files = _execute(solc, geth, digest)
    write_new_bundle(out, files)
    return strict_json(files['comparison.json'])


def _inventory(root: Path) -> set[str]:
    need(root.is_dir() and not root.is_symlink(), 'AUTHORITY_CROSS_BUNDLE_DIRECTORY')
    names = []
    for index, entry in enumerate(root.iterdir()):
        need(index < len(FILES) + 1, 'AUTHORITY_CROSS_BUNDLE_INVENTORY'); names.append(entry.name)
    need(set(names) == FILES | {'COMPLETE.json'}, 'AUTHORITY_CROSS_BUNDLE_INVENTORY')
    return set(names)


def verify(root: Path, solc: Path, geth: Path, digest: str) -> dict:
    _source(digest); names = _inventory(root)
    marker_raw = read_artifact(root, 'COMPLETE.json'); marker = strict_json(marker_raw)
    files = {name: read_artifact(root, name) for name in FILES}
    need(canonical(marker) == canonical({'schema_version': 1,
         'sha256': {name: sha(raw) for name, raw in files.items()}}), 'AUTHORITY_CROSS_BUNDLE_HASH')
    report = strict_json(files['comparison.json'])
    need(type(report) is dict and report.get('source_digest') == digest, 'AUTHORITY_CROSS_EXTERNAL_SOURCE')
    regenerated = _execute(solc, geth, digest)
    need(files == regenerated, 'AUTHORITY_CROSS_REPLAY_MISMATCH')
    need(all(read_artifact(root, name) == raw for name, raw in files.items()) and
         read_artifact(root, 'COMPLETE.json') == marker_raw and _inventory(root) == names,
         'AUTHORITY_CROSS_EVIDENCE_CHANGED_DURING_REPLAY')
    _source(digest)
    return strict_json(regenerated['comparison.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Compare only fixed own abstract authority cases in two EVMs')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('compare-owned-authority-engines')
    check = subs.add_parser('verify-owned-authority-engines')
    for p in (make, check):
        p.add_argument('--solc', type=Path, required=True); p.add_argument('--evm', type=Path, required=True)
        p.add_argument('--expected-source', required=True)
    make.add_argument('--out', type=Path, required=True); check.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (create(args.out, args.solc, args.evm, args.expected_source)
                  if args.command == 'compare-owned-authority-engines' else
                  verify(args.bundle, args.solc, args.evm, args.expected_source))
        print(json.dumps({'status': result['status'], 'source_digest': result['source_digest'],
            'cases': 11, 'counts': result['metrics']['full']['counts'],
            'all_seeded_cases_detected': result['all_seeded_cases_detected'],
            'vulnerability_confirmed': False}, sort_keys=True)); return 0
    except (ValueError, OSError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'status': 'OWNED_AUTHORITY_CROSS_EVM_BLOCKED', 'vulnerability_confirmed': False})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
