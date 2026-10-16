"""Offline fixed policy and source manifests; never calls RPC."""
import hashlib
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-transport-benchmark-20261016T0821'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
if sys.argv[1]=='policy':
    p=json.loads((PRIOR/'policy.json').read_text())
    p.pop('orders');p.pop('capture_max_expected_methods')
    p.update(study='NQC_PERSISTENT_COMPLETE_ACQUISITION_V1',rounds=12,
             cohort_freeze='after tail-only catch-up and protocol authentication; before position observations',
             transport='persistent for all requests; exactly one deliberate pre-observation pool rotation',
             repeated_heads='retain and flag; reject regressions or a different hash at equal height',
             pacing='sequential completion-driven; no retry, no parallel HTTP, no sleep or outlier removal')
    write(HERE/'policy.json',p)
elif sys.argv[1]=='lock':
    files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256')}
    lock=json.loads((PRIOR/'registration-sources.json').read_text())
    for name in [*lock['files'],'registration-sources.json','audit_transport.py','requirements.txt']:
        path=(PRIOR/name).resolve();files[os.path.relpath(path,HERE)]=sha(path)
    fixture=HERE.parent/'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json'
    files[os.path.relpath(fixture,HERE)]=sha(fixture)
    write(HERE/'registration-sources.json',{'base_commit':'170148bf07920ae0e9112cc7f28507ca6051dd77','files':files})
elif sys.argv[1]=='manifest':
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:raise ValueError('ACTION')
