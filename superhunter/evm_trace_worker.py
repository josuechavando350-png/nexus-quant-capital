"""Pinned, offline Geth trace worker for existing owned Solidity fixtures.

Accepts only the same fixed creator/call shapes as evm_worker. The parent
supplies a sealed, SHA-256-checked binary and prepared prestate. No RPC, API,
transaction broadcast, arbitrary command-line options, or code supplied by a
program on a bounty platform. Resource limits are not a sandbox for malware.
"""
from __future__ import annotations

import os
import re
import resource
import sys


def main() -> None:
    if len(sys.argv) != 5:
        raise ValueError('TRACE_WORKER_ARGUMENTS')
    mode, descriptor, data, gas = sys.argv[1:]
    if mode not in ('create', 'call') or not descriptor.isdecimal() or gas not in ('2000000', '1'):
        raise ValueError('TRACE_WORKER_PROFILE')
    if ((mode == 'create' and data != '-') or
        (mode == 'call' and re.fullmatch('[0-9a-f]{72}', data) is None)):
        raise ValueError('TRACE_WORKER_DATA')
    fd = int(descriptor)
    os.fstat(fd)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    args = ['evm', '--verbosity', '0', 'run', '--dump', '--trace',
            '--trace.nomemory', '--trace.nostack', '--trace.nostorage',
            '--gas', gas, '--prestate', 'prestate.json', '--sender', '0x' + '11'*20]
    if mode == 'create':
        args += ['--create', '--codefile', 'creation.hex']
    else:
        args += ['--receiver', '0x8f7a45ebde059392e46a46dcc14ab24681a961ea',
                 '--input', data]
    os.execve('/proc/self/fd/' + str(fd), args,
              {'LANG': 'C', 'LC_ALL': 'C', 'GOMAXPROCS': '2'})


if __name__ == '__main__':
    main()
