"""Read-only offline checks and receipts; does not run the chain capture."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
PROTOCOL=HERE.parent/'robinhood-paced-acquisition-20261016T1024'
out=HERE/'evidence/verification';out.mkdir(parents=True,exist_ok=True)
lock=json.loads((PROTOCOL/'registration-sources.json').read_text())
for name,digest in lock['files'].items():
    assert hashlib.sha256((PROTOCOL/name).read_bytes()).hexdigest()==digest,name
manifest=[]
for dirname in ['robinhood-history-backfill-20261016','robinhood-history-continuation-20261016T0715',
                'robinhood-transport-benchmark-20261016T0821','robinhood-acquisition-20261016T0922',PROTOCOL.name]:
    folder=HERE.parent/dirname;count=0
    for line in (folder/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1)
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name
        count+=1
    manifest.append({'folder':dirname,'files':count,'sha256':hashlib.sha256((folder/'MANIFEST.sha256').read_bytes()).hexdigest()})
deps={}
for line in (HERE.parent/'robinhood-transport-benchmark-20261016T0821/requirements.txt').read_text().splitlines():
    name,expected=line.split('==');deps[name]=version(name);assert deps[name]==expected
worktrees=[Path(line[9:]) for line in subprocess.check_output(['git','worktree','list','--porcelain'],cwd=ROOT,text=True).splitlines() if line.startswith('worktree ')]
assert not any((w/PROTOCOL.relative_to(ROOT)/'evidence/pilot').exists() for w in worktrees),'CAPTURE_ALREADY_EXISTS'
matches=[];inspected=0
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=path.read_bytes()
    except FileNotFoundError:continue
    inspected+=1
    if int(path.parent.name)!=os.getpid() and any(name in raw for name in (b'paced_acquisition.py',b'/acquisition.py',b'/collect.py')):
        matches.append(int(path.parent.name))
assert not matches,'CAPTURE_PROCESS_EXISTS'
commands=[('paced',['-m','unittest','discover','-s',str(PROTOCOL.relative_to(ROOT)),'-p','test_*.py','-v']),
          ('isolation-tests',['-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
          ('isolation',['migration/verify_isolation.py']),
          ('original-blobs',['migration/engine-v2-20261015/verify_import.py'])]
receipts=[]
for name,args in commands:
    completed=subprocess.run([sys.executable,*args],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
    (out/(name+'.txt')).write_text(completed.stdout+completed.stderr)
    receipts.append({'name':name,'command':['python',*args],'exit_code':completed.returncode})
    print(name,completed.returncode,flush=True)
report={'registered_sources':len(lock['files']),'prior_manifests':manifest,'dependencies':deps,
        'worktrees_checked':len(worktrees),'existing_capture_directories':0,
        'proc_entries_inspected':inspected,'matching_capture_processes':matches,
        'commands':receipts,'chain_rpc_calls':0,'python':sys.version}
(out/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
assert all(r['exit_code']==0 for r in receipts),'OFFLINE_FAILURE'
print(json.dumps(report,indent=2))
