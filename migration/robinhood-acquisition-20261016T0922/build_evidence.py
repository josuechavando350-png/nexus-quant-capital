"""Post-capture provenance; never retries or queries a provider."""
from datetime import datetime,timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
lock=json.loads((HERE/'registration-sources.json').read_text())
for name,expected in lock['files'].items():assert sha(HERE/name)==expected,name
prior={}
for directory in ('robinhood-history-backfill-20261016','robinhood-history-continuation-20261016T0715','robinhood-transport-benchmark-20261016T0821'):
    path=HERE.parent/directory;lines=(path/'MANIFEST.sha256').read_text().splitlines()
    for line in lines:
        expected,name=line.split('  ',1);assert sha(path/name)==expected,name
    prior[directory]={'files_verified':len(lines),'manifest_sha256':sha(path/'MANIFEST.sha256')}
tests={}
for name in ('acquisition','transport','continuation','lens','registry','isolation-tests'):
    text=(HERE/'evidence/verification'/f'{name}.txt').read_text()
    assert text.rstrip().endswith('OK'),name
    tests[name]=int(re.search(r'Ran (\d+) tests',text).group(1))
audit=json.loads((HERE/'evidence/audit.json').read_text())
assert audit['status']=='stopped' and audit['rpc_calls']==10 and audit['observations']==[] and audit['cohort'] is None
proof={
 'written_utc':datetime.now(timezone.utc).isoformat(),
 'repository':'josuechavando350-png/nexus-quant-capital',
 'base_commit':'170148bf07920ae0e9112cc7f28507ca6051dd77',
 'registration_commit':'d03ecc8e1106488e80d33d8a4beecff65375db80',
 'registration_tree':'28dc9e433543f26c0159748698d66361ed3a512b',
 'registered_sources_unchanged':len(lock['files']),'prior_manifests_verified':prior,
 'python_tests_passed':tests,'python_tests_total':sum(tests.values()),'python':platform.python_version(),
 'dependencies':{line.split('==')[0]:version(line.split('==')[0]) for line in
    (HERE.parent/'robinhood-transport-benchmark-20261016T0821/requirements.txt').read_text().splitlines()},
 'capture_command':'python migration/robinhood-acquisition-20261016T0922/acquisition.py --out migration/robinhood-acquisition-20261016T0922/evidence/pilot --registration-commit d03ecc8e1106488e80d33d8a4beecff65375db80',
 'capture_process_exit_code':1,'capture_process_elapsed_seconds':5.131330236,
 'terminal_reason':'HTTP_STATUS_429','provider_error_code':-32007,'provider_message':'5/second request limit reached',
 'further_rpc_after_denial':0,'measurement_started':False,'observations_completed':0,
 'rpc_methods_total':10,'http_requests_total':10,'rpc_retries':0,'endpoint_changes':0,
 'audit_command':'python migration/robinhood-acquisition-20261016T0922/audit_acquisition.py migration/robinhood-acquisition-20261016T0922/evidence/pilot --out migration/robinhood-acquisition-20261016T0922/evidence/audit.json',
 'audit_sha256':sha(HERE/'evidence/audit.json'),'summary_sha256':sha(HERE/'evidence/summary.json'),
 'journal_sha256':sha(HERE/'evidence/pilot/journal.jsonl'),'ledger_sha256':sha(HERE/'evidence/pilot/requests.json'),
 'next_source_file_sha256':sha(HERE/'evidence/pilot/registry.json'),
 'next_source_registry_root':audit['registry']['sha256'],'next_source_status':'valid_prefix_not_frozen',
 'original_blobs_verified':377,'disabled_workflows':106,'active_workflows':0,
 'solidity_tests_rerun':False,'rust_tests_rerun':False,'live_broadcasts':0,'route_simulations':0,
 'realized_profit':None,'funded_capacity_wei':0,
 'limitations':['HTTP 429 prevented completion','no fresh debt/coverage/candidate/latency observations',
    'partial tail target, canonical revalidation required next time','single demo provider; no independent state/log proof',
    'reported 5/second is not a purchased SLA or proof of exact quota scope']}
(HERE/'evidence/provenance.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
print(json.dumps({'sources':len(lock['files']),'tests':sum(tests.values()),'previous_manifests':prior,'status':audit['status']}))
