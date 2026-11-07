"""Pinned EELS Cancun execution of the existing four OWNED fixed controls.

Only pinned solc and a source digest are accepted. No source, target, RPC,
transaction or calldata is supplied by the caller. Dependencies are optional
and belong in a separate environment from the historical QA interpreter.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import resource
import sys

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from superhunter import native_compile as compiler, evm_execution as evm, quality
from superhunter import evm_pause_family as pause, evm_access_family as access
from superhunter.owned_spec_evm_pins import PINS
from superhunter.privacy import PrivateArgumentParser
from superhunter.safe_io import canonical

PROFILE = 'owned-cancun-two-implementation-v1'


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def dependency_identity() -> dict:
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64' and
         sys.version_info[:2] == (3,12), 'EELS_PLATFORM')
    identity = {}
    for name,pin in PINS.items():
        dist = distribution(name)
        need(dist.version == pin['version'], 'EELS_DEPENDENCY_VERSION')
        hashes = {}
        for item in dist.files or ():
            key = item.as_posix()
            if ('..' in item.parts or key.endswith('.pyc') or
                any(p.endswith('.dist-info') or p == '__pycache__' for p in item.parts)):
                continue
            path = Path(dist.locate_file(item))
            need(path.is_file() and not path.is_symlink() and
                 path.stat().st_size <= 32_000_000, 'EELS_DEPENDENCY_FILE')
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        digest = hashlib.sha256(json.dumps(hashes,sort_keys=True,
                                          separators=(',',':')).encode()).hexdigest()
        need(len(hashes) == pin['files'] and digest == pin['runtime_sha256'],
             'EELS_DEPENDENCY_BYTES')
        identity[name] = {'version':dist.version,'files':len(hashes),'runtime_sha256':digest}
    return identity


def decode_word(word: int, family: str) -> dict:
    """Decode fixed storage using byte slices, separate from the bit-mask adapter."""
    need(type(word) is int and 0 <= word < 2**256, 'EELS_STORAGE_WORD')
    raw = word.to_bytes(32,'little')
    if family == 'pause':
        need(raw[5:] == b'\0'*27, 'EELS_PAUSE_STORAGE')
        return {'remaining':int.from_bytes(raw[0:2],'little'),
                'distributed':int.from_bytes(raw[2:4],'little'),'paused':raw[4]}
    need(family == 'access' and raw[24:] == b'\0'*8, 'EELS_ACCESS_STORAGE')
    return {'admin':'0x'+raw[:20][::-1].hex(),
            'remaining':int.from_bytes(raw[20:22],'little'),
            'distributed':int.from_bytes(raw[22:24],'little')}


def execute_fixed(solc: Path, digest: str) -> dict:
    before = quality.source_snapshot()
    need(hashlib.sha256(canonical(before)).hexdigest() == digest, 'SOURCE_CHANGED')
    identity = dependency_identity()
    from ethereum.forks.cancun.vm import BlockEnvironment,TransactionEnvironment,Message
    from ethereum.forks.cancun.vm.interpreter import process_message,process_create_message
    from ethereum.forks.cancun.vm.exceptions import Revert,OutOfGasError
    from ethereum.forks.cancun.state import State,TransientStorage,get_storage,get_account
    from ethereum.forks.cancun.fork_types import Address
    from ethereum.forks.cancun.trie import copy_trie
    from ethereum_types.bytes import Bytes0,Bytes32
    from ethereum_types.numeric import Uint,U256,U64

    sender = Address(bytes.fromhex(evm.SENDER[2:]))
    receiver = Address(bytes.fromhex(evm.RECEIVER[2:]))
    zero = Bytes32(b'\0'*32)

    def message(state, caller, code, data, gas, creation=False):
        state.created_accounts.clear()
        block = BlockEnvironment(chain_id=U64(31337),state=state,block_gas_limit=Uint(gas),
            block_hashes=[],coinbase=Address(b'\0'*20),number=Uint(0),base_fee_per_gas=Uint(0),
            time=U256(1),prev_randao=zero,excess_blob_gas=U64(0),parent_beacon_block_root=zero)
        tx = TransactionEnvironment(origin=caller,gas_price=Uint(0),gas=Uint(gas),
            access_list_addresses={caller,receiver},access_list_storage_keys=set(),
            transient_storage=TransientStorage(),blob_versioned_hashes=(),
            index_in_block=None,tx_hash=None)
        return Message(block_env=block,tx_env=tx,caller=caller,
            target=Bytes0(b'') if creation else receiver,current_target=receiver,
            gas=Uint(gas),value=U256(0),data=data,code_address=None if creation else receiver,
            code=code,depth=Uint(0),should_transfer_value=True,is_static=False,
            accessed_addresses={caller,receiver},accessed_storage_keys=set(),parent_evm=None)

    def fork_state(state):
        need(not state._snapshots, 'EELS_ACTIVE_CHECKPOINT')
        # EELS accounts are immutable; deepcopy is not its state-copy protocol.
        # Use the same trie-copy primitive as its transaction checkpoints.
        return State(_main_trie=copy_trie(state._main_trie),
            _storage_tries={address:copy_trie(trie)
                           for address,trie in state._storage_tries.items()})

    image = compiler.read_pinned_binary(solc)
    rows, builds = [], []
    for family,module in (('pause',pause),('access',access)):
        for variant in module.VARIANTS:
            for codegen in module.CODEGEN:
                built = module.compile_owned(image,variant,codegen)
                contract = built['contract']
                runtime = bytes.fromhex(contract['evm']['deployedBytecode']['object'])
                state = State()
                birth = process_create_message(message(state,sender,
                    bytes.fromhex(contract['evm']['bytecode']['object']),b'',evm.GAS,True))
                need(birth.error is None and birth.output == runtime and
                     get_account(state,receiver).code == runtime, 'EELS_CONSTRUCTOR')
                initial_state = decode_word(int(get_storage(state,receiver,zero)),family)
                wanted = ({'remaining':15,'distributed':0,'paused':0} if family == 'pause'
                          else {'admin':evm.SENDER,'remaining':10,'distributed':0})
                need(initial_state == wanted, 'EELS_INITIAL_STATE')
                builds.append({'family':family,**built['record'],'initial_state':initial_state})
                initial = fork_state(state)
                for index,scenario in enumerate(module.SEQUENCES):
                    state = fork_state(initial)
                    for step,(arg,amount,gas) in enumerate(scenario):
                        caller = sender if family == 'pause' else Address(bytes.fromhex(arg[2:]))
                        method = (('setPaused(uint8)' if arg == 'pause' else 'release(uint8)')
                                  if family == 'pause' else 'payout(uint8)')
                        data = bytes.fromhex(contract['evm']['methodIdentifiers'][method]+
                                             format(amount,'064x'))
                        previous = decode_word(int(get_storage(state,receiver,zero)),family)
                        out = process_message(message(state,caller,runtime,data,gas))
                        if out.error is None:
                            status = 'COMMITTED'
                        elif isinstance(out.error,Revert):
                            status = 'REVERTED'
                        elif isinstance(out.error,OutOfGasError):
                            status = 'OUT_OF_GAS'
                        else:
                            raise ValueError('EELS_UNEXPECTED_EXECUTION_ERROR')
                        following = decode_word(int(get_storage(state,receiver,zero)),family)
                        need(not state._snapshots and get_account(state,receiver).code == runtime,
                             'EELS_STATE_OR_RUNTIME_CHANGED')
                        need(status == 'COMMITTED' or previous == following,
                             'EELS_FAILED_CALL_PERSISTED')
                        rows.append({'family':family,'variant':variant,'codegen':codegen,
                            'scenario':index,'step':step,'input':list((arg,amount,gas)),
                            'status':status,'before':previous,'after':following,
                            'return_data':'0x'+out.output.hex()})
    need(quality.source_snapshot() == before and dependency_identity() == identity,
         'EELS_INPUT_CHANGED_DURING_RUN')
    return {'profile':PROFILE,'source_digest':digest,'engine':'execution-specs',
            'fork':'Cancun','dependencies':identity,'builds':builds,'rows':rows,
            'constructor_executions':8,'runtime_calls':len(rows)}


def main(argv: list[str] | None = None) -> int:
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    p = PrivateArgumentParser(description='Fixed owned EELS Cancun worker')
    p.add_argument('--solc',type=Path,required=True)
    p.add_argument('--source-digest',required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(execute_fixed(args.solc,args.source_digest),sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'status':'OWNED_SPEC_EVM_BLOCKED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
