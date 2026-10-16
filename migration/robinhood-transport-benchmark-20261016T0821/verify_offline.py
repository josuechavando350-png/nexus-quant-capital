"""Save reproducible offline command results; no provider access."""
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
out = HERE/'evidence/verification'
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
commands = [
    ('transport', ['-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),
    ('continuation', ['-m','unittest','discover','-s','migration/robinhood-history-continuation-20261016T0715','-p','test_continuation.py','-v']),
    ('lens', ['-m','unittest','discover','-s','migration/robinhood-history-backfill-20261016','-p','test_experiment.py','-v']),
    ('registry', ['-m','unittest','discover','-s','migration/robinhood-borrower-registry-20261016','-p','test_registry.py','-v']),
    ('isolation-tests', ['-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
    ('isolation', ['migration/verify_isolation.py']),
    ('original-blobs', ['migration/engine-v2-20261015/verify_import.py'])]
results = []
for name, args in commands:
    result = subprocess.run([sys.executable,*args], cwd=ROOT, env=env, capture_output=True, text=True)
    (out/(name+'.txt')).write_text(result.stdout+result.stderr)
    results.append({'name':name,'command':['python',*args], 'exit_code':result.returncode})
    print(name, result.returncode, flush=True)
(out/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(int(any(r['exit_code'] for r in results)))
