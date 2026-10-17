"""Offline economic evidence audit. No network, signer, admission or P&L authority."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
MORPHO = HERE.parent/'experiments/morpho-sponsored-gas'
sys.path.insert(0, str(MORPHO))
import monthly_census as census
from case_b_route_audit import audit as case_b
from economic_ledger import Settlement, evaluate


def uint(value):
    if type(value) is not int or not 0 <= value < 2**256:
        raise ValueError('unsigned exact base units required')
    return value


def upfront_gap(balance, gas_limit, max_fee, value=0):
    """EOA fee-cap reserve; future proceeds cannot supply an earlier balance."""
    for amount in (balance, gas_limit, max_fee, value): uint(amount)
    return max(0, gas_limit*max_fee + value - balance)


def partition_flows(flows):
    """Each transfer once, by actor and (chain, asset); no asset conversions."""
    balances = defaultdict(int); seen = set()
    for f in flows:
        if f['id'] in seen: raise ValueError('duplicate flow identity')
        seen.add(f['id']); uint(f['amount']); uint(f['chain'])
        if not f['asset'] or not f['from'] or not f['to'] or f['from'] == f['to']:
            raise ValueError('distinct actors and asset identity required')
        for actor, sign in ((f['from'],-1),(f['to'],1)):
            balances[(f['chain'],f['asset'],actor)] += sign*f['amount']
    totals = defaultdict(int)
    for (chain,asset,_), amount in balances.items(): totals[(chain,asset)] += amount
    if any(totals.values()): raise ValueError('asset conservation failed')
    return [{'chain':c,'asset':a,'actor':o,'delta':n} for (c,a,o),n in sorted(balances.items())]


def before_cutoff(received, ready, cutoff, competitor, clock_comparable):
    """Necessary temporal order; unknown clocks/times must not become zero."""
    if clock_comparable is not True or any(x is None for x in (received,ready,cutoff,competitor)):
        return 'PENDIENTE'
    stamps = [datetime.fromisoformat(x) for x in (received,ready,cutoff,competitor)]
    if any(s.utcoffset() is None for s in stamps): raise ValueError('timezone required')
    r,p,c,w = stamps
    if p < r: raise ValueError('preparation before reception')
    return 'NECESSARY_ORDER_ONLY' if r <= p < min(c,w) else 'REFUTADO_FOR_THIS_TIMELINE'


def native_partition(fee):
    gas,charge = uint(fee['network_fee_wei']),uint(fee['sponsor_charge_wei'])
    flows = [dict(id='paymaster-charge',chain=4663,asset='native:ETH',
                  **{'from':'entrypoint_paymaster_deposit','to':'fixture_beneficiary'},amount=charge),
             dict(id='net-network-fee',chain=4663,asset='native:ETH',
                  **{'from':'transaction_gas_payer','to':'network_fee_collectors'},amount=gas)]
    return {'flows':flows,'actor_deltas':partition_flows(flows),
            'paymaster_cost_if_beneficiary_external_wei':charge,
            'beneficiary_and_payer_delta_if_same_entity_wei':charge-gas,
            'all_three_consolidated_external_cost_wei':gas,
            'incorrect_double_count_wei':charge+gas,
            'overstatement_if_all_three_consolidated_wei':charge,
            'actual_common_ownership_proven':False,'financing_commitment':None}


def cohort():
    root = census.EVIDENCE
    read = lambda n:json.loads((root/n).read_text())
    rows = census.validate_pages([read(f'page-{i:03}.json') for i in range(3)],
                                [read(f'reverse-{i:03}.json') for i in range(2)],
                                read('seven-day.json'),read('selection.json'))
    audited = census.audit(); grouped = defaultdict(list)
    for row in rows: grouped[row['txHash']].append(row)
    result=[]
    for tx, events in sorted(grouped.items()):
        receipt = audited['diagnostic_receipts'].get(tx,{'status':'NOT_REQUESTED'})
        result.append({'chain_id':1,'tx_hash':tx,'block':events[0]['blockNumber'],
                       'tx_index':events[0]['txIndex'],'event_count':len(events),
                       'log_indices':[e['logIndex'] for e in events],
                       'loan_assets':sorted({e['loanAsset']['address'] for e in events}),
                       'bad_debt_reported':any(e['badDebtAssets'] or e['badDebtShares'] for e in events),
                       'observed':'PROBADO_AS_API_RECORD','parsed':'PROBADO_OFFLINE',
                       'reproduced':'PENDIENTE','technically_compatible':'PENDIENTE',
                       'net_margin_evaluable':'PENDIENTE','nonrecourse_financeable':'PENDIENTE',
                       'temporally_capturable':'PENDIENTE','captured_by_nqc':False,
                       'first_unmet_stage':'REPRODUCED','receipt_status':receipt['status'],
                       'gas_cost_wei':receipt.get('gas_wei_per_transaction'),
                       'exclusion_reason':'NO_AUTHENTIC_NQC_PRETRANSACTION_REPLAY',
                       'case_b_external_known_cost_upper_bound_wei':
                           case_b()['incremental_residual_after_known_costs_upper_bound_wei'] if tx==census.TX_B else None})
    return {'transactions':result,'event_count':len(rows),'transaction_count':len(result),
            'first_unmet_counts':dict(Counter(r['first_unmet_stage'] for r in result)),
            'receipt_counts':dict(Counter(r['receipt_status'] for r in result)),
            'chain_population_complete':False,'eligible_count':None,
            'economic_admitted_count':0,'captured_nqc_count':0,'capture_probability':None}


def audit():
    a = json.loads((HERE/'evidence/aave-source-gate.json').read_text())
    b = json.loads((HERE/'evidence/robinhood-reconciliation.json').read_text())
    if a['classification']!='BLOCKED_NOT_A_PRODUCTION_SVR_BID_EXECUTOR':
        raise ValueError('Aave reference classification changed')
    if b['external_sponsor_committed'] or b['realized_nqc_revenue']:
        raise ValueError('unexpected Robinhood evidence promotion')
    reserves=[]
    for s in a['financial_experiments_only']:
        reserve=upfront_gap(0,s['transaction_gas_limit'],int(s['max_fee_per_gas_wei_assumed']))
        if reserve != int(s['minimum_EOA_upfront_gas_escrow_wei_at_max_fee']):
            raise ValueError('reference fee-cap reserve mismatch')
        reserves.append({'scenario':s['scenario_name'],'required_external_advance_wei':reserve,
                         'committed_external_advance_wei':None})
    # Reuse existing sponsor formula with explicit counterfactual amounts. It
    # illustrates separate top-up / included revert, not an operator quotation.
    f={k:0 for k in Settlement.__dataclass_fields__}
    f.update(sponsor_advance_wei=10**15,advance_returned_wei=6*10**14,
             sponsor_topup_actual_gas_wei=2*10**13)
    failure=evaluate(Settlement(**f))
    return {'scope':'OFFLINE_RECONCILIATION_AND_NECESSARY_CONDITIONS_NOT_EVM_REPLAY',
            'reference_contexts':{
                'aave':{'chain_id':1,'block':26142068,'source_commit':'6693542e675f930a7ef0a4fd60cb72e7a6608845',
                        'asset':'USDC','decimals':6,'attributable_realized_owner':None},
                'robinhood':{'chain_id':4663,'block':66744162,'transaction_index':1,
                             'source_commit':'6693542e675f930a7ef0a4fd60cb72e7a6608845',
                             'balances_are_simulated':True,'common_owner_of_fee_actors':None},
                'ethereum':{'chain_id':1,'block':26190955,'transaction_index':1,
                            'source_commit':'0f26557c1f83e12efcf364ece6cebd8505d2e2c2',
                            'operator':'external_liquidator_not_NQC'}},
            'aave_zero_eoa_reserves':reserves,
            'robinhood_success':native_partition(b['nqc_success']),
            'robinhood_included_failure':native_partition(b['nqc_parent_failure']),
            'robinhood_token_surplus_before_costs':{'chain_id':4663,'asset':'USDG as identified by reference route',
                                                'raw_units':b['surplus_before_gas_usdg_raw'],'decimals':6,
                                                'executable_usd_or_eth_conversion':None},
            'separate_topup_revert_sensitivity':{'assumptions_wei':f,'sponsor_loss_wei':-failure['sponsor_margin_wei'],
                                                'operator_failure_liability':None,'commercial_commitment':None},
            'morpho_ethereum_case_b':case_b(),
            'temporal_status_all_routes':'PENDIENTE_NO_COMPLETE_COMPARABLE_RECEPTION_AND_CUTOFF',
            'cohort':cohort(),'nqc_realized_usd_certified':'0','monthly_expectation':None,
            'monthly_target_sensitivity':census.audit()['target_sensitivity'],
            'sponsorship':'PATROCINIO_NO_DEMOSTRADO','economic_admission':False}


if __name__=='__main__':
    print(json.dumps(audit(),indent=2))
    raise SystemExit(2)
