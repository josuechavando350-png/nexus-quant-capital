"""Reproduce NQC054 from fixed Git objects, without network or credentials."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import Crypto

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def run():
    evidence=HERE/'evidence'; evidence.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    commands=[
        ('tests.log',[sys.executable,'-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),
        ('isolation-tests.log',[sys.executable,'-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
        ('isolation.json',[sys.executable,'migration/verify_isolation.py']),
        ('audit.json',[sys.executable,str(HERE/'audit.py')]),
    ]
    results=[]
    for filename,argv in commands:
        result=subprocess.run(argv,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (evidence/filename).write_bytes(result.stdout)
        count=re.search(r'Ran (\d+) tests',result.stdout.decode())
        results.append({'artifact':'evidence/'+filename,'argv':argv,'exit_code':result.returncode,
                        'tests':int(count[1]) if count else None,
                        'sha256':hashlib.sha256(result.stdout).hexdigest()})
    validation={'schema':'nqc054-validation-v1','python':sys.version,'pycryptodome':Crypto.__version__,
        'commands':results,'passed':all(r['exit_code']==0 for r in results) and Crypto.__version__=='4.0.1'
            and results[0]['tests']==19 and results[1]['tests']==9,
        'affected_tests_expected':19,'isolation_tests_expected':9,
        'prior_NQC037_052_053_suites':'NOT_RERUN_NO_CHANGE_OR_REGRESSION_IN_OLD_CODE',
        'Rust_and_Solidity':'NOT_RUN_NO_RUST_OR_SOLIDITY_CHANGED',
        'EVM_replay':'NOT_ATTEMPTED_MISSING_MANDATORY_STATE',
        'live_rpc':'NOT_RUN_NOT_AUTHORIZED',
        'development_errors':['One exploratory JSON inventory assumed a dictionary root and raised AttributeError on a list; final inventory handles both types.'],
        'environment_errors':['Initial shell invocation returned exec-server transport disconnected; subsequent non-login shell worked.'],
        'initial_validation_failure':'Dependency pin initially assumed 3.23.0 but installed distribution/module is 4.0.1. Corrected pin; no dependency install/change. See evidence/initial-version-mismatch.json and initial logs.',
        'commercial_admission':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(validation,indent=2))
    return 0 if validation['passed'] else 1


if __name__=='__main__':
    raise SystemExit(run())
