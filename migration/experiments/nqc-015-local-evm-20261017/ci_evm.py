"""NQC015 bounded local EVM test; no wallets, public RPC, paid services or remote writes.
Exact original protocol creation bytecode is recovered from pinned LAB records.
"""
from pathlib import Path
import base64,gzip,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile,traceback,urllib.request
REPO='josuechavando350-png/nexus-quant-capital'
BASE='f9d876990a85e55ba196702c32fe3668b49fda71'
BRANCH='refs/heads/research/nqc-015-local-evm-20261017'
MARKER='NQC015_APPROVED_LOCAL_EVM_ONCE'
ROOT=Path(__file__).resolve().parent
SUB='migration/experiments/nqc-sponsored-bundle-gate-20261017'
SOLC_SHA='fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'
ANVIL_SHA='10c1c727d6c1de973aeb160e59875b9a9a23464d6e74149ee8abb30b3500311b'
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def download(url,limit):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'NQC015-local-evidence'}),timeout=35) as r:
  if r.status!=200:raise ValueError('Download status is not 200')
  b=r.read(limit+1)
 if len(b)>limit:raise ValueError('Download exceeds bound')
 return b
def run(cmd):
 print('RUN '+json.dumps([str(x) for x in cmd]),flush=True)
 return subprocess.run([str(x) for x in cmd],check=True,timeout=120)

def recover(repo,out):
 expected=json.loads((repo/SUB/'SOURCE_LOCK.json').read_text())['bytecode']['bytecode_sha256']
 inverse={h:n for n,h in expected.items()};arts={};origins={}
 def walk(obj,path,pointer=''):
  if isinstance(obj,dict):
   candidates=[];req=obj.get('request')
   if isinstance(req,dict) and not req.get('to') and isinstance(req.get('data'),str):candidates.append((req['data'],pointer+'/request/data'))
   if obj.get('type')=='CREATE' and isinstance(obj.get('input'),str):candidates.append((obj['input'],pointer+'/input'))
   for text,where in candidates:
    if not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})+',text):continue
    raw=bytes.fromhex(text[2:])
    for words in range(17):
     length=len(raw)-32*words
     if length<=0:break
     code=raw[:length];name=inverse.get(digest(code))
     if name and name not in arts:
      arts[name]={'bytecode':'0x'+code.hex()}
      origins[name]={'file':str(path.relative_to(repo)),'pointer':where,'creation_sha256':digest(code),'constructor_suffix_bytes':32*words,'code_bytes':length,'source_file_sha256':digest(path.read_bytes())}
   for k,v in obj.items():walk(v,path,pointer+'/'+str(k))
  elif isinstance(obj,list):
   for k,v in enumerate(obj):walk(v,path,pointer+'/'+str(k))
 for folder in ('morpho-sponsor-e2e-20261017','nqc-sponsored-bundle-gate-20261017'):
  for p in sorted((repo/'migration/experiments'/folder/'evidence').glob('*.json')):
   walk(json.loads(p.read_text()),p)
   if len(arts)==len(expected):break
 missing=sorted(set(expected)-set(arts))
 save(out/'artifact_recovery.json',{'expected_count':len(expected),'recovered_count':len(arts),'missing':missing,'base_commit':BASE,'origins':origins,'mode':'EXACT_SHA256_CREATION_PREFIX_RECOVERY_NOT_RECOMPILATION'})
 if missing:raise ValueError('No substitute allowed; missing original bytecodes '+str(missing))
 save(out/'artifacts.json',arts)
 return out/'artifacts.json'

def export(out,status):
 save(out/'execution_status.json',status)
 print('NQC015_STATUS_BEGIN\n'+json.dumps(status,sort_keys=True)+'\nNQC015_STATUS_END',flush=True)
 bundle={}
 for p in sorted(out.rglob('*')):
  if p.is_file() and p.suffix in ('.json','.txt','.log') and p.stat().st_size<3000000:
   raw=p.read_bytes();bundle[str(p.relative_to(out))]={'sha256':digest(raw),'bytes':len(raw),'text':raw.decode('utf-8')}
 gz=gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0)
 print('NQC015_EXPORT_META '+json.dumps({'files':len(bundle),'gzip_bytes':len(gz),'gzip_sha256':digest(gz)}))
 if len(gz)>700000:raise ValueError('Export bound exceeded; not silently truncated')
 enc=base64.b64encode(gz).decode();print('NQC015_EVIDENCE_GZIP_BASE64_BEGIN')
 for i in range(0,len(enc),10000):print(enc[i:i+10000])
 print('NQC015_EVIDENCE_GZIP_BASE64_END',flush=True)
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
   f.write('# NQC 015 - actual local EVM test\n\n```json\n'+json.dumps(status,indent=2)+'\n```\nLocal chain 31337 only. No sponsorship acceptance or income established.\n')

def main():
 event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
 assert os.environ.get('GITHUB_ACTIONS')=='true'
 assert event['repository']['id']==1411047452 and event['repository']['full_name']==REPO and event['repository']['private'] is False
 assert os.environ['GITHUB_REF']==BRANCH and os.environ['GITHUB_RUN_ATTEMPT']=='1' and event['head_commit']['message']==MARKER
 work=Path(os.environ['RUNNER_TEMP'])/'nqc015';work.mkdir(exist_ok=False)
 out=work/'evidence';out.mkdir();repo=work/'base';runtime=work/'runtime';runtime.mkdir()
 status={'status':'INCOMPLETE_OR_FAILED','compiled':False,'evm_completed':False,'commercial_admission':False,'producer_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'base_commit':BASE,'realized_income_not_established':True,'chain_id':31337}
 try:
  run(['git','init','-q',repo]);run(['git','-C',repo,'remote','add','origin','https://github.com/'+REPO+'.git'])
  run(['git','-C',repo,'fetch','--depth=1','origin',BASE]);run(['git','-C',repo,'checkout','--detach','FETCH_HEAD'])
  assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==BASE
  artifacts=recover(repo,out)
  comp=ROOT.parent/'nqc-013-compile-only-20261017'
  for n in ('abi_migration.py','prepare_compile.py'):shutil.copyfile(comp/n,runtime/n)
  shutil.copytree(comp/'source',runtime/'source')
  for n in ('run_local_matrix.py','evidence_guard.py'):shutil.copyfile(ROOT/n,runtime/n)
  compiler=work/'solc';raw=download('https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9',20000000)
  assert digest(raw)==SOLC_SHA;compiler.write_bytes(raw);compiler.chmod(0o700)
  prov=json.loads((repo/'migration/experiments/morpho-sponsor-e2e-20261017/evidence/anvil-provenance.json').read_text())
  raw=download(prov['registry_url'],50000000)
  assert 'sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()==prov['integrity']
  with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
   members=[m for m in tf.getmembers() if m.isfile() and m.name.endswith('/bin/anvil')]
   assert len(members)==1 and members[0].size<100000000
   binary=tf.extractfile(members[0]).read()
  assert digest(binary)==ANVIL_SHA
  anvil=work/'anvil';anvil.write_bytes(binary);anvil.chmod(0o700)
  save(out/'tool_versions.json',{'solc_sha256':digest(compiler.read_bytes()),'anvil_sha256':digest(binary),'anvil_version':subprocess.check_output([str(anvil),'--version'],text=True),'python':sys.version})
  run([sys.executable,runtime/'prepare_compile.py','--out',out/'compilation','--solc',compiler,'--solc-sha256',SOLC_SHA])
  status['compiled']=json.loads((out/'compilation/status.json').read_text())['compiled']
  run([sys.executable,runtime/'run_local_matrix.py','--repo',repo,'--anvil',anvil,'--artifacts',artifacts,'--compiled-dir',out/'compilation','--out',out/'evm'])
  summary=json.loads((out/'evm/summary.json').read_text())
  assert summary['new_EVM_cases']==8 and summary['node_stopped'] is True and all(x['assertions_passed'] for x in summary['results'])
  run(['git','-C',repo,'diff','--exit-code','HEAD'])
  status.update(status='EIGHT_LOCAL_EVM_CASES_PASS',evm_completed=True,results=summary['results'],node_stopped=True)
 except Exception as exc:
  status.update(error_type=type(exc).__name__,error=str(exc));traceback.print_exc()
 finally:export(out,status)
 return 0 if status['evm_completed'] else 2
if __name__=='__main__':sys.exit(main())
