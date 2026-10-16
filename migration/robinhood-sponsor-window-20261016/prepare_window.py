#!/usr/bin/env python3
"""Pinned, offline build in a fresh external directory; original source unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dependencies', type=Path, required=True)
    ap.add_argument('--foundry-bin', type=Path, required=True)
    ap.add_argument('--solc', type=Path, required=True)
    ap.add_argument('--build', type=Path, required=True)
    args = ap.parse_args()
    # Existing preparer authenticates binaries, clean dependency commits and source blobs.
    subprocess.run([sys.executable, str(HERE.parent / 'robinhood-real-state-replay-20261016/prepare_cycle.py'),
                    '--dependencies', str(args.dependencies), '--foundry-bin', str(args.foundry_bin),
                    '--solc', str(args.solc), '--build', str(args.build)], check=True)
    shutil.copy2(HERE / 'NqcWindowedPaymasterFixture.sol', args.build / 'robinhood/src')
    shutil.copy2(HERE / 'NqcWindowedPaymaster.t.sol', args.build / 'robinhood/test')
    ep = json.loads((HERE.parent / 'robinhood-real-state-replay-20261016/evidence/nitro-phase1/02-entrypoint-at-parent.json').read_text())['result']
    (args.build / 'robinhood/runtime.json').write_text(json.dumps({'runtime': ep}) + '\n')
    with (args.build / 'window-tests.log').open('w') as log:
        subprocess.run([str(args.foundry_bin / 'forge'), 'test', '--root', str(args.build / 'robinhood'),
                        '--use', str(args.solc), '--match-contract', 'NqcWindowedPaymasterTest', '-vv'],
                        stdout=log, stderr=subprocess.STDOUT, check=True)
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.sol')}
    (args.build / 'window-source-lock.json').write_text(json.dumps({'sources': sources,
        'entrypoint_runtime_sha256': hashlib.sha256(bytes.fromhex(ep[2:])).hexdigest()}, indent=2) + '\n')
    print('PASS: isolated window fixture build and tests')


if __name__ == '__main__':
    main()
