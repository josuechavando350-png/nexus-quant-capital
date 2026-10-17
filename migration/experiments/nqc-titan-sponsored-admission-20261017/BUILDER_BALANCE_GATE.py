"""Offline identity-sensitive sponsorship gate. No signing, submission or networking.

PASS_LOCAL is explicitly scoped to a declared laboratory ownership/cost policy.
It never implies authenticated real-builder income or founder non-recourse terms.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'nqc-sponsored-bundle-gate-20261017'
sys.path.insert(0, str(BASE))
from reconcile_flows import reconcile
from run_coordinated import diff_balances


def group_cash(ledger, addresses):
    addresses = set(addresses)  # Two roles at one address do not double income.
    flow_net = sum(f['amount_base_units'] * ((f['actor_to'] in addresses) -
                   (f['actor_from'] in addresses))
                   for f in ledger['flows'] if f['asset'] == 'ETH')
    balance_net = sum(ledger['balance_delta_by_address'][a]['ETH'] for a in addresses)
    assert flow_net == balance_net, 'group flow/balance discrepancy'
    return balance_net


def evm_layer(run):
    before = run['initial']['balances']
    checks = []
    for t in run['transactions']:
        assert t['before'] == before, 'discontinuous balance history'
        assert diff_balances(before, t['state_diff'], run['actors']) == t['after']
        tx = t['request']; sender = tx['from']
        limit = int(tx['gas'], 16); cap = int(tx['maxFeePerGas'], 16)
        value = int(tx['value'], 16); base = int(t['block']['baseFeePerGas'], 16)
        tip = int(tx['maxPriorityFeePerGas'], 16)
        price = int(t['receipt']['effectiveGasPrice'], 16)
        state_nonce = t['state_diff']['pre'].get(sender, {}).get('nonce', 0)
        if isinstance(state_nonce, str): state_nonce = int(state_nonce, 16)
        assert int(tx['nonce'], 16) == state_nonce, 'request nonce/prestate mismatch'
        assert price == min(cap, base + tip) and cap >= base
        assert before[sender]['ETH'] >= limit*cap+value, 'prefix cannot reserve max fee plus value'
        checks.append({'label': t['label'], 'nonce': state_nonce, 'gas_limit': limit,
                       'max_fee_wei': cap, 'priority_fee_cap_wei': tip,
                       'effective_price_wei': price, 'gas_used': int(t['receipt']['gasUsed'],16),
                       'upfront_reserve_wei': limit*cap+value, 'top_level_value_wei': value,
                       'balance_before_wei': before[sender]['ETH'],
                       'actual_gas_wei': t['gas_cost_wei'],
                       'base_fee_burn_wei': int(t['receipt']['gasUsed'],16)*base,
                       'priority_paid_to_coinbase_wei': int(t['receipt']['gasUsed'],16)*(price-base)})
        before = t['after']
    assert before == run['final']['balances'], 'end state mismatch'
    ledger = reconcile(run)  # Independent trace/log cash flows versus storage/native diff.
    op = run['actors']['nqc_sender_and_beneficiary']
    closed = (run['initial']['position'][1] > run['final']['position'][1] == 0 and
              any(t['label']=='liquidate' and int(t['receipt']['status'],16)==1
                  for t in run['transactions']))
    fail = []
    if any(run['initial']['balances'][op].values()): fail.append('owner_initial_capital_not_zero')
    if not closed: fail.append('debt_not_repaid')
    if run.get('accepted_not_included') or run.get('rpc_rejections'): fail.append('incomplete_inclusion')
    if any(int(t['receipt']['status'],16)!=1 for t in run['transactions']): fail.append('included_revert')
    if ledger['sponsor']['U_actually_returned_wei'] <= 0: fail.append('U_not_received')
    if ledger['nqc']['native_retained_advance_wei'] != 0: fail.append('unreturned_funding')
    if ledger['nqc']['liquidation_generated_WETH'] <= 0: fail.append('no_new_NQC_WETH')
    return {'classification': 'REFUTED' if fail else 'PASS_LOCAL',
            'failures': fail, 'prefixes': checks, 'ledger': ledger}


def classify(checks):
    if any(value is False for value in checks.values()): return 'REFUTED'
    if any(value is None for value in checks.values()): return 'UNKNOWN'
    return 'PASS_LOCAL'


def value_documented(provider, extra_sponsored_value_wei):
    assert provider in ('Titan', 'Quasar') and extra_sponsored_value_wei >= 0
    # Missing documentation is not a prohibition. U uses already-funded money.
    return True if extra_sponsored_value_wei == 0 or provider == 'Titan' else None


def evaluate(run, builder_addresses, *, scope='LAB_ASSIGNMENT',
             provider='Titan', extra_sponsored_value_wei=0,
             loss_cap_wei=None, reverting_labels=(), dropping_labels=(),
             founder_model_recourse_wei=None):
    evm = evm_layer(run); ledger = evm['ledger']; a = run['actors']
    group = set(builder_addresses)
    assert group <= set(ledger['balance_delta_by_address']), 'unobserved owner address'
    # Never let an undocumented identity claim authenticate the proposer as builder.
    auth = scope == 'LAB_ASSIGNMENT' and a['proposer'] not in group
    margin = group_cash(ledger, group)
    s = ledger['sponsor']; opportunity = (s['A_disbursed_wei']+9999)//10000
    topup = next((t for t in run['transactions'] if t['label']=='topup'), None)
    first_create = next((t for t in run['transactions'] if t['label']=='nqc_adapter'), None)
    op = a['nqc_sender_and_beneficiary']
    missing = None if first_create is None else (
        run['initial']['balances'][op]['ETH'] < int(first_create['request']['gas'],16)*
        int(first_create['request']['maxFeePerGas'],16)+int(first_create['request']['value'],16))
    # Explicit conservative cash-at-risk limit: A plus all own tx maximum fees/values
    # other than A. An exposure bound is not a commercial reimbursement promise.
    own_caps = sum(int(t['request']['gas'],16)*int(t['request']['maxFeePerGas'],16)+
                   int(t['request']['value'],16) for t in run['transactions']
                   if t['request']['from'] in group)
    checks = {
        'EVM_complete': evm['classification']=='PASS_LOCAL',
        'initial_missing_gas': missing,
        'funding_from_builder_entity': topup is not None and topup['request']['from'] in group,
        'builder_identity_scoped': True if auth else None,
        'builder_margin_positive_after_lab_1bp': margin-opportunity>0 if auth else None,
        'extra_sponsored_value_documented': value_documented(provider, extra_sponsored_value_wei),
        'failure_exposure_within_declared_lab_cap': None if loss_cap_wei is None else own_caps<=loss_cap_wei,
        'required_transactions_not_optional': not (set(reverting_labels)|set(dropping_labels)),
        'founder_recourse_model_zero': None if founder_model_recourse_wei is None else founder_model_recourse_wei==0,
    }
    return {'classification': classify(checks), 'checks': checks,
            'scope': scope, 'source_scenario': run['scenario'],
            'builder_addresses': sorted(group),
            'observed_address_group_cash_delta_wei': margin,
            'builder_cash_delta_wei': margin if auth else None,
            'lab_opportunity_1bp_wei': opportunity,
            'builder_after_lab_charge_wei': margin-opportunity if auth else None,
            'declared_loss_cap_wei': loss_cap_wei,
            'own_max_caps_and_values_at_risk_wei': own_caps,
            'founder_model_recourse_wei': founder_model_recourse_wei,
            'founder_max_recourse_wei': None,
            'founder_real_terms': 'UNKNOWN',
            'builder_real_recipient': None, 'real_builder_acceptance': 'NOT_TESTED',
            'commercial_classification': 'UNKNOWN',
            'historical_B': 'BLOCKED_PRESTATE', 'monthly': 'NO_ESTIMABLE',
            'EVM': {k:v for k,v in evm.items() if k!='ledger'}}


def frontier(run):
    """Constant measured gas; all caps=effective f; A=minimal prefix reserve K*f.

    Strict margin R-G*f-ceil(K*f/10000)>0. Integer identity, no float search.
    Return uses 21000 gas, cap=f and U=A-operatorGas*f, so its reserve is exact.
    """
    e = evm_layer(run); ledger=e['ledger']; op=run['actors']['nqc_sender_and_beneficiary']
    G=sum(p['gas_used'] for p in e['prefixes']); K=0; spent=0
    for t in run['transactions']:
        if t['request']['from']==op:
            if t['label']!='return_unused_advance':
                K=max(K,spent+int(t['request']['gas'],16))
            spent+=int(t['receipt']['gasUsed'],16)
    R=ledger['sponsor']['R_refund_wei']
    f=((R-1)*10000)//(10000*G+K)
    def point(price):
        A=K*price; charge=(A+9999)//10000
        return {'effective_fee_wei_per_gas':price, 'minimum_advance_wei':A,
                'U_wei':A-spent*price, 'gas_cost_wei':G*price,
                'lab_opportunity_wei':charge,'margin_wei':R-G*price-charge}
    assert point(f)['margin_wei']>0>=point(f+1)['margin_wei']
    sensitivity=[]
    for extra in (10000,100000):
        # Conservative extra execution gas before the limiting CREATE prefix.
        g2=G+extra; k2=K+extra
        cutoff=((R-1)*10000)//(10000*g2+k2)
        sensitivity.append({'extra_gas_before_limiting_prefix':extra,
                            'effective_fee_cutoff_wei_per_gas':cutoff,
                            'minimum_advance_at_cutoff_wei':k2*cutoff})
    return {'classification':'MODEL_ONLY','gas_units_fixed':G,'prefix_K':K,
            'R_wei':R,'last_positive':point(f),'first_nonpositive':point(f+1),
            'fixed_advance_003_ETH_max_affordable_fee_wei_per_gas':3*10**16//K,
            'extra_gas_sensitivity_not_new_EVM':sensitivity,
            'sensitivity_only_not_EVM_replayed_at_frontier':True,
            'assumptions':['unchanged calldata/state/gas','cap equals effective fee',
                           'no additional bidder cost','known 21000-gas EOA return',
                           '1bp illustrative capital charge, not a provider quote']}
