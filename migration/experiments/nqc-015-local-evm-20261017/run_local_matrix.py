"""Finite eight-case integration. Local chain only; no public transactions or signing."""
import argparse,copy,hashlib,importlib,json,subprocess,sys
from pathlib import Path
from abi_migration import decode_raw,encode_raw,keccak256
from evidence_guard import validate_case
ROOT=Path(__file__).resolve().parent
BASE='f9d876990a85e55ba196702c32fe3668b49fda71'
SUB='migration/experiments/nqc-sponsored-bundle-gate-20261017'

def write(p,o):p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def sha(b):return hashlib.sha256(b).hexdigest()
def check_native(run):
 net={}; payments=[]
 def add(a,v):net[a]=net.get(a,0)+v
 def walk(n,label):
  if n.get('error'):return
  kind=n.get('type','').upper();v=int(n.get('value','0x0'),16)
  if v and kind in ('CALL','CREATE','CREATE2'):
   a=n['from'].lower();b=n['to'].lower();add(a,-v);add(b,v)
   if label=='liquidate' and a==run['settlement_contract']:payments.append({'from':a,'to':b,'value':v})
  elif v and kind not in ('STATICCALL','DELEGATECALL','CALLCODE'):raise ValueError('unknown value trace')
  for c in n.get('calls',[]):walk(c,label)
 for t in run['transactions']:
  g=int(t['receipt']['gasUsed'],16);p=int(t['receipt']['effectiveGasPrice'],16);b=int(t['block']['baseFeePerGas'],16)
  assert p>=b;add(t['request']['from'],-g*p);add(t['block']['miner'],g*(p-b));add('BASE_FEE_BURN',g*b)
  if int(t['receipt']['status'],16)==1:walk(t['trace'],t['label'])
 for a,v in run['initial']['balances'].items():
  assert run['final']['balances'][a]['ETH']-v['ETH']==net.get(a,0),('native balance',a)
 assert sum(net.values())==0,'native conservation'
 return {'native_net':net,'executor_payments':payments}

def check_tokens(run):
 topic='0x'+keccak256(b'Transfer(address,address,uint256)').hex()
 for t in run['transactions']:
  for token,asset in ((run['actors']['WETH'],'WETH'),(run['actors']['ERC20'],'COLLATERAL')):
   net={}
   for log in t['receipt']['logs']:
    if log['address'].lower()!=token or log['topics'][0].lower()!=topic:continue
    assert len(log['topics'])==3
    src='0x'+log['topics'][1][-40:].lower();dst='0x'+log['topics'][2][-40:].lower();v=int(log['data'],16)
    net[src]=net.get(src,0)-v;net[dst]=net.get(dst,0)+v
   for a,b in t['before'].items():assert t['after'][a][asset]-b[asset]==net.get(a,0),('token mismatch',t['label'],a,asset)
 return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--anvil',required=True)
 p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--compiled-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 x=p.parse_args();repo=x.repo.resolve();base=repo/SUB;out=x.out.resolve()
 assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==BASE
 assert repo not in out.parents and out!=repo
 for line in (base/'MANIFEST.sha256').read_text().splitlines():
  h,n=line.split(None,1);assert sha((base/n.strip()).read_bytes())==h
 for n,h in {'run_coordinated.py':'a500f5467f8d4e17cfdffed563bb61bac1390aee','local_node.py':'11d69ecef9d16aaa1e08ed1000d332ed468f1c35'}.items():
  raw=(base/n).read_bytes();assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==h
 assert json.loads((x.compiled_dir/'status.json').read_text())['status']=='COMPILE_AND_ABI_PASS_ONLY'
 compiled=json.loads((x.compiled_dir/'compiled_contracts.json').read_text());art=json.loads(x.artifacts.read_text())
 lock=json.loads((base/'SOURCE_LOCK.json').read_text())['bytecode']['bytecode_sha256']
 for n,h in lock.items():assert sha(bytes.fromhex(art[n]['bytecode'][2:]))==h
 out.mkdir(parents=True,exist_ok=False);(out/'evidence').mkdir()
 sys.path.insert(0,str(base));ln=importlib.import_module('local_node');rc=importlib.import_module('run_coordinated')
 ln.HERE=out;ln.ref.HERE=out
 cases=[('original_shared_rejected',False,True,1,False,3*10**16),('proposal_shared',True,True,1,False,3*10**16),
 ('proposal_separate',True,False,0,False,3*10**16),('proposal_wrong_header',True,True,1,True,3*10**16),
 ('proposal_separate_with_equal_recipients',True,True,0,False,3*10**16),('proposal_shared_with_distinct_recipients',True,False,1,False,3*10**16),
 ('proposal_fixed_return_002',True,True,1,False,2*10**16),('proposal_fixed_return_004',True,True,1,False,4*10**16)]
 results=[];baseline=None
 summary={'status':'INCOMPLETE_OR_FAILED','new_EVM_cases':0,'results':results,'commercial_admission':False,'node_stopped':False,'historical_replay':False}
 try:
  with ln.node(x.anvil,copy.deepcopy(art),pool_override=True) as lab:
   lab.setup();write(out/'evidence/setup.json',{'report':lab.setup_report,'transactions':lab.setup_records})
   for name,patched,shared,mode,wrong,advance in cases:
    snap=lab.rpc('evm_snapshot');actors=dict(lab.actors)
    try:
     builder=actors['simulated_builder'];op=actors['nqc_sender_and_beneficiary']
     lab.actors['sponsor_and_topup_financier']=builder;lab.rpc('anvil_setBalance',[builder,hex(100*rc.E)])
     expected=builder if shared else actors['proposer'];lab.coinbase=actors['proposer'] if wrong else expected
     lab.rpc('anvil_setCoinbase',[lab.coinbase]);lab.records=[];lab.art=copy.deepcopy(art)
     if patched:lab.art['NqcMorphoSponsoredLiquidation']=compiled['NqcMorphoSponsoredLiquidationPaymentLayout']
     requests=[t for t in rc.build_package(lab,advance=advance) if t['label']!='separate_builder_fee']
     if patched:
      for t in requests:
       if t['label']=='liquidate':
        d=decode_raw(bytes.fromhex(t['request']['data'][2:]),new=False)
        t['request']['data']='0x'+encode_raw(d.words+(int(expected,16),mode),d.collateral_route,d.weth_route,new=True).hex()
     trial_snap=lab.rpc('evm_snapshot');trial=rc.execute_block(lab,requests,10**9,name+'_planning',observe=False)
     qgas=sum(t['gas_cost_wei'] for t in trial['transactions'] if t['request']['from']==op)
     assert lab.rpc('evm_revert',[trial_snap]);u=advance-qgas
     if name.startswith('proposal_fixed_return_'):assert baseline is not None;u=baseline['return_wei']
     assert u>=0
     for t in requests:
      if t['label']=='return_unused_advance':t['request']['value']=hex(u)
     r=rc.execute_block(lab,requests,10**9,name)
     r.update(architecture='C1',fixture_cash_wei=0,patched_payment_layout=patched,expected_fee_recipient=expected,
       native_payment_layout=mode,discarded_planning_is_not_included=True,real_proposer_payment=None,
       source_proposal_sha256=sha((ROOT/'source/NqcMorphoSponsoredLiquidationPaymentLayout.sol').read_bytes()))
     write(out/('evidence/'+name+'.json'),r)
     native=check_native(r);write(out/('evidence/'+name+'_native.json'),native);check_tokens(r)
     checked=validate_case(r,name,native,baseline);write(out/('evidence/'+name+'_checked.json'),checked)
     if name=='proposal_shared':baseline={'return_wei':u}
     row={'case':name,'assertions_passed':True,'liquidation_completed':checked['liquidation_completed'],
          'included':len(r['transactions']),'gas':sum(int(t['receipt']['gasUsed'],16) for t in r['transactions']),
          'builder_native_delta':native['native_net'].get(builder,0),'owner_residual_financing':r['final']['balances'][op]['ETH'],
          'owner_WETH_new':r['final']['balances'][op]['WETH'],'builder_margin_after_real_proposer_and_costs':None,'commercial_admission':False}
     results.append(row);summary['new_EVM_cases']=len(results);print('NQC015_CASE '+json.dumps(row),flush=True)
    finally:
     assert lab.rpc('evm_revert',[snap]);lab.actors=actors
  summary['node_stopped']=True;summary['status']='LOCAL_ASSERTIONS_PASS_NOT_HISTORICAL_OR_COMMERCIAL'
 except Exception as e:summary['error']=repr(e);raise
 finally:write(out/'summary.json',summary)

if __name__=='__main__':main()
