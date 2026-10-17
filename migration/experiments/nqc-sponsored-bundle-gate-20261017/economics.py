"""Exact, fail-closed local participation policy. Never a real-builder admission gate."""
import json
from local_node import HERE, save, ref
from reconcile_flows import reconcile

UNKNOWN_COSTS = ('infrastructure', 'aggregated_failed_attempts', 'commercial_funding_terms',
                 'stake', 'contracting', 'personal_recourse', 'capture_probability')

def evaluate(run):
    if run.get('snapshot_source','').startswith('prestateTracer'):
        from run_coordinated import diff_balances
        previous=run['initial']['balances']
        for t in run['transactions']:
            assert t['before']==previous,'discontinuous balance snapshot'
            assert diff_balances(t['before'],t['state_diff'],run['actors'])==t['after'],'state diff differs'
            previous=t['after']
        assert previous==run['final']['balances'],'final state differs'
    ledger = reconcile(run)
    actors = run['actors']; op = actors['nqc_sender_and_beneficiary']
    sponsor = ledger['sponsor']; reasons = []
    a = sponsor['A_disbursed_wei']; u = sponsor['U_actually_returned_wei']
    gas = sum(s['gas_used'] for s in ledger['steps'])
    completed = run['final']['position'][1] == 0
    if not completed: reasons.append('position_not_closed')
    if any(int(t['receipt']['status'],16) != 1 for t in run['transactions']): reasons.append('included_revert')
    if run.get('rpc_rejections'): reasons.append('pool_rejection')
    if run.get('accepted_not_included'): reasons.append('candidate_not_fully_included')
    if u == 0: reasons.append('unused_advance_return_not_received')
    if ledger['nqc']['native_retained_advance_wei'] != 0: reasons.append('funding_retained_not_generated_profit')
    if sponsor['margin_after_lab_opportunity_charge_wei'] <= 0: reasons.append('financier_nonpositive')
    if ledger['nqc']['liquidation_generated_WETH'] <= 0: reasons.append('NQC_nonpositive_generated_WETH')
    if ledger['builder_cash_margin_wei'] < 2*10**15: reasons.append('hypothetical_builder_fee_not_met')
    if ledger['proposer_direct_tip_wei'] < 4*10**16: reasons.append('hypothetical_proposer_tip_not_met')
    upfront = []
    op_consumed = 0; minimum_a = 0
    for t in run['transactions']:
        tx=t['request']; who=tx['from']; limit=int(tx['gas'],16); cap=int(tx['maxFeePerGas'],16)
        value=int(tx['value'],16); balance=t['before'][who]['ETH']
        ceiling=limit*cap+value
        upfront.append({'label':t['label'],'transaction_index':int(t['receipt']['transactionIndex'],16),
                        'from':who,'nonce':int(tx['nonce'],16),'balance_before_wei':balance,
                        'max_upfront_including_value_wei':ceiling,'gas_actually_consumed_wei':t['gas_cost_wei'],
                        'effective_gas_price_wei':int(t['receipt']['effectiveGasPrice'],16),
                        'max_fee_per_gas_wei':cap,'full_max_cap_affordable':balance>=ceiling})
        assert balance>=ceiling, ('max-cap affordability failure',run['scenario'],t['label'])
        if who==op:
            if t['label']!='return_unused_advance': minimum_a=max(minimum_a,op_consumed+ceiling)
            op_consumed += t['gas_cost_wei']
    for t in run.get('accepted_not_included', []):
        # Pending transaction balances are not claimed as at-index snapshots.
        tx=t['request']; value=int(tx['value'],16); cap=int(tx['maxFeePerGas'],16); limit=int(tx['gas'],16)
        upfront.append({'label':t['label'],'transaction_index':None,'from':tx['from'],
            'nonce':int(tx['nonce'],16),'final_balance_wei':run['final']['balances'][tx['from']]['ETH'],
            'max_upfront_including_value_wei':value+cap*limit,'included':False})
    builder=ledger['builder_cash_margin_wei']
    ledger.update(
        classification='MODEL_ONLY' if not reasons else 'REFUTED_UNDER_ASSUMPTIONS',
        EVM_liquidation_local_pass=completed,
        policy={'name':'local distinct-financier full-return participation policy',
                'admitted_under_measured_and_explicit_lab_costs':not reasons,'rejection_reasons':reasons,
                'real_builder_acceptance':None,'source_of_thresholds':'hypothetical lab choices, not provider terms',
                'proposer_tip_floor_wei':4*10**16,'builder_fee_floor_wei':2*10**15},
        financier_and_builder_same_owner_hypothesis={
            'assumed_not_verified':True,'proposer_separate':True,
            'combined_cash_margin_wei':sponsor['cash_margin_wei']+builder,
            'combined_margin_after_lab_opportunity_wei':sponsor['margin_after_lab_opportunity_charge_wei']+builder,
            'internal_builder_fee_cancels_but_transaction_gas_does_not':True},
        total_gas_units=gas,upfront_by_included_transaction=upfront,
        minimum_trade_advance_at_measured_prefix_cost_and_caps_wei=minimum_a,
        actual_financier_starting_ETH_wei=run['initial']['balances'][actors['sponsor_and_topup_financier']]['ETH'],
        unknown_indispensable_external_costs={k:None for k in UNKNOWN_COSTS},
        expected_monthly_profit=None,realized_nqc_pnl_usd='0',
        balance_sources=run.get('snapshot_source','direct per-transaction RPC snapshots; six separate blocks'),
        predeployed_variant=run.get('mode')=='predeployed')
    ledger['flash_lender'] = 'ORIGINAL_MORPHO_8_WETH' if run.get('architecture')=='C2' else 'NOT_USED_C1_CALLBACK'
    return ledger

def comparable_state(run):
    s=run['initial'];a=run['actors']
    # Route addresses differ by design; all are initially empty or explicit predeployment.
    return {k:s[k] for k in ('market','market_id','market_totals','oracle','position','reserves')} | {
        'parent_hash':s['parent']['hash'],'parent_timestamp':s['parent']['timestamp'],
        'base_actor_balances':{name:s['balances'][a[name]] for name in ('Morpho','dex_pair','borrower','other_borrower',
            'lender','WETH','ERC20','nqc_sender_and_beneficiary','sponsor_and_topup_financier','simulated_builder','proposer')}}

def main():
    index=json.loads((HERE/'evidence/run-index.json').read_text()); runs={}; ledgers={}
    for item in index['runs']:
        name=item['scenario'];r=json.loads((HERE/'evidence'/f'{name}.json').read_text())
        runs[name]=r;ledgers[name]=evaluate(r)
    c1=runs['A2_C1_cash8'];c2=runs['C2a_cash8']
    assert comparable_state(c1)==comparable_state(c2),'comparison state differs'
    assert c1['transactions'][0]['block']==c2['transactions'][0]['block'] or (
        c1['transactions'][0]['block']['timestamp']==c2['transactions'][0]['block']['timestamp'] and
        c1['transactions'][0]['block']['baseFeePerGas']==c2['transactions'][0]['block']['baseFeePerGas'])
    comparison={'identical_prestate':comparable_state(c1),'status':'EVM_LOCAL_PASS',
                'same_block_timestamp':c1['transactions'][0]['block']['timestamp'],
                'same_R_P_builder_wei':[5*10**16,4*10**16,2*10**15],
                'scenarios':{n:{'total_gas':ledgers[n]['total_gas_units'],
                               'financier_cash_wei':ledgers[n]['sponsor']['cash_margin_wei'],
                               'NQC_generated_WETH':ledgers[n]['nqc']['liquidation_generated_WETH']}
                             for n in ('A2_C1_cash8','C2a_cash8','C2b_cash0','C2_hypothetical_predeployed')}}
    save('identical-state-comparison',comparison)
    boundaries={}
    for name in ('A2_C1_zero_cash','A2_C1_cash8','C2a_cash8','C2_hypothetical_predeployed'):
        l=ledgers[name];g=l['total_gas_units'];opp=l['sponsor']['opportunity_charge_1bp_wei']
        r=5*10**16;b=2*10**15;p=4*10**16;surplus=249365645570551238
        frontier=(r-b-opp-1)//g
        consumed=0; prefix_coefficient=0
        for t in runs[name]['transactions']:
            if t['request']['from'] == runs[name]['actors']['nqc_sender_and_beneficiary']:
                if t['label']!='return_unused_advance':
                    prefix_coefficient=max(prefix_coefficient,consumed+int(t['request']['gas'],16))
                consumed+=int(t['receipt']['gasUsed'],16)
        # Joint frontier with A increased only to cover the largest prefix, cap=effective fee.
        # ceil(A/10000) is still charged, so a larger advance is not costless in the model.
        funded_frontier=(r-b-1)*10000//(10000*g+prefix_coefficient)
        def funded_margin(price):
            aa=prefix_coefficient*price
            return r-b-g*price-(aa+9999)//10000
        assert funded_margin(funded_frontier)>0>=funded_margin(funded_frontier+1)
        boundaries[name]={'classification':'MODEL_ONLY_FIXED_MEASURED_GAS',
            'max_positive_effective_fee_wei':frontier,'margin_at_frontier_wei':r-b-opp-g*frontier,
            'margin_one_wei_higher':r-b-opp-g*(frontier+1),
            'minimum_R_strict_financier_profit_2gwei_wei':b+opp+g*2*10**9+1,
            'maximum_R_strict_NQC_profit_wei':surplus-p-1,
            'maximum_R_for_contract_minimum_0_01_WETH_wei':surplus-p-10**16,
            'uniform_price_and_cap_model':{
                'required_advance_wei_per_wei_of_fee':prefix_coefficient,
                'maximum_affordable_fee_at_fixed_0_03_ETH_wei':3*10**16//prefix_coefficient,
                'joint_positive_frontier_with_minimum_scaled_advance_wei':funded_frontier,
                'required_advance_at_joint_frontier_wei':prefix_coefficient*funded_frontier,
                'financier_margin_at_joint_frontier_wei':funded_margin(funded_frontier),
                'financier_margin_next_wei':funded_margin(funded_frontier+1)},
            'unknown_commercial_costs':None,
            'limitations':['R/P or fee changes may change gas; must replay changed calldata',
                'advance and fee caps must fund every prefix', 'WETH/ETH are distinct ledgers, no USD pricing',
                'predeployed case excludes previously-paid initialization; not a free first cycle']}
        assert boundaries[name]['margin_at_frontier_wei']>0>=boundaries[name]['margin_one_wei_higher']
    save('break-even',boundaries)
    output={'scope':'SYNTHETIC_LOCAL_ONLY_NO_REAL_PROVIDER',
            'formula':'R+U+V-A-F-P-O; cash partition reconciled, separate lab opportunity charge',
            'commercial_status':'BLOCKED_EXTERNAL_EVIDENCE','scenarios':list(ledgers.values())}
    (HERE/'FINANCIER_AND_BUILDER_LEDGER.json').write_text(json.dumps(output,separators=(',',':'))+'\n')
    print(json.dumps({'reconciled':len(ledgers),'model_admitted':[k for k,v in ledgers.items() if v['policy']['admitted_under_measured_and_explicit_lab_costs']],
                      'commercial_admitted':0}))

if __name__=='__main__':main()
