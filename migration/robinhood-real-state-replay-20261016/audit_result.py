#!/usr/bin/env python3
"""Reconcile captured Nitro simulations, real token flow and native fee movements."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

from local_replay import HERE, log_identity, load_capture
sys.path.insert(0, str(HERE.parent / 'robinhood-nitro-replay-20261016'))
from fee_accounting import route

EP = '0x0000000071727de22e5e9d8baf0edac6f37da032'
ARBSYS = '0x0000000000000000000000000000000000000064'
USEROP = '0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f'
EP_SHA = '674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def result(path):
    message = json.loads(path.read_text())
    require('error' not in message and 'result' in message, 'unsuccessful RPC response')
    return message['result']


def ordered_logs(trace):
    logs = []
    def walk(frame, reverted=False):
        reverted = reverted or bool(frame.get('error'))
        if reverted:
            return
        children = frame.get('calls', [])
        own = frame.get('logs', [])
        positions = [int(log['position'], 16) for log in own]
        require(positions == sorted(positions) and all(0 <= p <= len(children) for p in positions),
                'invalid call-frame log position')
        for i in range(len(children) + 1):
            logs.extend(log for log, position in zip(own, positions) if position == i)
            if i < len(children):
                walk(children[i], reverted)
    walk(trace)
    if any('index' in log for log in logs):
        require(all('index' in log for log in logs), 'mixed indexed and unindexed logs')
        indices = [int(log['index'], 16) for log in logs]
        require(len(indices) == len(set(indices)) and indices == sorted(indices), 'trace log index order mismatch')
    return logs


def flatten(trace):
    yield trace
    for child in trace.get('calls', []):
        yield from flatten(child)


def native_fee(trace):
    before, after = trace['beforeEVMTransfers'], trace['afterEVMTransfers']
    paid = sum(int(item['value'], 16) for item in before if item['purpose'] == 'feePayment')
    refunded = sum(int(item['value'], 16) for item in after if item['purpose'] == 'gasRefund')
    collected = sum(int(item['value'], 16) for item in after if item['purpose'] == 'feeCollection')
    require(0 < collected == paid - refunded, 'native fee accounting mismatch')
    return {'upfront_native_fee_wei': paid, 'native_gas_refund_wei': refunded,
            'network_fee_wei': collected, 'network_fee_eth': str(Decimal(collected) / Decimal(10**18)),
            'gas_used': int(trace['gasUsed'], 16),
            'fee_collections': [item for item in after if item['purpose'] == 'feeCollection']}


def operation(trace, expected_success):
    logs = ordered_logs(trace)
    events = [x for x in logs if x['address'].lower() == EP and x['topics'][0] == USEROP]
    require(len(events) == 1 and not trace.get('error'), 'missing operation or reverted bundle')
    nonce, success, cost, gas = route.words(events[0]['data'], 4)
    require(nonce == 0 and bool(success) is expected_success and cost > 0 and gas > 0, 'unexpected UserOperation result')
    fee = native_fee(trace)
    fee.update(userop_success=bool(success), sponsor_charge_wei=cost,
               sponsor_charge_eth=str(Decimal(cost) / Decimal(10**18)),
               userop_billed_gas=gas, userop_effective_price_wei=cost // gas)
    require(cost % gas == 0, 'nonintegral UserOperation gas price')
    return fee, logs


def validate_overrides(data):
    addresses = data['addresses']
    expected = set(addresses.values()) | {EP, data['transaction']['from']}
    require(set(data['state_overrides']) == expected, 'unexpected overridden account')
    require(not {route.MORPHO, route.WSNET, route.SNET, route.NET, route.STAKING, route.USDG, route.POOL} & expected,
            'historical protocol account overridden')
    require(ARBSYS not in expected, 'native ArbSys replaced')
    eoa = data['state_overrides'][data['transaction']['from']]
    require(eoa == {'balance': hex(10**16), 'code': '0x', 'nonce': '0x0'}, 'bundler fixture context differs')
    require(int(data['state_overrides'][EP]['balance'], 16) == 10**17, 'prefunded EntryPoint context differs')


def audit(evidence):
    tx, receipt, header, historical_trace, original_state, _ = load_capture(evidence / 'provider-capture')
    # Authenticate the original evidence against the previous pinned receipt audit.
    route.audit(HERE.parent / 'robinhood-route-admission-20261016/evidence')
    require([log_identity(x) for x in ordered_logs(historical_trace)] ==
            [log_identity(x) for x in receipt['logs']], 'historical ordered logs differ')
    indexed = result(evidence / 'nitro-phase1/01-historical-direct-at-index.json')
    require(indexed['gasUsed'] == historical_trace['gasUsed'] and
            indexed['output'] == historical_trace['output'] and
            [log_identity(x) for x in ordered_logs(indexed)] == [log_identity(x) for x in receipt['logs']],
            'txIndex calibration differs from historical execution')
    for phase in sorted(evidence.glob('nitro-phase*')):
        for record in json.loads((phase / 'requests.json').read_text()):
            if 'response_file' in record:
                require(hashlib.sha256((phase / record['response_file']).read_bytes()).hexdigest() == record['response_sha256'],
                        'RPC response digest mismatch')
    ep = result(evidence / 'nitro-phase1/02-entrypoint-at-parent.json')
    require(hashlib.sha256(bytes.fromhex(ep[2:])).hexdigest() == EP_SHA, 'historical EntryPoint runtime mismatch')
    data = json.loads((evidence / 'final-simulation-input.json').read_text())
    validate_overrides(data)
    records = json.loads((evidence / 'nitro-phase5/requests.json').read_text())
    for record in records[:3]:
        params = record['request']['params']
        require(params[0] == data['transaction'] and params[1] == header['hash'] and
                params[2]['txIndex'] == '0x1' and params[2]['stateOverrides'] == data['state_overrides'],
                'simulation context mismatch')
    success = result(evidence / 'nitro-phase5/01-nqc-plain-eoa-success.json')
    prior = result(evidence / 'nitro-phase5/04-nqc-plain-eoa-parent.json')
    prestate = result(evidence / 'nitro-phase5/02-nqc-plain-eoa-prestate.json')
    diff = result(evidence / 'nitro-phase5/03-nqc-plain-eoa-state-diff.json')
    fee, logs = operation(success, True)
    failure, failure_logs = operation(prior, False)
    require(all(not frame.get('error') for frame in flatten(success)), 'nested error in success')
    require(any(bytes.fromhex(frame.get('output', '0x')[2:]).find(b'position is healthy') >= 0
                for frame in flatten(prior)), 'parent failure reason differs')
    require(not any(log['address'].lower() == route.MORPHO for log in failure_logs), 'failed liquidation emitted protocol logs')
    clock = [f for f in flatten(success) if f.get('to', '').lower() == ARBSYS and f.get('input') == '0xa3b1b31d']
    require(len(clock) == 1 and int(clock[0]['output'], 16) == int(header['number'], 16), 'native L2 clock mismatch')
    local_receipt = json.loads((evidence / 'nqc-local/success-receipt.json').read_text())
    protocol = lambda rows: [log_identity(x) for x in rows if x['address'].lower() != EP]
    require(protocol(logs) == protocol(local_receipt['logs']), 'local/Nitro protocol ordered logs differ')
    account = data['addresses']['account']
    executor = data['addresses']['executor']
    router = data['addresses']['router']
    flow = []
    for log in logs:
        if log['topics'][0] == route.TRANSFER and log['address'].lower() in {route.USDG, route.NET, route.WSNET, route.SNET}:
            flow.append((log['address'].lower(), route.address_topic(log['topics'][1]),
                         route.address_topic(log['topics'][2]), route.words(log['data'], 1)[0]))
    delta = lambda token, owner: sum(n * ((dest == owner) - (src == owner)) for t, src, dest, n in flow if t == token)
    surplus = delta(route.USDG, account)
    require(surplus == 32060665, 'USDG account surplus differs')
    for owner in [executor, router]:
        for token in [route.USDG, route.WSNET, route.SNET, route.NET]:
            require(delta(token, owner) == 0, 'stranded route asset')
    require(sum(n for t, src, dest, n in flow if (t, src, dest) == (route.NET, router, route.COLLECTOR)) == 15442822,
            'NET tax differs')
    require(sum(n for t, src, dest, n in flow if (t, src, dest) == (route.USDG, executor, route.MORPHO)) == 194034131,
            'Morpho repayment differs')
    # Native storage-diff balances corroborate trace fees and sponsor payment.
    balance = lambda part, address: int(diff[part][address].get('balance', '0x0'), 16)
    payer = data['transaction']['from'].lower()
    beneficiary = '0x000000000000000000000000000000000000beef'
    require(balance('pre', payer) - balance('post', payer) == fee['network_fee_wei'], 'gas payer balance mismatch')
    require(balance('pre', EP) - balance('post', EP) == fee['sponsor_charge_wei'], 'EntryPoint cash mismatch')
    require(balance('post', beneficiary) - balance('pre', beneficiary) == fee['sponsor_charge_wei'], 'beneficiary cash mismatch')
    local_pre = json.loads((evidence / 'nqc-local/nqc-local-prestate.json').read_text())
    compared = 0
    for address, state in local_pre.items():
        if address in data['state_overrides'] or address == ARBSYS:
            continue
        if not state.get('code') or state['code'] == '0x':
            continue
        require(address in prestate and state['code'] == prestate[address]['code'], 'protocol runtime differs')
        for slot, value in state.get('storage', {}).items():
            require(slot in prestate[address].get('storage', {}) and
                    int(value, 16) == int(prestate[address]['storage'][slot], 16), 'protocol state differs')
            compared += 1
    l1 = []
    for filename in ['03-nqc-l1-parent.json', '04-nqc-l1-selected-end.json']:
        gas, base, parent_price = route.words(result(evidence / 'nitro-phase3' / filename), 3)
        require(gas == 0 and parent_price == 0 and base > 0, 'historical L1 estimator changed')
        l1.append({'source': filename, 'l1_gas_in_l2_units': gas, 'base_fee_wei': base,
                   'l1_base_fee_estimate_wei': parent_price})
    final = result(evidence / 'nitro-phase5/05-canonical-final.json')
    for key in ['hash', 'number', 'parentHash', 'timestamp', 'stateRoot', 'transactionsRoot']:
        require(final[key] == header[key], 'final historical header changed')
    require(fee['network_fee_wei'] == fee['gas_used'] * int(header['baseFeePerGas'], 16), 'native base fee reconciliation')
    return {'status': 'NQC_NITRO_HISTORICAL_COUNTERFACTUAL_SUCCESS',
            'historical_transaction': tx['hash'], 'historical_block': int(header['number'], 16),
            'transaction_index': 1, 'source_state_at_tx_index_calibrated': True,
            'original_local_replay': json.loads((evidence / 'historical-local/report.json').read_text()),
            'nqc_success': fee, 'nqc_parent_failure': failure, 'surplus_before_gas_usdg': str(Decimal(surplus) / Decimal(10**6)),
            'surplus_before_gas_usdg_raw': surplus, 'native_l2_clock_verified': True,
            'matched_local_nitro_protocol_logs': len(protocol(logs)),
            'local_protocol_read_slots_confirmed_by_nitro': compared,
            'net_tax_raw': 15442822, 'nodeinterface_l1_estimates': l1,
            'combined_nodeinterface_estimate_available': False,
            'network_fee_source': 'Nitro feePayment minus gasRefund equals sum feeCollection; includes native fees',
            'sponsor_charge_is_transfer_to_bundler_not_additional_network_fee': True,
            'hypothetical_prefunded_entrypoint_wei': 10**17, 'hypothetical_bundler_native_balance_wei': 10**16,
            'state_cryptographic_proofs_verified': False, 'production_bundler_admission_proven': False,
            'deployment_cost_included': False, 'future_gas_and_da_guaranteed': False,
            'external_sponsor_committed': False, 'live_transaction_submitted': False, 'realized_nqc_revenue': False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    report = audit(HERE / 'evidence')
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'surplus_before_gas_usdg', 'local_protocol_read_slots_confirmed_by_nitro',
                                            'nqc_success', 'nqc_parent_failure']}, indent=2))


if __name__ == '__main__':
    main()
