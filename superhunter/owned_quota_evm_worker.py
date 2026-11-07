"""Dedicated two-GiB worker for fixed owned quota controls only.

The caller passes a sealed, hash-checked official evm image. This resource limit
wrapper is not an OS sandbox for hostile native code. No RPC/node mode exists.
"""
import os
import re
import resource
import sys


def main() -> None:
    if len(sys.argv) != 5:
        raise ValueError('WORKER_ARGUMENTS')
    mode, descriptor, data, gas = sys.argv[1:]
    if mode not in ('create', 'call') or not descriptor.isdecimal() or gas not in ('2000000', '1'):
        raise ValueError('WORKER_PROFILE')
    if (mode == 'create' and data != '-') or (mode == 'call' and re.fullmatch('[0-9a-f]{72}', data) is None):
        raise ValueError('WORKER_DATA')
    fd = int(descriptor)
    os.fstat(fd)
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    # Match the enclosing QA/lab budget; a child cannot raise an inherited
    # hard limit. The previous 4 GiB request failed inside a 2 GiB worker.
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    args = ['evm', '--verbosity', '0', 'run', '--dump', '--gas', gas,
            '--prestate', 'prestate.json', '--sender', '0x' + '11' * 20]
    if mode == 'create':
        args += ['--create', '--codefile', 'creation.hex']
    else:
        args += ['--receiver', '0x8f7a45ebde059392e46a46dcc14ab24681a961ea', '--input', data]
    os.execve('/proc/self/fd/' + str(fd), args,
              {'LANG': 'C', 'LC_ALL': 'C', 'GOMAXPROCS': '2'})


if __name__ == '__main__':
    main()
