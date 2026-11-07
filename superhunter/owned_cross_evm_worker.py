"""Bounded second implementation for the four fixed OWNED Cancun controls.

Accepts pinned solc plus a code digest, never contract/target/calldata inputs.
The optional py-evm backend is checked before importing it. Message execution
includes rollback; execute_bytecode alone would omit that call boundary.
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
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superhunter import evm_execution as evm, native_compile as compiler, quality
from superhunter import evm_pause_family as pause, evm_access_family as access
from superhunter.owned_cross_evm_pins import PINS
from superhunter.privacy import PrivateArgumentParser
from superhunter.safe_io import canonical

PROFILE = 'owned-cancun-two-implementation-v1'


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def dependency_identity() -> dict:
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64' and
         sys.version_info[:2] == (3, 12), 'PY_EVM_PLATFORM')
    observed = {}
    for name, pin in PINS.items():
        dist = distribution(name)
        need(dist.version == pin['version'], 'PY_EVM_DEPENDENCY_VERSION')
        hashes = {}
        for item in dist.files or ():
            key = item.as_posix()
            if ('..' in item.parts or key.endswith('.pyc') or
                any(p.endswith('.dist-info') or p == '__pycache__' for p in item.parts)):
                continue
            path = Path(dist.locate_file(item))
            need(path.is_file() and not path.is_symlink() and
                 path.stat().st_size <= 32_000_000, 'PY_EVM_DEPENDENCY_FILE')
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
        need(len(hashes) == pin['files'] and digest == pin['runtime_sha256'],
             'PY_EVM_DEPENDENCY_BYTES')
        observed[name] = {'version':dist.version, 'runtime_sha256':digest,
                          'files':len(hashes)}
    return observed


def decode_word(word: int, family: str) -> dict:
    need(type(word) is int and word >= 0, 'PY_EVM_STORAGE_WORD')
    if family == 'pause':
        need(word >> 40 == 0, 'PY_EVM_PAUSE_STORAGE')
        return {'remaining':word & 65535, 'distributed':(word >> 16) & 65535,
                'paused':(word >> 32) & 255}
    need(family == 'access' and word >> 192 == 0, 'PY_EVM_ACCESS_STORAGE')
    return {'admin':'0x' + (word & ((1 << 160)-1)).to_bytes(20, 'big').hex(),
            'remaining':(word >> 160) & 65535, 'distributed':(word >> 176) & 65535}


def execute_fixed(solc: Path, digest: str) -> dict:
    before = quality.source_snapshot()
    need(hashlib.sha256(canonical(before)).hexdigest() == digest, 'SOURCE_CHANGED')
    identity = dependency_identity()
    # No imports from the second implementation until the distribution checks.
    from eth.vm.forks.cancun import CancunVM
    from eth.vm.forks.cancun.computation import CancunComputation
    from eth.db.atomic import AtomicDB
    from eth.chains.base import ChainContext
    from eth.vm.message import Message
    from eth.vm.transaction_context import BaseTransactionContext
    from eth.exceptions import OutOfGas, Revert

    image = compiler.read_pinned_binary(solc)
    sender, receiver = bytes.fromhex(evm.SENDER[2:]), bytes.fromhex(evm.RECEIVER[2:])
    context = ChainContext(31337)
    header = CancunVM.create_genesis_header(difficulty=0, gas_limit=evm.GAS,
                                            timestamp=1, base_fee_per_gas=0)
    rows, builds = [], []
    for family, module in (('pause', pause), ('access', access)):
        for variant in module.VARIANTS:
            for codegen in module.CODEGEN:
                built = module.compile_owned(image, variant, codegen)
                contract = built['contract']
                init = bytes.fromhex(contract['evm']['bytecode']['object'])
                runtime = bytes.fromhex(contract['evm']['deployedBytecode']['object'])
                db = AtomicDB()
                state = CancunVM.build_state(db, header, context)
                birth = CancunComputation.apply_create_message(state, Message(
                    gas=evm.GAS, to=b'', sender=sender, value=0, data=b'',
                    code=init, create_address=receiver),
                    BaseTransactionContext(gas_price=0, origin=sender))
                need(not birth.is_error and state.get_code(receiver) == runtime and
                     birth.output == runtime, 'PY_EVM_CONSTRUCTOR')
                initial = decode_word(state.get_storage(receiver, 0), family)
                wanted = ({'remaining':15, 'distributed':0, 'paused':0} if family == 'pause'
                          else {'admin':evm.SENDER, 'remaining':10, 'distributed':0})
                need(initial == wanted, 'PY_EVM_INITIAL_STATE')
                state.persist()
                initial_header = header.copy(state_root=state.state_root)
                builds.append({'family':family, 'variant':variant, 'codegen':codegen,
                               **built['record'], 'initial_state':initial})
                for index, scenario in enumerate(module.SEQUENCES):
                    # Each sequence starts from the independently run constructor.
                    state = CancunVM.build_state(db, initial_header, context)
                    for step, (arg, amount, gas) in enumerate(scenario):
                        caller = sender if family == 'pause' else bytes.fromhex(arg[2:])
                        method = (('setPaused(uint8)' if arg == 'pause' else 'release(uint8)')
                                  if family == 'pause' else 'payout(uint8)')
                        data = bytes.fromhex(contract['evm']['methodIdentifiers'][method] +
                                             format(amount, '064x'))
                        previous = decode_word(state.get_storage(receiver, 0), family)
                        state.mark_address_warm(caller)
                        state.mark_address_warm(receiver)
                        comp = CancunComputation.apply_message(state, Message(
                            gas=gas, to=receiver, sender=caller, value=0, data=data,
                            code=runtime), BaseTransactionContext(gas_price=0, origin=caller))
                        if not comp.is_error:
                            status = 'COMMITTED'
                        elif isinstance(comp.error, Revert):
                            status = 'REVERTED'
                        elif isinstance(comp.error, OutOfGas):
                            status = 'OUT_OF_GAS'
                        else:
                            raise ValueError('PY_EVM_UNEXPECTED_EXECUTION_ERROR')
                        following = decode_word(state.get_storage(receiver, 0), family)
                        need(state.get_code(receiver) == runtime, 'PY_EVM_RUNTIME_CHANGED')
                        need(status == 'COMMITTED' or previous == following,
                             'PY_EVM_FAILED_CALL_PERSISTED')
                        rows.append({'family':family, 'variant':variant, 'codegen':codegen,
                            'scenario':index, 'step':step, 'input':list((arg, amount, gas)),
                            'status':status, 'before':previous, 'after':following,
                            'return_data':'0x' + comp.output.hex()})
                        # Clear per-message warm/transient caches while preserving
                        # all committed account/storage data through the database.
                        state.persist()
                        state = CancunVM.build_state(db, header.copy(state_root=state.state_root),
                                                     context)
    need(quality.source_snapshot() == before and dependency_identity() == identity,
         'PY_EVM_INPUT_CHANGED_DURING_RUN')
    return {'profile':PROFILE, 'source_digest':digest, 'engine':'py-evm',
            'fork':'Cancun', 'dependencies':identity, 'builds':builds, 'rows':rows,
            'constructor_executions':8, 'runtime_calls':len(rows)}


def main(argv: list[str] | None = None) -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    # The pinned solc image is copied into a sealed memfd before execution;
    # RLIMIT_FSIZE applies to that file too. Match the existing QA 20 MiB cap.
    resource.setrlimit(resource.RLIMIT_FSIZE, (20*1024**2, 20*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    p = PrivateArgumentParser(description='Fixed owned second-EVM worker')
    p.add_argument('--solc', type=Path, required=True)
    p.add_argument('--source-digest', required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(execute_fixed(args.solc, args.source_digest), sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'status':'OWNED_SECOND_EVM_BLOCKED'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
