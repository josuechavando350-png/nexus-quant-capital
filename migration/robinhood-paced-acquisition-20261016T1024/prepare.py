"""Generate NEW offline policy/locks/manifests; no chain access."""
import hashlib
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-acquisition-20261016T0922'
BASE='a6c356ad6379d51683a07f0c67bbd280eb1ec5bf'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')

if sys.argv[1]=='policy':
    p=json.loads((PRIOR/'policy.json').read_text())
    source=PRIOR/'evidence/pilot/registry.json'
    p.update(study='NQC_GLOBALLY_PACED_ACQUISITION_V1',
             source_path=str(source.relative_to(HERE.parent.parent)),
             source_file_sha256=sha(source), source_root=json.loads(source.read_text())['sha256'],
             minimum_start_interval_ns=350_000_000,
             pacing='global local dispatch-start spacing; no burst credit; survives rotation; all waits count in run deadline',
             admission='fail closed on early wake, expired budget or error; never retry or replace failed session',
             latency='primary: before admission of header through canonical verification; secondary: RPC start through verification',
             cadence='retain all rounds; report consecutive header-admission intervals; 3 requests require >=1050 ms steady cadence locally',
             rate_limit_claim='conservative local policy, not SLA or proof of provider arrival-window quota')
    write(HERE/'policy.json',p)
elif sys.argv[1]=='lock':
    files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256','CONTINUITY.md')}
    previous=json.loads((PRIOR/'registration-sources.json').read_text())
    for name in [*previous['files'],'registration-sources.json','acquisition.py','audit_acquisition.py','test_acquisition.py','evidence/pilot/registry.json']:
        path=(PRIOR/name).resolve();files[os.path.relpath(path,HERE)]=sha(path)
    write(HERE/'registration-sources.json',{'base_commit':BASE,'files':files})
elif sys.argv[1]=='manifest':
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:raise ValueError('ACTION')
