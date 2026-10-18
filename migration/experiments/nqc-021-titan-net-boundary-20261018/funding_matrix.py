"""NQC021: fixed unsigned operator requests, one opaque lab advance, no fixed return.

This tests a design boundary suggested by Titan's public prepend/net description.
NOT Titan's implementation, acceptance, funding commitment or no-recourse terms.
Residual ETH is unresolved financing, never distributable operator profit.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, subprocess, sys
from pathlib import Path
BASE='f9d876990a85e55ba196702c32fe3668b49fda71'
SUB='migration/experiments/nqc-sponsored-bundle-gate-20261017'
E=10**18
TARGET=42468410000000000
OP_LABELS=['nqc_adapter','nqc_executor','liquidate']
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical(v)+b'\n')
def uint(v):
    if type(v) is not int or not 0<=v<2**256: raise ValueError('expected uint256')
    return v
def validate_operator(ops,operator):
    if [t['label'] for t in ops]!=OP_LABELS: raise ValueError('wrong mandatory operator set')
    for t in ops:
        r=t['request']
        if r['from']!=operator or int(r['value'],16)!=0: raise ValueError('unauthorized actor or native value')
        if int(r['gas'],16)<=0: raise ValueError('invalid gas')
    return sha(canonical(ops))
def gate(complete,residual,margin,weth):
    if type(complete) is not bool or type(margin) is not int: raise ValueError('unknown inputs')
    uint(residual);uint(weth)
    return {'cash_positive_candidate':complete and margin>0 and weth>0,
        'financing_residual_wei':residual,'distributable_residual_eth_wei':0,
        'residual_disposition':'UNKNOWN','personal_liability':'UNKNOWN',
        'commercial_admission':False,'no_recourse_verified':False}
def max_advance(payment,priority_received,own_external_gas,payout,other_cost):
    for v in (payment,priority_received,own_external_gas,payout):uint(v)
    if other_cost is None: return None
    uint(other_cost)
    return payment+priority_received-own_external_gas-payout-other_cost-1

def cases():
    # name, provider-selected advance, block base fee, omit payout, bad min, wrong header
    return [
      ('net_020',2*10**16,10**9,False,False,False),
      ('net_030',3*10**16,10**9,False,False,False),
      ('net_040',4*10**16,10**9,False,False,False),
      ('net_049',49*10**15,10**9,False,False,False),
      ('net_050',5*10**16,10**9,False,False,False),
      ('net_060',6*10**16,10**9,False,False,False),
      ('no_advance',0,10**9,False,False,False),
      ('insufficient_011',11*10**15,10**9,False,False,False),
      ('omitted_proposer',3*10**16,10**9,True,False,False),
      ('gas3_same_operator',3*10**16,2*10**9,False,False,False),
      ('slippage_revert',3*10**16,10**9,False,True,False),
      ('wrong_header_revert',3*10**16,10**9,False,False,True)]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('repo','runtime','artifacts','compiled-dir','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--anvil',required=True);a=p.parse_args();repo=a.repo.resolve();out=a.out.resolve()
    assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==BASE
    assert out!=repo and repo not in out.parents
    out.mkdir(parents=True,exist_ok=False)
    sys.path[:0]=[str(a.runtime),str(repo/SUB)]
    from abi_migration import decode_raw,encode_raw
    from run_local_matrix import check_native,check_tokens
    import local_node as ln
    import run_coordinated as rc
    ln.HERE=out;ln.ref.HERE=out
    art=json.loads(a.artifacts.read_text());lock=json.loads((repo/SUB/'SOURCE_LOCK.json').read_text())['bytecode']['bytecode_sha256']
    assert set(art)==set(lock)
    for n,h in lock.items():assert sha(bytes.fromhex(art[n]['bytecode'][2:]))==h
    for line in (repo/SUB/'MANIFEST.sha256').read_text().splitlines():
        h,n=line.split(None,1);assert sha((repo/SUB/n.strip()).read_bytes())==h
    assert json.loads((a.compiled_dir/'status.json').read_text())['status']=='COMPILE_AND_ABI_PASS_ONLY'
    compiled=json.loads((a.compiled_dir/'compiled_contracts.json').read_text())
    summary={'status':'INCOMPLETE','cases':[],'node_stopped':False,'planning_blocks_discarded':0,'final_receipts':0,
        'commercial_admission':False,'unknown_advance':'NOT_AN_OPERATOR_INPUT; PROVIDER_SIMULATION_REQUIRED',
        'no_recourse_terms':None,'provider_acceptance':None,'historical_replay':False}
    reference_digest=None
    try:
      with ln.node(a.anvil,copy.deepcopy(art),pool_override=True) as lab:
        lab.setup();builder=lab.actors['simulated_builder'];op=lab.actors['nqc_sender_and_beneficiary'];proposer=lab.actors['proposer']
        lab.rpc('anvil_setBalance',[builder,hex(E)])
        write(out/'evidence/setup.json',{'original':lab.setup_report,'transactions':lab.setup_records,
           'synthetic_builder_seed_wei':E,'seed_is_not_provider_financing':True,'post_seed':lab.snapshot()})
        for name,advance,base_fee,omit,bad,wrong in cases():
          snap=lab.rpc('evm_snapshot');actors=dict(lab.actors)
          try:
            lab.actors['sponsor_and_topup_financier']=builder;lab.coinbase=builder
            lab.rpc('anvil_setCoinbase',[builder]);lab.art=copy.deepcopy(art)
            lab.art['NqcMorphoSponsoredLiquidation']=compiled['NqcMorphoSponsoredLiquidationPaymentLayout']
            # No advance argument from the provider enters operator construction.
            raw=rc.build_package(lab,mode='slippage' if bad else 'omit_return',advance=0,base_fee=10**9)
            ops=[copy.deepcopy(t) for t in raw if t['label'] in OP_LABELS]
            for t in ops:
                if t['label']=='liquidate':
                    d=decode_raw(bytes.fromhex(t['request']['data'][2:]),new=False)
                    expected=proposer if wrong else builder
                    t['request']['data']='0x'+encode_raw(d.words+(int(expected,16),1),d.collateral_route,d.weth_route,new=True).hex()
            digest=validate_operator(ops,op)
            if not bad and not wrong:
                if reference_digest is None:reference_digest=digest
                assert digest==reference_digest,'advance or block gas changed operator instructions'
            initial=rc.state(lab);assert initial['balances'][op]=={'ETH':0,'WETH':0,'COLLATERAL':0}
            nonce=int(lab.rpc('eth_getTransactionCount',[builder,'latest']),16)
            def provider_tx(label,to,value,n):
                return {'label':label,'request':{'from':builder,'to':to,'data':'0x','value':hex(value),'gas':hex(21000),
                    'nonce':hex(n),'maxFeePerGas':hex(3*10**9),'maxPriorityFeePerGas':hex(10**9)}}
            seq=[]
            if advance:seq.append(provider_tx('one_prepended_advance',op,advance,nonce));nonce+=1
            seq.extend(copy.deepcopy(ops))
            if not omit:seq.append(provider_tx('external_proposer_payout',proposer,TARGET,nonce))
            assert validate_operator(ops,op)==digest
            write(out/('evidence/'+name+'_plan.json'),{'operator_requests':ops,'operator_sha256':digest,
                'candidate_requests':seq,'provider_selected_advance_wei':advance,'operator_knows_advance':False,
                'return_instruction':None,'revertingTxHashes':[],'droppingTxHashes':[],
                'signatures_created':0,'real_rpc_payload':False,'provider_algorithm':'HYPOTHESIS_NOT_TITAN',
                'residual_rule':'UNRESOLVED_NOT_PROFIT','personal_liability':None})
            r=rc.execute_block(lab,seq,base_fee,name);write(out/('evidence/'+name+'_execution.json'),r)
            native=check_native(r);check_tokens(r);write(out/('evidence/'+name+'_native.json'),native)
            included=r['transactions'];ok=[t['label'] for t in included if int(t['receipt']['status'],16)==1]
            required=['one_prepended_advance']+OP_LABELS+['external_proposer_payout']
            complete=(ok==required and not r['rpc_rejections'] and not r['accepted_not_included'])
            liquidated=r['final']['position'][1]==0
            residual=r['final']['balances'][op]['ETH'];weth=r['final']['balances'][op]['WETH']
            margin=r['final']['balances'][builder]['ETH']-r['initial']['balances'][builder]['ETH']
            prop=r['final']['balances'][proposer]['ETH']-r['initial']['balances'][proposer]['ETH']
            supplied=sum(int(t['request']['value'],16) for t in included if t['label']=='one_prepended_advance' and int(t['receipt']['status'],16)==1)
            op_cost=sum(t['gas_cost_wei'] for t in included if t['request']['from']==op)
            assert residual==supplied-op_cost,'residual ETH cannot be called profit'
            assert margin==native['native_net'].get(builder,0)
            payment=sum(t['value'] for t in native['executor_payments'] if t['to']==builder)
            op_priority=sum(int(t['receipt']['gasUsed'],16)*(int(t['receipt']['effectiveGasPrice'],16)-base_fee)
                  for t in included if t['request']['from']==op)
            own_burn=sum(int(t['receipt']['gasUsed'],16)*base_fee for t in included if t['request']['from']==builder)
            assert margin==payment+op_priority-supplied-own_burn-prop,'builder cash reconciliation'
            if complete:assert liquidated and prop==TARGET and supplied==advance
            result=gate(complete,residual,margin,weth)
            row={'case':name,'operator_sha256':digest,'provider_advance_wei':supplied,
                'package_complete':complete,'liquidation_completed':liquidated,'receipt_count':len(included),
                'gas_total':sum(int(t['receipt']['gasUsed'],16) for t in included),
                'operator_gas_paid':op_cost,'residual_financing':residual,'owner_WETH_new':weth,
                'builder_cash_after_observed_payout':margin,'proposer_received':prop,
                'executor_payment_to_builder':payment,'operator_priority_to_builder':op_priority,'builder_own_base_fee_burn':own_burn,
                'max_profitable_advance_known_costs':max_advance(payment,op_priority,own_burn,prop,0) if complete else None,
                'max_profitable_advance_all_costs':None,'policy_gate':result,
                'legacy_return_based_flag':r['flags']['EVM_LOCAL_PASS'],
                'note':'legacy flag requires a return; retained, not used as evidence of AUTO_NET correctness'}
            expected_complete=name not in ('no_advance','insufficient_011','omitted_proposer','slippage_revert','wrong_header_revert')
            assert complete==expected_complete,(name,'unexpected completion',row)
            if name in ('net_020','net_030','net_040','net_049','gas3_same_operator'):assert result['cash_positive_candidate']
            if name in ('net_050','net_060'):assert complete and margin<0 and not result['cash_positive_candidate']
            if name in ('slippage_revert','wrong_header_revert'):
                liq=next(t for t in included if t['label']=='liquidate');assert int(liq['receipt']['status'],16)==0
                assert all(x in ok for x in ['one_prepended_advance','nqc_adapter','nqc_executor'])
            assert not result['commercial_admission'] and not result['no_recourse_verified']
            row['assertions_passed']=True;summary['cases'].append(row);summary['final_receipts']+=len(included)
            write(out/('evidence/'+name+'_result.json'),row);print('NQC021_CASE '+json.dumps(row,sort_keys=True),flush=True)
          finally:
            assert lab.rpc('evm_revert',[snap]);lab.rpc('anvil_dropAllTransactions');lab.actors=actors
        summary['operator_digest_reference']=reference_digest
      summary['node_stopped']=True;summary['status']='LOCAL_NET_CASH_TESTED_RESIDUAL_AND_NO_RECOURSE_UNRESOLVED'
    finally:write(out/'summary.json',summary)
if __name__=='__main__':main()
