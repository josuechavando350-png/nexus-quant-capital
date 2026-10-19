"""Offline economic boundaries from pinned, already-acquired Morpho observations.

No network. No USD price feed. No authorization or financial admission. Fractions
and integer wei preserve the distinction between exact arithmetic and evidence.
"""
import hashlib
import json
import subprocess
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MORPHO = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
EZETH = '0xbf5495efe5db9ce00f80364c8b423567e58d2110'
EXECUTOR = '0x5ac9bc14376bf2727c6211960cf3cec1e2f295bd'
LIQUIDITY = '0x52aa899454998be5b000ad077a46bbe360f4e497'
POOL = '0xdd72157a021804141817d46d9852a97addfb9f59'
TX = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'
LIQUIDATE_TOPIC = '0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41'
START, END = 1789603200, 1792195200


def require(value, message):
    if not value:
        raise ValueError(message)


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


class Sources:
    def __init__(self):
        self.manifest = parse((HERE / 'SOURCE_MANIFEST.json').read_bytes())
        self.used = set()

    def load(self, name):
        item = self.manifest['files'][name]
        raw = subprocess.check_output(['git', '-C', str(REPO), 'show',
                                       item['commit'] + ':' + item['path']])
        require(hashlib.sha256(raw).hexdigest() == item['sha256'], 'source SHA256 mismatch')
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == item['git_blob_sha1'], 'source Git blob mismatch')
        self.used.add(name)
        return parse(raw)


def events(page):
    require(page['http_status'] == 200 and not page['response'].get('errors'), 'provider error')
    require(page['url'] == 'https://api.morpho.org/graphql', 'unexpected event provider')
    return page['response']['data']['marketTransactions']['items']


def event_map(rows):
    out = {}
    for row in rows:
        row = {**row, 'data':dict(row['data'])}
        require(type(row['chain']['id']) is int and row['chain']['id'] == 1, 'wrong chain')
        require(row['type'] == 'Liquidation' and START <= row['timestamp'] < END, 'wrong event window')
        require(row['data']['__typename'] == 'MarketTransactionLiquidationData', 'wrong event type')
        for key in ('repaidAssets', 'repaidShares', 'seizedAssets', 'badDebtAssets', 'badDebtShares'):
            value = row['data'][key]
            if type(value) is str:
                require(value.isascii() and value.isdigit() and str(int(value)) == value,
                        'canonical integer string required')
                value = int(value)
            require(type(value) is int and value >= 0, 'exact integer amount required')
            row['data'][key] = value
        key = (row['chain']['id'], row['txHash'].lower(), row['logIndex'])
        require(key not in out, 'duplicate event identity')
        out[key] = row
    return out


def ceil(value):
    value = Fraction(value)
    return -(-value.numerator // value.denominator)


def usd_per_capture(target, captures, overhead=0, failed_cost=0):
    require(type(captures) is int and captures > 0, 'positive integer captures required')
    require(all(Fraction(x) >= 0 for x in (target, overhead, failed_cost)), 'negative budget')
    # Rounded upward to cents. Each captured result must already be NET of its
    # debt, venue, gas, bid and financing costs. Add monthly failures/overhead here.
    return str(Fraction(ceil(100 * Fraction(target + overhead + failed_cost, captures)), 100))


def repayment_fee(debt, bps):
    require(type(debt) is int and debt >= 0 and Fraction(bps) >= 0, 'invalid financing terms')
    return ceil(Fraction(debt) * Fraction(bps) / 10000)


def strict_failures_budget(net_per_win, cost_per_failure):
    require(type(cost_per_failure) is int and cost_per_failure > 0, 'positive failure cost')
    return max(0, (net_per_win - 1) // cost_per_failure) if net_per_win > 0 else None


def words(data):
    require(data.startswith('0x') and len(data[2:]) % 64 == 0, 'ABI word length')
    return [int(data[i:i+64], 16) for i in range(2, len(data), 64)]


def audit_case(rows, receipt_wrapper, trace_wrapper, block_wrapper, observation):
    receipt = receipt_wrapper['response']['result']
    block = block_wrapper['data']['block_details']
    require(receipt_wrapper['http_status'] == 200 and receipt['status'] == '0x1', 'unsuccessful receipt')
    require(receipt_wrapper['request']['params'] == [TX] and receipt['transactionHash'] == TX,
            'wrong transaction')
    require(trace_wrapper['request']['chain_id'] == '1' and
            block_wrapper['request']['chain_id'] == '1', 'wrong trace chain')
    require(TX in trace_wrapper['request']['endpoint_path'], 'wrong trace transaction')
    require(receipt['blockHash'] == block['hash'] and int(receipt['blockNumber'],16) == block['height'],
            'block identity conflict')
    require(int(receipt['transactionIndex'],16) == observation['data']['position'] == 1, 'transaction order')
    require(receipt['from'].lower() == observation['data']['from'].lower() and
            receipt['to'].lower() == EXECUTOR, 'executor identity')
    relevant = [r for r in rows if r['txHash'].lower() == TX]
    require(len(relevant) == 1, 'one case B event required')
    event = relevant[0]
    require(event['blockNumber'] == block['height'] and event['txIndex'] == 1, 'census block conflict')
    require(event['market']['loanAsset']['address'].lower() == WETH and
            event['market']['collateralAsset']['address'].lower() == EZETH, 'wrong assets')
    logs = [x for x in receipt['logs'] if x['address'].lower() == MORPHO and x['topics'][0] == LIQUIDATE_TOPIC]
    require(len(logs) == 1, 'liquidation receipt event required')
    log = logs[0]
    require(not log['removed'] and log['transactionHash'] == TX and log['blockHash'] == block['hash'],
            'removed or conflicting event')
    amounts = words(log['data'])
    require(amounts == [event['data'][k] for k in
            ('repaidAssets','repaidShares','seizedAssets','badDebtAssets','badDebtShares')], 'event amount conflict')
    require(log['topics'][1] == event['market']['marketId'] and
            int(log['logIndex'],16) == event['logIndex'], 'market or log conflict')
    require('0x'+log['topics'][2][-40:] == event['data']['liquidator'].lower() == EXECUTOR, 'liquidator conflict')
    trace = trace_wrapper['data']['items']
    require(len({tuple(t['traceAddress']) for t in trace}) == len(trace), 'duplicate trace address')
    require(all(not t.get('error') for t in trace), 'trace failure')
    coinbase = block['miner']['hash'].lower()
    def native(sender, recipient):
        return sum(int(t['action'].get('value','0x0'),16) for t in trace
                   if t['type']=='call' and t['action'].get('callType')=='call'
                   and t['action']['from'].lower()==sender and t['action']['to'].lower()==recipient)
    sale, bid = native(LIQUIDITY, EXECUTOR), native(EXECUTOR, coinbase)
    require(sale > 0 and bid > 0, 'missing value flows')
    swaps = [t for t in trace if t['action'].get('to','').lower()==POOL
             and t['action'].get('input','').startswith('0x2668dfaa')]
    require(len(swaps)==1 and swaps[0]['action']['from'].lower()==EXECUTOR, 'Fluid swap identity')
    require(words('0x'+swaps[0]['action']['input'][10:])[1]==amounts[2] and
            words(swaps[0]['result']['output']) == [sale], 'swap amount conflict')
    transfers = observation['data']['token_transfers']
    def token_flow(token, sender, recipient):
        return sum(int(t['total']['value']) for t in transfers if t['token']['address_hash'].lower()==token
                   and t['from'].lower()==sender and t['to'].lower()==recipient)
    require(token_flow(EZETH,MORPHO,EXECUTOR)==token_flow(EZETH,EXECUTOR,LIQUIDITY)==amounts[2],
            'collateral movement conflict')
    require(token_flow(WETH,EXECUTOR,MORPHO)==amounts[0], 'debt repayment conflict')
    gas_units, gas_price = int(receipt['gasUsed'],16), int(receipt['effectiveGasPrice'],16)
    gas = gas_units*gas_price
    require(gas == int(observation['data']['transaction_burnt_fee']), 'gas accounting conflict')
    debt, collateral = amounts[0], amounts[2]
    gross, residual = sale-debt, sale-debt-bid-gas
    return {
        'classification':'AUTHENTIC_ARCHIVED_OBSERVATIONS_NOT_STATE_AUTHENTICATED_OR_NQC_PNL',
        'chain_id':1, 'protocol':'Morpho Blue', 'morpho':MORPHO, 'tx_hash':TX,
        'block_number':block['height'], 'block_hash':block['hash'], 'tx_index':1,
        'market_id':event['market']['marketId'], 'borrower':'0x'+log['topics'][3][-40:],
        'loan_asset':WETH, 'collateral_asset':EZETH, 'pool':POOL, 'liquidity':LIQUIDITY,
        'external_executor':EXECUTOR, 'gas_payer':receipt['from'], 'coinbase':coinbase,
        'repaid_debt_weth_wei':debt, 'repaid_shares':amounts[1], 'seized_ezeth_wei':collateral,
        'sale_output_eth_wei':sale, 'sale_minus_debt_wei':gross,
        'coinbase_transfer_wei':bid, 'coinbase_fraction_of_sale_minus_debt':str(Fraction(bid,gross)),
        'gas_units':gas_units, 'effective_gas_price_wei':gas_price, 'gas_cost_wei':gas,
        'residual_upper_bound_before_unknown_obligations_wei':residual,
        'strict_positive_additional_financing_fee_limit_wei':residual-1 if residual>0 else None,
        'financing_break_even_bps_on_repaid_debt':str(Fraction(residual*10000,debt)),
        'hypothetical_financing_sweep':[
            {'fee_bps':str(bps),'fee_wei_rounded_up':repayment_fee(debt,bps),
             'residual_before_other_unknown_costs_wei':residual-repayment_fee(debt,bps)}
            for bps in map(Fraction,('0','1/2','1','5','9'))],
        'hypothetical_failed_attempts_at_same_gas_cost_per_one_identical_win':{
            'max_failures_for_strict_positive_before_unknown_costs':strict_failures_budget(residual,gas),
            'assumed_failure_cost_wei':gas, 'measured_failure_rate':None,
            'qualification':'COST SENSITIVITY ONLY; failures may cost differently or not be included'},
        'gas_financing_terms':None, 'external_financing_premium':None, 'historical_eth_usd':None,
        'dex_fee_separately_authenticated':None, 'consolidated_operator_net':None,
        'nqc_captured_net':None, 'live_executable':False, 'commercial_admission':False,
        'missing':['exact prestate before txIndex1 and prior transaction replay',
                   'authenticated Morpho/oracle/IRM/Fluid state and runtime',
                   'ex-ante route quote and executable bid/capture conditions',
                   'upfront gas sponsor commitment and repayment obligations',
                   'external financing liabilities and consolidated account ownership',
                   'historical USD conversion and all ongoing/failure costs'],
    }


def analyze(source=None):
    s = source or Sources()
    forward = event_map(sum((events(s.load(f'page-{i:03}.json')) for i in range(3)), []))
    reverse = event_map(sum((events(s.load(f'reverse-{i:03}.json')) for i in range(2)), []))
    require(forward == reverse, 'forward/reverse event content conflict')
    rows = list(forward.values())
    txs = {r['txHash'].lower() for r in rows}
    case = audit_case(rows, s.load('b-receipt.json'), s.load('case_b_trace.json'),
                      s.load('case_b_block.json'), s.load('case_b.json'))
    control = s.load('b-morpho-logs.json')
    require(control['request']['params'][0]['blockHash'] == case['block_hash'] and
            control['request']['params'][0]['topics'] == [LIQUIDATE_TOPIC] and
            control['request']['params'][0]['address'] == MORPHO, 'control scope conflict')
    require(control['response']['result'] == [], 'known-positive omission changed')
    selection = s.load('receipt-selection.json')['transactions']
    nulls = []
    for i, item in enumerate(selection):
        if item['tx_hash'] == TX:
            continue
        reply = s.load(f'receipt-{i:02}.json')
        require(reply['request']['params'] == [item['tx_hash']], 'receipt selection conflict')
        require(reply['response']['result'] is None, 'receipt availability changed')
        nulls.append(item['tx_hash'])
    liquidators = Counter(r['data']['liquidator'].lower() for r in rows)
    n = len(txs)
    return {
        'schema':'nqc053-economic-boundary-v1', 'network_requests':0,
        'observed_sample':{'chain_id':1,'start_utc':'2026-09-17T00:00:00Z',
            'end_utc_exclusive':'2026-10-17T00:00:00Z','days':30,
            'events':len(rows),'distinct_transactions':n,'markets':len({r['market']['marketId'] for r in rows}),
            'liquidator_addresses':len(liquidators), 'top_address_event_counts':liquidators.most_common(5),
            'bad_debt_events':sum(bool(r['data']['badDebtAssets'] or r['data']['badDebtShares']) for r in rows),
            'diagnostic_receipt_selection':len(selection),'null_receipts':len(nulls),'usable_receipts':1,
            'coverage_status':'KNOWN_POSITIVE_OMISSION_OR_CONFLICT_NOT_COMPLETE_MARKET_CENSUS',
            'independent_profit_opportunities_demonstrated':0,'nqc_capturable_count_demonstrated':0},
        'case_b':case,
        'monthly_required_volume_scenarios':[
            {'net_usd_per_captured_success_ASSUMED':net,'target_net_usd':target,
             'required_successes':ceil(Fraction(target,net)),
             'exceeds_141_observed_transactions_in_this_sample':ceil(Fraction(target,net))>n}
            for net in (50,100,500,1000) for target in (5000,15000,45000)],
        'sample_conditioned_required_net_scenarios':[
            {'captured_transactions_ASSUMED':wins,'fraction_of_observed_transactions':str(Fraction(wins,n)),
             'target_net_usd':target,'minimum_usd_per_capture_rounded_up_cent_fraction':usd_per_capture(target,wins),
             'extra_monthly_overhead_and_failed_attempt_costs_ASSUMED_usd':0}
            for wins in (1,7,14,35,n) for target in (5000,15000,45000)],
        'conditions':['sample is a diagnostic observation, not complete market volume or a future forecast',
                      'capture counts, positive net per success and zero additional overhead are assumptions',
                      'debt principal and token amounts are not USD revenue',
                      'coinbase transfer is not attributed automatically to builder income',
                      'observed sale output already includes venue effects; do not subtract the same effect twice'],
        'monthly_nqc_net_forecast_usd':None, 'commercial_admission':False,
        'sources_verified':sorted(s.used),
    }


if __name__ == '__main__':
    print(json.dumps(analyze(), indent=2, sort_keys=True))
