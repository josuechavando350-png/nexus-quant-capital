"""Real, fixed owned EVM regression: constructor, persistence, revert and gas.

No arbitrary contracts, source, target, calldata, RPC or transaction submission
are accepted. Inputs are rebuilt from bytecode_controls on each execution and
replay. References distinguish pre-assertion arithmetic from COMMITTED storage.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile

from . import bytecode_controls as builds, native_compile as compiler
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PIN = {'version': '1.17.10-stable-1df30b18', 'platform': 'linux-amd64',
       'bytes': 42001080, 'sha256': 'd8cfddad15a8c601e7b069bc5973ad073dbc2d632b8c5ab50e513ef27c53d6da',
       'archive_sha256': 'f991c32e5b7bb68db97a1b06d50c7c06f6aa9ae84d8f6f9b2301dc02cad2a7cf',
       'signer_fingerprint': 'FDE5A1A044FA13D2F7ADA019A61A13569BA28146'}
SENDER = '0x' + '11' * 20
RECEIVER = '0x8f7a45ebde059392e46a46dcc14ab24681a961ea'
SLOT = '0x' + '00' * 32
PANIC_ASSERT = '0x4e487b71' + '0' * 63 + '1'
GAS = 2_000_000
STEPS = ((2, GAS), (16, GAS), (3, GAS), (4, GAS), (0, GAS), (0, 1))
FILES = {'execution.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE = ('evm_execution.py', 'evm_worker.py', 'bytecode_controls.py', 'solidity_stateful.py',
        'native_compile.py', 'solc_worker.py', 'smt_backend.py', 'safe_io.py', 'native_runtime.py')
HEX = re.compile(r'[0-9a-fA-F]*\Z')


class EVMError(ValueError):
    """Only fixed diagnostics are sent to the public console."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise EVMError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_evm(path: Path) -> bytes:
    need(platform.system() == 'Linux' and platform.machine() in ('x86_64', 'amd64'), 'EVM_PLATFORM')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise EVMError('EVM_BINARY_UNAVAILABLE') from None
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size == PIN['bytes'], 'EVM_BINARY_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(PIN['bytes'] + 1)
        need(len(raw) == PIN['bytes'] and sha(raw) == PIN['sha256'] and raw.startswith(b'\x7fELF'), 'EVM_BINARY_HASH')
        return raw
    finally:
        os.close(fd)


def genesis(alloc: dict | None = None, *, gas: int = GAS) -> dict:
    # Geth run uses genesis.gasLimit ahead of --gas; bind BOTH to the same budget.
    need(type(gas) is int and gas in (GAS, 1), 'GAS_PROFILE')
    # Fixed synthetic Cancun environment. No production-chain state is loaded.
    config = {'chainId': 31337, 'homesteadBlock': 0, 'eip150Block': 0, 'eip155Block': 0,
              'eip158Block': 0, 'byzantiumBlock': 0, 'constantinopleBlock': 0,
              'petersburgBlock': 0, 'istanbulBlock': 0, 'berlinBlock': 0, 'londonBlock': 0,
              'mergeNetsplitBlock': 0, 'terminalTotalDifficulty': 0, 'shanghaiTime': 0,
              'cancunTime': 0, 'blobSchedule': {'cancun': {'target': 3, 'max': 6,
                                                        'baseFeeUpdateFraction': 3338477}}}
    return {'config': config, 'alloc': deepcopy(alloc or {}), 'gasLimit': hex(gas),
            'difficulty': '0x0', 'timestamp': '0x1', 'baseFeePerGas': '0x0',
            'excessBlobGas': '0x0', 'blobGasUsed': '0x0'}


def _pairs(rows: list) -> dict:
    value = {}
    for key, item in rows:
        need(key not in value, 'DUPLICATE_EVM_JSON_KEY')
        value[key] = item
    return value


def parse_run(raw: bytes) -> dict:
    """Decode actual evm run dump + return data/error, rejecting trailing ambiguity."""
    need(type(raw) is bytes and 0 < len(raw) < 2_000_000, 'EVM_OUTPUT_SIZE')
    text = raw.decode('utf-8', errors='strict')
    def bad_number(_):
        raise EVMError('NONFINITE_EVM_JSON')
    decoder = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=bad_number)
    dump, end = decoder.raw_decode(text)
    need(type(dump) is dict and set(dump) == {'root', 'accounts'}, 'EVM_DUMP_SCHEMA')
    root = dump['root']
    need(type(root) is str and re.fullmatch('[0-9a-f]{64}', root) is not None, 'EVM_ROOT')
    accounts = dump['accounts']
    need(type(accounts) is dict and 1 <= len(accounts) <= 2, 'EVM_ACCOUNT_COUNT')
    clean = {}
    for address, row in accounts.items():
        need(type(address) is str and address.lower() in (SENDER, RECEIVER) and address.lower() not in clean,
             'UNEXPECTED_EVM_ACCOUNT')
        need(type(row) is dict and set(row).issubset({'balance', 'nonce', 'root', 'codeHash',
             'code', 'storage', 'address', 'key'}) and {'balance', 'nonce', 'address'} <= set(row), 'EVM_ACCOUNT_SCHEMA')
        need(type(row['address']) is str and row['address'].lower() == address.lower() and row['balance'] == '0' and
             type(row['nonce']) is int and row['nonce'] == 1, 'EVM_ACCOUNT_PROFILE')
        code = row.get('code', '0x')
        need(type(code) is str and code.startswith('0x') and len(code) <= 64_002 and
             len(code) % 2 == 0 and HEX.fullmatch(code[2:]) is not None, 'EVM_CODE')
        storage = row.get('storage', {})
        need(type(storage) is dict and set(storage).issubset({SLOT}), 'EVM_STORAGE_PROFILE')
        normalized = {}
        for key, value in storage.items():
            need(type(value) is str and 0 < len(value) <= 64 and HEX.fullmatch(value) is not None,
                 'EVM_STORAGE_VALUE')
            normalized[key] = '0x' + value.lower().zfill(64)
        clean[address.lower()] = {'balance': '0', 'nonce': 1, 'code': code.lower(), 'storage': normalized}
    tail = text[end:].strip()
    error = None
    for suffix in ('error: execution reverted', 'error: out of gas'):
        if tail.endswith(suffix):
            error = suffix.removeprefix('error: ')
            tail = tail[:-len(suffix)].strip()
            break
    need(not tail or re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', tail) is not None, 'EVM_RETURN_OR_ERROR')
    return {'state_root': root, 'alloc': clean, 'return_data': tail.lower() if tail else '0x', 'error': error}


def _run(image: bytes, *, prestate: dict, creation: str | None = None,
         calldata: str = '', gas: int = GAS) -> dict:
    """Internal fixed-image process boundary, not a public arbitrary EVM runner."""
    need(type(gas) is int and gas in (GAS, 1), 'GAS_PROFILE')
    need(sha(image) == PIN['sha256'], 'EVM_BINARY_HASH')
    need(prestate.get('gasLimit') == hex(gas), 'GENESIS_GAS_DISAGREEMENT')
    mode = 'create' if creation is not None else 'call'
    need((mode == 'create' and type(creation) is str and 0 < len(creation) <= 64000 and
          re.fullmatch('[0-9a-f]+', creation) is not None and len(creation) % 2 == 0) or
         (mode == 'call' and re.fullmatch('[0-9a-f]{72}', calldata) is not None), 'EVM_CALL_PROFILE')
    with compiler._sealed_executable(image) as fd, tempfile.TemporaryDirectory(prefix='sh-evm-fixed-') as tmp:
        root = Path(tmp)
        (root/'prestate.json').write_bytes(canonical(prestate))
        if creation is not None:
            (root/'creation.hex').write_text(creation)
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            command = [sys.executable, '-I', '-B', str(ROOT/'evm_worker.py'), mode, str(fd),
                       '-' if mode == 'create' else calldata, str(gas)]
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                cwd=root, env={'LANG': 'C', 'LC_ALL': 'C'}, pass_fds=(fd,), start_new_session=True)
            try:
                rc = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise EVMError('EVM_PROCESS_TIMEOUT') from None
            need(out.seek(0, os.SEEK_END) < 2_000_000 and err.seek(0, os.SEEK_END) < 2_000_000, 'EVM_OUTPUT_LIMIT')
            out.seek(0); err.seek(0)
            stdout, stderr = out.read(), err.read()
            need(rc == 0 and not stderr, 'EVM_PROCESS_FAILED')
    parsed = parse_run(stdout)
    return {'prestate_sha256': sha(canonical(prestate)), 'mode': mode, 'gas_limit': gas,
            'calldata': calldata, 'stdout_utf8': stdout.decode(), 'stderr_utf8': '', 'observed': parsed}


def decode_state(alloc: dict, contract: dict) -> dict:
    """Decode only the three fixed fields using the freshly compiled layout."""
    need(RECEIVER in alloc, 'CONTRACT_NOT_CREATED')
    rows = contract['storageLayout']['storage']
    expected = [('debit', '0', 0, 'uint16'), ('credit', '0', 2, 'uint16'), ('steps', '0', 4, 'uint8')]
    types = contract['storageLayout']['types']
    actual = [(r['label'], r['slot'], r['offset'], types[r['type']]['label']) for r in rows]
    need(actual == expected, 'FIXED_STORAGE_LAYOUT')
    account = alloc[RECEIVER]
    need(account['code'] == '0x' + contract['evm']['deployedBytecode']['object'], 'RUNTIME_NOT_FROM_CONSTRUCTOR')
    word = int(account['storage'].get(SLOT, '0x0'), 16)
    need(word >> 40 == 0, 'UNEXPECTED_STORAGE_BITS')
    result = {}
    for row in rows:
        width = int(types[row['type']]['numberOfBytes'])
        result[row['label']] = (word >> (8 * row['offset'])) & ((1 << (8 * width)) - 1)
    return result


def reference(name: str, state: dict, quantity: int, gas: int) -> dict:
    """Committed-state semantics; no expected changes from a reverted assertion."""
    need(name in builds.formal.NAMES and type(quantity) is int and 0 <= quantity <= 255 and type(gas) is int and gas in (GAS, 1), 'REFERENCE_PROFILE')
    before = dict(state)
    if gas == 1:
        return {'status': 'RESOURCE_EXHAUSTED', 'state': before, 'return_data': '0x', 'error': 'out of gas'}
    if name == 'unreachable' or state['steps'] >= 3 or quantity > state['debit']:
        return {'status': 'PRECONDITION_REVERT', 'state': before, 'return_data': '0x', 'error': 'execution reverted'}
    tentative = {'debit': state['debit'] - quantity,
                 'credit': state['credit'] + quantity + (1 if name == 'delayed_credit' and state['steps'] == 2 else 0),
                 'steps': state['steps'] + 1}
    if tentative['debit'] + tentative['credit'] != 15:
        return {'status': 'ASSERTION_REVERT', 'state': before, 'return_data': PANIC_ASSERT,
                'error': 'execution reverted', 'uncommitted_model_state': tentative}
    return {'status': 'COMMITTED', 'state': tentative, 'return_data': '0x', 'error': None}


def validate_case(name: str, row: dict, contract: dict) -> dict:
    """Recalculate stored observations and references, not proof of remote execution."""
    need(type(row) is dict and set(row) == {'constructor', 'constructor_state', 'calls',
         'final_state', 'source_property_status'}, 'CASE_SCHEMA')
    initial = {'debit': 15, 'credit': 0, 'steps': 0}
    def observation(item: dict, mode: str, pre: dict, data: str, gas: int) -> dict:
        need(type(item) is dict and set(item) == {'prestate_sha256','mode','gas_limit','calldata',
             'stdout_utf8','stderr_utf8','observed'}, 'OBSERVATION_SCHEMA')
        need(item['mode'] == mode and type(item['gas_limit']) is int and item['gas_limit'] == gas
             and item['calldata'] == data and item['prestate_sha256'] == sha(canonical(pre)), 'EXECUTION_BINDING')
        need(type(item['stdout_utf8']) is str and item['stderr_utf8'] == '', 'EXECUTION_OUTPUT')
        parsed = parse_run(item['stdout_utf8'].encode())
        need(canonical(parsed) == canonical(item['observed']), 'OBSERVATION_NOT_FROM_STDOUT')
        return parsed
    birth = observation(row['constructor'], 'create', genesis(), '', GAS)
    need(birth['error'] is None and birth['return_data'] == '0x' + contract['evm']['deployedBytecode']['object'],
         'CONSTRUCTOR_RESULT')
    alloc = birth['alloc']
    need(set(alloc) == {SENDER, RECEIVER} and decode_state(alloc, contract) == initial and
         canonical(row['constructor_state']) == canonical(initial), 'CONSTRUCTOR_STORAGE')
    calls = row['calls']
    need(type(calls) is list and len(calls) == len(STEPS), 'CALL_COVERAGE')
    state = initial
    counts = {}
    for index, ((quantity, gas), call) in enumerate(zip(STEPS, calls)):
        need(type(call) is dict and set(call) == {'index','quantity','reference','state_before','state_after','execution'}, 'CALL_SCHEMA')
        need(type(call['index']) is int and call['index'] == index and type(call['quantity']) is int and
             call['quantity'] == quantity and canonical(call['state_before']) == canonical(state), 'CALL_ORDER_OR_INPUT')
        data = contract['evm']['methodIdentifiers']['move(uint8)'] + format(quantity, '064x')
        observed = observation(call['execution'], 'call', genesis(alloc, gas=gas), data, gas)
        wanted = reference(name, state, quantity, gas)
        actual_state = decode_state(observed['alloc'], contract)
        need(canonical(call['reference']) == canonical(wanted), 'FALSE_REFERENCE_RESULT')
        need(actual_state == wanted['state'] and canonical(call['state_after']) == canonical(actual_state), 'COMMITTED_STATE_MISMATCH')
        need(observed['error'] == wanted['error'] and observed['return_data'] == wanted['return_data'], 'RETURN_STATUS_MISMATCH')
        if wanted['status'] != 'COMMITTED':
            need(canonical(alloc) == canonical(observed['alloc']), 'EVM_REVERT_CHANGED_STATE')
        counts[wanted['status']] = counts.get(wanted['status'], 0) + 1
        state, alloc = actual_state, observed['alloc']
    need(canonical(row['final_state']) == canonical(state), 'FINAL_STATE_MISMATCH')
    return counts


def engine_identity() -> dict:
    return {'sources_sha256': {n: sha(read_artifact(ROOT, n)) for n in CODE},
            'native_sources': source_inventory(), 'evm_pin': PIN, 'compiler_pin': compiler.PIN,
            'formal_engine': builds.engine_identity()}


def execute(solc: Path, evm: Path) -> dict:
    before = engine_identity()
    image = read_evm(evm)  # Fail before compilation when EVM is missing/untrusted.
    proof, code = builds.execute(solc)
    cases = {}
    for name in builds.formal.NAMES:
        built = code['cases'][name]
        builds.bound_case(name, built, proof['cases'][name])
        contract = strict_json(built['output_utf8'])['contracts'][builds.SOURCE_FILE][builds.CONTRACT]
        birth = _run(image, prestate=genesis(), creation=contract['evm']['bytecode']['object'])
        need(birth['observed']['error'] is None and birth['observed']['return_data'] ==
             '0x' + contract['evm']['deployedBytecode']['object'], 'CONSTRUCTOR_RESULT')
        alloc = birth['observed']['alloc']
        need(set(alloc) == {SENDER, RECEIVER}, 'CONSTRUCTOR_ACCOUNTS')
        state = decode_state(alloc, contract)
        need(state == {'debit': 15, 'credit': 0, 'steps': 0}, 'CONSTRUCTOR_STORAGE')
        calls = []
        for index, (quantity, gas) in enumerate(STEPS):
            expected = reference(name, state, quantity, gas)
            calldata = contract['evm']['methodIdentifiers']['move(uint8)'] + format(quantity, '064x')
            observed = _run(image, prestate=genesis(alloc, gas=gas), calldata=calldata, gas=gas)
            actual = observed['observed']
            after_state = decode_state(actual['alloc'], contract)
            need(actual['return_data'] == expected['return_data'] and actual['error'] == expected['error'], 'EVM_RETURN_MISMATCH')
            need(after_state == expected['state'], 'EVM_COMMITTED_STATE_MISMATCH')
            if expected['status'] != 'COMMITTED':
                need(canonical(alloc) == canonical(actual['alloc']), 'EVM_REVERT_CHANGED_STATE')
            calls.append({'index': index, 'quantity': quantity, 'reference': expected,
                          'state_before': state, 'state_after': after_state, 'execution': observed})
            state, alloc = after_state, actual['alloc']
        cases[name] = {'constructor': birth, 'constructor_state': {'debit': 15, 'credit': 0, 'steps': 0},
                       'calls': calls, 'final_state': state, 'source_property_status': proof['cases'][name]['verdict']['status']}
    need(engine_identity() == before, 'ENGINE_CHANGED_DURING_EXECUTION')
    return {'schema_version': 1, 'profile': 'owned-state-rollback-controls-v1', 'engine': before,
            'genesis_template': genesis(), 'formal': proof, 'builds': code, 'cases': cases}


def result_from(execution: dict, at: str) -> dict:
    need(type(at) is str and datetime.fromisoformat(at).tzinfo is not None, 'RESULT_TIME')
    need(type(execution) is dict and set(execution) == {'schema_version', 'profile', 'engine', 'genesis_template',
         'formal', 'builds', 'cases'} and type(execution['schema_version']) is int and execution['schema_version'] == 1,
         'EXECUTION_SCHEMA')
    need(execution['profile'] == 'owned-state-rollback-controls-v1' and set(execution['cases']) == set(builds.formal.NAMES), 'EXECUTION_PROFILE')
    # Reparse every observed state; native replay remains required for execution evidence.
    need(canonical(execution['genesis_template']) == canonical(genesis()), 'GENESIS_PROFILE')
    counts = {}
    for name, row in execution['cases'].items():
        build = execution['builds']['cases'][name]
        proof = execution['formal']['cases'][name]
        builds.bound_case(name, build, proof)
        need(row['source_property_status'] == proof['verdict']['status'], 'FORMAL_RESULT_BINDING')
        contract = strict_json(build['output_utf8'])['contracts'][builds.SOURCE_FILE][builds.CONTRACT]
        for status, count in validate_case(name, row, contract).items():
            counts[status] = counts.get(status, 0) + count
    return {'schema_version': 1, 'status': 'LOCAL_EVM_STATE_CONTROLS_REPRODUCED', 'created_at': at,
            'execution_sha256': sha(canonical(execution)), 'evm_executed': True,
            'constructor_calls': len(builds.formal.NAMES), 'runtime_calls': len(builds.formal.NAMES) * len(STEPS),
            'call_outcomes': counts, 'rollback_checked': True, 'fixture_only': True,
            'scope': 'fixed-owned-message-calls-in-synthetic-cancun-state',
            'network_used': False, 'onchain_transactions': False, 'token_balances_or_profit_measured': False,
            'source_properties_transferred_as_bytecode_proof': False,
            'same_engines_replayed': False, 'independent_evm_used': False,
            'vulnerability_confirmed': False, 'platform_complete': False}


def documents(execution: dict, at: str) -> dict[str, bytes]:
    result = result_from(execution, at)
    audit = load_components().audit.AuditLog(clock=lambda: at)
    audit.append('evm.fixed.start', {'execution_sha256': result['execution_sha256']})
    for name, row in execution['cases'].items():
        audit.append('evm.fixed.constructor', {'case': name, 'sha256': sha(canonical(row['constructor']))})
        for call in row['calls']:
            audit.append('evm.fixed.call', {'case': name, 'index': call['index'], 'sha256': sha(canonical(call))})
    audit.append('evm.fixed.complete', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    text = ('# EVM local: estado persistente y reversiones\n\n' + result['status'] + '\n\n' +
            '\n'.join(f'{k}: {v}' for k, v in sorted(result['call_outcomes'].items())) +
            '\n\nSe ejecutan constructores y llamadas de controles propios conocidos. '
            'Una aserción fallida revierte: el estado tentativo NO se presenta como pérdida persistente. '
            'El agotamiento de gas no certifica una propiedad ni equivale a una vulnerabilidad. '
            'No hay red, transacciones firmadas, objetivos externos o recompensas. '
            'Replay usa el mismo compilador, solver y EVM, no implementaciones independientes.\n')
    return {'execution.json': canonical(execution), 'result.json': canonical(result),
            'audit.json': canonical({'events': [asdict(e) for e in audit.entries]}), 'REVIEW.md': text.encode()}


def create(solc: Path, evm: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.parent), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    run = execute(solc, evm)
    at = datetime.now(timezone.utc).isoformat()
    write_new_bundle(out, documents(run, at))
    return result_from(run, at)


def replay(root: Path, solc: Path, evm: Path) -> dict:
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
         'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILE_SET')
    data = {n: read_artifact(root, n) for n in FILES}
    need(all(sha(b) == marker['sha256'][n] for n, b in data.items()), 'BUNDLE_HASH')
    at = strict_json(data['result.json']).get('created_at')
    # NEVER execute code, queries, prestate or calldata supplied by this bundle.
    actual = execute(solc, evm)
    need(data == documents(actual, at), 'NATIVE_EVM_REPLAY_MISMATCH')
    return {**result_from(actual, at), 'same_engines_replayed': True}


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Fixed owned EVM state controls only; no arbitrary targets or RPC')
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run-evm-state-controls'); run.add_argument('--out', type=Path, required=True)
    check = sub.add_parser('replay-evm-state-controls'); check.add_argument('--bundle', type=Path, required=True)
    for command in (run, check):
        command.add_argument('--solc', type=Path, required=True)
        command.add_argument('--evm', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        r = create(a.solc, a.evm, a.out) if a.command == 'run-evm-state-controls' else replay(a.bundle, a.solc, a.evm)
        print(json.dumps({k: r[k] for k in ('status','constructor_calls','runtime_calls','call_outcomes','evm_executed','same_engines_replayed','vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError):
        print(json.dumps({'status': 'EVM_STATE_CONTROLS_BLOCKED', 'vulnerability_confirmed': False})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
