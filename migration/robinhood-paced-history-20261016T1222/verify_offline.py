"""Offline receipts, historical-byte checks and duplicate-run preflight."""
import hashlib,json,os,subprocess,sys
from importlib.metadata import version
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
out=HERE/'evidence/verification';out.mkdir(parents=True,exist_ok=True)
suites=[('history',str(HERE.relative_to(ROOT)),'test_history.py'),
        ('paced','migration/robinhood-paced-acquisition-20261016T1024','test_paced.py'),
        ('continuation','migration/robinhood-history-continuation-20261016T0715','test_continuation.py'),
        ('lens-merge','migration/robinhood-history-backfill-20261016','test_experiment.py'),
        ('registry','migration/robinhood-borrower-registry-20261016','test_registry.py'),
        ('isolation-tests','migration','test_isolation.py')]
commands=[(name,['-m','unittest','discover','-s',folder,'-p',pattern,'-v']) for name,folder,pattern in suites]
commands += [('isolation',['migration/verify_isolation.py']),('original-blobs',['migration/engine-v2-20261015/verify_import.py'])]
receipts=[]
for name,args in commands:
    r=subprocess.run([sys.executable,*args],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
    (out/(name+'.txt')).write_text(r.stdout+r.stderr)
    receipts.append({'name':name,'command':['python',*args],'exit_code':r.returncode});print(name,r.returncode,flush=True)
assert all(r['exit_code']==0 for r in receipts),'OFFLINE_FAILURE'
manifests=[]
for dirname in ['robinhood-history-backfill-20261016','robinhood-history-continuation-20261016T0715',
                'robinhood-transport-benchmark-20261016T0821','robinhood-acquisition-20261016T0922',
                'robinhood-paced-acquisition-20261016T1024','robinhood-paced-capture-20261016T1117']:
    folder=HERE.parent/dirname;file=folder/'MANIFEST.sha256';count=0
    for line in file.read_text().splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name;count+=1
    manifests.append({'folder':dirname,'files':count,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
deps={}
for line in (HERE.parent/'robinhood-transport-benchmark-20261016T0821/requirements.txt').read_text().splitlines():
    name,expected=line.split('==');deps[name]=version(name);assert deps[name]==expected
worktrees=[Path(s[9:]) for s in subprocess.check_output(['git','worktree','list','--porcelain'],cwd=ROOT,text=True).splitlines() if s.startswith('worktree ')]
assert not any((w/HERE.relative_to(ROOT)/'evidence/pilot').exists() for w in worktrees),'CAPTURE_EXISTS'
matches=[];inspected=0
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=p.read_bytes()
    except FileNotFoundError:continue
    inspected+=1
    if int(p.parent.name)!=os.getpid() and any(n in raw for n in (b'history_acquisition.py',b'paced_acquisition.py',b'/run_continuation.py')):matches.append(int(p.parent.name))
assert not matches,'CAPTURE_PROCESS_EXISTS'
report={'commands':receipts,'prior_manifests':manifests,'dependencies':deps,'python':sys.version,
        'worktrees_checked':len(worktrees),'processes_inspected':inspected,'matching_capture_processes':matches,'chain_rpc_calls':0}
(out/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print('Prior manifests unchanged:',[m['files'] for m in manifests])
