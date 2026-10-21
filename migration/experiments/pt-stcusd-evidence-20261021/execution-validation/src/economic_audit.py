#!/usr/bin/env python3
"""Exact ledger of recorded EXTERNAL history; unknown NQC costs stay unknown."""
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'route-audit/src'))
from route_audit import analyze, word

def fraction_json(f):
    return {'numerator':str(f.numerator),'denominator':str(f.denominator)}

def decimal6(f):
    n=(abs(f.numerator)*10**6)//f.denominator
    return ('-' if f<0 else '')+str(n//10**6)+'.'+str(n%10**6).zfill(6)

def ledger():
    c=json.loads((ROOT.parent/'route-audit/inputs/route_evidence.json').read_text())
    original=json.loads((ROOT.parent/'route-audit/reference/selected_log.json').read_text())
    route=analyze(c,original)
    journal=[]
    def add(asset,fr,to,amount,source):
        assert isinstance(amount,int) and amount>=0
        journal.append({'asset':asset,'from':fr,'to':to,'amount_base':str(amount),'source':source})
    for e in c['events']:
        if e['event']=='TRANSFER' and e['emitter'] in ('USDC','WETH'):
            add(e['emitter'],*e['indexed'],int(word(e['words'][0],c['addresses']),16),'route-audit log '+str(e['index']))
    unwrap=int(route['builder_paid_event_wei'])
    add('WETH','EXECUTOR','WETH_UNWRAP_BURN',unwrap,'route-audit log 49 Withdrawal, not ERC20 Transfer')
    add('ETH','WETH_CONTRACT','EXECUTOR',unwrap,'CONTINUIDAD.md prior indexed native transfer 293')
    add('ETH','EXECUTOR','HISTORICAL_COINBASE',unwrap,'CONTINUIDAD.md prior indexed native transfer 294; BuilderPaid log is not another payment')
    gas_used=1870816; gas_price=1042435069; basefee=42435069
    target=json.loads((ROOT/'evidence/target_indexed_block.json').read_text())['data']['block_details']
    assert int(target['base_fee_per_gas'])==basefee
    gas=gas_used*gas_price; burn=gas_used*basefee; tip=gas-burn
    add('ETH','HISTORICAL_GAS_EOA','BASEFEE_BURN',burn,'CONTINUIDAD.md gasUsed/effectiveGasPrice; indexed target base fee')
    add('ETH','HISTORICAL_GAS_EOA','HISTORICAL_COINBASE',tip,'Priority portion ALREADY INCLUDED in total gas')
    balances=defaultdict(lambda:defaultdict(int))
    for j in journal:
        n=int(j['amount_base']); balances[j['asset']][j['from']]-=n;balances[j['asset']][j['to']]+=n
    assert all(sum(v.values())==0 for v in balances.values())
    usdc_payout=balances['USDC']['PAYOUT']; weth_residue=balances['WETH']['EXECUTOR']
    usdc_swap=balances['USDC']['POOL']; weth_received=-balances['WETH']['POOL']
    assert gas==1950204206046304 and usdc_payout==23882951 and weth_residue==225720514923773
    # Illustrative historical marking only. This is not an executable reverse quote.
    ratio=Fraction(usdc_swap,weth_received)
    conditional_base=Fraction(usdc_payout)+(weth_residue-gas)*ratio
    R=3305262344; D=3220954251
    return {
      'schema':'nqc-pt-stcusd-integral-accounting-v1',
      'verdict':'NQC_NET_NOT_DETERMINABLE', 'nqc_net_profit':None,
      'nqc_original_replay_executed':False,'nqc_variant_executed':False,
      'nqc_settlement_or_realized_gain_demonstrated':False,
      'historical_operator':'EXTERNAL_NOT_NQC',
      'sources':{'route':'../route-audit/inputs/route_evidence.json','prior_gas_and_native':'../CONTINUIDAD.md',
                 'new_block_metadata':'evidence/target_indexed_block.json'},
      'source_limit':'53 normalized indexed logs plus prior gas/native transcription; not a raw authenticated receipt or complete pre/poststate.',
      'historical_flow_journal':journal,
      'historical_deltas_base_units':{a:{k:str(v) for k,v in sorted(b.items())} for a,b in balances.items()},
      'journal_balances_per_asset':True,
      'historical_gas':{'gas_used':gas_used,'effective_gas_price_wei':str(gas_price),'basefee_wei':str(basefee),
         'total_wei':str(gas),'burn_wei':str(burn),'priority_wei':str(tip),
         'gas_limit':2683545,'max_fee_per_gas_wei':'1084920764','gas_limit_times_max_fee_wei':str(2683545*1084920764),
         'upfront_cap_is_not_final_cost':True,'raw_receipt_recovered_this_run':False},
      'historical_coinbase_receipts':{'direct_transfer_wei':str(unwrap),'priority_wei':str(tip),
         'total_observed_wei':str(unwrap+tip),'sponsor_receipts_verified':False,'builder_net_profit':None},
      'conditional_external_owner_residual':{'USDC_base':str(usdc_payout),'WETH_base':str(weth_residue),'ETH_base':str(-gas),
         'ownership_consolidation_verified':False,'other_obligations_complete':False,
         'historical_swap_mark_USDC_per_ETH':fraction_json(ratio*10**12),
         'conditional_mark_USDC':fraction_json(conditional_base/10**6),
         'conditional_mark_USDC_truncated_6dp':decimal6(conditional_base/10**6),
         'is_executable_quote':False,'is_audited_external_profit':False,'is_NQC_profit':False},
      'morpho_liquidity_conditions':{'direct_callback_USDC_global_prefix_lower_bound_base':str(R),
         'actual_parent_USDC_balance':None,'actual_withdrawable_market_assets':None,'adapter_supply_shares':None,
         'withdrawal_market_id':c['addresses']['WITHDRAWAL_MARKET'],
         'liquidation_market_id':c['addresses']['LIQUIDATION_MARKET'],
         'hypothetical_flash_from_same_morpho_empty_liquidation_callback':{
           'classification':'CONDITIONAL_SEQUENCE_ARITHMETIC_NOT_EXECUTED',
           'morpho_USDC_signed_sequence_base':[str(-D),str(D),str(-R),str(D)],
           'global_prefix_lower_bound_base':str(max(D,R)),
           'meaning':'Flash D; liquidate with empty callback and repay D first; redeem R; return flash D. Shares, withdrawals and route feasibility still unverified.'},
         'hypothetical_flash_plus_nested_redemption_before_debt_repayment':{
           'classification':'CONDITIONAL_SEQUENCE_ARITHMETIC_NOT_EXECUTED',
           'global_prefix_lower_bound_base':str(D+R),
           'meaning':'Holding borrowed D while withdrawing R needs D+R global USDC. Do not conflate the two call orders.'}},
      'strategies':{'A_direct_morpho_callback':{'executed':False,'net_USDC':None,'gas':None},
                    'B_flash_loan_or_swap':{'executed':False,'net_USDC':None,'gas':None,'financing_fee':None},
                    'winner':None},
      'nqc_unknown_costs':{k:None for k in ['recoverable_real_output','debt_at_execution','financing_fee','deployment_gas',
         'execution_gas','approvals_gas','sponsor_advance','unused_advance_return','sponsor_reimbursement','sponsor_margin',
         'builder_payment','priority_fee','minimum_operator_profit','revert_or_reorg_liability','other_attributable_costs']},
      'double_count_rules':['Use swap output net of included pool fees; do not subtract them again.',
         'Gas = base-fee burn + priority; never subtract total and priority again.',
         'WETH unwrap changes denomination, not income; BuilderPaid event is not a second ETH transfer.',
         'Starting from USDC payout already deducts USDC converted to WETH; track residual WETH and ETH separately.',
         'Sponsor advance principal is financing, not profit. Reconcile repayment and unused advance before cost attribution.',
         'Sponsor reimbursement that includes gas must not also be charged as a second independent gas cost.'],
      'unknown_costs_treated_as_zero':False,
      'zero_proprietary_capital_proven':False}

if __name__=='__main__':print(json.dumps(ledger(),indent=2,sort_keys=True))
