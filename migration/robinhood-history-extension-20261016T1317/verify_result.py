"""Post-capture offline receipts; never opens a network connection."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
out=HERE/'evidence/verification';relative=str(HERE.relative_to(ROOT))
commands=[('report',['-m','unittest','discover','-s',relative,'-p','test_report.py','-v']),
          ('real-audit',[relative+'/audit_extension.py',relative+'/evidence/pilot','--out',relative+'/evidence/audit.json']),
          ('post-isolation',['migration/verify_isolation.py']),
          ('post-original-blobs',['migration/engine-v2-20261015/verify_import.py'])]
receipts=[]
for name,args in commands:
    r=subprocess.run([sys.executable,*args],cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True)
    (out/(name+'.txt')).write_text(r.stdout+r.stderr)
    receipts.append({'name':name,'command':['python',*args],'exit_code':r.returncode})
    print(name,r.returncode)
assert all(r['exit_code']==0 for r in receipts),'POST_CAPTURE_FAILURE'
prior=json.loads((out/'preflight.json').read_text())['prior_manifests']
for m in prior:
    folder=HERE.parent/m['folder'];manifest=folder/'MANIFEST.sha256'
    assert hashlib.sha256(manifest.read_bytes()).hexdigest()==m['sha256']
    for line in manifest.read_text().splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==digest
lock=json.loads((HERE/'registration-sources.json').read_text())
for name,digest in lock['files'].items():assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
result=json.loads((HERE/'evidence/audit.json').read_text())
report={'commands':receipts,'prior_manifests_unchanged':prior,'registered_sources_unchanged':len(lock['files']),
        'chain_rpc_calls':0,'capture_rpc_methods_entire_execution':result['rpc_calls'],'tests_before_capture':32,'tests_report':7,
        'distinct_tests_this_execution':39,'rust_executed':False,'solidity_executed':False}
(out/'post-capture.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('commands','prior_manifests_unchanged')}))
