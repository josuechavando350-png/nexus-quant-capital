"""Create a new immutable policy and transitive lock; manifest is derived."""
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-paced-history-20261016T1222'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
if sys.argv[1]=='policy':
    p=json.loads((PRIOR/'policy.json').read_text());source=PRIOR/'evidence/pilot/registry.json'
    p.update(study='NQC_PACED_HISTORY_EXTENSION_20261016T1317',backfill_from_block=87846281,
             backfill_through_block=88246280,source_path=str(source.relative_to(HERE.parent.parent)),
             source_root=json.loads(source.read_text())['sha256'],source_file_sha256=sha(source))
    write(HERE/'policy.json',p)
elif sys.argv[1]=='lock':
    files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256','CONTINUITY.md')}
    previous=json.loads((PRIOR/'registration-sources.json').read_text())
    for name in [*previous['files'],'registration-sources.json','evidence/pilot/registry.json']:
        path=(PRIOR/name).resolve();files[os.path.relpath(path,HERE)]=sha(path)
    write(HERE/'registration-sources.json',{'base_commit':'ca184cdd14d8d5a8a4d447a9723a0e792dc00132','files':files})
elif sys.argv[1]=='manifest':
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:raise ValueError('ACTION')
