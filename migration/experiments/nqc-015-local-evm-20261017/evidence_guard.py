"""Validate local EVM records. No network, signatures or commercial certification."""
from __future__ import annotations
import re
from abi_migration import decode_raw, selector

CASES = {
 'original_shared_rejected': (False, True, False, 1),
 'proposal_shared': (True, True, True, 1),
 'proposal_separate': (True, False, True, 0),
 'proposal_wrong_header': (True, False, False, 1),
 'proposal_separate_with_equal_recipients': (True, True, False, 0),
 'proposal_shared_with_distinct_recipients': (True, False, False, 1),
 'proposal_fixed_return_002': (True, True, True, 1),
 'proposal_fixed_return_004': (True, True, True, 1),
}
INVALID_PLAN='0x'+selector('InvalidPlan()').hex()
ORDER=['topup','nqc_adapter','nqc_executor','liquidate','return_unused_advance']
class EvidenceError(ValueError): pass

def require(ok,message):
 if not ok: raise EvidenceError(message)
def addr(x):
 require(type(x) is str and re.fullmatch(r'0x[0-9a-fA-F]{40}',x),'bad address')
 return x.lower()
def num(x):
 if type(x) is int:
  require(x>=0,'negative integer');return x
 require(type(x) is str and re.fullmatch(r'0x[0-9a-fA-F]+',x),'bad exact quantity')
 return int(x,16)
def nodes(t):
 require(isinstance(t,dict),'missing trace')
 result=[t]
 for c in t.get('calls',[]): result.extend(nodes(c))
 return result

def validate_case(run,name,native,baseline=None):
 require(name in CASES,'unknown case')
 patched,shared,completed,mode=CASES[name]
 require(run['scenario']==name and type(run['chain_id']) is int and run['chain_id']==31337,'wrong local identity')
 a=run['actors']; op=addr(a['nqc_sender_and_beneficiary']); builder=addr(a['simulated_builder'])
 morpho=addr(a['Morpho']); ex=addr(run['settlement_contract'])
 require(len({op,builder,ex})==3,'invalid participants')
 initial=run['initial']; final=run['final']
 require(all(num(initial['balances'][op][k])==0 for k in ('ETH','WETH','COLLATERAL')),'owner not empty')
 require(num(initial['position'][1])>0,'no initial debt')
 txs=run['transactions']; low=name=='proposal_fixed_return_002'
 require([t['label'] for t in txs]==(ORDER[:-1] if low else ORDER),'incorrect included sequence')
 require(not run.get('rpc_rejections'),'RPC rejection is not contract rejection')
 blockhashes=set(); hashes=set(); by={t['label']:t for t in txs}
 for i,t in enumerate(txs):
  r=t['receipt']; b=t['block']
  require(re.fullmatch(r'0x[0-9a-fA-F]{64}',r.get('blockHash','')) is not None,'missing block hash')
  require(r['blockHash'].lower()==b['hash'].lower(),'header mismatch');blockhashes.add(b['hash'])
  h=r.get('transactionHash','');require(re.fullmatch(r'0x[0-9a-fA-F]{64}',h) is not None,'missing tx hash');hashes.add(h)
  require(num(r['transactionIndex'])==i,'wrong index')
  require(num(r['status'])==(0 if t['label']=='liquidate' and not completed else 1),'wrong receipt status '+t['label'])
  require(0<num(r['gasUsed'])<=num(t['request']['gas']),'wrong gas')
  require((addr(b['miner'])==builder)==shared,'wrong fee recipient')
 require(len(blockhashes)==1 and len(hashes)==len(txs),'not one block or duplicate receipts')
 for label in ('nqc_adapter','nqc_executor'):
  t=by[label];tr=t['trace']
  require(addr(t['receipt']['contractAddress'])==addr(a[label]),'wrong deployment address')
  require(tr.get('type','').upper()=='CREATE' and not tr.get('error'),'CREATE failed')
  require(re.fullmatch(r'0x(?:[0-9a-fA-F]{2})+',tr.get('output','')) is not None,'no runtime')
 require(addr(a['nqc_executor'])==ex,'wrong executor')
 t=by['liquidate'];tr=t['trace'];header=addr(t['block']['miner'])
 require(addr(t['request']['to'])==ex==addr(tr['to']),'wrong execute recipient')
 require(addr(t['request']['from'])==op==addr(tr['from']),'wrong execute caller')
 d=decode_raw(bytes.fromhex(t['request']['data'][2:]),new=patched)
 require(f'0x{d.words[13]:040x}'==builder,'wrong reimbursement recipient')
 if patched:
  require(d.words[16]==mode,'wrong layout')
  require((f'0x{d.words[15]:040x}'!=header)==(name=='proposal_wrong_header'),'wrong header condition')
 else: require(builder==header,'collision not tested')
 calls=nodes(tr)
 if completed:
  require(not tr.get('error') and num(final['position'][1])==0,'debt not closed')
  require(num(final['balances'][op]['WETH'])>0,'no new WETH')
  require(any(addr(n['to'])==morpho for n in calls if n.get('to')),'no Morpho call')
  pays=[(addr(c['to']),num(c['value'])) for c in native['executor_payments']]
  expected=[(builder,d.words[14]+d.words[12])] if mode==1 else [(builder,d.words[14]),(header,d.words[12])]
  require(sorted(pays)==sorted(expected),'incorrect payment vector')
 else:
  require(tr.get('error') and tr.get('output','').lower()==INVALID_PLAN,'wrong rejection reason')
  require(initial['position']==final['position'] and num(final['balances'][op]['WETH'])==0,'rejected call changed debt/profit')
  require(not any(addr(n['to'])==morpho for n in calls if n.get('to')),'rejected after Morpho call')
  require(not native['executor_payments'],'committed rejected payment')
 pending=run.get('accepted_not_included',[])
 if low:
  require(len(pending)==1 and pending[0]['label']=='return_unused_advance','wrong pending transaction')
  require(baseline is not None,'no measured baseline');r=pending[0]['request']
  require(num(r['value'])==baseline['return_wei'],'wrong fixed return')
  require(num(final['balances'][op]['ETH'])<num(r['gas'])*num(r['maxFeePerGas'])+num(r['value']),'return is not underfunded')
 else:
  require(not pending,'unexpected pending transaction');r=by['return_unused_advance']['request']
  require(addr(r['to'])==builder and num(r['value'])>0,'return not received by funder')
  if name=='proposal_fixed_return_004':
   require(baseline is not None and num(r['value'])==baseline['return_wei'],'wrong fixed return')
   require(num(final['balances'][op]['ETH'])==10**16,'wrong financing remainder')
  else: require(num(final['balances'][op]['ETH'])==0,'unexplained native remainder')
 return {'scope':'OBSERVED_RECORD_VALIDATION_ONLY','case':name,'liquidation_completed':completed,
         'expected_revert':None if completed else INVALID_PLAN,'commercial_admission':False}
