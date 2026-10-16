#!/usr/bin/env python3
"""Compile only in a new external build directory using existing pinned overlays."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'robinhood-aa-20261016'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dependencies', type=Path, required=True)
    ap.add_argument('--foundry-bin', type=Path, required=True)
    ap.add_argument('--solc', type=Path, required=True)
    ap.add_argument('--build', type=Path, required=True)
    args = ap.parse_args()
    lock = json.loads((PREVIOUS / 'toolchain.json').read_text())
    for name, expected in lock['binary_sha256'].items():
        assert hashlib.sha256((args.foundry_bin / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256(args.solc.read_bytes()).hexdigest() == lock['solc']['0.8.23']
    subprocess.run([sys.executable, str(PREVIOUS / 'prepare.py'), '--dependencies', str(args.dependencies),
                    '--build', str(args.build)], check=True, stdout=subprocess.DEVNULL)
    for name in ['NqcHistoricalNetRoute.sol', 'NqcHistoricalScenario.sol']:
        shutil.copy2(HERE / name, args.build / 'robinhood/src' / name)
    with (args.build / 'compile.log').open('w') as log:
        subprocess.run([str(args.foundry_bin / 'forge'), 'build', '--root', str(args.build / 'robinhood'),
                        '--use', str(args.solc), '--skip', 'test', '--skip', 'script'],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.sol')}
    (args.build / 'route-source-lock.json').write_text(json.dumps({'sources': sources, 'toolchain': lock}, indent=2) + '\n')
    print('PASS: pinned offline build')


if __name__ == '__main__':
    main()
