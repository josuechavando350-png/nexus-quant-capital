#!/usr/bin/env python3
"""Start and stop the local chain in the same process/network namespace as its client."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--foundry-bin',type=Path,required=True)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    # Fixed loopback URL. No fork, remote URL, real signer or externally funded account.
    port=18564
    process=subprocess.Popen([str(args.foundry_bin/'anvil'),'--host','127.0.0.1',
        '--port',str(port),'--chain-id','4663','--hardfork','paris','--base-fee',
        '1000000000','--silent'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        session=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(40):
            if process.poll() is not None: raise RuntimeError(process.stderr.read().decode())
            request=urllib.request.Request(f'http://127.0.0.1:{port}',
                data=json.dumps({'jsonrpc':'2.0','id':1,'method':'web3_clientVersion','params':[]}).encode(),
                headers={'Content-Type':'application/json'})
            try:
                with session.open(request,timeout=1): break
            except OSError: time.sleep(0.1)
        subprocess.run([sys.executable,str(Path(__file__).with_name('local_receipts.py')),
            '--port',str(port),'--build',str(args.build),'--cast',str(args.foundry_bin/'cast'),
            '--out',str(args.out)],check=True)
    finally:
        process.terminate()
        process.wait(timeout=5)

if __name__=='__main__': main()
