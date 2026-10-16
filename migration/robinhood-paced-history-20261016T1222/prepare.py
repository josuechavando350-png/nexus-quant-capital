"""New policy, transitive source lock and manifest; no RPC."""
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-paced-acquisition-20261016T1024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
if sys.argv[1]=='policy':
    p=json.loads((PRIOR/'policy.json').read_text())
    source=PRIOR/'evidence/pilot/registry.json'
    p.update(study='NQC_PACED_HISTORY_V1',rounds=3,backfill_from_block=88246281,
             backfill_through_block=88646280,backfill_blocks=400000,
             source_path=str(source.relative_to(HERE.parent.parent)),source_file_sha256=sha(source),
             source_root=json.loads(source.read_text())['sha256'],
             transport='one persistent session for history, merge verification, tail, authentication and observation; no rotation',
             cohort_freeze='after complete history merge, tail catch-up and protocol authentication',
             phase_budget='one global 512-method/900-second/350-ms gate; no reset between phases',
             observation_scope='three retained current hash-pinned observations; coverage study, not repeated transport benchmark')
    write(HERE/'policy.json',p)
elif sys.argv[1]=='lock':
    files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256','CONTINUITY.md')}
    previous=json.loads((PRIOR/'registration-sources.json').read_text())
    for name in [*previous['files'],'registration-sources.json','evidence/pilot/registry.json']:
        path=(PRIOR/name).resolve();files[os.path.relpath(path,HERE)]=sha(path)
    write(HERE/'registration-sources.json',{'base_commit':'9063049967530a682d28d94af5ff17cf46c7bd66','files':files})
elif sys.argv[1]=='manifest':
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:raise ValueError('ACTION')
