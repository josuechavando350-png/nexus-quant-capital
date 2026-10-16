#!/usr/bin/env python3
"""Offline transfer reconciliation and one historical arithmetic replay; never trades."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
MORPHO = '0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010'
MARKET = '0xaa586d26a6fe62d9c0f0948fede6e2130500ac7a655587447e2d4a37e6330589'
USDG = '0x5fc5360d0400a0fd4f2af552add042d716f1d168'
WSNET = '0x63c12667638f2ae6fc6ae09b43d98ec84a8586ea'
SNET = '0xb773ec2c326b7f98a5a83fc098825492f020a4c7'
NET = '0xca9c78dd337a67f6e0077f65f5e9218719d30edf'
STAKING = '0xb078cc304a0b264c5f3680dc0488954accd02e87'
COLLECTOR = '0x086c58400b8708ef993f256e12e752dcf0ac918e'
POOL = '0x59f95461e68e0c77605299791e1449f175165b54'
ZERO = '0x' + '0' * 40
SELECTED = '0xf9e0d2e116d99e2eb8ef2cf236f7cd7f06225e92a6dfd9162f98c7d8e1974842'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
LIQUIDATE = '0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41'
# keccak256('Swap(address,uint256,uint256,uint256,uint256,address)')
SWAP = '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822'
SYNC = '0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def data_hex(value, size=None):
    require(isinstance(value, str) and re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', value), 'invalid hex data')
    require(size is None or len(value) == 2 + 2 * size, 'wrong data size')
    return value.lower()


def number(value):
    require(isinstance(value, str) and re.fullmatch(r'0x[0-9a-fA-F]+', value), 'invalid quantity')
    return int(value, 16)


def address_topic(value):
    value = data_hex(value, 32)
    require(value[2:26] == '0' * 24, 'noncanonical address topic')
    return '0x' + value[-40:]


def words(value, count):
    value = data_hex(value, 32 * count)
    return [int(value[i:i + 64], 16) for i in range(2, len(value), 64)]


def validate_receipt(receipt, requested_tx):
    require(data_hex(receipt['transactionHash'], 32) == data_hex(requested_tx, 32), 'receipt identity')
    require(number(receipt['status']) == 1, 'unsuccessful receipt')
    data_hex(receipt['blockHash'], 32)
    data_hex(receipt['from'], 20)
    data_hex(receipt['to'], 20)
    require(number(receipt['gasUsed']) > 0 and number(receipt['effectiveGasPrice']) > 0, 'gas missing')
    previous = -1
    for log in receipt['logs']:
        for key in ['transactionHash', 'blockHash', 'blockNumber', 'transactionIndex']:
            require(log[key].lower() == receipt[key].lower(), 'log/receipt identity mismatch')
        require(log['removed'] is False, 'removed log')
        index = number(log['logIndex'])
        require(index > previous, 'duplicate or unordered log index')
        previous = index
        data_hex(log['address'], 20)
        data_hex(log['data'])
        require(len(log['topics']) <= 4, 'invalid topic count')
        for topic in log['topics']:
            data_hex(topic, 32)


def transfers(receipt):
    result = []
    for log in receipt['logs']:
        if log['topics'] and log['topics'][0].lower() == TRANSFER:
            # The four assets in this study are ERC-20. Do not silently decode NFTs.
            if log['address'].lower() not in {USDG, WSNET, SNET, NET}:
                continue
            require(len(log['topics']) == 3, 'ERC20 transfer topic count')
            result.append({'token': log['address'].lower(), 'from': address_topic(log['topics'][1]),
                           'to': address_topic(log['topics'][2]), 'amount': words(log['data'], 1)[0],
                           'log_index': number(log['logIndex'])})
    return result


def events(receipt, emitter, topic):
    return [l for l in receipt['logs'] if l['address'].lower() == emitter
            and l['topics'] and l['topics'][0].lower() == topic]


def analyze_case(receipt):
    liquidation = events(receipt, MORPHO, LIQUIDATE)
    require(len(liquidation) == 1, 'need exactly one Morpho liquidation')
    event = liquidation[0]
    require(len(event['topics']) == 4 and event['topics'][1].lower() == MARKET, 'wrong liquidation market')
    caller = address_topic(event['topics'][2])
    repay, shares, seized, bad_assets, bad_shares = words(event['data'], 5)
    flow = transfers(receipt)
    usd = [t for t in flow if t['token'] == USDG]
    incoming = sum(t['amount'] for t in usd if t['to'] == caller)
    outgoing = sum(t['amount'] for t in usd if t['from'] == caller)
    morpho_paid = sum(t['amount'] for t in usd if t['from'] == caller and t['to'] == MORPHO)
    pool_paid = sum(t['amount'] for t in usd if t['from'] == POOL and t['to'] == caller)
    collateral_received = sum(t['amount'] for t in flow if t['token'] == WSNET and t['from'] == MORPHO and t['to'] == caller)
    simple = (incoming > 0 and incoming == pool_paid and morpho_paid == repay and
              collateral_received == seized and bad_assets == 0 and bad_shares == 0 and
              len(events(receipt, POOL, SWAP)) == 1 and incoming >= repay)
    classification = ('single_main_pool_usdg_exit' if simple else
                      'no_usdg_inflow_inventory_required' if incoming == 0 else 'other_or_complex_usdg_flow')
    return {'tx': receipt['transactionHash'], 'block': number(receipt['blockNumber']),
            'caller': caller, 'gas_payer': receipt['from'].lower(), 'repaid_usdg_raw': repay,
            'seized_wsnet_raw': seized, 'bad_debt_usdg_raw': bad_assets,
            'gas_used': number(receipt['gasUsed']), 'gas_price_wei': number(receipt['effectiveGasPrice']),
            'gas_fee_wei': number(receipt['gasUsed']) * number(receipt['effectiveGasPrice']),
            'usdg_in_raw': incoming, 'usdg_out_raw': outgoing, 'usdg_net_transfer_change_raw': incoming - outgoing,
            'usdg_paid_to_morpho_raw': morpho_paid,
            'usdg_forwarded_to_gas_payer_raw': sum(t['amount'] for t in usd if t['from'] == caller and t['to'] == receipt['from'].lower()),
            'classification': classification,
            'usdg_exit_less_repay_raw': incoming - repay if simple else None,
            'is_nqc_revenue': False, 'transfers': flow}


def v2_out(amount, reserve_in, reserve_out):
    require(all(type(v) is int and v > 0 for v in [amount, reserve_in, reserve_out]), 'invalid quote inputs')
    weighted = amount * 997
    return weighted * reserve_out // (reserve_in * 1000 + weighted)


def replay_selected(receipt, explorer, reserves, market):
    case = analyze_case(receipt)
    require(case['tx'] == SELECTED and case['block'] == 66744162, 'selected case identity')
    require(explorer['block_number'] == case['block'] and explorer['from'].lower() == case['gas_payer']
            and explorer['to'].lower() == receipt['to'].lower(), 'independent transaction mismatch')
    require(int(explorer['gas_used']) == case['gas_used'] and int(explorer['fee']['value']) == case['gas_fee_wei']
            and int(explorer['gas_price']) == case['gas_price_wei'], 'independent fee mismatch')
    require(explorer['token_transfers_overflow'] is False, 'incomplete explorer transfers')
    explorer_flow = [{'token': t['token']['address_hash'].lower(), 'from': t['from'].lower(),
                     'to': t['to'].lower(), 'amount': int(t['total']['value']), 'log_index': t['log_index']}
                    for t in explorer['token_transfers']]
    require(sorted(explorer_flow, key=lambda x: x['log_index']) == case['transfers'], 'independent transfer mismatch')
    require([v.lower() if isinstance(v, str) else v for v in market] == [USDG, WSNET,
            '0xcde9599059f8ae6d6b9f33a0af7877827ec75f16', '0x2bd3d5965b26b51814ac95127b2b80dd6ccc0fa1',
            625000000000000000], 'market state mismatch')
    caller = case['caller']

    def one(token, source, dest):
        rows = [t for t in case['transfers'] if (t['token'], t['from'], t['to']) == (token, source, dest)]
        require(len(rows) == 1, 'ambiguous route leg')
        return rows[0]

    legs = [one(WSNET, MORPHO, caller), one(WSNET, caller, ZERO), one(SNET, WSNET, caller),
            one(SNET, caller, STAKING), one(NET, STAKING, caller), one(NET, caller, COLLECTOR),
            one(NET, caller, POOL), one(USDG, POOL, caller), one(USDG, caller, MORPHO),
            one(USDG, caller, case['gas_payer'])]
    require([v['log_index'] for v in legs] == sorted(v['log_index'] for v in legs), 'route ordering')
    amounts = [v['amount'] for v in legs]
    require(amounts[0] == amounts[1] == case['seized_wsnet_raw'], 'collateral burn mismatch')
    require(amounts[2] == amounts[3] == amounts[4], 'unstake conversion mismatch')
    gross_net, tax, pair_input, proceeds = amounts[4:8]
    require(tax == gross_net * 500 // 10000 and gross_net == tax + pair_input, 'tax reconciliation')
    require(amounts[8] == case['repaid_usdg_raw'] and proceeds == amounts[8] + amounts[9], 'USDG conservation')
    swaps, syncs = events(receipt, POOL, SWAP), events(receipt, POOL, SYNC)
    require(len(swaps) == len(syncs) == 1, 'ambiguous pool events')
    require(words(swaps[0]['data'], 4) == [0, pair_input, proceeds, 0], 'pool swap mismatch')
    post_usdg, post_net = words(syncs[0]['data'], 2)
    pre_usdg, pre_net, timestamp = reserves
    require(pre_usdg == post_usdg + proceeds and pre_net == post_net - pair_input, 'prior-block reserves mismatch')
    require(v2_out(pair_input, pre_net, pre_usdg) == proceeds, 'v2 arithmetic mismatch')
    no_tax_quote = v2_out(gross_net, pre_net, pre_usdg)
    return {'tx': SELECTED, 'historical_block': case['block'], 'reserves_block': case['block'] - 1,
            'all_ten_transfers_match_independent_explorer': True, 'legs': legs,
            'pre_reserves_usdg_net': [pre_usdg, pre_net], 'pre_reserves_last_update': timestamp,
            'net_tax_bps_observed': 500, 'v2_fee_numerator_consistent_with_receipt': 997,
            'v2_fee_denominator': 1000, 'quoted_usdg_raw': proceeds,
            'counterfactual_no_tax_usdg_raw': no_tax_quote,
            'overstatement_if_tax_omitted_usdg_raw': no_tax_quote - proceeds,
            'surplus_before_native_gas_usdg_raw': amounts[9], 'gas_fee_wei': case['gas_fee_wei'],
            'gas_used_for_l1_reported': number(receipt['gasUsedForL1']),
            'historical_eth_usdg_conversion': None, 'net_profit_usdg': None,
            'full_calldata_available': not explorer['raw_input_truncated'],
            'live_quote': False, 'full_evm_replay': False, 'bundler_admission_proven': False,
            'nqc_execution_or_revenue': False}


def audit(evidence):
    historical = evidence / 'historical-receipts'
    expected = {'rpc_original_receipts.json': 'be33cda6e32cc0cc6401a693e1818058b2abea324c73f959973f58b0cdf89f98',
                'report.json': 'd3aa7a5da665d17e55acaf2a1303843e9471325fddb4484f3607951bb1ed4b20'}
    for name, digest in expected.items():
        require(hashlib.sha256((historical / name).read_bytes()).hexdigest() == digest, 'archived bytes changed')
    rows = json.loads((historical / 'rpc_original_receipts.json').read_text())
    require(len(rows) == 23 and rows[0]['request']['method'] == 'eth_chainId' and number(rows[0]['result']) == 4663, 'chain or record count')
    cases, receipts = [], {}
    for row in rows[1:]:
        require(row['request']['method'] == 'eth_getTransactionReceipt' and len(row['request']['params']) == 1, 'unexpected RPC request')
        tx = row['request']['params'][0].lower()
        require(tx not in receipts, 'duplicate transaction')
        validate_receipt(row['result'], tx)
        receipts[tx] = row['result']
        cases.append(analyze_case(row['result']))
    explorer = evidence / 'explorer'
    get = lambda name: json.loads((explorer / name).read_text())['data']
    replay = replay_selected(receipts[SELECTED], get('transaction.json'),
                             get('pool_at_66744161.json')['result'], get('market_at_66744162.json')['result'])
    return {'chain_id': 4663, 'receipt_count': len(cases), 'classification_counts': dict(Counter(c['classification'] for c in cases)),
            'selection': '12 systematic + 6 size-enriched outside top3 + 4 size-enriched top3; not a random population sample',
            'aggregate_profit': None, 'nqc_revenue_proven': False, 'selected_replay': replay, 'cases': cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, default=HERE / 'evidence')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.evidence)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'cases', 'selected_replay'}}, indent=2))


if __name__ == '__main__':
    main()
