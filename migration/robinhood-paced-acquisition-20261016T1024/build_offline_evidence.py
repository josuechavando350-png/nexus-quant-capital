"""Persist explicitly SYNTHETIC traces, regressions and provenance; no RPC."""
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

from test_paced import HERE, execute, previous, POLICY, Reader, run, audit
from paced_acquisition import canonical

ROOT=HERE.parent.parent
out=HERE/'evidence'
summaries=[]
with patch.object(previous,'POLICY',POLICY), patch.object(previous,'Reader',Reader), patch.object(previous,'run',run), \
     patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY')):
    for name,seconds,fault in [('complete',900,None),('quota-stop',900,10),('deadline-before-index',1,None),('deadline-after-rotation',9,None)]:
        chain,p,raw=previous.fixture();p['max_run_seconds']=seconds
        path=out/'synthetic'/name
        reader,_=execute(path,chain,p,raw,fail=fault)
        result=audit(path,p)
        (path/'audit.json').write_bytes(canonical(result))
        summaries.append({'case':name,'synthetic_only':True,'status':result['status'],
            'rpc_calls_simulated':result['rpc_calls'],'admission_attempts':result['admission_attempts'],
            'minimum_start_gap_ms':result['minimum_start_gap_ms'],
            'observations_simulated':len(result['observations']),
            'added_blocks_simulated':result['registry']['added_blocks'],
            'admission_to_verified_ms_simulated':[r['admission_to_verified_ms'] for r in result['observations']],
            'rpc_start_to_verified_ms_simulated':[r['request_to_verified_ms'] for r in result['observations']],
            'admission_intervals_ms_simulated':result['acquisition_admission_intervals_ms'],
            'audit_sha256':hashlib.sha256((path/'audit.json').read_bytes()).hexdigest()})

old=[]
for directory in ['robinhood-history-backfill-20261016','robinhood-history-continuation-20261016T0715',
                  'robinhood-transport-benchmark-20261016T0821','robinhood-acquisition-20261016T0922']:
    folder=HERE.parent/directory;manifest=folder/'MANIFEST.sha256';count=0
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1)
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
        count+=1
    old.append({'directory':directory,'files_verified':count,'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()})

# Re-run the real historical STOPPED capture with its original auditor, not
# the new protocol, which must not reinterpret that capture retroactively.
sys.path.insert(0,str(HERE.parent/'robinhood-acquisition-20261016T0922'))
from audit_acquisition import audit as old_audit
old_report=old_audit(HERE.parent/'robinhood-acquisition-20261016T0922/evidence/pilot')
assert old_report['status']=='stopped' and old_report['rpc_calls']==10 and old_report['observations']==[]
(out/'pr16-replay.json').write_bytes(canonical(old_report))

tests=[]
for receipt in sorted((out/'verification').glob('*.txt')):
    match=re.search(r'Ran (\d+) tests? in',receipt.read_text())
    if match:
        assert '\nOK\n' in receipt.read_text()
        tests.append({'suite':receipt.stem,'passed':int(match[1]),'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()})
lock=json.loads((HERE/'registration-sources.json').read_text())
for name,digest in lock['files'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
report={'kind':'OFFLINE_PREPARATION_NOT_CHAIN_MEASUREMENT','chain_rpc_calls':0,'chain_capture_seconds':0,
        'live_broadcasts':0,'profitability_measured':False,'realized_profit':None,
        'python':sys.version,'tests':tests,'tests_passed':sum(t['passed'] for t in tests),
        'registered_source_files_verified':len(lock['files']),'prior_manifests':old,'synthetic_cases':summaries,
        'registry_source_path':POLICY['source_path'],'registry_source_root':POLICY['source_root'],
        'registry_source_file_sha256':POLICY['source_file_sha256'],
        'rust_solidity':'unchanged, not rerun','historical_pr16_replay':'stopped, 10 RPC, 0 observations; unchanged'}
(out/'offline-summary.json').write_bytes(canonical(report))
print(json.dumps(report,indent=2))
