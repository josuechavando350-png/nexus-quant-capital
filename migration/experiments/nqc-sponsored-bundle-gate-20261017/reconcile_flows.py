"""Derived from immutable Directiva 003 reconciler. Adds C2 settlement address,
successful U receipt validation and actual position closure. All step balances
come from independent prestateTracer diffs in coordinated runs (or RPC in A1).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path
from local_node import HERE, ref
TRANSFER, ZERO, E = ref.TRANSFER, ref.ZERO, ref.E

def number(s): return int(s,16)

def reconcile(run):
    flows=[];steps=[];accounts=run['actors'];tokens={accounts['WETH']:'WETH',accounts['ERC20']:'COLLATERAL'}
    def append(asset,src,dst,amount,i,ref,kind):
        if amount:
            flows.append({'chain_id':31337,'asset':asset,'actor_from':src,'actor_to':dst,
                'amount_base_units':amount,'tx_index':i,'evidence_ref':ref,'kind':kind})
    for i,t in enumerate(run['transactions']):
        receipt=t['receipt'];trace=t['trace'];start=len(flows)
        ref=f'evidence/{run["scenario"]}.json#/transactions/{i}'
        def native(frame,path):
            if frame.get('error'):return # Reverted descendants never become settled cash flows.
            amount=number(frame.get('value','0x0'))
            if frame['type'] in ('CALL','CREATE','CREATE2','SELFDESTRUCT'):
                append('ETH',frame['from'].lower(),frame.get('to',receipt['contractAddress']).lower(),amount,i,ref+path,'committed_native')
            for j,child in enumerate(frame.get('calls',[])):native(child,path+f'/calls/{j}')
        native(trace,'/trace')
        for j,log in enumerate(receipt['logs']):
            if log['address'].lower() in tokens and log['topics'][0]==TRANSFER:
                assert len(log['topics'])==3 and len(log['data'])==66
                src='0x'+log['topics'][1][-40:];dst='0x'+log['topics'][2][-40:]
                append(tokens[log['address'].lower()],src if src!=ZERO else 'TOKEN_ISSUANCE',
                    dst if dst!=ZERO else 'TOKEN_BURN',number(log['data']),i,ref+f'/receipt/logs/{j}','committed_erc20')
        gas=number(receipt['gasUsed']);price=number(receipt['effectiveGasPrice']);base=number(t['block']['baseFeePerGas'])
        assert base<=price<=number(t['request']['maxFeePerGas'])
        assert gas<=number(t['request']['gas']) and t['gas_cost_wei']==gas*price
        sender=t['request']['from'];coinbase=t['block']['miner'].lower()
        append('ETH',sender,'BASE_FEE_BURN',gas*base,i,ref+'/receipt','gas_burn')
        append('ETH',sender,coinbase,gas*(price-base),i,ref+'/receipt','priority_fee')
        computed=defaultdict(int)
        for f in flows[start:]:
            computed[f['actor_from'],f['asset']]-=f['amount_base_units']
            computed[f['actor_to'],f['asset']]+=f['amount_base_units']
        all_accounts=set(t['before'])|set(t['after'])
        for who,asset in computed:
            if who.startswith('0x') and who not in all_accounts:raise ValueError(('unobserved flow actor',who,t['label']))
        for who in all_accounts:
            for asset in ('ETH','WETH','COLLATERAL'):
                actual=t['after'].get(who,{}).get(asset,0)-t['before'].get(who,{}).get(asset,0)
                if computed[who,asset]!=actual:raise ValueError(('balance does not reconcile',run['scenario'],t['label'],who,asset,computed[who,asset],actual))
        steps.append({'tx_index':i,'label':t['label'],'transaction_hash':receipt['transactionHash'],
            'local_block_number':number(receipt['blockNumber']),'local_transaction_index':number(receipt['transactionIndex']),
            'status':number(receipt['status']),'gas_used':gas,'effective_gas_price_wei':price,
            'actual_gas_cost_wei':gas*price,'gas_ceiling_wei':number(t['request']['gas'])*number(t['request']['maxFeePerGas']),
            'gas_payer':sender,'economic_source':'sponsor advance' if sender==accounts['nqc_sender_and_beneficiary'] else 'own synthetic fixture balance',
            'before':t['before'],'after':t['after'],'reconciled':True})
    initial=run['initial']['balances'];final=run['final']['balances']
    delta={who:{token:final.get(who,{}).get(token,0)-initial.get(who,{}).get(token,0)
                for token in ('ETH','WETH','COLLATERAL')} for who in sorted(set(initial)|set(final))}
    sponsor=accounts['sponsor_and_topup_financier'];op=accounts['nqc_sender_and_beneficiary'];builder=accounts['simulated_builder']
    R=sum(f['amount_base_units'] for f in flows if f['asset']=='ETH' and f['actor_to']==sponsor and f['actor_from']==run.get('settlement_contract', accounts.get('nqc_executor')))
    U=sum(number(t['request']['value']) for t in run['transactions'] if t['label']=='return_unused_advance' and number(t['receipt']['status']) == 1 and t['request'].get('to') == sponsor)
    A=sum(number(t['request']['value']) for t in run['transactions'] if t['label']=='topup')
    F=sum(t['gas_cost_wei'] for t in run['transactions'] if t['label']=='topup')
    other_sponsor_gas=sum(t['gas_cost_wei'] for t in run['transactions'] if t['request']['from']==sponsor and t['label']!='topup')
    builder_fee=sum(f['amount_base_units'] for f in flows if f['asset']=='ETH' and f['actor_to']==builder and f['actor_from']==sponsor)
    O=other_sponsor_gas+builder_fee
    cash_margin=R+U-A-F-O
    assert cash_margin==delta[sponsor]['ETH']
    # Explicit lab capital opportunity charge: 1bp per attempted sequence, a sensitivity, not a provider quote.
    opportunity=(A+9999)//10000
    tips=sum(f['amount_base_units'] for f in flows if f['asset']=='ETH' and f['actor_from']==run.get('settlement_contract', accounts.get('nqc_executor')) and f['actor_to']==accounts['proposer'])
    owner_income=delta[op].copy()
    owner_income['ETH']-=A-U # Unreturned funding is not generated income, even if the owner controls that EOA.
    assert owner_income['ETH']<=0 # Gas is financed out of A; separate vector avoids falsely calling trapped advance profit.
    success=run['final']['position'][1] == 0 and any(t['label']=='liquidate' and number(t['receipt']['status'])==1 for t in run['transactions'])
    liquidation=next((t for t in run['transactions'] if t['label']=='liquidate'),None)
    inventory=liquidation['before'].get(run.get('settlement_contract', accounts.get('nqc_executor'))) if liquidation else None
    return {'scenario':run['scenario'],'classification':'LOCAL_SYNTHETIC_E2E_PASS' if success and cash_margin-opportunity>0 else 'LOCAL_SYNTHETIC_CONTROL',
        'actors':accounts,'external_identities_verified':False,'flash_lender':'NOT_USED_C1_CALLBACK',
        'chain_id':31337,'steps':steps,'flows':flows,'balance_delta_by_address':delta,
        'sponsor':{'R_refund_wei':R,'U_actually_returned_wei':U,'V_other_receipts_wei':0,'A_disbursed_wei':A,
            'F_funding_gas_wei':F,'P_separate_proposer_payment_wei':0,'O_other_cash_costs_wei':O,
            'other_gas_wei':other_sponsor_gas,'builder_fee_wei':builder_fee,'cash_margin_wei':cash_margin,
            'opportunity_charge_1bp_wei':opportunity,'margin_after_lab_opportunity_charge_wei':cash_margin-opportunity,
            'real_opportunity_and_operating_costs':None,'real_failure_recourse_terms':None},
        'nqc':{'initial':initial[op],'final':final[op],
            'liquidation_generated_WETH':delta[op]['WETH'],'native_retained_advance_wei':A-U-sum(t['gas_cost_wei'] for t in run['transactions'] if t['request']['from']==op),
            'executor_inventory_before_liquidation_excluded_from_income':inventory,
            'gas_paid_from_advance_wei':sum(t['gas_cost_wei'] for t in run['transactions'] if t['request']['from']==op),
            'real_indirect_costs':None,'real_recourse_liability':None},
        'builder_cash_margin_wei':delta[builder]['ETH'],'proposer_direct_tip_wei':tips,
        'realized_nqc_pnl_usd':'0','commercial_status':'PENDING_EXTERNAL_EVIDENCE','flags':run['flags']}
