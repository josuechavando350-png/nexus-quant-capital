"""Post-capture provenance and immutable-source checks; no network calls."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
lock = json.loads((HERE/'registration-sources.json').read_text())
for name, expected in lock['files'].items():
    assert digest(HERE/name) == expected, name
prior = {}
for directory in ('robinhood-history-backfill-20261016','robinhood-history-continuation-20261016T0715'):
    folder = HERE.parent/directory
    lines = (folder/'MANIFEST.sha256').read_text().splitlines()
    for line in lines:
        expected, name = line.split('  ',1)
        assert digest(folder/name) == expected, name
    prior[directory] = {'files_verified':len(lines),'manifest_sha256':digest(folder/'MANIFEST.sha256')}
tests = {}
for name in ('transport','continuation','lens','registry','isolation-tests'):
    text = (HERE/'evidence/verification'/f'{name}.txt').read_text()
    assert text.endswith('OK\n'), name
    tests[name] = int(re.search(r'Ran (\d+) tests',text).group(1))
names = subprocess.check_output(['git','diff','--name-only','26bf4105926a57480a0a920091d8dc3f720351a4','HEAD'],cwd=ROOT,text=True).splitlines()
assert all(name.startswith(str(HERE.relative_to(ROOT))+'/') for name in names)
proof = {
    'written_utc':datetime.now(timezone.utc).isoformat(),
    'repository':'josuechavando350-png/nexus-quant-capital',
    'base_commit':lock['base_commit'],
    'registration_commit':'8bdd6f8be2cc16ceb6c8330d9186c60cde90c522',
    'registration_tree':'bae5302735d65daab17ade950e186edc70161a74',
    'registered_files_unchanged':len(lock['files']),
    'prior_manifests_verified':prior,
    'python_tests_passed':tests,'python_tests_total':sum(tests.values()),
    'python':platform.python_version(),
    'dependencies':{line.split('==')[0]:version(line.split('==')[0]) for line in (HERE/'requirements.txt').read_text().splitlines()},
    'capture_command':'python migration/robinhood-transport-benchmark-20261016T0821/benchmark.py --out migration/robinhood-transport-benchmark-20261016T0821/evidence/pilot --registration-commit 8bdd6f8be2cc16ceb6c8330d9186c60cde90c522',
    'capture_process_exit_code':0, 'capture_process_elapsed_seconds':114.696889078,
    'audit_command':'python migration/robinhood-transport-benchmark-20261016T0821/audit_transport.py migration/robinhood-transport-benchmark-20261016T0821/evidence/pilot --out migration/robinhood-transport-benchmark-20261016T0821/evidence/audit.json',
    'audit_sha256':digest(HERE/'evidence/audit.json'),
    'summary_sha256':digest(HERE/'evidence/summary.json'),
    'journal_sha256':digest(HERE/'evidence/pilot/journal.jsonl'),
    'ledger_sha256':digest(HERE/'evidence/pilot/requests.json'),
    'solidity_tests_rerun':False,'rust_tests_rerun':False,
    'original_blobs_verified':377,'disabled_workflows':106,'active_workflows':0,
    'realized_profit':None,'route_simulations':0,'live_broadcasts':0,'funded_capacity_wei':0,
    'limitations':['single demo provider and configured proxy','six blocks, five reused views',
        'partial fixed cohort, no tail catch-up','headers use old transport, complete acquisition target unmet',
        'no independent cryptographic provider-state proof','socket tags describe client, not upstream server']}
(HERE/'evidence/provenance.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
print(json.dumps({'registered_sources':len(lock['files']),'tests':sum(tests.values()),'prior_manifests':prior}))
