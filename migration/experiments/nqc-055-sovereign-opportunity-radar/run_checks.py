"""Offline validation; writes only the new experiment's evidence."""
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
    evidence=HERE/'evidence'; evidence.mkdir(exist_ok=True)
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'1'}
    commands=[
        ('tests.log',[sys.executable,'-m','unittest','discover','-s',str(HERE),'-p','test_*.py','-v']),
        ('isolation-tests.log',[sys.executable,'-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
        ('isolation.json',[sys.executable,'migration/verify_isolation.py']),
        ('radar.json',[sys.executable,str(HERE/'radar.py')]),
    ]
    records=[]
    for name,argv in commands:
        result=subprocess.run(argv,cwd=REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (evidence/name).write_bytes(result.stdout)
        count=re.search(rb'Ran (\d+) tests',result.stdout)
        records.append({'artifact':'evidence/'+name,'argv':argv,'exit_code':result.returncode,
            'tests':int(count[1]) if count else None,'sha256':hashlib.sha256(result.stdout).hexdigest()})
    again=subprocess.run(commands[-1][1],cwd=REPO,env={**env,'PYTHONHASHSEED':'55'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    identical=again.returncode==0 and again.stdout==(evidence/'radar.json').read_bytes()
    validation={'schema':'nqc055-validation-v1','python':sys.version,'dependencies':'Python standard library only; no installation',
        'commands':records,'determinism':{'fresh_process_hashseeds':[1,55],'second_exit_code':again.returncode,
            'byte_identical':identical,'second_sha256':hashlib.sha256(again.stdout).hexdigest()},
        'passed':all(r['exit_code']==0 for r in records) and identical and records[0]['tests']==35 and records[1]['tests']==9,
        'first_development_suite':'35 passed, 0 failed, 0 skipped; evidence/first-tests.log',
        'prior_experiment_suites':'NOT_RERUN_NO_OLD_SOURCE_CHANGED',
        'Rust_Solidity':'NOT_RUN_NO_RUST_SOLIDITY_CHANGED',
        'live_RPC_EVM_replay_trading':'NOT_RUN_OFFLINE_ONLY',
        'commercial_admission':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    if records[-1]['exit_code']==0:
        report=json.loads((evidence/'radar.json').read_text())
        summary={k:report[k] for k in ('schema','policy','sources_verified','evaluation','proposed_next_probe','outcome','security','monthly','result_sha256')}
        summary['shared_market_groups']=len(report['shared_requirements']['same_market_groups'])
        summary['shared_asset_pair_groups']=len(report['shared_requirements']['same_asset_pair_groups'])
        (evidence/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(validation,indent=2))
    return 0 if validation['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
