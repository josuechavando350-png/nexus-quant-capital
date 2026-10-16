#!/usr/bin/env python3
"""Offline reproduction after explicit dependency checkout; all EVM transactions stay local."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dependencies',type=Path,required=True)
    ap.add_argument('--foundry-bin',type=Path,required=True)
    ap.add_argument('--solc-019',type=Path,required=True)
    ap.add_argument('--solc-023',type=Path,required=True)
    ap.add_argument('--build',type=Path,required=True)
    args=ap.parse_args()
    for path,expected in [(args.solc_019,'7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48'),
        (args.solc_023,'28726a452290c70e1984f15c53ad3088e7d98783ee3070b11b3664da77415732')]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('compiler identity')
    tool_lock=json.loads((HERE/'toolchain.json').read_text())
    for name,expected in tool_lock['binary_sha256'].items():
        if hashlib.sha256((args.foundry_bin/name).read_bytes()).hexdigest()!=expected:raise ValueError('Foundry identity: '+name)
    def run(*cmd,log=None):
        if log:
            with log.open('w') as f:
                subprocess.run([str(v) for v in cmd],stdout=f,stderr=subprocess.STDOUT,check=True)
            print('PASS:',log.name,flush=True)
        else:subprocess.run([str(v) for v in cmd],check=True)
    run(sys.executable,HERE/'prepare.py','--dependencies',args.dependencies,'--build',args.build)
    results=args.build/'results';results.mkdir()
    run(sys.executable,HERE/'verify_entrypoint.py','--dependencies',args.dependencies,
        '--rpc-evidence',HERE/'evidence/historical-rpc/original_responses.json',
        '--solc',args.solc_023,'--cast',args.foundry_bin/'cast','--out',args.build/'identity',log=results/'identity.txt')
    shutil.copy2(args.build/'identity/runtime.json',args.build/'robinhood/runtime.json')
    for lab,compiler,contract in [('morpho-native-lab',args.solc_019,'NqcMorphoNativeCallbackLabTest'),
        ('baseline',args.solc_023,'NqcRealEntryPointV07GasSponsorTest'),
        ('robinhood',args.solc_023,'NqcRobinhoodCycleTest')]:
        run(args.foundry_bin/'forge','test','--root',args.build/lab,'--use',compiler,
            '--match-contract',contract,'-vv',log=results/(lab+'.txt'))
    run(sys.executable,HERE/'run_local.py','--foundry-bin',args.foundry_bin,
        '--build',args.build,'--out',results/'local',log=results/'local-receipts.txt')
    print('PASS: local reproduction completed; no live or commercial certification',flush=True)

if __name__=='__main__':main()
