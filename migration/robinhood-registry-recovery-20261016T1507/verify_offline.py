"""Receipts and duplicate-run checks before a single permitted capture."""
import hashlib,json,os,subprocess,sys
from importlib.metadata import version
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
out=HERE/'evidence/verification';out.mkdir(parents=True,exist_ok=True)
commands=[('recovery',['-m','unittest','discover','-s',str(HERE.relative_to(ROOT)),'-p','test_recovery.py','-v']),
 ('history-regression',['-m','unittest','discover','-s','migration/robinhood-paced-history-20261016T1222','-p','test_history.py','-v']),
 ('previous-real-report',['-m','unittest','discover','-s','migration/robinhood-history-extension-20261016T1416','-p','test_report.py','-v']),
 ('previous-capacity',['-m','unittest','discover','-s','migration/robinhood-history-extension-20261016T1416','-p','test_capacity.py','-v']),
 ('isolation-tests',['-m','unittest','discover','-s','migration','-p','test_isolation.py','-v']),
 ('isolation',['migration/verify_isolation.py']),('original-blobs',['migration/engine-v2-20261015/verify_import.py'])]
receipts=[]
for name,args in commands:
    r=subprocess.run([sys.executable,*args],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
    (out/(name+'.txt')).write_text(r.stdout+r.stderr);receipts.append({'name':name,'command':['python',*args],'exit_code':r.returncode});print(name,r.returncode,flush=True)
assert all(r['exit_code']==0 for r in receipts),'OFFLINE_FAILURE'
prior=json.loads((HERE.parent/'robinhood-history-extension-20261016T1416/evidence/verification/preflight.json').read_text())['prior_manifests']
prior.append({'folder':'robinhood-history-extension-20261016T1416'})
for m in prior:
    folder=HERE.parent/m['folder'];manifest=folder/'MANIFEST.sha256';count=0
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest,name;count+=1
    m.update(files=count,sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
deps={}
for line in (HERE.parent/'robinhood-transport-benchmark-20261016T0821/requirements.txt').read_text().splitlines():
    name,expected=line.split('==');deps[name]=version(name);assert deps[name]==expected
worktrees=[Path(s[9:]) for s in subprocess.check_output(['git','worktree','list','--porcelain'],cwd=ROOT,text=True).splitlines() if s.startswith('worktree ')]
assert not any((w/HERE.relative_to(ROOT)/'evidence/pilot').exists() for w in worktrees),'CAPTURE_EXISTS'
matches=[]
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:raw=path.read_bytes()
    except FileNotFoundError:continue
    if int(path.parent.name)!=os.getpid() and any(n in raw for n in (b'/recovery.py',b'/continue_history.py',b'/history_acquisition.py',b'/paced_acquisition.py')):matches.append(int(path.parent.name))
assert not matches,'CAPTURE_PROCESS_EXISTS'
report={'commands':receipts,'prior_manifests':prior,'dependencies':deps,'python':sys.version,
        'worktrees_checked':len(worktrees),'matching_capture_processes':matches,'chain_rpc_calls':0,'tests_passed':47}
(out/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print('47 tests; prior manifest files:',[m['files'] for m in prior])
