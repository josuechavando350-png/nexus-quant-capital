"""Re-audit an existing pinned source export offline; never starts an EVM/RPC."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    source = a.source_dir.resolve()
    manifest = json.loads((HERE/'evidence/reference-extraction.json').read_text())
    for item in manifest['entries']:
        path = (source/item['path']).resolve()
        if not path.is_relative_to(source):
            raise ValueError('source escaped export directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('source hash mismatch: '+item['path'])
    out = a.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)  # preserve prior results
    base = source/'migration/engine-v2-20261015/source/ci/nqc-census'
    commands = [
        ('aave-source-gate', [sys.executable, str(base/'rmc-v2-shadow/svr_auction_finance_gate.py'),
            '--source', str(base/'weth-physical/script/NqcV2OneShotAtomicLocal.s.sol'),
            '--out', str(out/'aave-source-gate.json')]),
        ('aave-reference-tests', [sys.executable,'-m','unittest','discover','-v','-s',
            str(base/'rmc-v2-shadow'),'-p','test_svr_auction_finance_gate.py']),
        ('robinhood-reconciliation', [sys.executable,
            str(source/'migration/robinhood-real-state-replay-20261016/audit_result.py'),
            '--out',str(out/'robinhood-reconciliation.json')])]
    records=[]
    for label, command in commands:
        start=datetime.now(timezone.utc).isoformat()
        r=subprocess.run(command,cwd=source,capture_output=True,timeout=60)
        output=r.stdout+r.stderr
        (out/(label+'.log')).write_bytes(output)
        records.append(dict(command=command,cwd=str(source),started_at_utc=start,
                            ended_at_utc=datetime.now(timezone.utc).isoformat(),exit_code=r.returncode,
                            output=label+'.log',sha256=hashlib.sha256(output).hexdigest()))
        (out/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
        if r.returncode: raise RuntimeError('reference audit failed: '+label)
    for name in ('aave-source-gate.json','robinhood-reconciliation.json'):
        if json.loads((out/name).read_text()) != json.loads((HERE/'evidence'/name).read_text()):
            raise ValueError('recorded reference output changed: '+name)
    print(json.dumps({'pinned_input_files_verified':len(manifest['entries']),
                      'reference_outputs_equal':True,'new_evm_execution':False,
                      'commercial_admission':False,'source_commit':manifest['source_commit']}))


if __name__=='__main__': main()
