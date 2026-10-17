"""Independent offline accounting of saved evidence; no EVM, RPC or signing.

Python standard library only. No Astra module is imported or executed.
All monetary arithmetic uses int or Fraction. None denotes UNKNOWN.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
DEPOSIT = '0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c'
WITHDRAWAL = '0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65'
LIQUIDATION = '0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41'


class Truth(Enum):
    TRUE = 'TRUE'
    FALSE = 'FALSE'
    UNKNOWN = 'UNKNOWN'

    def __bool__(self):
        raise TypeError('Use tri_and explicitly; UNKNOWN has no Python truth value')


def exact_int(value):
    if type(value) is int:
        return value
    if type(value) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]*)', value):
        return int(value)
    raise ValueError('Exact integer or canonical decimal string required')


def uint(value):
    value = exact_int(value)
    if value < 0:
        raise ValueError('Nonnegative amount required')
    return value


def hexint(value):
    if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]+', value):
        raise ValueError('Hexadecimal input required')
    return int(value, 16)


def quantity(value):
    if type(value) is not str or not re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value):
        raise ValueError('Canonical hexadecimal quantity required')
    return int(value, 16)


def hash32(value):
    if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{64}', value):
        raise ValueError('32-byte hexadecimal hash required')
    return value.lower()


def tri_and(*conditions):
    if not conditions or any(type(c) is not Truth for c in conditions):
        raise ValueError('Nonempty explicit Truth conditions required')
    if Truth.FALSE in conditions:
        return Truth.FALSE
    if Truth.UNKNOWN in conditions:
        return Truth.UNKNOWN
    return Truth.TRUE


def strictly_positive(value):
    return Truth.UNKNOWN if value is None else (Truth.TRUE if exact_int(value) > 0 else Truth.FALSE)


def nonrecourse(*founder_requirements):
    if not founder_requirements:
        raise ValueError('Explicit founder obligation dimensions required')
    known = [uint(x) for x in founder_requirements if x is not None]
    if any(x > 0 for x in known):
        return Truth.FALSE
    return Truth.UNKNOWN if None in founder_requirements else Truth.TRUE


def first_operation_covered(costs):
    """Every necessary first-operation cost needs its own funded payer."""
    if not costs:
        raise ValueError('Nonempty cost inventory required')
    gates = []
    for cost in costs:
        if cost['amount'] is None:
            gates.append(Truth.UNKNOWN)
        elif uint(cost['amount']) == 0:
            gates.append(Truth.TRUE)
        elif cost['payer'] == 'founder':
            gates.append(Truth.FALSE)
        elif cost['payer'] is None:
            gates.append(Truth.UNKNOWN)
        else:
            gates.append(tri_and(cost['commitment'], cost['nonrecourse']))
    return tri_and(*gates)


def eligible(net_owner, margin_sponsor, sponsor_threshold, founder_state,
             time_state, execution_state):
    sponsor_gate = Truth.UNKNOWN if margin_sponsor is None or sponsor_threshold is None else (
        Truth.TRUE if exact_int(margin_sponsor) >= uint(sponsor_threshold) else Truth.FALSE)
    return tri_and(strictly_positive(net_owner), sponsor_gate, founder_state,
                   time_state, execution_state)


def residual(sale, debt, coinbase, gas_units, gas_price, other_cost):
    inputs = [sale, debt, coinbase, gas_units, gas_price, other_cost]
    if any(v is None for v in inputs):
        return None
    sale, debt, coinbase, gas_units, gas_price, other_cost = map(uint, inputs)
    if gas_units == 0:
        raise ValueError('Positive measured gas units required')
    return sale - debt - coinbase - gas_units * gas_price - other_cost


def gas_frontier(sale, debt, coinbase, gas_units, other_cost):
    if any(v is None for v in [sale, debt, coinbase, gas_units, other_cost]):
        return None
    sale, debt, coinbase, gas_units, other_cost = map(uint, [sale, debt, coinbase, gas_units, other_cost])
    if gas_units == 0:
        raise ValueError('Positive measured gas units required')
    available = sale - debt - coinbase - other_cost
    return None if available <= 0 else (available - 1) // gas_units


def builder_margin(*, A, U, R, V, F, P, O):
    values = [A, U, R, V, F, P, O]
    if any(v is None for v in values):
        return None
    A, U, R, V, F, P, O = map(uint, values)
    if U > A:
        raise ValueError('Returned unused advance cannot exceed advance')
    return R + U + V - A - F - P - O


def owner_margin(*, initial_assets, final_assets, initial_direct_liabilities,
                 final_direct_liabilities, initial_contingent_liabilities,
                 final_contingent_liabilities, capital_added, donations_added,
                 distributions):
    values = [initial_assets, final_assets, initial_direct_liabilities,
              final_direct_liabilities, initial_contingent_liabilities,
              final_contingent_liabilities, capital_added, donations_added,
              distributions]
    if any(v is None for v in values):
        return None
    ia, fa, il, fl, ic, fc, capital, gifts, dist = map(uint, values)
    return (fa - fl - fc) - (ia - il - ic) + dist - capital - gifts


def realizable_usd(token_units, bid_usd_per_token, conversion_cost_usd):
    if any(v is None for v in [token_units, bid_usd_per_token, conversion_cost_usd]):
        return None
    if any(type(v) not in (str, int, Fraction) for v in [token_units, bid_usd_per_token, conversion_cost_usd]):
        raise ValueError('Exact rational valuation required, no floats')
    q, p, cost = map(Fraction, [token_units, bid_usd_per_token, conversion_cost_usd])
    if min(q, p, cost) < 0:
        raise ValueError('Nonnegative valuation inputs required')
    return q * p - cost


def decimal_units_to_raw(value, decimals):
    if type(value) is not str or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',value):
        raise ValueError('Exact decimal unit string required')
    raw = Fraction(value) * 10 ** uint(decimals)
    if raw.denominator != 1:
        raise ValueError('Value exceeds asset precision')
    return raw.numerator


def transfer_deltas(transfers, perimeter, asset):
    """Signed asset delta across a participant boundary; internal flows cancel."""
    seen = set()
    delta = 0
    for flow in transfers:
        if flow['id'] in seen:
            raise ValueError('Duplicate transfer identity')
        seen.add(flow['id'])
        amount = uint(flow['amount'])
        if flow['asset'] != asset:
            continue
        if flow['to'] in perimeter:
            delta += amount
        if flow['from'] in perimeter:
            delta -= amount
    return delta


def coherent_state(block_numbers, block_hashes):
    if not block_numbers or len(block_numbers) != len(block_hashes):
        raise ValueError('Paired state contexts required')
    known_numbers = [uint(x) for x in block_numbers if x is not None]
    known_hashes = [hash32(x) for x in block_hashes if x is not None]
    if len(set(known_numbers)) > 1 or len(set(known_hashes)) > 1:
        return Truth.FALSE
    if None in block_numbers or None in block_hashes:
        return Truth.UNKNOWN
    return Truth.TRUE


def known_positive_coverage(expected_log, returned_logs):
    """Match one known positive control; TRUE is never proof of global coverage."""
    if returned_logs is None:
        return Truth.UNKNOWN
    if type(returned_logs) is not list:
        raise ValueError('List of returned logs required')
    fields = [k for k in ['transactionHash','logIndex','blockHash','blockNumber',
                          'transactionIndex','address','topics','data','removed'] if k in expected_log]
    def project(row):
        out = {}
        for key in fields:
            if key not in row:
                return None
            value = row[key]
            if key in ('transactionHash','blockHash'):
                out[key] = hash32(value)
            elif key in ('logIndex','blockNumber','transactionIndex'):
                out[key] = quantity(value)
            elif key == 'address':
                if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{40}',value):
                    raise ValueError('20-byte log address required')
                out[key] = value.lower()
            elif key == 'topics':
                if type(value) is not list:
                    raise ValueError('Topic list required')
                out[key] = [hash32(x) for x in value]
            elif key == 'data':
                if type(value) is not str or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*',value):
                    raise ValueError('Byte-aligned hexadecimal log data required')
                out[key] = value.lower()
            elif key == 'removed':
                if type(value) is not bool:
                    raise ValueError('Explicit removed boolean required')
                out[key] = value
        return out
    key = lambda row: (hash32(row['transactionHash']), quantity(row['logIndex']))
    key(expected_log)
    expected = project(expected_log)
    seen = set()
    found = False
    for row in returned_logs:
        identity = key(row)
        if identity in seen:
            raise ValueError('Duplicate positive-control log identity')
        seen.add(identity)
        candidate = project(row)
        if candidate == expected:
            found = True
    return Truth.TRUE if found else Truth.FALSE


def nqc_realization(attribution, settlement_verified, complete_net_verified):
    if attribution == 'THIRD_PARTY':
        return Truth.FALSE
    attribution_gate = Truth.TRUE if attribution == 'NQC_VERIFIED' else Truth.UNKNOWN
    return tri_and(attribution_gate, settlement_verified, complete_net_verified)


def required_wins(target, fixed_cost, per_win_margin):
    if any(x is None for x in [target, fixed_cost, per_win_margin]):
        return None
    if any(type(x) not in (int, str, Fraction) for x in [target, fixed_cost, per_win_margin]):
        raise ValueError('Exact amounts required')
    target, fixed_cost, per_win_margin = map(Fraction, [target, fixed_cost, per_win_margin])
    if target < 0 or fixed_cost < 0:
        raise ValueError('Target and fixed cost must be nonnegative')
    if per_win_margin <= 0:
        raise ValueError('Strictly positive margin required; target not reached by this formula')
    ratio = (target + fixed_cost) / per_win_margin
    return (ratio.numerator + ratio.denominator - 1) // ratio.denominator


def load_inputs(path=ROOT / 'evidence/accounting_inputs.json'):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def snapshot(inputs, sid):
    return json.loads(inputs['source_snapshots'][sid]['content_utf8'])


def reconcile_robinhood_reported(inputs):
    """Parse source decimal ETH explicitly; preserves the source's simulation scope."""
    source = inputs['source_snapshots']['robinhood_readme']['content_utf8']
    values = dict(inputs['robinhood'])
    patterns = {'native_network_fee_wei':r'La comisión nativa simulada es\s*\*\*([0-9.]+) ETH\*\*',
                'paymaster_charge_wei':r'el paymaster transfiere\s*\*\*([0-9.]+) ETH\*\*'}
    for key,pattern in patterns.items():
        matches = re.findall(pattern,source)
        decimal = single(matches,key+' decimal ETH source')
        converted = decimal_units_to_raw(decimal,18)
        if uint(values[key]) != converted:
            raise ValueError('Robinhood decimal ETH to wei mismatch: '+key)
        values[key] = converted
    return values


def source_digests(inputs):
    results = {}
    for sid, source in inputs['source_snapshots'].items():
        raw = source['content_utf8'].encode('utf-8')
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        complete = sid != 'rpc_script_excerpt_read_only'
        if complete and actual != source['git_blob_sha']:
            raise ValueError('Git blob content mismatch: ' + sid)
        results[sid] = {'sha256': hashlib.sha256(raw).hexdigest(),
                        'git_blob_sha_computed': actual,
                        'full_blob_identity_checked': complete,
                        'bytes': len(raw)}
    return results


def single(rows, label):
    if len(rows) != 1:
        raise ValueError(f'{label}: exactly one item required, got {len(rows)}')
    return rows[0]


def reconcile_saved_case_b(inputs):
    """Reconcile stored RPC/indexer evidence, without authenticating chain state."""
    case = inputs['case_b']
    env = snapshot(inputs, 'case_b_saved_receipt')
    receipt = env['response']['result']
    block = snapshot(inputs, 'case_b_saved_block')['data']['block_details']
    indexer = snapshot(inputs, 'case_b_indexer')['data']
    trace = snapshot(inputs, 'case_b_saved_trace')['data']['items']
    if env['request']['params'] != [case['tx_hash']] or receipt['transactionHash'] != case['tx_hash']:
        raise ValueError('Receipt transaction identity mismatch')
    if (receipt['blockHash'] != case['block_hash'] or block['hash'] != case['block_hash'] or
        hexint(receipt['blockNumber']) != case['block_number'] or block['height'] != case['block_number'] or
        hexint(receipt['transactionIndex']) != case['tx_index'] or hexint(receipt['status']) != 1):
        raise ValueError('Receipt/block execution context mismatch')
    if block['miner']['hash'].lower() != case['coinbase']:
        raise ValueError('Coinbase identity mismatch')
    seen = set()
    for log in receipt['logs']:
        identity = (log['transactionHash'], log['logIndex'])
        if identity in seen or log['transactionHash'] != case['tx_hash'] or log['blockHash'] != case['block_hash'] or log['removed']:
            raise ValueError('Duplicate, removed or conflicting receipt log')
        seen.add(identity)
    if any(node.get('error') for node in trace):
        raise ValueError('Trace error requires path-aware rollback analysis')
    if trace[0]['action']['from'] != case['sender'] or trace[0]['action']['to'] != case['executor']:
        raise ValueError('Top-level trace actor mismatch')
    topic_addr = lambda value: '0x' + value[-40:].lower()
    ex, weth, morpho = case['executor'], case['weth'], case['morpho']
    native = [n for n in trace if n.get('action', {}).get('callType') == 'call'
              and hexint(n['action']['value']) > 0]
    sale_call = single([n for n in native if n['action']['from'] == case['fluid_liquidity'] and n['action']['to'] == ex], 'native Fluid sale')
    bid_call = single([n for n in native if n['action']['from'] == ex and n['action']['to'] == case['coinbase']], 'native coinbase payment')
    transfer = single([r for r in receipt['logs'] if r['address'] == weth and r['topics'][0] == TRANSFER
                       and topic_addr(r['topics'][1]) == ex and topic_addr(r['topics'][2]) == morpho], 'WETH debt repayment')
    deposit = single([r for r in receipt['logs'] if r['address'] == weth and r['topics'][0] == DEPOSIT
                      and topic_addr(r['topics'][1]) == ex], 'WETH wrapping')
    withdrawal = single([r for r in receipt['logs'] if r['address'] == weth and r['topics'][0] == WITHDRAWAL
                         and topic_addr(r['topics'][1]) == ex], 'WETH unwrapping')
    sale, debt, bid = hexint(sale_call['action']['value']), hexint(transfer['data']), hexint(bid_call['action']['value'])
    if hexint(deposit['data']) != sale or hexint(withdrawal['data']) != bid:
        raise ValueError('ETH/WETH bridge flow mismatch')
    balance_reads = [n for n in trace if n['action'].get('to') == weth and n['action'].get('from') == ex
                     and n['action'].get('input') == '0x70a08231' + '0' * 24 + ex[2:]]
    if not balance_reads:
        raise ValueError('No initial WETH balance observation')
    initial_weth = hexint(balance_reads[0]['result']['output'])
    weth_delta = sale - debt - bid
    native_delta = sum(hexint(n['action']['value']) * ((n['action']['to'] == ex) - (n['action']['from'] == ex)) for n in native)
    collateral_delta = sum(hexint(r['data']) * ((topic_addr(r['topics'][2]) == ex) - (topic_addr(r['topics'][1]) == ex))
                           for r in receipt['logs'] if r['address'] == case['collateral'] and r['topics'][0] == TRANSFER)
    gas_units, gas_price = hexint(receipt['gasUsed']), hexint(receipt['effectiveGasPrice'])
    if (gas_units != uint(indexer['gas_used']) or gas_price != uint(indexer['gas_price']) or
        gas_units * gas_price != uint(indexer['fee']['value'])):
        raise ValueError('Stored RPC/indexer gas mismatch')
    actual = {'sale_wei': sale, 'debt_wei': debt, 'coinbase_wei': bid,
              'gas_units': gas_units, 'gas_price_wei': gas_price, 'initial_weth_wei': initial_weth,
              'final_weth_inferred_wei': initial_weth + weth_delta}
    for key, value in actual.items():
        if value != uint(case[key]):
            raise ValueError('Input amount disagrees with saved evidence: ' + key)
    liquidation = single([r for r in receipt['logs'] if r['address'] == morpho and r['topics'][0] == LIQUIDATION], 'Morpho liquidation')
    return {**actual, 'sender_gas_cost_wei': gas_units * gas_price,
            'executor_weth_delta_wei': weth_delta, 'executor_native_delta_wei': native_delta,
            'executor_collateral_delta_raw': collateral_delta,
            'residual_known_cost_upper_bound_wei': weth_delta - gas_units * gas_price,
            'known_liquidation_log': liquidation,
            'classification': 'REPRODUCIDO_LOCALMENTE_SOBRE_ARTEFACTOS_GUARDADOS',
            'new_rpc_queries': 0, 'onchain_consensus_authenticated': False,
            'runtime_authenticated': False, 'historical_state_replay_run': False,
            'sender_executor_ownership_proved': False, 'nqc_profit_certified': False}


def falsification_controls(inputs, reconciled):
    case = inputs['case_b']
    sale, debt, bid, gas, price = [uint(case[k]) for k in ['sale_wei','debt_wei','coinbase_wei','gas_units','gas_price_wei']]
    frontier = gas_frontier(sale, debt, bid, gas, 0)
    env = snapshot(inputs, 'case_b_saved_getlogs')
    filt = env['request']['params'][0]
    if filt['blockHash'] != case['block_hash'] or filt['address'].lower() != case['morpho'] or filt['topics'][0] != LIQUIDATION:
        raise ValueError('getLogs positive control is not matched to case B')
    r = reconcile_robinhood_reported(inputs); pm, network = uint(r['paymaster_charge_wei']), uint(r['native_network_fee_wei'])
    flows = [{'id':'paymaster_to_bundler','asset':'ETH','from':'paymaster','to':'bundler','amount':pm},
             {'id':'bundler_network_fee','asset':'ETH','from':'bundler','to':'network','amount':network}]
    owner_fixture = dict(initial_assets=0,final_assets=5,initial_direct_liabilities=0,final_direct_liabilities=1,
                         initial_contingent_liabilities=0,final_contingent_liabilities=0,capital_added=0,donations_added=0,distributions=0)
    checks = {
        'T-01': (first_operation_covered([{'name':'principal','amount':0,'payer':None}, {'name':'first_gas','amount':100,'payer':None}]) is Truth.UNKNOWN and nonrecourse(0, None) is Truth.UNKNOWN, 'BLOCKED', 'Zero principal does not fund first gas; payer unknown blocks admission.'),
        'T-02': (nonrecourse(0, 1, 0) is Truth.FALSE, 'BLOCKED', 'An explicit deferred bill rejects zero-capital/nonrecourse admission.'),
        'T-03': (builder_margin(A=100,U=100,R=0,V=0,F=2,P=0,O=0) == -2 and nonrecourse(None) is Truth.UNKNOWN, 'BLOCKED', 'Even full return of isolated top-up leaves funding gas; loss bearer contract unknown.'),
        'T-04': (reconciled['coinbase_wei'] == 368092735714237547 and case['coinbase'] != case['executor'] and nqc_realization('UNKNOWN',Truth.TRUE,Truth.UNKNOWN) is Truth.UNKNOWN, 'PASS', 'Saved-evidence recipient check only. Native recipient equals saved block coinbase; economic builder ownership remains unknown.'),
        'T-05': (frontier == 2481140052 and residual(sale,debt,bid,gas,frontier,0) > 0 and residual(sale,debt,bid,gas,frontier+1,0) <= 0 and residual(sale,debt,bid,gas,3000000000,0) == -386814760229962, 'PASS', 'Fixed saved-input arithmetic only. Strict exact wei boundary; no NQC gas quote.'),
        'T-06': (transfer_deltas(flows,{'paymaster'},'ETH') == -pm and transfer_deltas(flows,{'paymaster','bundler'},'ETH') == -network and transfer_deltas(flows,{'bundler'},'ETH') == pm-network, 'NOT_RUN', 'Consolidation identity checked on source-reported Nitro simulation values; EVM trace not rerun.'),
        'T-07': (coherent_state([26210230,26210231,26210229],[None,None,None]) is Truth.FALSE, 'NOT_RUN', 'Document-reported heterogeneous heights reject coherence; no new prospective observation.'),
        'T-08': (env['http_status'] == 200 and known_positive_coverage(reconciled['known_liquidation_log'],env['response']['result']) is Truth.FALSE, 'PASS', 'Saved conflicting envelopes only. Stored matched getLogs query is empty despite positive saved receipt; global coverage unproved.'),
        'T-09': (owner_margin(**owner_fixture) == 4 and nonrecourse(1) is Truth.FALSE, 'BLOCKED', 'Positive owner margin can coexist with a founder debt; admission still rejected.'),
        'T-10': (nqc_realization('THIRD_PARTY',Truth.TRUE,Truth.TRUE) is Truth.FALSE, 'BLOCKED', 'Third-party liquidation never becomes NQC realized profit without attribution.')}
    return {tid:{'guardrail_status':'PASS' if ok else 'FAIL','guardrail_type':'OFFLINE_ACCOUNTING_OR_DOCUMENTARY',
                 'historical_or_commercial_verification_status':historical,'meaning':meaning,
                 'real_network_test_run':False} for tid,(ok,historical,meaning) in checks.items()}


def build_report(inputs):
    digests = source_digests(inputs)
    case = inputs['case_b']; rec = reconcile_saved_case_b(inputs)
    sale, debt, bid, gas, price = [uint(case[k]) for k in ['sale_wei','debt_wei','coinbase_wei','gas_units','gas_price_wei']]
    boundary = gas_frontier(sale,debt,bid,gas,0)
    known_bound = rec['residual_known_cost_upper_bound_wei']
    points = sorted(set([0,price,10**9,boundary-1,boundary,boundary+1,3*10**9,5*10**9,10*10**9]))
    sensitivity = [{'gas_price_wei_per_gas':p,'residual_before_unknown_costs_wei':residual(sale,debt,bid,gas,p,0)} for p in points]
    comparison = snapshot(inputs,'reported_case_b_results')
    if comparison['incremental_residual_after_known_costs_upper_bound_wei'] != known_bound or comparison['cost_frontier']['max_total_gas_price_wei_for_strict_positive_before_unknown_costs'] != boundary:
        raise ValueError('Independent arithmetic disagrees with reported baseline')
    goals=inputs['monthly_sensitivity']
    monthly=[{'fixed_cost_usd_assumed':f,'per_win_net_margin_usd_assumed':m,'required_wins':{t:required_wins(t,f,m) for t in goals['target_usd']}}
             for f in goals['fixed_cost_usd'] for m in goals['margin_per_win_usd']]
    rh=reconcile_robinhood_reported(inputs); pm=uint(rh['paymaster_charge_wei']); network=uint(rh['native_network_fee_wei'])
    actual_net = residual(sale,debt,bid,gas,price,case['external_obligations_wei'])
    return {'generated_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'INDEPENDENT_OFFLINE_ACCOUNTING_ONLY',
            'source_digests':digests,'case_b_reconciliation':rec,
            'case_b_fixed_route_gas_sensitivity':sensitivity,'max_gas_price_strict_positive_wei_per_gas':boundary,
            'max_additional_cost_for_strict_positive_wei':known_bound-1,
            'additional_cost_exhausting_known_upper_bound_wei':known_bound,
            'after_one_extra_wei_cost_upper_bound_wei':residual(sale,debt,bid,gas,price,1),
            'actual_net_after_unknown_obligations_wei':actual_net,
            'nqc_economic_eligibility':eligible(actual_net,None,0,nonrecourse(None),Truth.UNKNOWN,Truth.UNKNOWN).value,
            'robinhood_consolidation':{'classification':'ARITHMETIC_OF_REPORTED_SIMULATION_NOT_EVM_VERIFICATION',
                  'external_bundler_sponsor_outflow_wei':pm,'consolidated_paymaster_bundler_network_cost_wei':network,
                  'bundler_receipt_minus_network_cost_before_other_obligations_wei':pm-network,
                  'incorrect_double_count_total_wei':pm+network,'usd_realizable_value':None},
            'falsification_controls':falsification_controls(inputs,rec),
            'monthly_target_sensitivity':monthly,'monthly_income_estimate':None,'monthly_capture_rate':None,
            'warnings':['Saved RPC/indexer records are not fresh on-chain queries or state-root proof.',
                        'Zero other cost is used only for a conditional upper bound; actual unknown costs remain null.',
                        'Astra test counts are not our test results; neither original scripts nor EVM tests were run.',
                        'Winning gas price is total effective price, not only priority fee.',
                        'Historical executor and sender cannot be consolidated as one owner without evidence.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=ROOT/'evidence/accounting_inputs.json')
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/accounting_results.json')
    args=parser.parse_args()
    report=build_report(load_inputs(args.inputs))
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Independent saved-evidence accounting completed; no economic admission.')
    print('Guardrails: '+', '.join(f'{k}={v["guardrail_status"]}' for k,v in report['falsification_controls'].items()))
    print('Maximum fixed-route gas price for strict positive upper bound:',report['max_gas_price_strict_positive_wei_per_gas'],'wei/gas')
    print('Actual net after unknown obligations: UNKNOWN. NQC eligibility:',report['nqc_economic_eligibility'])
    return 0 if all(v['guardrail_status']=='PASS' for v in report['falsification_controls'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
