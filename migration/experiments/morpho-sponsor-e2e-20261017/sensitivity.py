"""Exact conditional sensitivities. Receipt gas is held fixed; these are NOT additional EVM runs."""
import json
from fractions import Fraction
from run_e2e import HERE, E, ints

def quote(amount,x,y):
    if any(type(n) is not int or n<0 for n in (amount,x,y)) or x==0 or y==0:raise ValueError('integer reserves')
    return amount*997*y//(x*1000+amount*997)
def ceiling(f):return -(-f.numerator//f.denominator)
def rational(f):return {'numerator':f.numerator,'denominator':f.denominator}
def main():
    run=json.loads((HERE/'evidence/C1_success.json').read_text())
    led=json.loads((HERE/'ACTOR_SETTLEMENT_LEDGER.json').read_text())['scenarios'][0]
    before=run['initial']['reserves'];after=run['final']['reserves']
    seized=after[0]-before[0];out=before[1]-after[1]
    assert quote(seized,*before[:2])==out
    oracle_value=Fraction(seized*9,10);post_fee=oracle_value*Fraction(997,1000)
    gas=sum(s['gas_used'] for s in led['steps']);refund=5*10**16;tip=4*10**16;builder=2*10**15
    opportunity=led['sponsor']['opportunity_charge_1bp_wei']
    max_price=(refund-builder-opportunity-1)//gas
    threshold=811*10**16; a=seized*997;denominator=9*a-10000*threshold
    n=ceiling(Fraction(threshold*a,denominator))
    assert quote(seized,10*n,9*n)>=threshold and quote(seized,10*(n-1),9*(n-1))<threshold
    result={'scope':'EXACT_MATHEMATICAL_SENSITIVITY_NOT_ADDITIONAL_EVM_OR_HISTORICAL_EVIDENCE',
        'base':{'seized_collateral_units':seized,'oracle_value_WETH_rational':rational(oracle_value),
            'fee_value_at_initial_marginal_price_rational':rational(oracle_value-post_fee),
            'price_impact_and_output_rounding_rational':rational(post_fee-out),
            'executable_WETH_units':out,'debt_returned_WETH_units':8*E,'pre_allocation_surplus_WETH_units':out-8*E,
            'infinite_depth_post_fee_surplus_rational':rational(post_fee-8*E),
            'sponsor_refund_ETH_wei':refund,'proposer_tip_ETH_wei':tip,'operator_WETH_units':out-8*E-refund-tip,
            'network_gas_units':gas,'builder_fee_ETH_wei':builder,'opportunity_charge_ETH_wei':opportunity},
        'gas_break_even_with_fixed_A_and_units':{'maximum_strictly_positive_effective_price_wei':max_price,
            'sponsor_margin_at_boundary_wei':refund-builder-opportunity-gas*max_price,
            'sponsor_margin_next_wei':refund-builder-opportunity-gas*(max_price+1),
            'advance_must_be_increased_if_required':'Gas price alone does not establish up-front affordability'},
        'price_cases':[], 'pool_depth_cases':[],
        'one_wei_depth_boundary':{'x':10*n,'y':9*n,'out':quote(seized,10*n,9*n),
            'previous_x':10*(n-1),'previous_y':9*(n-1),'previous_out':quote(seized,10*(n-1),9*(n-1)),
            'target_output':threshold},
        'tip_strict_maximum_given_fixed_refund_wei':out-8*E-refund-1,
        'tip_maximum_meeting_contract_min_profit_wei':out-8*E-refund-10**16,
        'refund_strict_minimum_at_2gwei_wei':builder+gas*2*10**9+opportunity+1,
        'upfront_caps':{'operator_sum_limit_times_cap_wei':sum(s['gas_ceiling_wei'] for s in led['steps'] if s['gas_payer']==run['actors']['nqc_sender_and_beneficiary']),
            'operator_observed_gas_wei':led['nqc']['gas_paid_from_advance_wei'],
            'actual_topup_gas_wei':led['sponsor']['F_funding_gas_wei'],
            'observed_advance_wei':led['sponsor']['A_disbursed_wei']},
        'real_recurring_costs':None,'real_capture_probability':None,'expected_monthly_profit':None}
    for base,priority,cap in [(1,1,3),(1,2,3),(5,1,10),(20,1,30),(30,2,40),(5,1,4)]:
        price=min(cap,base+priority)*10**9
        result['price_cases'].append({'base_gwei':base,'priority_gwei':priority,'cap_gwei':cap,
            'includable_under_fee_cap':cap>=base,'sponsor_margin_wei':refund-builder-opportunity-gas*price if cap>=base else None,
            'classification':'FIXED_GAS_MATH_ONLY'})
    for x in (20*E,100*E,1000*E,10000*E):
        q=quote(seized,x,x*9//10)
        result['pool_depth_cases'].append({'collateral_reserve':x,'WETH_reserve':x*9//10,'out':q,
            'surplus_before_allocations':q-8*E,'operator_residual_after_fixed_allocation':q-8*E-refund-tip,
            'meets_current_plan_output':q>=threshold})
    (HERE/'evidence/exact-sensitivity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'sponsor_price_frontier':max_price,'pool_x_boundary':10*n,'classification':result['scope']}))

if __name__=='__main__':main()
