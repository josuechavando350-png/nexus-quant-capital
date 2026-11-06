"""Linux resource limits for a byte-pinned compiler. Not a hostile-code sandbox.

Only a parent-verified, sealed executable fd is accepted by the public runner.
This private worker does not resolve executable names or load source files.
"""
from __future__ import annotations
import os
import resource
import sys


def main() -> int:
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ('version', 'compile'):
            raise ValueError('WORKER_ARGUMENTS')
        mode, fd = sys.argv[1], int(sys.argv[2])
        if fd < 3 or os.execve not in os.supports_fd:
            raise ValueError('EXEC_FD_REQUIRED')
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        args = ['solc', '--version'] if mode == 'version' else [
            'solc', '--standard-json', '--no-import-callback']
        os.execve(fd, args, {'LANG':'C', 'LC_ALL':'C'})
    except Exception:
        sys.stderr.write('COMPILER_WORKER_ERROR\n')
        return 125
    return 125


if __name__ == '__main__':
    raise SystemExit(main())
