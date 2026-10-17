"""Offline Fluid receipt/call reconciliation, not a state replay or executable quote."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from evm_hash import keccak256
from historical_rpc_audit import data, load, verify_b_movements
from historical_trace_audit import inspect, trace_tree, uints, EXECUTOR

ROOT = Path(__file__).resolve().parent
REFERENCE_SHA256 = 'f9131605ad37602aae1821d8459b932629c45b1549b5119ef2ef6e7f9797c284'
SWAP_PATH = (0, 1, 3, 3, 1, 0, 1)


def signed(word):
    return word if word < 2**255 else word - 2**256


def address(word):
    if not 0 <= word < 2**160:
        raise ValueError('noncanonical ABI address')
    return '0x' + word.to_bytes(20, 'big').hex()


def signature(name):
    return '0x' + keccak256(name.encode()).hex()


def cost_frontier(sale_minus_debt, coinbase, gas_units, observed_gas_price):
    """Unchanged external route/bid sensitivity, not a gas or sponsor quote."""
    for value in (sale_minus_debt,coinbase,gas_units,observed_gas_price):
        if type(value) is not int or not 0 <= value < 2**256:
            raise ValueError('exact unsigned cost inputs required')
    if gas_units == 0: raise ValueError('positive measured gas required')
    after_bid = sale_minus_debt-coinbase
    residual = after_bid-gas_units*observed_gas_price
    return {'scope':'UNCHANGED_EXTERNAL_ROUTE_AND_COINBASE_BID_ONLY','gas_units_assumption':gas_units,
            'max_total_gas_price_wei_for_strict_positive_before_unknown_costs':
                (after_bid-1)//gas_units if after_bid > 0 else None,
            'additional_cost_that_consumes_all_remaining_residual_wei':max(0,residual),
            'max_additional_cost_wei_for_strict_positive':residual-1 if residual > 0 else None,
            'counterfactual_gas_scenarios':[
                {'gas_price_wei':p,'residual_before_unknown_obligations_wei':after_bid-gas_units*p}
                for p in sorted({observed_gas_price,10**9,3*10**9,5*10**9,10*10**9})],
            'nqc_gas_or_sponsor_estimate':False}


def audit(trace=None, receipt=None):
    raw = (ROOT / 'fixtures/fluid_case_b_reference.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError('reference snapshot changed')
    ref = json.loads(raw)
    original = ROOT / 'evidence/2026-10-17'
    trace = trace if trace is not None else json.loads((original / 'case_b_trace.json').read_text())
    receipt = receipt if receipt is not None else load('b-receipt.json')['response']['result']
    ledger = inspect(trace, json.loads((original / 'case_b_block.json').read_text()),
                     json.loads((original / 'case_b.json').read_text()))
    verify_b_movements(receipt)
    tree = trace_tree(trace)
    pool = ref['address'].lower()
    cfg = ref['constructor_args'][0]
    liquidity, token0, token1 = (cfg[k].lower() for k in ('liquidity', 'token0', 'token1'))
    call = tree[SWAP_PATH]
    action = call['action']
    selector = signature('swapIn(bool,uint256,uint256,address)')[:10]
    if (action['from'].lower(), action['to'].lower(), action['input'][:10], action['callType']) != (
            EXECUTOR, pool, selector, 'call') or int(action['value'], 16):
        raise ValueError('unexpected Fluid swap call')
    direction, amount_in, min_out, to_word = uints('0x' + action['input'][10:], 4)
    recipient = address(to_word) if to_word else EXECUTOR
    amount_out = uints(call['result']['output'], 1)[0]
    if direction != 1 or amount_in != ledger['quote']['seized_assets'] or amount_out != ledger['ledger']['dex_output_after_venue_costs_wei']:
        raise ValueError('swap differs from liquidation ledger')
    swap_logs = [x for x in receipt['logs'] if x['address'].lower() == pool]
    if len(swap_logs) != 1 or swap_logs[0]['topics'] != [signature('Swap(bool,uint256,uint256,address)')]:
        raise ValueError('swap event identity')
    if uints(swap_logs[0]['data'], 4) != [direction, amount_in, amount_out, int(recipient, 16)]:
        raise ValueError('swap event disagrees with call')
    operate_logs = [x for x in receipt['logs'] if x['address'].lower() == liquidity]
    if len(operate_logs) != 2:
        raise ValueError('unexpected Liquidity event count')
    operations = []
    for index, token in ((5, token0), (6, token1)):
        node = tree[SWAP_PATH + (index,)]
        a = node['action']
        if (a['from'].lower(), a['to'].lower(), a['input'][:10], a['callType']) != (
                pool, liquidity, signature('operate(address,int256,int256,address,address,bytes)')[:10], 'call'):
            raise ValueError('unexpected operate call')
        head = uints('0x' + a['input'][10:10 + 6*64], 6)
        if address(head[0]) != token or head[5] != 192:
            raise ValueError('operate token or dynamic offset')
        event = operate_logs[index-5]
        expected_topics = [signature(ref['liquidity_log_operate_signature']),
                           '0x' + int(pool, 16).to_bytes(32, 'big').hex(),
                           '0x' + int(token, 16).to_bytes(32, 'big').hex()]
        words = uints(event['data'], 6)
        if event['topics'] != expected_topics or words[:4] != head[1:5]:
            raise ValueError('operate event disagrees with call')
        operations.append({'token': token, 'supply_amount': signed(words[0]),
                           'borrow_amount': signed(words[1]), 'withdraw_to': address(words[2]),
                           'borrow_to': address(words[3]),
                           'post_operation_packed_totals': words[4],
                           'post_operation_packed_exchange_prices': words[5]})
    if operations[0]['borrow_amount'] or operations[1]['borrow_amount'] or operations[1]['supply_amount'] != -amount_out:
        raise ValueError('observed route is not collateral-only')
    reads = []
    for index in range(1, 5):
        node = tree[SWAP_PATH + (index,)]
        a = node['action']
        if (a['from'].lower(), a['to'].lower(), a['input'][:10], a['callType']) != (
                pool, liquidity, signature('readFromStorage(bytes32)')[:10], 'staticcall'):
            raise ValueError('unexpected Fluid storage read')
        slot = '0x' + data('0x' + a['input'][10:], 32).hex()
        names = [key for key, value in cfg.items() if key.endswith('Slot') and value.lower() == slot]
        if len(names) != 1:
            raise ValueError('storage slot not identified by deployment record')
        reads.append({'slot': slot, 'name': names[0], 'value': uints(node['result']['output'], 1)[0],
                      'temporal_scope': 'inside winning transaction, before its Fluid operate calls'})
    debt = ledger['quote']['repaid_assets']
    coinbase = ledger['coinbase_received_wei']
    gas = ledger['sender_gas_cost_wei']
    oracle_value = Fraction(amount_in * ledger['post_accrual_witness']['oracle_price'], 10**36)
    pre_gas = amount_out - debt
    residual_bound = pre_gas - coinbase - gas
    if residual_bound != ledger['residual_minus_sender_gas_arithmetic_wei']:
        raise ValueError('economic reconciliation')
    return {
        'classification': 'OBSERVED_ROUTE_RECONCILED_NOT_HISTORICAL_REPLAY',
        'reference_commit': ref['commit'], 'pool': pool, 'liquidity_layer': liquidity,
        'token_in': token0, 'token_out': token1, 'swap_in': amount_in, 'swap_out_wei': amount_out,
        'minimum_output_from_original_call': min_out, 'recipient': recipient,
        'operations': operations, 'observed_storage_reads': reads,
        'collateral_transfer_minus_liquidity_supply_credit': amount_in - operations[0]['supply_amount'],
        'gap_qualification': 'Accounting gap consistent with revenue-cut/precision effects in reference source; NOT a separately verified total DEX fee or price impact',
        'oracle_value_wei_fraction': str(oracle_value),
        'oracle_value_minus_sale_wei_fraction': str(oracle_value - amount_out),
        'sale_minus_debt_wei': pre_gas,
        'coinbase_out_wei': coinbase, 'sender_gas_out_wei': gas,
        'incremental_residual_after_known_costs_upper_bound_wei': residual_bound,
        'cost_frontier':cost_frontier(pre_gas,coinbase,int(receipt['gasUsed'],16),
                                     int(receipt['effectiveGasPrice'],16)),
        'upper_bound_scope': 'Observed flows only, before unknown external obligations; not a counterfactual NQC quote',
        'initial_weth_excluded_from_income_wei': ledger['executor_initial_weth_wei'],
        'final_weth_inferred_wei': ledger['executor_final_weth_inferred_wei'],
        'dex_fee_separately_verified': None, 'price_impact_separately_verified': None,
        'sponsor_cost': None, 'historical_runtime_verified': False,
        'pretransaction_state_reconstructed': False, 'nqc_profit_certified': False,
    }


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
    raise SystemExit(2)  # Deliberately pending, never a financial admission.
