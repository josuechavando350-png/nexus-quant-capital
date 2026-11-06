"""Fixed, local Geth guest-call worker. No general sender/network interface.

This worker isolates a second SYNTHETIC caller so the original pinned EVM
worker and all its historic evidence identities remain unchanged.
"""
from __future__ import annotations

import os
import re
import resource
import sys


GUEST = '0x' + '22' * 20
RECEIVER = '0x8f7a45ebde059392e46a46dcc14ab24681a961ea'


def main() -> None:
    if len(sys.argv) != 4:
        raise ValueError('FIXED_GUEST_WORKER_ARGUMENTS')
    descriptor, calldata, gas = sys.argv[1:]
    if not descriptor.isdecimal() or not re.fullmatch(r'[0-9a-f]{72}',calldata):
        raise ValueError('FIXED_GUEST_WORKER_DATA')
    if gas not in ('2000000','1'):
        raise ValueError('FIXED_GUEST_WORKER_GAS')
    fd=int(descriptor)
    os.fstat(fd)
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(2_000_000,2_000_000))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    args=['evm','--verbosity','0','run','--dump','--gas',gas,
          '--prestate','prestate.json','--sender',GUEST,
          '--receiver',RECEIVER,'--input',calldata]
    os.execve('/proc/self/fd/'+str(fd),args,
              {'LANG':'C','LC_ALL':'C','GOMAXPROCS':'2'})


if __name__ == '__main__':
    main()
