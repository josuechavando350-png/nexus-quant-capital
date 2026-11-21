"""Compile and exercise only the fixed arithmetic fixture inside a Mewt campaign."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    source = Path('arithmetic.cpp').read_bytes()
    if len(source) > 512 or len(Path('assertions.c').read_bytes()) > 2048:
        raise ValueError('owned mutation input exceeds its bound')
    compiler = root/'bin/gcc'
    commands = [
        [compiler, '-B', str(root/'bin')+'/', '-std=c11', '-O0', '-ffreestanding',
         '-fno-stack-protector', '-fno-pie', '-fno-asynchronous-unwind-tables', '-nostdinc',
         '-x', 'c', '-c', name, '-o', output]
        for name, output in (('arithmetic.cpp', 'arithmetic.o'), ('assertions.c', 'assertions.o'))]
    commands.append([root/'bin/ld', '-static', '--build-id=none', '-e', '_start', '-o', 'owned-test',
                     'arithmetic.o', 'assertions.o'])
    for command in commands:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=8)
        if result.returncode or result.stdout or result.stderr:
            raise ValueError('owned mutation compilation failed or emitted diagnostics')
    result = subprocess.run(['./owned-test'], stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
    if result.returncode not in (0, 1) or result.stdout or result.stderr:
        raise ValueError('owned mutation test did not terminate with a checked assertion result')
    print(json.dumps({'compiled': True, 'exit_code': result.returncode,
                      'source_sha256': hashlib.sha256(source).hexdigest()}, sort_keys=True, separators=(',', ':')))
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
