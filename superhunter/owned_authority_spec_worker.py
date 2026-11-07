"""Pinned EELS execution and byte-slice storage decoding of own authority cases."""
from __future__ import annotations

import json
from pathlib import Path
import resource
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superhunter import owned_authority_evm_cases as cases, quality
from superhunter.owned_spec_evm_worker import dependency_identity
from superhunter.privacy import PrivateArgumentParser
from superhunter.safe_io import canonical

need, sha, compiler, evm = cases.need, cases.sha, cases.compiler, cases.evm


def decode_word(word: int) -> dict:
    need(type(word) is int and 0 <= word < 2**120, 'AUTHORITY_EELS_STORAGE_WORD')
    raw = word.to_bytes(15, 'little')
    result = {'phase': raw[0], 'accepted': raw[1], 'enabled': raw[2],
              'generations': list(raw[3:11]), 'effects': list(raw[11:15])}
    cases.validate_state(result)
    return result


def execute_fixed(solc: Path, digest: str) -> dict:
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest, 'AUTHORITY_EELS_SOURCE_CHANGED')
    identity = dependency_identity()
    from ethereum.forks.cancun.vm import BlockEnvironment, TransactionEnvironment, Message
    from ethereum.forks.cancun.vm.interpreter import process_message, process_create_message
    from ethereum.forks.cancun.vm.exceptions import Revert, OutOfGasError
    from ethereum.forks.cancun.state import State, TransientStorage, get_storage, get_account
    from ethereum.forks.cancun.fork_types import Address
    from ethereum_types.bytes import Bytes0, Bytes32
    from ethereum_types.numeric import Uint, U256, U64

    sender = Address(bytes.fromhex(evm.SENDER[2:])); receiver = Address(bytes.fromhex(evm.RECEIVER[2:]))
    zero = Bytes32(b'\0' * 32)

    def message(state, code, data, gas, creation=False):
        state.created_accounts.clear()
        block = BlockEnvironment(chain_id=U64(31337), state=state, block_gas_limit=Uint(gas),
            block_hashes=[], coinbase=Address(b'\0' * 20), number=Uint(0), base_fee_per_gas=Uint(0),
            time=U256(1), prev_randao=zero, excess_blob_gas=U64(0), parent_beacon_block_root=zero)
        tx = TransactionEnvironment(origin=sender, gas_price=Uint(0), gas=Uint(gas),
            access_list_addresses={sender, receiver}, access_list_storage_keys=set(),
            transient_storage=TransientStorage(), blob_versioned_hashes=(), index_in_block=None, tx_hash=None)
        return Message(block_env=block, tx_env=tx, caller=sender,
            target=Bytes0(b'') if creation else receiver, current_target=receiver,
            gas=Uint(gas), value=U256(0), data=data, code_address=None if creation else receiver,
            code=code, depth=Uint(0), should_transfer_value=True, is_static=False,
            accessed_addresses={sender, receiver}, accessed_storage_keys=set(), parent_evm=None)

    image = compiler.read_pinned_binary(solc)
    compiled = {(v, c): cases.compile_owned(image, v, c)
                for v in cases.model.VARIANTS for c in cases.CODEGEN}
    constructors, rows = [], []
    for case, codegen in cases.inventory():
        built = compiled[case['variant'], codegen]; contract = built['contract']
        runtime = bytes.fromhex(contract['evm']['deployedBytecode']['object'])
        state = State()
        birth = process_create_message(message(state, bytes.fromhex(contract['evm']['bytecode']['object']),
                                                b'', evm.GAS, True))
        need(birth.error is None and birth.output == runtime and
             get_account(state, receiver).code == runtime, 'AUTHORITY_EELS_CONSTRUCTOR')
        initial = decode_word(int(get_storage(state, receiver, zero)))
        need(initial == cases.INITIAL, 'AUTHORITY_EELS_INITIAL_STATE')
        constructors.append({'case_id': case['case_id'], 'codegen': codegen,
                             'initial_state': initial, 'runtime_sha256': built['record']['runtime_sha256']})
        for call_index, item in enumerate(cases.schedule(case['events'])):
            previous = decode_word(int(get_storage(state, receiver, zero)))
            data = bytes.fromhex(contract['evm']['methodIdentifiers']['step(uint256)'] + format(item['word'], '064x'))
            out = process_message(message(state, runtime, data, item['gas']))
            if out.error is None: status = 'COMMITTED'
            elif isinstance(out.error, Revert): status = 'REVERTED'
            elif isinstance(out.error, OutOfGasError): status = 'OUT_OF_GAS'
            else: raise ValueError('AUTHORITY_EELS_EXECUTION_ERROR')
            following = decode_word(int(get_storage(state, receiver, zero)))
            need(not state._snapshots and get_account(state, receiver).code == runtime,
                 'AUTHORITY_EELS_STATE_OR_RUNTIME_CHANGED')
            need(status == 'COMMITTED' or previous == following, 'AUTHORITY_EELS_FAILED_PERSISTENCE')
            rows.append({'case_id': case['case_id'], 'codegen': codegen, 'call_index': call_index,
                'event_index': item['event_index'], 'probe': item['probe'],
                'observation': {'before': previous, 'after': following, 'word': item['word'],
                    'gas': item['gas'], 'status': status, 'return_data': '0x' + out.output.hex()}})
    need(quality.source_snapshot() == before and dependency_identity() == identity,
         'AUTHORITY_EELS_INPUT_CHANGED_DURING_RUN')
    return {'schema_version': 1, 'profile': cases.PROFILE, 'source_digest': digest,
        'engine': 'execution-specs', 'fork': 'Cancun', 'solc_sha256': sha(image),
        'dependencies': identity, 'builds': [b['record'] for b in compiled.values()],
        'constructors': constructors, 'rows': rows, 'compiler_runs': len(compiled),
        'constructor_executions': len(constructors), 'runtime_calls': len(rows)}


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 1024**2, 20 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser = PrivateArgumentParser(description='Fixed own abstract authority EELS worker')
    parser.add_argument('--solc', type=Path, required=True)
    parser.add_argument('--source-digest', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(execute_fixed(args.solc, args.source_digest), sort_keys=True)); return 0
    except Exception:
        print(json.dumps({'status': 'OWNED_AUTHORITY_EELS_BLOCKED'})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
