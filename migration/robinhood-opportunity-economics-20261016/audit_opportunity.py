#!/usr/bin/env python3
"""Offline audit of timing, capital commitments and conditional economics."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'robinhood-real-state-replay-20261016'
sys.path.insert(0, str(PREVIOUS))
from audit_result import (EP, ARBSYS, USEROP, audit as previous_audit, flatten, operation,
                          ordered_logs, require, result, route)
from local_replay import log_identity
from economics import D, evaluate, stringify, required_prefund
from prepare_fee_variant import unpack_handle_ops, limits

ORACLE = '0xcde9599059f8ae6d6b9f33a0af7877827ec75f16'


def transfer_delta(logs, token, account):
    total = 0
    for log in logs:
        if log['address'].lower() == token and log['topics'][0] == route.TRANSFER:
            src, dst = map(route.address_topic, log['topics'][1:3])
            total += route.words(log['data'], 1)[0] * ((dst == account) - (src == account))
    return total


def summarize(trace, success, account):
    fee, logs = operation(trace, success)
    prices = [int(n['output'], 16) for n in flatten(trace) if n.get('to', '').lower() == ORACLE]
    require(len(prices) == 1, 'expected one oracle observation')
    return {**{k: v for k, v in fee.items() if k != 'fee_collections'},
            'oracle_price_raw': prices[0], 'surplus_usdg_raw': transfer_delta(logs, route.USDG, account)}


def audit(evidence=HERE / 'evidence'):
    baseline = previous_audit(PREVIOUS / 'evidence')
    source = json.loads((PREVIOUS / 'evidence/final-simulation-input.json').read_text())
    header = result(PREVIOUS / 'evidence/provider-capture/05-block.json')
    parent = result(PREVIOUS / 'evidence/provider-capture/06-parent.json')
    require(header['parentHash'] == parent['hash'], 'parent identity mismatch')
    parent_time = int(parent['timestamp'], 16)
    count = 0
    for folder in ['timing-phase1', 'timing-phase2', 'fee-variant-nitro', 'position-reads']:
        for rec in json.loads((evidence / folder / 'requests.json').read_text()):
            require(hashlib.sha256((evidence / folder / rec['response_file']).read_bytes()).hexdigest() == rec['response_sha256'], 'capture hash mismatch')
            req = rec['request']
            require(req['method'] in {'debug_traceCall', 'eth_getBlockByHash', 'eth_call'}, 'unexpected remote method')
            if req['method'] == 'debug_traceCall':
                config = req['params'][2]
                require(config['stateOverrides'] == source['state_overrides'], 'fixture or protocol state changed')
                require(config['timeout'] == '10s' and config['reexec'] == 0, 'unbounded trace')
                block = req['params'][1]
                require(block in [{'blockHash': header['hash'], 'requireCanonical': True},
                                  {'blockHash': parent['hash'], 'requireCanonical': True}], 'unanchored block')
                if folder == 'fee-variant-nitro':
                    variant = json.loads((evidence / 'fee-variant/simulation-input.json').read_text())
                    require(req['params'][0] == variant['transaction'] and config.get('txIndex') == '0x1', 'fee experiment mismatch')
                else:
                    require(req['params'][0] == source['transaction'] and 'txIndex' not in config, 'timing experiment changed the operation or state position')
                    time = config.get('blockOverrides')
                    expected_times = {'nqc-parent-time-plus-one': 1, 'nqc-parent-time-plus-2': 2,
                                      'nqc-parent-time-plus-4': 4, 'parent-time-plus-one-prestate': 1}
                    if rec['label'] in expected_times:
                        require(time == {'time': hex(parent_time + expected_times[rec['label']])} and
                                block['blockHash'] == parent['hash'], 'projection must use parent state and only change time')
                    else:
                        require(rec['label'] == 'nqc-selected-end' and time is None and block['blockHash'] == header['hash'], 'unexpected timing case')
            count += 1
    account = source['addresses']['account']
    snapshots = {
        'parent_end': (PREVIOUS / 'evidence/nitro-phase5/04-nqc-plain-eoa-parent.json', False),
        'parent_time_plus_1': (evidence / 'timing-phase1/03-nqc-parent-time-plus-one.json', True),
        'parent_time_plus_2': (evidence / 'timing-phase2/01-nqc-parent-time-plus-2.json', True),
        'parent_time_plus_4': (evidence / 'timing-phase2/02-nqc-parent-time-plus-4.json', True),
        'actual_pre_liquidation': (PREVIOUS / 'evidence/nitro-phase5/01-nqc-plain-eoa-success.json', True),
        'actual_block_end': (evidence / 'timing-phase1/02-nqc-selected-end.json', False)}
    timing = {name: summarize(result(path), success, account) for name, (path, success) in snapshots.items()}
    require(timing['parent_time_plus_1']['surplus_usdg_raw'] == timing['actual_pre_liquidation']['surplus_usdg_raw'] == 32060665, 'projected surplus differs')
    protocol = lambda trace: [log_identity(x) for x in ordered_logs(trace) if x['address'].lower() != EP]
    require(protocol(result(snapshots['parent_time_plus_1'][0])) == protocol(result(snapshots['actual_pre_liquidation'][0])), 'time-only projection protocol logs differ')
    before = route.words(result(evidence / 'position-reads/01-position-parent.json'), 3)
    after = route.words(result(evidence / 'position-reads/02-position-selected-end.json'), 3)
    require(before[1] > 0 and before[2] > 0 and after[1] == 0 and
            before[2] - after[2] == 93436250743843184, 'borrower debt or seized collateral differs')
    full = result(evidence / 'timing-phase1/01-selected-full-block.json')
    require(full['hash'] == header['hash'] and [x['hash'] for x in full['transactions']] == header['transactions'], 'transaction list mismatch')
    first, second = full['transactions'][:2]
    require(first['type'] == '0x6a' and first['from'] == first['to'] == '0x00000000000000000000000000000000000a4b05', 'unexpected first system transaction')
    require(second['hash'] == baseline['historical_transaction'], 'liquidation ordering differs')
    final = result(evidence / 'timing-phase2/04-canonical-final.json')
    require(all(final[k] == header[k] for k in ['hash', 'stateRoot', 'transactionsRoot', 'number', 'timestamp']), 'canonical historical block changed')
    pre = result(evidence / 'timing-phase2/03-parent-time-plus-one-prestate.json')
    actual_pre = result(PREVIOUS / 'evidence/nitro-phase5/02-nqc-plain-eoa-prestate.json')
    compared = 0
    for addr, item in actual_pre.items():
        if addr in source['state_overrides'] or addr == ARBSYS or not item.get('code') or item['code'] == '0x':
            continue
        require(pre[addr].get('code') == item['code'], 'projection protocol runtime mismatch')
        for slot, value in item.get('storage', {}).items():
            require(pre[addr].get('storage', {}).get(slot) == value, 'projection protocol read differs')
            compared += 1
    fields, _ = unpack_handle_ops(source['transaction']['data'])
    original_limits = limits(fields)
    variant_input = json.loads((evidence / 'fee-variant/simulation-input.json').read_text())
    variant_fields, beneficiary = unpack_handle_ops(variant_input['transaction']['data'])
    require(variant_input['state_overrides'] == source['state_overrides'], 'fee variant funding changed')
    require(all(fields[i] == variant_fields[i] for i in range(9) if i not in {6, 8}), 'fee variant changed operation execution')
    require({k:v for k,v in variant_input['transaction'].items() if k != 'data'} ==
            {k:v for k,v in source['transaction'].items() if k != 'data'}, 'outer transaction fields changed')
    variant_limits = limits(variant_fields)
    require(variant_limits['priority_fee_wei'] == original_limits['priority_fee_wei'] and
            variant_limits['max_fee_wei'] == (int(header['baseFeePerGas'], 16) * 3 + 1) // 2 + original_limits['priority_fee_wei'], 'unexpected fee cap')
    vtrace = result(evidence / 'fee-variant-nitro/01-lower-fee-cap-at-index.json')
    vfee = summarize(vtrace, True, account)
    require(protocol(vtrace) == protocol(result(snapshots['actual_pre_liquidation'][0])), 'fee variant protocol result differs')
    require(vfee['sponsor_charge_wei'] == timing['actual_pre_liquidation']['sponsor_charge_wei'], 'fee-cap variant charge differs')
    self_call = next(n for n in flatten(vtrace) if n.get('from', '').lower() == EP and n.get('to', '').lower() == EP and n.get('input', '').startswith('0x0042dc53'))
    words = route.words('0x' + self_call['input'][10:10+16*64], 16)
    require(words[12] == variant_limits['required_prefund_wei'], 'EntryPoint actual prefund differs')
    preop = words[14]
    pm_call = next(n for n in flatten(vtrace) if n.get('input', '').startswith('0x52b7512c'))
    validation = int(pm_call['output'][66:130], 16)
    require(validation == 0, 'fixture validation no longer has unlimited time validity')
    for limit in [original_limits, variant_limits]:
        require(required_prefund(limit['gas_limits'], limit['max_fee_wei']) == limit['required_prefund_wei'], 'prefund arithmetic differs')
    assumptions = dict(eth_usdg='3000', surplus_haircut_bps=1000, provider_markup_bps=0,
                       rpc_per_attempt_usdg='0.02', fixed_period_usdg='250',
                       deployment_period_usdg='25', capital_period_usdg='2', attempts=1000)
    success_fee = baseline['nqc_success']['sponsor_charge_wei']
    failure_fee = max(x['sponsor_charge_wei'] for x in timing.values() if not x['userop_success'])
    economic = {p: evaluate('32.060665', success_fee, failure_fee, capture_probability=p, **assumptions)
                for p in ['0', '0.01', '0.05', '0.10']}
    risk_cases = {}
    for name, cost in [('observed_failures', failure_fee), ('original_full_prefund_loss', original_limits['required_prefund_wei']),
                       ('variant_full_prefund_loss', variant_limits['required_prefund_wei'])]:
        risk_cases[name] = evaluate('32.060665', success_fee, cost, capture_probability='0.05', **assumptions)
    risk_cases['8_percent_markup_sensitivity_not_provider_quote'] = evaluate('32.060665', success_fee, failure_fee,
        capture_probability='0.05', **{**assumptions, 'provider_markup_bps': 800})
    sponsor_shares = {str(share): evaluate('32.060665', success_fee, failure_fee,
        capture_probability='0.05', revenue_share_bps=share, **assumptions) for share in [0, 2500, 5000]}
    sample_dir = HERE.parent / 'robinhood-route-admission-20261016/evidence'
    sample = json.loads((sample_dir / 'route-report.json').read_text())
    receipts = {x['result']['transactionHash']: x['result'] for x in
                json.loads((sample_dir / 'historical-receipts/rpc_original_receipts.json').read_text())
                if isinstance(x.get('result'), dict)}
    selected = [{'transaction': c['tx'], 'block': c['block'],
                 'transaction_index': int(receipts[c['tx']]['transactionIndex'], 16),
                 'third_party_surplus_usdg_raw': c['usdg_exit_less_repay_raw']}
                for c in sample['cases'] if c['classification'] == 'single_main_pool_usdg_exit']
    data = {'status': 'TIME_PROJECTION_AND_CAPITAL_HYPOTHESIS_NOT_CAPTURE_PROOF',
            'new_read_only_requests': count, 'historical_block': int(header['number'], 16),
            'historical_sample_count': 1, 'candidate_and_size_selected_with_hindsight': True,
            'time_only_projection_protocol_read_slots_match': compared,
            'position_parent': dict(zip(['supply_shares', 'borrow_shares', 'collateral'], before)),
            'position_block_end': dict(zip(['supply_shares', 'borrow_shares', 'collateral'], after)),
            'first_transaction_is_system_type_106': True,
            'liquidation_is_first_non_system_transaction': True,
            'timestamp_step_seconds': int(header['timestamp'], 16)-parent_time,
            'timestamp_step_is_not_measured_latency': True, 'timing': timing,
            'previous_selected_sample': {'same_route_cases': selected,
                'at_transaction_index_one': sum(x['transaction_index'] == 1 for x in selected),
                'selection_is_not_random': True, 'universe_frequency_inferred': False,
                'other_blocks_system_transaction_not_fetched': True},
            'fee_cap_experiment': {'original': original_limits, 'variant': variant_limits,
                'variant_nitro': vfee, 'preop_gas': preop,
                'preop_efficiency': D(preop)/sum(variant_limits['gas_limits'][k] for k in ['verification','paymaster_verification','pre_verification']),
                'required_prefund_reduction_percent': 100*(1-D(variant_limits['required_prefund_wei'])/original_limits['required_prefund_wei']),
                'fixture_validation_data': validation,
                'full_bundler_admission_proven': False},
            'economics_assumptions_not_quotes': assumptions,
            'economics_external_bundler_own_paymaster': economic,
            'failure_and_fee_sensitivity': risk_cases,
            'sponsor_revenue_share_bps_sensitivity': sponsor_shares,
            'verified_available_financing_wei': 0,
            'future_capture_rate': None, 'latency_measured': False,
            'new_paymaster_deployed': False, 'external_sponsor_committed': False,
            'live_transaction_submitted': False, 'realized_nqc_revenue': False}
    return stringify(data)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    report = audit()
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'requests': report['new_read_only_requests'],
                      'matched_protocol_slots': report['time_only_projection_protocol_read_slots_match'],
                      'prefund_reduction_percent': report['fee_cap_experiment']['required_prefund_reduction_percent']}, indent=2))
