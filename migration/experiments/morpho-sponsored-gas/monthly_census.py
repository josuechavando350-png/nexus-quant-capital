"""Offline, exact analysis of a preselected public Morpho liquidation census.

API records are observations, not independent opportunities or NQC revenue.
Unknown receipts, prices, financing and capture remain unknown, never zero costs.
The 7-day window is a subset of the 30-day window and must not be added to it.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import re

from evm_hash import keccak256
from historical_rpc_audit import load as historical_load, quantity, data, TX_B, HASH_B
from morpho_liquidation_math import incentive_factor

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence/2026-10-17-monthly'
MORPHO = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
LIQUIDATE = '0x' + keccak256(b'Liquidate(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)').hex()
AMOUNTS = ('repaidAssets', 'repaidShares', 'seizedAssets', 'badDebtAssets', 'badDebtShares')


def integer(value, maximum=2**256-1):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r'0|[1-9][0-9]*', value):
        number = int(value)
    else:
        raise ValueError('exact nonnegative integer required, not float/bool')
    if not 0 <= number <= maximum:
        raise ValueError('integer outside range')
    return number


def hex_value(value, size):
    data(value, size)
    return value.lower()


def units(amount, decimals):
    amount, decimals = integer(amount), integer(decimals, 255)
    if decimals == 0:
        return str(amount)
    return f'{amount // 10**decimals}.{amount % 10**decimals:0{decimals}d}'


def normalize(row, start, end):
    if row['type'] != 'Liquidation' or integer(row['chain']['id']) != 1:
        raise ValueError('wrong chain or event type')
    ts = integer(row['timestamp'])
    if not start <= ts < end:
        raise ValueError('event outside frozen half-open window')
    if row['data']['__typename'] != 'MarketTransactionLiquidationData':
        raise ValueError('wrong transaction data type')
    market = row['market']
    assets = {}
    for side in ('loanAsset', 'collateralAsset'):
        asset = market[side]
        assets[side] = {'address': hex_value(asset['address'], 20),
                        'decimals': integer(asset['decimals'], 255), 'symbol': asset['symbol']}
    return {'txHash': hex_value(row['txHash'], 32), 'logIndex': integer(row['logIndex']),
            'timestamp': ts, 'blockNumber': integer(row['blockNumber']),
            'txIndex': integer(row['txIndex']), 'marketId': hex_value(market['marketId'], 32),
            'lltv': integer(market['lltv'], 10**18), **assets,
            'liquidator': hex_value(row['data']['liquidator'], 20),
            **{key: integer(row['data'][key]) for key in AMOUNTS}}


def event_key(row):
    return (1, row['txHash'], row['logIndex'])


def unique(rows):
    result = {}
    for row in rows:
        key = event_key(row)
        if key in result:
            raise ValueError('duplicate event: pagination cannot be certified by silently dropping it')
        result[key] = row
    return result


def page(record):
    if record.get('http_status') != 200 or record['response'].get('errors'):
        raise ValueError('unsuccessful census query')
    return record['response']['data']['marketTransactions']


def validate_pages(forward, reverse, seven, selection):
    start, end = selection['start_30d'], selection['end_exclusive']
    if (end-start, end-selection['start_7d'], selection['chain_id'], selection['type'],
            selection['asset_filters'], selection['profit_filters']) != (30*86400, 7*86400, 1, 'Liquidation', None, None):
        raise ValueError('selection changed')
    # Confirm actual requests used exactly the frozen bounds and cursor chaining.
    size = selection['page_size']
    def walk(records, direction):
        all_rows, previous = [], None
        for index, record in enumerate(records):
            query = record['request']['query']
            required = [f'first:{size}', 'chainId_in:[1]', 'type_in:[Liquidation]',
                        f'timestamp_gte:{start}', f'timestamp_lte:{end-1}',
                        'orderBy:Timestamp', f'orderDirection:{direction}']
            if record['url'] != 'https://api.morpho.org/graphql' or any(x not in query for x in required):
                raise ValueError('query differs from selected window/order')
            if index:
                if previous is None:
                    raise ValueError('page after empty cursor')
                cursor = 'cursor:{txHash:"'+previous['txHash']+'",logIndex:'+str(previous['logIndex'])+'}'
                if cursor not in query:
                    raise ValueError('cursor not anchored to previous page')
            elif 'cursor:' in query:
                raise ValueError('initial page has cursor')
            raw = page(record)['items']
            if len(raw) > size:
                raise ValueError('oversized page')
            rows = [normalize(r, start, end) for r in raw]
            all_rows += rows
            previous = raw[-1] if raw else None
        timestamps = [x['timestamp'] for x in all_rows]
        if timestamps != sorted(timestamps, reverse=direction == 'Desc'):
            raise ValueError('timestamp order changed')
        return unique(all_rows)
    asc, desc = walk(forward, 'Asc'), walk(reverse, 'Desc')
    if page(forward[-1])['items']:
        raise ValueError('forward terminal empty page missing')
    if len(page(reverse[-1])['items']) >= size:
        raise ValueError('reverse pagination not exhausted')
    if asc != desc or integer(page(reverse[0])['pageInfo']['countTotal']) != len(asc):
        raise ValueError('directional census or provider count differs')
    sub = {key: r for key, r in asc.items() if r['timestamp'] >= selection['start_7d']}
    q = seven['request']['query']
    if (f'timestamp_gte:{selection["start_7d"]}' not in q or f'timestamp_lte:{end-1}' not in q
            or 'cursor:' in q or 'chainId_in:[1]' not in q or 'type_in:[Liquidation]' not in q):
        raise ValueError('seven-day query differs')
    actual = unique([normalize(r, selection['start_7d'], end) for r in page(seven)['items']])
    if actual != sub or integer(page(seven)['pageInfo']['countTotal']) != len(actual):
        raise ValueError('seven-day independent query differs')
    # Different token decimals or market configuration cannot silently be merged.
    tokens, markets, transactions = {}, {}, {}
    for row in asc.values():
        for side in ('loanAsset', 'collateralAsset'):
            asset = row[side]
            old = tokens.setdefault(asset['address'], asset['decimals'])
            if old != asset['decimals']:
                raise ValueError('inconsistent token decimals')
        config = (row['loanAsset']['address'], row['collateralAsset']['address'], row['lltv'])
        if markets.setdefault(row['marketId'], config) != config:
            raise ValueError('inconsistent immutable market configuration')
        position = (row['blockNumber'], row['txIndex'], row['timestamp'])
        if transactions.setdefault(row['txHash'], position) != position:
            raise ValueError('inconsistent transaction position')
    return sorted(asc.values(), key=lambda r: (r['blockNumber'], r['txIndex'], r['logIndex']))


def receipt_check(receipt, rows):
    unique(rows)
    if not rows or len({r['txHash'] for r in rows}) != 1:
        raise ValueError('exactly one transaction per receipt accounting')
    if receipt is None:
        return {'status': 'UNAVAILABLE', 'gas_wei_per_transaction': None,
                'net_profit': None, 'events_checked': 0}
    tx = rows[0]['txHash']
    if (receipt['transactionHash'].lower() != tx or quantity(receipt['status']) != 1 or
            quantity(receipt['blockNumber']) != rows[0]['blockNumber'] or
            quantity(receipt['transactionIndex']) != rows[0]['txIndex']):
        raise ValueError('receipt transaction differs from census')
    actual = {}
    for log in receipt['logs']:
        if log['address'].lower() != MORPHO or not log['topics'] or log['topics'][0] != LIQUIDATE:
            continue
        if (log.get('removed', False) or log['transactionHash'].lower() != tx or
                log['blockHash'] != receipt['blockHash'] or
                quantity(log['blockNumber']) != rows[0]['blockNumber'] or
                quantity(log['transactionIndex']) != rows[0]['txIndex'] or len(log['topics']) != 4):
            raise ValueError('invalid liquidation log identity')
        words = data(log['data'], 160)
        values = tuple(int.from_bytes(words[i:i+32], 'big') for i in range(0, 160, 32))
        index = quantity(log['logIndex'])
        if index in actual:
            raise ValueError('duplicate receipt log')
        actual[index] = (hex_value(log['topics'][1], 32),
                         '0x' + data(log['topics'][2], 32)[12:].hex(), values)
    expected = {r['logIndex']: (r['marketId'], r['liquidator'], tuple(r[k] for k in AMOUNTS)) for r in rows}
    if actual != expected:
        raise ValueError('API liquidation amounts or membership disagree with receipt')
    return {'status': 'RPC_API_EVENT_CROSSCHECK', 'events_checked': len(rows),
            'gas_used': quantity(receipt['gasUsed']),
            'effective_gas_price_wei': quantity(receipt['effectiveGasPrice']),
            'gas_wei_per_transaction': quantity(receipt['gasUsed']) * quantity(receipt['effectiveGasPrice']),
            'net_profit': None, 'receipt_trie_verified': False}


def log_coverage_check(record, receipt):
    request = record['request']
    if (request['method'] != 'eth_getLogs' or request['params'] != [
            {'blockHash': HASH_B, 'address': MORPHO, 'topics': [LIQUIDATE]}]):
        raise ValueError('known-positive coverage request changed')
    if record.get('http_status') != 200 or 'result' not in record['response']:
        return {'status': 'ACCESS_UNAVAILABLE', 'usable_for_complete_census': False}
    expected = [x for x in receipt['logs'] if x['address'].lower() == MORPHO and x['topics'][0] == LIQUIDATE]
    if not expected:
        raise ValueError('control receipt lacks known-positive event')
    same = record['response']['result'] == expected
    return {'status': 'KNOWN_POSITIVE_MATCH' if same else 'KNOWN_POSITIVE_OMISSION_OR_CONFLICT',
            'receipt_events': len(expected), 'get_logs_events': len(record['response']['result']),
            # Even one positive control would not establish whole-window completeness.
            'usable_for_complete_census': False}


def summarize(rows, days, start):
    debt_groups = defaultdict(list)
    daily = {datetime.fromtimestamp(start+i*86400, timezone.utc).date().isoformat(): 0 for i in range(days)}
    for row in rows:
        debt_groups[row['loanAsset']['address']].append(row)
        daily[datetime.fromtimestamp(row['timestamp'], timezone.utc).date().isoformat()] += 1
    assets = []
    for addr, group in sorted(debt_groups.items()):
        token = group[0]['loanAsset']; repayments = [r['repaidAssets'] for r in group]
        total, bad = sum(repayments), sum(r['badDebtAssets'] for r in group)
        assets.append({**token, 'events': len(group), 'repaid_units': total,
                       'repaid_tokens_exact': units(total, token['decimals']),
                       'smallest_repayment_tokens': units(min(repayments), token['decimals']),
                       'largest_repayment_tokens': units(max(repayments), token['decimals']),
                       'bad_debt_units': bad, 'historical_usd_value': None})
    senders = Counter(r['liquidator'] for r in rows)
    txs = Counter(r['txHash'] for r in rows)
    return {'days': days, 'observed_events': len(rows), 'observed_transactions': len(txs),
            'observed_markets': len({r['marketId'] for r in rows}),
            'observed_liquidator_addresses': len(senders),
            'liquidator_event_counts': dict(senders.most_common()),
            'events_per_day_fraction': str(Fraction(len(rows), days)),
            'daily_api_event_counts': daily,
            'multi_event_transactions': {tx: n for tx, n in txs.items() if n > 1},
            'debt_assets': assets, 'weth_debt_events': sum(r['loanAsset']['address'] == WETH for r in rows),
            'other_debt_events_need_separate_gas_asset_conversion': sum(r['loanAsset']['address'] != WETH for r in rows),
            'bad_debt_events': sum(r['badDebtAssets'] > 0 or r['badDebtShares'] > 0 for r in rows),
            'zero_seizure_events': sum(r['seizedAssets'] == 0 for r in rows),
            'same_debt_collateral_events_rejected_by_current_executor': sum(
                r['loanAsset']['address'] == r['collateralAsset']['address'] for r in rows),
            'theoretical_incentive_factors_wad': sorted({incentive_factor(r['lltv']) for r in rows}),
            'nqc_technically_eligible_count': None, 'nqc_plausibly_winnable_count': None,
            'positive_authentic_nqc_replays': 0, 'capture_probability': None}


def required_wins(target_cents, net_per_win_cents, fixed_cost_cents=0):
    target_cents, net_per_win_cents, fixed_cost_cents = map(integer, (target_cents, net_per_win_cents, fixed_cost_cents))
    if net_per_win_cents == 0:
        raise ValueError('positive net margin required')
    total = target_cents + fixed_cost_cents
    return (total + net_per_win_cents - 1) // net_per_win_cents


def audit(directory=EVIDENCE):
    def read(name):
        return json.loads((directory / name).read_text())
    selection = read('selection.json')
    rows = validate_pages([read(f'page-{n:03}.json') for n in range(3)],
                          [read(f'reverse-{n:03}.json') for n in range(2)], read('seven-day.json'), selection)
    by_tx = defaultdict(list)
    for row in rows:
        by_tx[row['txHash']].append(row)
    b_receipt = historical_load('b-receipt.json')['response']['result']
    receipts = {}
    for i, chosen in enumerate(read('receipt-selection.json')['transactions']):
        tx = chosen['tx_hash']
        path = directory / f'receipt-{i:02}.json'
        if tx == TX_B:
            receipt = b_receipt
        elif not path.exists():
            receipts[tx] = {'status': 'UNRUN', 'net_profit': None}
            continue
        else:
            record = read(path.name)
            if record['request'] != {'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getTransactionReceipt', 'params': [tx]}:
                raise ValueError('receipt request identity')
            if record.get('http_status') != 200 or 'result' not in record.get('response', {}):
                receipts[tx] = {'status': 'ACCESS_ERROR', 'net_profit': None}
                continue
            receipt = record['response']['result']
        receipts[tx] = receipt_check(receipt, by_tx[tx])
    seven = [r for r in rows if r['timestamp'] >= selection['start_7d']]
    return {'classification': 'OBSERVED_CENSUS_MONTHLY_PROFIT_NOT_ESTIMABLE',
            'selection': selection,
            'coverage': {'forward_reverse_match': True, 'provider_count_match': True,
                         'independent_seven_day_query_match': True, 'independent_chain_population_verified': False,
                         'get_logs_control': log_coverage_check(read('b-morpho-logs.json'), b_receipt)},
            'windows': {'30d': summarize(rows, 30, selection['start_30d']),
                        '7d': summarize(seven, 7, selection['start_7d'])},
            'diagnostic_receipts': receipts,
            'receipt_status_counts': dict(Counter(r['status'] for r in receipts.values())),
            'income_categories': {
                'A_realized_nqc_certified_profit_usd': '0',
                'B_authentic_historical_nqc_replays': 0,
                'C_conditional_sensitivity_only': True,
                'D_monthly_profit_expectation_usd': None},
            'target_sensitivity': {
                'unit': 'net USD per captured transaction AFTER all variable obligations',
                'fixed_monthly_cost_usd_assumption': '0 (lower requirement bound, not measured production cost)',
                'capture_probability': None,
                'required_captured_transactions': [
                    {'target_usd': goal, 'assumed_net_per_win_usd': margin,
                     'wins_required': required_wins(goal*100, margin*100)}
                    for goal in (1000, 5000, 10000, 50000) for margin in (10, 50, 100, 500)]},
            'economic_admitted_operations': 0,
            'limitations': ['Events can share a transaction, gas and competing state; not independent opportunities',
                            'Liquidator addresses are not identities, losing bids or capture probabilities',
                            'No contemporary USD prices substituted for historical executable conversion',
                            'Gas, deployment, financing, failed-attempt and recurring costs remain unmeasured for NQC',
                            'WETH debt is only a conversion simplification, not established compatibility',
                            'The two historical windows overlap; do not sum their counts']}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
    raise SystemExit(2)  # Missing economics cannot be promoted by a successful census.
