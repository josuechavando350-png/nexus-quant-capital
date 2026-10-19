"""Reproduce NQC053 offline in a full checkout; no RPC or credentials."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVIDENCE = HERE / 'evidence'


def run():
    EVIDENCE.mkdir(exist_ok=True)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
    commands = [
        ('economics-tests.log', [sys.executable,'-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),
        ('ledger-tests.log', ['node','--test','--test-reporter=tap',str(HERE/'test_ledger.js')]),
        ('isolation-tests.log', [sys.executable,'-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
        ('isolation.json', [sys.executable,'migration/verify_isolation.py']),
        ('economics.json', [sys.executable,str(HERE/'economics.py')]),
    ]
    results = []
    for filename, command in commands:
        result = subprocess.run(command,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (EVIDENCE/filename).write_bytes(result.stdout)
        text = result.stdout.decode()
        count = re.search(r'Ran (\d+) tests',text) or re.search(r'# tests (\d+)',text)
        results.append({'artifact':filename,'argv':command,'exit_code':result.returncode,
                        'tests':int(count[1]) if count else None})
    manifest = json.loads((HERE/'SOURCE_MANIFEST.json').read_text())
    control = []
    for name, pin in manifest['unchanged_control_sources'].items():
        raw = (REPO/pin['path']).read_bytes()
        good = hashlib.sha256(raw).hexdigest()==pin['sha256']
        control.append({'path':pin['path'],'sha256':hashlib.sha256(raw).hexdigest(),'match':good})
    validation = {'schema':'nqc053-validation-v1','python':sys.version,
        'node':subprocess.check_output(['node','--version'],text=True).strip(),
        'commands':results,'unchanged_control_sources':control,
        'passed':all(r['exit_code']==0 for r in results) and all(r['match'] for r in control),
        'historical_nqc037_and_nqc052_suites':'NOT_RERUN_NO_SOURCE_CHANGE_OR_REGRESSION',
        'rust_solidity_tests':'NOT_RUN_NO_RUST_OR_SOLIDITY_CHANGED',
        'real_multihost_or_remote_rollback_tests':'NOT_RUN_LOCAL_MODEL_ONLY',
        'live_rpc_tests':'NOT_RUN_SAFETY_GATES_NOT_SATISFIED',
        'triport_requests_this_experiment':0,'commercial_admission':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(validation,indent=2))
    return 0 if validation['passed'] else 1


if __name__=='__main__':
    raise SystemExit(run())
