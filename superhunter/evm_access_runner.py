"""Bounded guest EVM runner for a fixed owned access-control regression.

Uses the exact pinned Geth bytes, a sealed file descriptor and an isolated
synthetic caller. It does not modify the historical EVM worker, accept arbitrary
senders/contracts or provide a network/RPC interface.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

from . import evm_execution as evm, native_compile as compiler
from .safe_io import canonical
from .evm_access_worker import GUEST

ROOT=Path(__file__).resolve().parent


def run_guest(image: bytes, *, prestate: dict, calldata: str, gas: int) -> dict:
    evm.need(type(gas) is int and gas in (evm.GAS,1), 'GUEST_GAS_PROFILE')
    evm.need(type(calldata) is str and re.fullmatch('[0-9a-f]{72}',calldata),
             'GUEST_CALL_PROFILE')
    evm.need(type(image) is bytes and evm.sha(image)==evm.PIN['sha256'],
             'GUEST_EVM_IDENTITY')
    evm.need(type(prestate) is dict and prestate.get('gasLimit')==hex(gas),
             'GUEST_GENESIS_GAS_MISMATCH')
    # There is no arbitrary source, process argument, sender, receiver or RPC.
    with compiler._sealed_executable(image) as fd, tempfile.TemporaryDirectory(prefix='sh-evm-guest-') as tmp:
        root=Path(tmp)
        (root/'prestate.json').write_bytes(canonical(prestate))
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            command=[sys.executable,'-I','-B',str(ROOT/'evm_access_worker.py'),
                     str(fd),calldata,str(gas)]
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                         stdout=output,stderr=error,cwd=root,
                         env={'LANG':'C','LC_ALL':'C'},pass_fds=(fd,),start_new_session=True)
            try:
                code=process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise evm.EVMError('GUEST_EVM_PROCESS_TIMEOUT') from None
            evm.need(output.seek(0,os.SEEK_END)<2_000_000 and
                     error.seek(0,os.SEEK_END)<2_000_000, 'GUEST_EVM_OUTPUT_LIMIT')
            output.seek(0);error.seek(0)
            stdout,stderr=output.read(),error.read()
            evm.need(code==0 and not stderr,'GUEST_EVM_PROCESS_FAILED')
    # An unexpected third account would be rejected, not silently trusted;
    # the pinned Geth profile only emits the constructor sender and receiver.
    observed=evm.parse_run(stdout)
    return {'prestate_sha256':evm.sha(canonical(prestate)), 'mode':'call',
            'gas_limit':gas,'calldata':calldata,
            'stdout_utf8':stdout.decode(),'stderr_utf8':'','observed':observed}
