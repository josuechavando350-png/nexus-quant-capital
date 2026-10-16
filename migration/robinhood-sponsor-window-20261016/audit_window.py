#!/usr/bin/env python3
"""Offline audit of fixed historical Nitro responses and loopback receipts."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'robinhood-real-state-replay-20261016'
PRIOR = HERE.parent / 'robinhood-opportunity-economics-20261016'
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(PRIOR))
from audit_result import EP, ARBSYS, USEROP, require, result, flatten, ordered_logs, native_fee, operation, validate_overrides, route
from local_replay import log_identity, load_capture
from prepare_fee_variant import unpack_handle_ops, limits
from admission_window import compare

BENEFICIARY = '0x000000000000000000000000000000000000beef'
ARBOS_STORAGE = '0xa4b05fffffffffffffffffffffffffffffffffff'
VALIDATE = '0x52b7512c'
POST_OP = '0x7c627b21'
BUDGET_SLOT = '0x' + (1).to_bytes(32, 'big').hex()


def read(path):
    return json.loads(path.read_text())


def protocol_logs(logs):
    return [log_identity(x) for x in logs if x['address'].lower() != EP]


def validate_fixture(data, original):
    validate_overrides(data)
    require(data['transaction'] == original['transaction'] and data['addresses'] == original['addresses'],
            'operation or fixture addresses changed')
    pm = data['addresses']['paymaster']
    for address, value in original['state_overrides'].items():
        if address != pm:
            require(data['state_overrides'][address] == value, 'non-paymaster fixture changed')
    window = data['window_fixture']
    override = data['state_overrides'][pm]
    require(set(override) == {'code', 'state'}, 'unexpected paymaster override fields')
    require(hashlib.sha256(bytes.fromhex(override['code'][2:])).hexdigest() == window['runtime_sha256'],
            'runtime digest mismatch')
    fields, _ = unpack_handle_ops(data['transaction']['data'])
    cap = limits(fields)['required_prefund_wei']
    expected_state = {'0x' + '00' * 32: '0x' + (0xcafe).to_bytes(32, 'big').hex(),
                      BUDGET_SLOT: '0x' + cap.to_bytes(32, 'big').hex()}
    require(override['state'] == expected_state and cap == window['budget_wei'], 'constructor budget differs')
    compare(window['valid_after'], window['valid_until'], window['valid_after'])
    return pm, window, cap


def check_validation(trace, data):
    pm, window = data['addresses']['paymaster'], data['window_fixture']
    calls = [f for f in flatten(trace) if f.get('to', '').lower() == pm]
    require(not any(f.get('input', '').startswith(POST_OP) for f in calls), 'postOp unexpectedly called')
    validations = [f for f in calls if f.get('input', '').startswith(VALIDATE)]
    require(len(validations) == 1, 'expected exactly one paymaster validation')
    frame = validations[0]
    require(frame.get('from', '').lower() == EP and not frame.get('error'), 'paymaster validation failed')
    raw = bytes.fromhex(frame['input'][2:])
    require('0x' + raw[36:68].hex() == window['approved_userop_hash'] and
            int.from_bytes(raw[68:100], 'big') == window['budget_wei'], 'validation hash or prefund differs')
    output = bytes.fromhex(frame['output'][2:])
    require(len(output) == 96 and int.from_bytes(output[:32], 'big') == 64 and
            int.from_bytes(output[64:], 'big') == 0, 'expected empty paymaster context')
    packed = int.from_bytes(output[32:64], 'big')
    expected = (window['valid_until'] << 160) | (window['valid_after'] << 208)
    require(packed == expected, 'returned validation window differs')


def check_expired(trace, data):
    require(bool(trace.get('error')) and b'AA32 paymaster expired or not due' in
            bytes.fromhex(trace.get('output', '0x')[2:]), 'expected root AA32 rejection')
    require(not ordered_logs(trace), 'rejected bundle has committed logs')
    blocked = {data['addresses']['router'], data['addresses']['executor'], route.MORPHO, route.POOL}
    require(not any(f.get('to', '').lower() in blocked for f in flatten(trace)), 'route executed after time rejection')
    check_validation(trace, data)
    fee = native_fee(trace)
    return dict(fee, bundle_success=False, userop_success=None, sponsor_charge_wei=0, surplus_usdg_raw=0)


def verify_diff(diff, data, fee, success):
    payer, pm = data['transaction']['from'], data['addresses']['paymaster']
    bal = lambda part, address: int(diff[part][address].get('balance', '0x0'), 16)
    require(bal('pre', payer) - bal('post', payer) == fee['network_fee_wei'], 'bundler native fee delta differs')
    if success:
        require(bal('pre', EP) - bal('post', EP) == fee['sponsor_charge_wei'], 'EntryPoint balance delta differs')
        require(bal('post', BENEFICIARY) - bal('pre', BENEFICIARY) == fee['sponsor_charge_wei'], 'beneficiary delta differs')
        before = int(diff['pre'][pm]['storage'][BUDGET_SLOT], 16)
        after = int(diff['post'][pm].get('storage', {}).get(BUDGET_SLOT, '0x0'), 16)
        require(before == data['window_fixture']['budget_wei'] and after == 0, 'full prefund not consumed from budget')
    else:
        # A reverted root may still charge the gas payer and the native fee system.
        # This provider's diff records ArbOS gas-accounting storage, while native
        # fee-recipient transfers are reported separately by callTracer.
        require((set(diff['pre']) | set(diff['post'])) == {payer, ARBOS_STORAGE},
                'expired bundle changed sponsorship or protocol state')


def authenticate_requests(folder, plan, data, header):
    records = read(folder / 'requests.json')
    require(len(records) == len(plan), 'incomplete capture')
    outputs = {}
    for index, (record, expected) in enumerate(zip(records, plan), 1):
        request = {'jsonrpc': '2.0', 'id': index, 'method': expected['method'], 'params': expected['params']}
        require(record['request'] == request and record['label'] == expected['label'], 'request context differs')
        path = folder / record['response_file']
        require(hashlib.sha256(path.read_bytes()).hexdigest() == record['response_sha256'], 'RPC response digest mismatch')
        envelope = read(path)
        require(envelope.get('id') == index and envelope.get('jsonrpc') == '2.0', 'RPC envelope differs')
        outputs[record['label']] = result(path)
        if expected['method'] == 'debug_traceCall':
            tx, block, config = expected['params']
            require(tx == data['transaction'] and block == {'blockHash': header['hash'], 'requireCanonical': True},
                    'historical block or operation differs')
            require(config.get('txIndex') == '0x1' and config.get('stateOverrides') == data['state_overrides'] and
                    config.get('reexec') == 0 and config.get('timeout') == '10s', 'trace fixture context differs')
            label = record['label']
            is_diff = label.endswith('state-diff')
            require(config.get('tracer') == ('prestateTracer' if is_diff else 'callTracer') and
                    config.get('tracerConfig') == ({'diffMode': True} if is_diff else {'withLog': True}), 'unexpected tracer')
            when = {'not-due': data['window_fixture']['valid_after'] - 1,
                    'valid-until': data['window_fixture']['valid_until'],
                    'expired': data['window_fixture']['valid_until'] + 1,
                    'expired-state-diff': data['window_fixture']['valid_until'] + 1}.get(label)
            expected_block_override = {'time': hex(when)} if when is not None else None
            require(config.get('blockOverrides') == expected_block_override, 'unexpected block override')
    final = outputs['canonical-final']
    for key in ['hash', 'number', 'parentHash', 'timestamp', 'stateRoot', 'transactionsRoot']:
        require(final[key] == header[key], 'canonical historical header differs')
    return outputs


def audit_variant(evidence, local_name, nitro_name, header, original):
    local = evidence / local_name
    data = read(local / 'simulation-input.json')
    pm, window, cap = validate_fixture(data, original)
    full_plan = read(local / 'nitro-plan.json')
    plan = full_plan if nitro_name == 'nitro' else read(evidence / 'nitro-31-plan.json')
    if nitro_name != 'nitro':
        labels = {'valid-after', 'expired', 'valid-state-diff', 'expired-state-diff', 'canonical-final'}
        require(plan == [p for p in full_plan if p['label'] in labels], '31 second subset plan differs')
    captures = authenticate_requests(evidence / nitro_name, plan, data, header)
    results = {}
    for label in ['not-due', 'valid-after', 'valid-until', 'expired']:
        if label not in captures:
            continue
        trace = captures[label]
        if label in {'not-due', 'expired'}:
            results[label] = check_expired(trace, data)
        else:
            fee, logs = operation(trace, True)
            require(all(not f.get('error') for f in flatten(trace)), 'nested error in successful route')
            check_validation(trace, data)
            receipt = read(local / (label.replace('-', '_') + '-receipt.json'))
            require(protocol_logs(logs) == protocol_logs(receipt['logs']), 'local/Nitro protocol logs differ')
            flow = [x for x in logs if x['address'].lower() == route.USDG and x['topics'][0] == route.TRANSFER]
            account = data['addresses']['account']
            surplus = sum(route.words(x['data'], 1)[0] *
                ((route.address_topic(x['topics'][2]) == account) - (route.address_topic(x['topics'][1]) == account)) for x in flow)
            if label == 'valid-after':
                require(surplus == 32060665, 'historical same-state surplus differs')
            self_calls = [f for f in flatten(trace) if f.get('from', '').lower() == EP and
                          f.get('to', '').lower() == EP and f.get('input', '').startswith('0x0042dc53')]
            require(len(self_calls) == 1, 'expected EntryPoint innerHandleOp')
            info = route.words('0x' + self_calls[0]['input'][10:10 + 16 * 64], 16)
            require(info[12] == cap, 'EntryPoint prefund differs')
            op_fields, _ = unpack_handle_ops(data['transaction']['data'])
            gas_limits = limits(op_fields)['gas_limits']
            preop_limit = sum(gas_limits[k] for k in ['verification', 'paymaster_verification', 'pre_verification'])
            execution = [f for f in flatten(trace) if f.get('from', '').lower() == EP and
                         f.get('to', '').lower() == account and f.get('input', '').startswith('0x1cff79cd')]
            require(len(execution) == 1, 'expected account execution frame')
            call_gas = int(execution[0]['gasUsed'], 16)
            gas_comparison = {'preop_gas': info[14], 'preop_limit': preop_limit,
                              'preop_efficiency': str(Decimal(info[14]) / preop_limit),
                              'account_call_gas': call_gas, 'call_limit': gas_limits['call'],
                              'call_efficiency': str(Decimal(call_gas) / gas_limits['call']),
                              'historical_trace_ratios_both_at_least_15_percent':
                                  info[14] * 100 >= preop_limit * 15 and call_gas * 100 >= gas_limits['call'] * 15,
                              'provider_simulation_executed': False}
            clock = [f for f in flatten(trace) if f.get('to', '').lower() == ARBSYS and f.get('input') == '0xa3b1b31d']
            require(len(clock) == 1 and int(clock[0]['output'], 16) == int(header['number'], 16), 'native L2 clock differs')
            results[label] = dict(fee, bundle_success=True, surplus_usdg_raw=surplus,
                                  protocol_log_count=len(protocol_logs(logs)), gas_efficiency_comparison=gas_comparison)
        require(results[label]['network_fee_wei'] == results[label]['gas_used'] * int(header['baseFeePerGas'], 16),
                'native Nitro fee/base-fee reconciliation differs')
    verify_diff(captures['valid-state-diff'], data, results['valid-after'], True)
    verify_diff(captures['expired-state-diff'], data, results['expired'], False)
    local_report = read(local / 'report.json')
    require(local_report['window'] == window and not local_report['local_is_nitro'], 'local report scope differs')
    late = next(x for x in local_report['records'] if x['case'] == 'l2_execution_expired')
    late_receipt = read(local / 'l2_execution_expired-receipt.json')
    events = [x for x in late_receipt['logs'] if x['address'].lower() == EP and x['topics'][0] == USEROP]
    require(int(late_receipt['status'], 16) == 1 and len(events) == 1, 'expected successful bundle for failed UserOp')
    _, success, cost, billed = route.words(events[0]['data'], 4)
    require(success == 0 and cost == late['sponsor_charge_wei'] > 0 and billed == late['billed_gas'] and
            late['surplus_usdg_raw'] == 0 and late['budget_after_wei'] == 0, 'execution-expiry loss differs')
    samples = sorted({window['valid_after'] - 1, window['valid_after'], window['valid_until'] - 20,
                      window['valid_until'] - 19, window['valid_until'], window['valid_until'] + 1})
    return {'window_seconds': window['valid_until'] - window['valid_after'], 'window': window,
            'nitro': results, 'local_l2_expiry_only': late,
            'admission_time_samples': [{'timestamp': n, **compare(window['valid_after'], window['valid_until'], n)} for n in samples],
            'full_prefund_reserved_wei': cap, 'rpc_calls': len(plan)}


def audit(evidence):
    _, _, header, _, _, _ = load_capture(OLD / 'evidence/provider-capture')
    original = read(PRIOR / 'evidence/fee-variant/simulation-input.json')
    original_hash = read(PRIOR / 'evidence/fee-variant/report.json')['variant_userop_hash']
    short = audit_variant(evidence, 'local', 'nitro', header, original)
    long = audit_variant(evidence, 'local-31', 'nitro-31', header, original)
    require(short['window_seconds'] == 1 and long['window_seconds'] == 31, 'window comparison differs')
    require(short['window']['approved_userop_hash'] == long['window']['approved_userop_hash'] == original_hash,
            'preapproved operation changed')
    require(short['nitro']['valid-after'] == long['nitro']['valid-after'], 'long window changed same-state economics')
    lock = read(evidence / 'verification/final-window-source-lock.json')
    for filename, sha in lock['sources'].items():
        require(hashlib.sha256((HERE / filename).read_bytes()).hexdigest() == sha, 'built Solidity source differs')
    repro = read(evidence / 'verification/short-runtime-reproduction.json')
    require(all(repro['final_source_reproduces_initial_short_window'].values()) and
            repro['runtime_sha256'] == short['window']['runtime_sha256'], 'short variant not reproduced from final source')
    return {'status': 'HISTORICAL_WINDOW_AND_BUDGET_VERIFIED', 'historical_block': int(header['number'], 16),
            'historical_block_hash': header['hash'], 'historical_timestamp': int(header['timestamp'], 16),
            'historical_transaction_index': 1, 'variants': [short, long],
            'new_read_only_rpc_calls': short['rpc_calls'] + long['rpc_calls'],
            'net_surplus_before_costs_usdg': str(Decimal(long['nitro']['valid-after']['surplus_usdg_raw']) / 10**6),
            'sponsor_charge_is_internal_reimbursement_not_additional_network_fee': True,
            'native_fee_includes_captured_arbos_fee_movements': True,
            'separate_da_component_remeasured_for_this_variant': False,
            'deployment_and_stake_cost_included': False, 'future_da_price_guaranteed': False,
            'production_bundler_admission_proven': False, 'rundler_binary_executed': False,
            'external_sponsor_funding_committed': False, 'prospective_capture_rate_measured': False,
            'live_transaction_submitted': False, 'realized_nqc_revenue': False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    report = audit(HERE / 'evidence')
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'new_read_only_rpc_calls', 'net_surplus_before_costs_usdg']}, indent=2))


if __name__ == '__main__':
    main()
