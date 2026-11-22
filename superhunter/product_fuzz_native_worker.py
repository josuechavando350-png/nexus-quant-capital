"""Fixed local fuzzer processes, without target/RPC or caller-selected flags."""
import os
from pathlib import Path
import resource
import sys


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('echidna', 'medusa', 'forge'):
        raise ValueError('unknown owned fuzzer worker')
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    root = Path.cwd().parent/'bin'
    mode = sys.argv[1]
    if mode == 'echidna':
        command = [str(root/'echidna'), 'Owned.sol', '--contract', 'OwnedCap',
                   '--config', 'config.json', '--disable-onchain-sources',
                   '--corpus-dir', 'corpus', '+RTS', '-N1', '-M512m', '-RTS']
    elif mode == 'medusa':
        command = [str(root/'medusa'), 'fuzz', '--config', 'medusa.json']
    else:
        command = [str(root/'forge'), 'test', '--root', '.', '--use', str(root/'solc'), '--offline', '--json']
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
