"""Replay pinned native compilations before reviewing their storage layout.

This closes the source -> solc -> AST/layout -> profile-v4 review circuit.
It compiles only; it does not execute contracts, approve upgrades, authenticate
repository ownership or discover exploits. Verification re-runs the SAME solc,
not an independently implemented compiler or a remote attestation service.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

from . import compiler_layout as binding, native_compile as compiler
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SIDES = ('before', 'after')
COMPILE_FILES = compiler.FILES | {'COMPLETE.json'}
PACKED = {side + '--' + name for side in SIDES for name in COMPILE_FILES}
OUTPUT_FILES = (PACKED | {'layout--' + name for name in binding.FILES} |
                {'expected.json', 'result.json', 'audit.json', 'REVIEW.md'})
MAX_TOTAL = 32_000_000


class NativeLayoutError(ValueError):
    """Fixed diagnostics, without supplied paths or source content."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise NativeLayoutError(code)


def validate_expected(value: object) -> dict:
    need(type(value) is dict and set(value) == {
        'schema_version', 'repo', 'source', 'contract', 'before', 'after'}, 'REFERENCE_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1, 'REFERENCE_VERSION')
    for side in SIDES:
        row = value[side]
        need(type(row) is dict and set(row) == {'commit', 'input_sha256'}, 'REFERENCE_SIDE')
    # Reuse the existing strict identities, but do not accept supplied outputs,
    # claimed compiler versions or a weaker layout profile.
    projected = {**value, 'schema_version': 4}
    for side in SIDES:
        projected[side] = {**value[side], 'compiler_version': '0.8.30', 'output_sha256': '0' * 64}
    binding.validate_manifest(projected)
    return strict_json(canonical(value))


def _reference(path: Path, bundle: Path) -> bytes:
    need(not path.resolve().is_relative_to(bundle.resolve()), 'EXTERNAL_REFERENCE_REQUIRED')
    raw = read_artifact(path.parent, path.name)
    validate_expected(strict_json(raw))
    return raw


def _engine() -> dict:
    names = sorted(set(('native_layout.py', *compiler.CODE_FILES, *binding.CODE_FILES)))
    return {'sha256': {name: compiler.sha(read_artifact(ROOT, name)) for name in names},
            'native_sources': source_inventory()}


def _capture(root: Path, expected_hash: str) -> dict[str, bytes]:
    need(not root.is_symlink(), 'COMPILATION_ROOT_SYMLINK')
    first = compiler._read_bundle(root, expected_input_sha256=expected_hash)
    marker = read_artifact(root, 'COMPLETE.json')
    second = compiler._read_bundle(root, expected_input_sha256=expected_hash)
    need(first == second and marker == read_artifact(root, 'COMPLETE.json'), 'COMPILATION_CHANGED')
    return {**first, 'COMPLETE.json': marker}


def _replay_pair(expected: dict, packed: dict[str, bytes], binary: Path) -> tuple[dict, dict[str, bytes]]:
    need(set(packed) == PACKED and all(type(v) is bytes and len(v) <= 2_000_000
                                      for v in packed.values()), 'COMPILATION_FILE_SET')
    need(sum(map(len, packed.values())) <= MAX_TOTAL, 'COMPILATION_TOTAL_LIMIT')
    replays, inputs = {}, {}
    with tempfile.TemporaryDirectory(prefix='sh-native-layout-') as temp:
        parent = Path(temp)
        for side in SIDES:
            root = parent / side
            root.mkdir(mode=0o700)
            for name in sorted(COMPILE_FILES):
                path = root / name
                with path.open('xb') as stream:
                    stream.write(packed[side + '--' + name])
                path.chmod(0o600)
            # This is intentionally mandatory, including during verification.
            replay = compiler.replay_bundle(root, binary, expected_input_sha256=expected[side]['input_sha256'])
            need(replay.get('status') == 'COMPILATION_REPLAY_MATCH' and
                 replay.get('compilation_status') == 'SOLC_COMPILATION_COMPLETED' and
                 replay.get('same_compiler_reexecuted') is True and
                 replay.get('independent_compiler') is False and
                 replay.get('compiler_sha256') == compiler.PIN['sha256'] and
                 replay.get('input_sha256') == expected[side]['input_sha256'], 'SUCCESSFUL_REPLAY_REQUIRED')
            replays[side] = replay
            for kind in ('input', 'output'):
                inputs[side + '-' + kind + '.json'] = packed[side + '--' + kind + '.json']
    return replays, inputs


def render(result: dict) -> bytes:
    return ('# Revisión de almacenamiento con compilación nativa reproducida\n\n'
            f"Estado: {result['status']}. Perfil de artefactos: v4.\n"
            f"Compilador: {compiler.PIN['version']}.\n"
            'Antes de comparar, se reejecutaron las dos entradas con el compilador fijado.\n'
            'Se exigió coincidencia exacta de salida y diagnósticos con cada paquete.\n'
            f"Cambios estructurales: {result['structural_change_count']}.\n\n"
            'Es reproducción con el mismo compilador, no dos compiladores independientes.\n'
            'No autentica commits remotos, ejecución histórica de un tercero o autorización.\n'
            'No ejecuta una EVM ni confirma vulnerabilidades ni seguridad de una actualización.\n'
            'El paquete completo contiene fuentes y diagnósticos privados.\n').encode()


def _documents(reference_raw: bytes, packed: dict[str, bytes], binary: Path) -> dict[str, bytes]:
    expected = validate_expected(strict_json(reference_raw))
    engine = _engine()
    replays, inputs = _replay_pair(expected, packed, binary)
    m = {**expected, 'schema_version': 4}
    for side in SIDES:
        m[side] = {**expected[side], 'compiler_version': '0.8.30',
                   'output_sha256': compiler.sha(inputs[side + '-output.json'])}
    derived = binding._documents(canonical(m), inputs)
    review = strict_json(derived['result.json'])
    states = {
        'SOURCE_LAYOUT_PRESERVED_IN_PROFILE': 'NATIVE_LAYOUT_PRESERVED_IN_PROFILE',
        'SOURCE_LAYOUT_CHANGE_DETECTED': 'NATIVE_LAYOUT_CHANGE_DETECTED',
        'SOURCE_LAYOUT_REVIEW_REQUIRED': 'NATIVE_LAYOUT_REVIEW_REQUIRED',
    }
    need(review['status'] in states, 'LAYOUT_STATE_UNSUPPORTED')
    result = {
        'schema_version': 1, 'status': states[review['status']], 'profile': 'pinned-solc-layout-v1',
        'reference_sha256': compiler.sha(canonical(expected)), 'engine': engine,
        'compilation_manifest_sha256': {side: compiler.sha(packed[side + '--COMPLETE.json']) for side in SIDES},
        'replays': replays, 'layout_result_sha256': compiler.sha(derived['result.json']),
        'layout_status': review['status'], 'structural_change_count': len(review['layout_review']['changes']),
        'native_compiler_reexecuted': True, 'independent_compiler': False,
        'remote_producer_authenticated': False, 'repository_commits_authenticated': False,
        'executed_contracts': False, 'upgrade_authorized': False, 'vulnerability_confirmed': False,
        'human_review_required': True,
    }
    audit = load_components().audit.AuditLog(clock=lambda: '1970-01-01T00:00:00+00:00')
    for side in SIDES:
        audit.append('native_layout.replay', {'side': side, 'replay_sha256': compiler.sha(canonical(replays[side])),
                                             'manifest_sha256': result['compilation_manifest_sha256'][side]})
    audit.append('native_layout.result', {'result_sha256': compiler.sha(canonical(result))})
    audit.assert_intact()
    need(engine == _engine(), 'ENGINE_CHANGED')
    files = {**packed, **{'layout--' + name: raw for name, raw in derived.items()},
             'expected.json': reference_raw, 'result.json': canonical(result),
             'audit.json': canonical({'entries': [asdict(e) for e in audit.entries],
                                      'clock_semantics': 'fixed-reference-not-attestation'}),
             'REVIEW.md': render(result)}
    need(set(files) == OUTPUT_FILES and all(len(v) <= 2_000_000 for v in files.values()) and
         sum(map(len, files.values())) <= MAX_TOTAL, 'OUTPUT_LIMIT')
    return files


def create(expected_path: Path, before: Path, after: Path, binary: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_IN_CHECKOUT')
    reference = _reference(expected_path, out)
    expected = validate_expected(strict_json(reference))
    paths = {'before': before, 'after': after}
    original = {side: read_artifact(path.parent, path.name) for side, path in paths.items()}
    for side, raw in original.items():
        need(compiler.sha(raw) == expected[side]['input_sha256'], 'EXTERNAL_INPUT_MISMATCH')
        compiler.validate_input(raw)
    compiler.read_pinned_binary(binary)  # Fail before compilation if unavailable/mismatched.
    packed = {}
    with tempfile.TemporaryDirectory(prefix='sh-native-pair-') as tmp:
        parent = Path(tmp)
        for side in SIDES:
            path = parent / (side + '-input.json')
            path.write_bytes(original[side]); path.chmod(0o600)
            compiled = parent / side
            receipt = compiler.compile_bundle(path, binary, compiled)
            need(receipt['status'] == 'SOLC_COMPILATION_COMPLETED', 'COMPILATION_UNSUCCESSFUL')
            packed.update({side + '--' + name: raw for name, raw in
                           _capture(compiled, expected[side]['input_sha256']).items()})
    docs = _documents(reference, packed, binary)
    need(_reference(expected_path, out) == reference and all(
        read_artifact(path.parent, path.name) == original[side] for side, path in paths.items()), 'INPUT_CHANGED')
    write_new_bundle(out, docs)
    # Read-back verifies written bytes; callers can independently use verify-native-layout,
    # which performs mandatory fresh native recompilations, not just hash validation.
    need(all(read_artifact(out, name) == raw for name, raw in docs.items()), 'OUTPUT_CHANGED')
    return strict_json(docs['result.json'])


def verify(root: Path, expected_path: Path, binary: Path) -> dict:
    need(not root.is_symlink(), 'ROOT_SYMLINK')
    reference = _reference(expected_path, root)
    marker_raw = read_artifact(root, 'COMPLETE.json')
    marker = strict_json(marker_raw)
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and
         set(marker['sha256']) == OUTPUT_FILES and
         {p.name for p in root.iterdir()} == OUTPUT_FILES | {'COMPLETE.json'}, 'BUNDLE_INVENTORY')
    files, total = {}, 0
    for name in sorted(OUTPUT_FILES):
        raw = read_artifact(root, name); total += len(raw)
        need(total <= MAX_TOTAL and compiler.sha(raw) == marker['sha256'][name], 'BUNDLE_HASH_OR_LIMIT')
        files[name] = raw
    need(canonical(strict_json(files['expected.json'])) == canonical(strict_json(reference)), 'EXTERNAL_REFERENCE_MISMATCH')
    recalculated = _documents(files['expected.json'], {name: files[name] for name in PACKED}, binary)
    need(files == recalculated, 'NATIVE_REVIEW_MISMATCH')
    need(read_artifact(root, 'COMPLETE.json') == marker_raw and _reference(expected_path, root) == reference and
         all(read_artifact(root, name) == raw for name, raw in files.items()), 'BUNDLE_CHANGED')
    return strict_json(files['result.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Replay the fixed native compiler, then review storage; never execute contracts')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-native-layout')
    for name in ('expected', 'before-input', 'after-input', 'binary', 'out'):
        make.add_argument('--' + name, type=Path, required=True)
    check = sub.add_parser('verify-native-layout')
    for name in ('expected', 'binary', 'bundle'):
        check.add_argument('--' + name, type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        r = (create(a.expected, a.before_input, a.after_input, a.binary, a.out)
             if a.command == 'review-native-layout' else verify(a.bundle, a.expected, a.binary))
        print(json.dumps({k: r[k] for k in ('status', 'native_compiler_reexecuted', 'structural_change_count',
                                           'executed_contracts', 'vulnerability_confirmed')}))
        return 0 if r['status'] == 'NATIVE_LAYOUT_PRESERVED_IN_PROFILE' else 1
    except compiler.CompilerUnavailable:
        print(json.dumps({'status': 'NATIVE_LAYOUT_BLOCKED', 'compiler_execution_verified': False})); return 3
    except (ValueError, OSError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'status': 'NATIVE_LAYOUT_REJECTED', 'compiler_execution_verified': False})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
