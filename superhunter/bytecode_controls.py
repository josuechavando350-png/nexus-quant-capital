"""Compile fixed owned controls to creation/runtime bytecode and bind CHC evidence.

No EVM, deployment, RPC, arbitrary source or exploit target is accepted. Replay
regenerates every source and re-executes solc/Z3. Source-level proofs are NOT
promoted to bytecode-level guarantees. The EVM stage remains explicitly pending.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from . import native_compile as compiler, solidity_stateful as formal
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = {'formal.json', 'builds.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE = ('bytecode_controls.py', 'solidity_stateful.py', 'smt_backend.py',
        'native_compile.py', 'solc_worker.py', 'native_runtime.py', 'safe_io.py')
CONTRACT = 'StatefulConservation'
SOURCE_FILE = 'State.sol'
EXPECTED_ABI = [{'inputs': [{'internalType': 'uint8', 'name': 'quantity', 'type': 'uint8'}],
                 'name': 'move', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}]
OUTPUTS = ['abi', 'storageLayout', 'metadata', 'evm.bytecode.object',
           'evm.bytecode.linkReferences', 'evm.deployedBytecode.object',
           'evm.deployedBytecode.linkReferences', 'evm.deployedBytecode.immutableReferences',
           'evm.methodIdentifiers']
MAX_OBJECT_BYTES = 32_000  # Local artifact budget, not a claim about protocol limits.


class BytecodeBuildError(ValueError):
    """Fixed codes only; no supplied paths or source text in public diagnostics."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise BytecodeBuildError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_input(name: str) -> dict:
    # Reuse EXACTLY the property source from the existing fixed CHC controls.
    inp = formal.fixed_input(name, 'property')
    inp['settings']['modelChecker'] = {'engine': 'none'}
    inp['settings']['outputSelection'] = {'*': {'': ['ast'], '*': list(OUTPUTS)}}
    return inp


def _object(value: object, code: str) -> bytes:
    need(type(value) is str and 0 < len(value) <= 2 * MAX_OBJECT_BYTES and
         len(value) % 2 == 0 and re.fullmatch('[0-9a-f]+', value) is not None, code)
    return bytes.fromhex(value)


def inspect_output(name: str, raw: bytes) -> dict:
    """Check the bounded profile of freshly compiled own controls, not arbitrary code."""
    inp = build_input(name)
    info = compiler.classify_output(inp, raw)
    need(info['status'] == 'SOLC_COMPILATION_COMPLETED', 'BYTECODE_COMPILATION_FAILED')
    data = strict_json(raw)
    contracts = data['contracts']
    need(set(contracts) == {SOURCE_FILE} and set(contracts[SOURCE_FILE]) == {CONTRACT},
         'FIXED_CONTRACT_SET_REQUIRED')
    contract = contracts[SOURCE_FILE][CONTRACT]
    need(canonical(contract.get('abi')) == canonical(EXPECTED_ABI), 'FIXED_ABI_REQUIRED')
    evm = contract.get('evm')
    need(type(evm) is dict and set(evm) == {'bytecode', 'deployedBytecode', 'methodIdentifiers'},
         'EVM_ARTIFACT_SET')
    creation, runtime = evm['bytecode'], evm['deployedBytecode']
    need(type(creation) is dict and set(creation) == {'object', 'linkReferences'}, 'CREATION_SCHEMA')
    need(type(runtime) is dict and set(runtime) == {'object', 'linkReferences', 'immutableReferences'},
         'RUNTIME_SCHEMA')
    need(creation['linkReferences'] == {} and runtime['linkReferences'] == {} and
         runtime['immutableReferences'] == {}, 'NO_LINK_OR_IMMUTABLE_PATCHES')
    init = _object(creation['object'], 'CREATION_BYTECODE_REQUIRED')
    code = _object(runtime['object'], 'RUNTIME_BYTECODE_REQUIRED')
    methods = evm['methodIdentifiers']
    need(type(methods) is dict and set(methods) == {'move(uint8)'} and
         type(methods['move(uint8)']) is str and re.fullmatch('[0-9a-f]{8}', methods['move(uint8)']) is not None,
         'METHOD_IDENTIFIER_PROFILE')
    metadata = strict_json(contract.get('metadata', ''))
    need(metadata.get('compiler', {}).get('version') == compiler.PIN['version'], 'METADATA_COMPILER')
    settings = metadata.get('settings', {})
    need(settings.get('compilationTarget') == {SOURCE_FILE: CONTRACT} and
         settings.get('evmVersion') == inp['settings']['evmVersion'] and
         settings.get('optimizer', {}).get('enabled') is False, 'METADATA_TARGET_SETTINGS')
    need(set(metadata.get('sources', {})) == {SOURCE_FILE}, 'METADATA_SOURCE_SET')
    # Constructor initializers are in creation code. Runtime alone does not
    # initialize storage; never replace execution with hand-written slot values.
    return {'source_sha256': sha(inp['sources'][SOURCE_FILE]['content'].encode()),
            'input_sha256': sha(canonical(inp)), 'output_sha256': sha(raw),
            'creation_bytes': len(init), 'creation_sha256': sha(init),
            'runtime_bytes': len(code), 'runtime_sha256': sha(code),
            'abi_sha256': sha(canonical(contract['abi'])),
            'layout_sha256': sha(canonical(contract['storageLayout'])),
            'method_identifiers_as_compiled': deepcopy(methods),
            'evm_target': inp['settings']['evmVersion'], 'warnings': info['warnings'],
            'constructor_executed': False, 'runtime_executed': False,
            'compiled_bytecode_semantics_verified': False}


def bound_case(name: str, build: dict, proof: dict) -> dict:
    """Link source and semantic settings, without claiming source/bytecode equivalence."""
    need(type(build) is dict and set(build) == {'input', 'output_utf8', 'stderr_utf8'}, 'BUILD_SCHEMA')
    expected = build_input(name)
    need(canonical(build['input']) == canonical(expected), 'FIXED_BUILD_INPUT_MISMATCH')
    need(build['stderr_utf8'] == '', 'COMPILER_STDERR')
    need(type(build['output_utf8']) is str, 'OUTPUT_TEXT')
    proof_input = proof['runs']['property']['input']
    need(canonical(proof_input['sources']) == canonical(expected['sources']), 'FORMAL_BUILD_SOURCE_MISMATCH')
    need(proof_input['language'] == expected['language'], 'FORMAL_BUILD_LANGUAGE_MISMATCH')
    # All semantic code-generation settings must coincide. Only requested output
    # and the model checker differ; these do not establish bytecode correctness.
    stripped = lambda x: {k: v for k, v in x['settings'].items() if k not in ('outputSelection', 'modelChecker')}
    need(canonical(stripped(proof_input)) == canonical(stripped(expected)), 'FORMAL_BUILD_SETTINGS_MISMATCH')
    summary = inspect_output(name, build['output_utf8'].encode())
    return {**summary, 'formal_case_sha256': sha(canonical(proof)),
            'source_property_status': proof['verdict']['status'],
            'source_level_only': True, 'independent_compiler_used': False}


def engine_identity() -> dict:
    return {'sources_sha256': {n: sha(read_artifact(ROOT, n)) for n in CODE},
            'compiler_pin': compiler.PIN, 'solver': formal.smt_backend.engine_identity(),
            'native_sources': source_inventory()}


def execute(binary: Path) -> tuple[dict, dict]:
    """Real formal replay plus three fresh code-generation runs; no user source input."""
    before = engine_identity()
    image = compiler.read_pinned_binary(binary)
    proof = formal.execute_lab(binary, 'normal')
    builds = {}
    for name in formal.NAMES:
        inp = build_input(name)
        raw, err = compiler._execute(image, 'compile', canonical(inp))
        need(not err, 'COMPILER_STDERR')
        item = {'input': inp, 'output_utf8': raw.decode('utf-8'), 'stderr_utf8': err.decode('utf-8')}
        bound_case(name, item, proof['cases'][name])
        builds[name] = item
    need(engine_identity() == before, 'ENGINE_CHANGED_DURING_BUILD')
    return proof, {'schema_version': 1, 'profile': 'fixed-stateful-bytecode-v1',
                   'engine': before, 'cases': builds, 'evm_execution': 'NOT_EXECUTED',
                   'constructor_initialization_checked': False}


def result_from(proof: dict, builds: dict, produced_at: str) -> dict:
    need(type(produced_at) is str and len(produced_at) <= 40 and
         datetime.fromisoformat(produced_at).tzinfo is not None, 'PRODUCED_AT')
    need(type(builds) is dict and set(builds) == {'schema_version', 'profile', 'engine', 'cases',
         'evm_execution', 'constructor_initialization_checked'} and type(builds['schema_version']) is int and
         builds['schema_version'] == 1 and builds['profile'] == 'fixed-stateful-bytecode-v1', 'BUILD_ENVELOPE')
    need(builds['evm_execution'] == 'NOT_EXECUTED' and builds['constructor_initialization_checked'] is False,
         'UNSUPPORTED_EXECUTION_CLAIM')
    need(type(builds['cases']) is dict and set(builds['cases']) == set(formal.NAMES) and
         type(proof) is dict and set(proof.get('cases', {})) == set(formal.NAMES), 'COMPLETE_FIXED_CASE_SET')
    need(proof.get('budget') == 'normal' and proof.get('evm_executed') is False, 'FORMAL_PROFILE')
    expected = {'conservation': 'STATEFUL_PROPERTY_PROVED_IN_FIXED_MODEL',
                'delayed_credit': 'STATEFUL_PROPERTY_VIOLATED',
                'unreachable': 'VACUOUS_STATEFUL_NO_CERTIFICATION'}
    need({n: proof['cases'][n]['verdict']['status'] for n in formal.NAMES} == expected,
         'FORMAL_ACCEPTANCE_INCOMPLETE')
    cases = {n: bound_case(n, builds['cases'][n], proof['cases'][n]) for n in formal.NAMES}
    return {'schema_version': 1, 'status': 'NATIVE_BYTECODE_BUILT_EVM_PENDING', 'produced_at': produced_at,
            'profile': builds['profile'], 'controls': cases,
            'formal_sha256': sha(canonical(proof)), 'builds_sha256': sha(canonical(builds)),
            'compiled_controls': len(cases), 'compiler_processes_executed': proof['compiler_processes_executed'] + len(cases),
            'solver_queries_executed': proof['solver_queries_executed'],
            'evm_executed': False, 'bytecode_level_property_proved': False,
            'constructor_executed': False, 'deployed': False, 'vulnerability_confirmed': False,
            'platform_complete': False, 'blocking_stage': 'EVM_EXECUTION_NOT_AVAILABLE',
            'next_required_evidence': 'constructor-and-state-transitions-in-an-established-EVM'}


def documents(proof: dict, builds: dict, produced_at: str) -> dict[str, bytes]:
    result = result_from(proof, builds, produced_at)
    audit = load_components().audit.AuditLog(clock=lambda: produced_at)
    audit.append('bytecode.formal', {'formal_sha256': result['formal_sha256']})
    for name, row in result['controls'].items():
        audit.append('bytecode.bound', {'control': name, 'summary_sha256': sha(canonical(row))})
    audit.append('bytecode.pending-evm', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    text = ('# Bytecode nativo vinculado a controles formales\n\n' + result['status'] + '\n\n' +
            '\n'.join(f"{n}: creación {x['creation_bytes']} bytes; runtime {x['runtime_bytes']} bytes; "
                       f"propiedad de fuente {x['source_property_status']}." for n, x in result['controls'].items()) +
            '\n\nEl bytecode fue generado por solc; no se ejecutó en una EVM ni se desplegó.\n'
            'La verificación de la fuente no se transfiere como garantía de corrección del bytecode.\n'
            'No se sustituyeron constructores por slots preparados ni se contó un revert simulado.\n'
            'Solo controles propios fijos. Sin fuentes, destinos, RPC o transacciones arbitrarios.\n')
    return {'formal.json': canonical(proof), 'builds.json': canonical(builds), 'result.json': canonical(result),
            'audit.json': canonical({'events': [asdict(x) for x in audit.entries], 'clock_authenticated': False}),
            'REVIEW.md': text.encode()}


def create(binary: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    proof, builds = execute(binary)
    at = datetime.now(timezone.utc).isoformat()
    write_new_bundle(out, documents(proof, builds, at))
    return result_from(proof, builds, at)


def replay(root: Path, binary: Path) -> dict:
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
         'BUNDLE_SCHEMA')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    data = {n: read_artifact(root, n) for n in FILES}
    need(all(sha(raw) == marker['sha256'][n] for n, raw in data.items()), 'BUNDLE_HASH')
    # Evidence inputs are data only. NEVER execute source or queries read from it.
    actual_proof, actual_builds = execute(binary)
    at = strict_json(data['result.json']).get('produced_at')
    need(data == documents(actual_proof, actual_builds, at), 'NATIVE_BYTECODE_REPLAY_MISMATCH')
    return {**result_from(actual_proof, actual_builds, at), 'same_engines_reexecuted': True,
            'independent_engine': False}


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Build fixed owned bytecode; EVM execution is not implemented here')
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('build-stateful-bytecode')
    run.add_argument('--solc', type=Path, required=True); run.add_argument('--out', type=Path, required=True)
    check = sub.add_parser('replay-stateful-bytecode')
    check.add_argument('--solc', type=Path, required=True); check.add_argument('--bundle', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        r = create(a.solc, a.out) if a.command == 'build-stateful-bytecode' else replay(a.bundle, a.solc)
        print(json.dumps({k: r[k] for k in ('status', 'compiled_controls', 'compiler_processes_executed',
                                          'solver_queries_executed', 'evm_executed', 'platform_complete')}))
        return 1  # The wider acceptance is PARTIAL until a real EVM is run.
    except (ValueError, OSError, KeyError, TypeError, RecursionError, OverflowError):
        print(json.dumps({'status': 'NATIVE_BYTECODE_BUILD_BLOCKED', 'evm_executed': False,
                          'platform_complete': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
