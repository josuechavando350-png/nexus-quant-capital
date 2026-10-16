"""Offline suite receipts; no provider access."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
out=HERE/'evidence/verification';out.mkdir(parents=True,exist_ok=True)
suites=[('paced',str(HERE.relative_to(ROOT)),'test_*.py'),
        ('acquisition','migration/robinhood-acquisition-20261016T0922','test_acquisition.py'),
        ('transport','migration/robinhood-transport-benchmark-20261016T0821','test_transport.py'),
        ('continuation','migration/robinhood-history-continuation-20261016T0715','test_continuation.py'),
        ('lens','migration/robinhood-history-backfill-20261016','test_experiment.py'),
        ('registry','migration/robinhood-borrower-registry-20261016','test_registry.py'),
        ('isolation-tests','migration','test_isolation.py')]
commands=[(name,['-m','unittest','discover','-s',folder,'-p',pattern,'-v']) for name,folder,pattern in suites]
commands += [('isolation',['migration/verify_isolation.py']),('original-blobs',['migration/engine-v2-20261015/verify_import.py'])]
results=[]
for name,args in commands:
    result=subprocess.run([sys.executable,*args],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
    (out/(name+'.txt')).write_text(result.stdout+result.stderr)
    results.append({'name':name,'command':['python',*args],'exit_code':result.returncode})
    print(name,result.returncode,flush=True)
(out/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(int(any(r['exit_code'] for r in results)))
