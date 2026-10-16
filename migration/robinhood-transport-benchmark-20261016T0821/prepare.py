"""Offline preregistration/manifest generation; never queries a provider."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')

if sys.argv[1] == 'policy':
    policy = json.loads((HERE.parent/'robinhood-history-continuation-20261016T0715/policy.json').read_text())
    for name in list(policy):
        if name.startswith(('backfill_', 'source_registry_')) or name in ('rounds', 'read_mode', 'cohort_freeze'):
            policy.pop(name)
    source = HERE.parent/'robinhood-history-continuation-20261016T0715/evidence/pilot/registry.json'
    policy.update(study='NQC_FIXED_COHORT_TRANSPORT_TRIADS_V1',
        source_path=str(source.relative_to(HERE.parent.parent)), source_file_sha256=sha(source),
        source_root='3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de',
        orders=[['legacy','fresh','persistent'],['fresh','persistent','legacy'],
                ['persistent','legacy','fresh'],['persistent','fresh','legacy'],
                ['fresh','legacy','persistent'],['legacy','persistent','fresh']],
        cohort_freeze='unchanged PR14 30-account cohort; canonical boundaries rechecked; no new logs',
        capture_max_expected_methods=49, retries=0, redirects=False, parallel_http=False,
        max_response_bytes=2097152, max_total_response_bytes=33554432, http_wall_timeout_seconds=20)
    write(HERE/'policy.json', policy)
elif sys.argv[1] == 'lock':
    prior = HERE.parent/'robinhood-history-continuation-20261016T0715'
    files = {str(p.relative_to(HERE)): sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256')}
    old = json.loads((prior/'registration-sources.json').read_text())
    import os
    for name in [*old['files'], 'registration-sources.json', 'evidence/pilot/registry.json']:
        path = (prior/name).resolve()
        files[os.path.relpath(path, HERE)] = sha(path)
    write(HERE/'registration-sources.json', {'base_commit':'26bf4105926a57480a0a920091d8dc3f720351a4','files':files})
elif sys.argv[1] == 'manifest':
    files = sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:
    raise ValueError('ACTION')
