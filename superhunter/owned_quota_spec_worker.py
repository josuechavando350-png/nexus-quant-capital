"""Pinned EELS execution of six fixed OWNED quota controls, no external inputs."""
from __future__ import annotations

import json
from pathlib import Path
import resource
import sys

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from superhunter import native_compile as compiler, evm_execution as evm, quality
from superhunter import owned_quota_cases as cases
from superhunter.owned_quota_cases import need,sha
from superhunter.owned_spec_evm_worker import dependency_identity
from superhunter.privacy import PrivateArgumentParser
from superhunter.safe_io import canonical

PROFILE = 'owned-quota-two-implementation-cancun-v1'


def decode_word(word: int) -> dict:
    need(type(word) is int and 0 <= word < 2**48,'QUOTA_EELS_STORAGE_WORD')
    raw = word.to_bytes(6,'little')
    return {name:int.from_bytes(raw[start:start+2],'little')
            for name,start in (('remaining',0),('distributed',2),('quota',4))}


def execute_fixed(solc: Path, digest: str) -> dict:
    before = quality.source_snapshot()
    need(sha(canonical(before)) == digest,'QUOTA_EELS_SOURCE_CHANGED')
    identity = dependency_identity()
    from ethereum.forks.cancun.vm import BlockEnvironment,TransactionEnvironment,Message
    from ethereum.forks.cancun.vm.interpreter import process_message,process_create_message
    from ethereum.forks.cancun.vm.exceptions import Revert,OutOfGasError
    from ethereum.forks.cancun.state import State,TransientStorage,get_storage,get_account
    from ethereum.forks.cancun.fork_types import Address
    from ethereum.forks.cancun.trie import copy_trie
    from ethereum_types.bytes import Bytes0,Bytes32
    from ethereum_types.numeric import Uint,U256,U64

    sender = Address(bytes.fromhex(evm.SENDER[2:])); receiver = Address(bytes.fromhex(evm.RECEIVER[2:]))
    zero = Bytes32(b'\0'*32)

    def message(state,code,data,gas,creation=False):
        state.created_accounts.clear()
        block = BlockEnvironment(chain_id=U64(31337),state=state,block_gas_limit=Uint(gas),
            block_hashes=[],coinbase=Address(b'\0'*20),number=Uint(0),base_fee_per_gas=Uint(0),
            time=U256(1),prev_randao=zero,excess_blob_gas=U64(0),parent_beacon_block_root=zero)
        tx = TransactionEnvironment(origin=sender,gas_price=Uint(0),gas=Uint(gas),
            access_list_addresses={sender,receiver},access_list_storage_keys=set(),
            transient_storage=TransientStorage(),blob_versioned_hashes=(),index_in_block=None,tx_hash=None)
        return Message(block_env=block,tx_env=tx,caller=sender,
            target=Bytes0(b'') if creation else receiver,current_target=receiver,
            gas=Uint(gas),value=U256(0),data=data,code_address=None if creation else receiver,
            code=code,depth=Uint(0),should_transfer_value=True,is_static=False,
            accessed_addresses={sender,receiver},accessed_storage_keys=set(),parent_evm=None)

    def fork_state(state):
        need(not state._snapshots,'QUOTA_EELS_ACTIVE_CHECKPOINT')
        return State(_main_trie=copy_trie(state._main_trie),
            _storage_tries={address:copy_trie(trie) for address,trie in state._storage_tries.items()})

    image = compiler.read_pinned_binary(solc); rows,builds = [],[]
    for variant in cases.VARIANTS:
        for codegen in cases.CODEGEN:
            built = cases.compile_owned(image,variant,codegen); contract = built['contract']
            runtime = bytes.fromhex(contract['evm']['deployedBytecode']['object'])
            initial = State()
            birth = process_create_message(message(initial,
                bytes.fromhex(contract['evm']['bytecode']['object']),b'',evm.GAS,True))
            need(birth.error is None and birth.output == runtime and
                 get_account(initial,receiver).code == runtime,'QUOTA_EELS_CONSTRUCTOR')
            initial_state = decode_word(int(get_storage(initial,receiver,zero)))
            need(initial_state == cases.INITIAL,'QUOTA_EELS_INITIAL_STATE')
            builds.append({**built['record'],'initial_state':initial_state})
            for index,scenario in enumerate(cases.SEQUENCES):
                state = fork_state(initial)
                for step,(amount,gas) in enumerate(scenario):
                    data = bytes.fromhex(contract['evm']['methodIdentifiers']['release(uint8)']+
                                         format(amount,'064x'))
                    previous = decode_word(int(get_storage(state,receiver,zero)))
                    out = process_message(message(state,runtime,data,gas))
                    if out.error is None: status = 'COMMITTED'
                    elif isinstance(out.error,Revert): status = 'REVERTED'
                    elif isinstance(out.error,OutOfGasError): status = 'OUT_OF_GAS'
                    else: raise ValueError('QUOTA_EELS_UNEXPECTED_EXECUTION_ERROR')
                    following = decode_word(int(get_storage(state,receiver,zero)))
                    need(not state._snapshots and get_account(state,receiver).code == runtime,
                         'QUOTA_EELS_STATE_OR_RUNTIME_CHANGED')
                    need(status == 'COMMITTED' or previous == following,'QUOTA_EELS_FAILED_CALL_PERSISTED')
                    rows.append({'variant':variant,'codegen':codegen,'scenario':index,'step':step,
                        'observation':{'before':previous,'after':following,'amount':amount,'gas':gas,
                                       'status':status,'return_data':'0x'+out.output.hex()}})
    need(quality.source_snapshot() == before and dependency_identity() == identity,
         'QUOTA_EELS_INPUT_CHANGED_DURING_RUN')
    return {'profile':PROFILE,'source_digest':digest,'engine':'execution-specs','fork':'Cancun',
        'solc_sha256':sha(image),'dependencies':identity,'builds':builds,'rows':rows,
        'constructor_executions':len(builds),'runtime_calls':len(rows)}


def main(argv: list[str] | None = None) -> int:
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    p = PrivateArgumentParser(description='Fixed owned quota EELS worker')
    p.add_argument('--solc',type=Path,required=True);p.add_argument('--source-digest',required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(execute_fixed(args.solc,args.source_digest),sort_keys=True));return 0
    except Exception:
        print(json.dumps({'status':'OWNED_QUOTA_EELS_BLOCKED'}));return 2


if __name__ == '__main__':
    raise SystemExit(main())
