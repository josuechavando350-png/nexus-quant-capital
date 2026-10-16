#!/usr/bin/env python3
"""Offline, fixed-evidence principal audit. No provider client or transaction sender."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent / 'robinhood-real-state-replay-20261016'
WINDOW = HERE.parent / 'robinhood-sponsor-window-20261016'
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(WINDOW))
import audit_result as replay
import audit_window as window

TOKENS = {name: getattr(replay.route, name) for name in ('USDG', 'WSNET', 'SNET', 'NET')}
require = replay.require


def one(items, message):
    require(len(items) == 1, message)
    return items[0]


def matches(frame, target, selector):
    return frame.get('to', '').lower() == target and frame.get('input', '').startswith(selector)


def args(frame):
    data = frame['input'][10:]
    require(len(data) % 64 == 0, 'unaligned fixed ABI arguments')
    return [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]


def zero_balance(frame, owner, token):
    require(matches(frame, token, '0x70a08231') and frame.get('type') == 'STATICCALL'
            and args(frame) == [int(owner, 16)] and int(frame['output'], 16) == 0,
            'initial token inventory is not observed zero')


def transfer_flows(trace):
    rows = []
    for ordinal, log in enumerate(replay.ordered_logs(trace)):
        if log['address'].lower() in TOKENS.values() and log['topics'][0] == replay.route.TRANSFER:
            require(len(log['topics']) == 3, 'unexpected Transfer topics')
            rows.append({'ordinal': ordinal, 'token': log['address'].lower(),
                         'from': replay.route.address_topic(log['topics'][1]),
                         'to': replay.route.address_topic(log['topics'][2]),
                         'amount_raw': replay.route.words(log['data'], 1)[0]})
    return rows


def inventory_prefix(flows, owner, token):
    balance = minimum = 0
    steps = []
    for row in flows:
        if row['token'] != token or owner not in (row['from'], row['to']):
            continue
        balance += row['amount_raw'] * ((row['to'] == owner) - (row['from'] == owner))
        minimum = min(minimum, balance)
        steps.append({'ordinal': row['ordinal'], 'balance_raw': balance})
    return {'minimum_initial_inventory_raw': -minimum, 'final_delta_raw': balance, 'steps': steps}


def audit_principal(trace, data):
    require(all(not f.get('error') for f in replay.flatten(trace)), 'reverted frame')
    executor, router, account = [data['addresses'][x] for x in ('executor', 'router', 'account')]
    morpho = replay.route.MORPHO
    execution = one([f for f in replay.flatten(trace) if matches(f, executor, '0x3d47ed94')],
                    'expected one executor execution')
    require(execution['from'].lower() == account, 'wrong operator account')
    children = execution['calls']
    liquidation = one([f for f in children if matches(f, morpho, '0xd8eabcb8')], 'expected direct liquidation')
    require(children.index(liquidation) == 3, 'initial inventory checks moved')
    zero_balance(children[1], executor, TOKENS['USDG'])
    zero_balance(children[2], executor, TOKENS['WSNET'])
    calls = liquidation['calls']
    collateral = one([f for f in calls if matches(f, TOKENS['WSNET'], '0xa9059cbb')], 'collateral transfer absent')
    callback = one([f for f in calls if matches(f, executor, '0xcf7ea196')], 'native callback absent')
    repay = one([f for f in calls if matches(f, TOKENS['USDG'], '0x23b872dd')], 'repayment pull absent')
    require(calls.index(collateral) < calls.index(callback) < calls.index(repay), 'collateral/callback/repay order')
    require(callback['from'].lower() == morpho and repay['from'].lower() == morpho, 'wrong callback/repayment caller')
    require(args(collateral) == [int(executor, 16), 93436250743843184], 'collateral amount/receiver differs')
    require(args(repay) == [int(executor, 16), int(morpho, 16), 194034131], 'repayment amount/parties differ')
    swap = one([f for f in callback['calls'] if matches(f, router, '0x2948a5b4')], 'callback swap missing')
    require(swap['from'].lower() == executor, 'wrong router caller')
    for frame, token in zip(swap['calls'][:4], [TOKENS[x] for x in ('WSNET', 'SNET', 'NET', 'USDG')]):
        zero_balance(frame, router, token)
    approved = [f for f in callback['calls'] if matches(f, TOKENS['USDG'], '0x095ea7b3')
                and args(f) == [int(morpho, 16), 194034131]]
    approval = one(approved, 'exact repayment approval missing')
    require(callback['calls'].index(swap) < callback['calls'].index(approval), 'approval precedes sale')
    # Five STATICCALLs with selector 0x5c60e39a and one trailing word are nested
    # in this trace. They cannot transfer tokens. Do not infer a function name
    # from a four-byte selector or confuse read-only calls with loans.
    morpho_calls = [f for f in replay.flatten(execution) if f.get('to', '').lower() == morpho]
    reads = [f for f in morpho_calls if f.get('type') == 'STATICCALL'
             and f.get('input', '').startswith('0x5c60e39a') and len(f['input']) == 74]
    require(len(reads) == 5 and [f for f in morpho_calls if f not in reads] == [liquidation]
            and liquidation.get('type') == 'CALL', 'additional Morpho call')
    flows = transfer_flows(trace)
    ledgers = {}
    for name, owner in [('executor', executor), ('router', router)]:
        for symbol, token in TOKENS.items():
            ledger = inventory_prefix(flows, owner, token)
            require(ledger['minimum_initial_inventory_raw'] == 0, 'token outflow precedes funding')
            require(ledger['final_delta_raw'] == 0, 'stranded route asset')
            ledger['initial_zero_observed'] = name == 'router' or symbol in ('USDG', 'WSNET')
            ledgers[name + ':' + symbol] = ledger
    loan_flow = [r for r in flows if r['token'] == TOKENS['USDG']]
    expected = [(replay.route.POOL, router, 226094796), (router, executor, 226094796),
                (executor, morpho, 194034131), (executor, account, 32060665)]
    require([(r['from'], r['to'], r['amount_raw']) for r in loan_flow] == expected,
            'unexpected source, ordering or amount of loan-token funding')
    return {'status': 'ZERO_INITIAL_ROUTE_TOKEN_INVENTORY_IN_FIXED_HISTORICAL_SIMULATION',
            'usd_gross_sale_raw': 226094796, 'usd_debt_repayment_raw': 194034131,
            'usd_surplus_before_gas_raw': 32060665, 'unit': 'USDG, 6 decimals; not a USD parity assertion',
            'separate_morpho_flash_loan_invoked': False, 'morpho_static_reads': len(reads),
            'initial_balances_observed_zero': 6,
            'ordered_inventory_ledgers': ledgers, 'ordered_transfers': flows,
            'scope': 'One counterfactual at historical block 66744162 / transaction index 1; not live revenue.'}


def loss_row(name, evidence_kind, fee):
    network, charge = fee['network_fee_wei'], fee['sponsor_charge_wei']
    return {'outcome': name, 'evidence_kind': evidence_kind, 'network_fee_wei': network,
            'sponsor_cash_delta_wei': -charge, 'bundler_and_beneficiary_cash_delta_wei': charge - network,
            'consolidated_cash_delta_wei': -network,
            'external_bundler_recharge_to_funder_wei': None,
            'future_occurrence_probability': None}


def audit():
    lock = json.loads((HERE / 'sources.json').read_text())
    for name, sha in lock['files'].items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, 'source changed: ' + name)
    old = replay.audit(OLD / 'evidence')
    win = window.audit(WINDOW / 'evidence')
    data = json.loads((OLD / 'evidence/final-simulation-input.json').read_text())
    proof = audit_principal(replay.result(OLD / 'evidence/nitro-phase5/01-nqc-plain-eoa-success.json'), data)
    selected = win['variants'][1]
    rows = [loss_row('successful_userop', 'historical Nitro; window variant 31s', selected['nitro']['valid-after']),
            loss_row('included_userop_failure', 'historical Nitro; original parent-state variant, different operation', old['nqc_parent_failure']),
            loss_row('included_bundle_revert', 'historical Nitro; window variant expired', selected['nitro']['expired']),
            {'outcome': 'preinclusion_rejection', 'evidence_kind': 'accounting definition; not measured',
             'network_fee_wei': 0, 'sponsor_cash_delta_wei': 0, 'bundler_and_beneficiary_cash_delta_wei': 0,
             'consolidated_cash_delta_wei': 0, 'offchain_cost_usdg': None,
             'external_bundler_recharge_to_funder_wei': None, 'future_occurrence_probability': None}]
    for row in rows:
        require(row['sponsor_cash_delta_wei'] + row['bundler_and_beneficiary_cash_delta_wei'] ==
                row['consolidated_cash_delta_wei'], 'cash does not conserve')
    return {'status': 'PRINCIPAL_PROOF_VERIFIED_COMMERCIAL_FINANCING_UNPROVEN',
            'new_rpc_methods': 0, 'new_capture_seconds': 0, 'historical_block': 66744162,
            'historical_block_hash': win['historical_block_hash'], 'principal': proof,
            'loss_attribution': rows, 'loss_cases_are_not_a_statistical_sample': True,
            'historical_window_prefund_reservation_wei': selected['full_prefund_reserved_wei'],
            'historical_fixture_balances': {'entrypoint_wei': 10**17, 'bundler_wei': 10**16,
                                            'available_funding_proven': False, 'minimum_required_claimed': False},
            'current_production_bundler_admission': None, 'external_funding_committed_wei': None,
            'founder_no_recourse_agreement': None, 'future_net_margin_usdg': None,
            'realized_revenue': False, 'verified_source_files': len(lock['files'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    output = parser.parse_args().out
    require(not output.exists(), 'refuse evidence overwrite')
    report = audit()
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'new_rpc_methods', 'verified_source_files')}))
