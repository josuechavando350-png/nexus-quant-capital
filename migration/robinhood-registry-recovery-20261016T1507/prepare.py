"""Create a new immutable policy and transitive lock; manifest is derived."""
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-history-extension-20261016T1416'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
if sys.argv[1]=='lock':
    files={p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name not in ('registration-sources.json','MANIFEST.sha256','CONTINUITY.md')}
    previous=json.loads((PRIOR/'registration-sources.json').read_text())
    for name in [*previous['files'],'registration-sources.json','evidence/pilot/registry.json','evidence/pilot/older-registry.json']:
        path=(PRIOR/name).resolve();files[os.path.relpath(path,HERE)]=sha(path)
    write(HERE/'registration-sources.json',{'base_commit':'276883828ef921c4f3b55b3dd5ea395615222c73','files':files})
elif sys.argv[1]=='manifest':
    files=sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST.sha256')
    (HERE/'MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(HERE)}\n' for p in files))
else:raise ValueError('ACTION')
