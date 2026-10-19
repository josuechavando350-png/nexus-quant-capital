"""Reproduce the bounded archive search and First Gold decision without network."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def main():
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    commands=[
        ('corpus.json',[sys.executable,str(HERE/'corpus_scan.py')]),
        ('decision.json',[sys.executable,str(HERE/'check_evidence.py')]),
        ('tests.log',[sys.executable,'-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),
        ('isolation-tests.log',[sys.executable,'-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
        ('isolation.json',[sys.executable,'migration/verify_isolation.py']),
    ]
    results=[]
    for name,argv in commands:
        result=subprocess.run(argv,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (HERE/'evidence'/name).write_bytes(result.stdout)
        count=re.search(rb'Ran (\d+) tests',result.stdout)
        results.append({'artifact':'evidence/'+name,'argv':argv,'exit_code':result.returncode,
            'tests':int(count[1]) if count else None,'sha256':hashlib.sha256(result.stdout).hexdigest()})
    validation={'schema':'nqc056-validation-v1','python':sys.version,'dependencies':'Standard library plus unchanged hash-pinned NQC055 core.py',
        'commands':results,'passed':all(r['exit_code']==0 for r in results) and results[2]['tests']==9 and results[3]['tests']==9,
        'older_suites':'NOT_RERUN_NO_OLD_SOURCE_CHANGE','Rust_Solidity':'NOT_RUN_NO_CHANGED_RUST_SOLIDITY',
        'EVM_replay':'NOT_ATTEMPTED_MISSING_INPUTS','live_RPC':'NOT_RUN_NOT_AUTHORIZED',
        'synthetic_data':'Only adversarial tests and a temporary in-memory archive; not market observations or gains',
        'commercial_admission':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    print(json.dumps(validation,indent=2))
    return 0 if validation['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
