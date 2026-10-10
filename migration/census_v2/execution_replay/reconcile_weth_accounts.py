#!/usr/bin/env python3
"""Account-separated event/trace cashflows for all nine historical WETH cases.

No balance proof, common ownership, route-specific profit or NQC admission is
inferred. WETH withdrawals debit the token ledger and credit native exactly once.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
sys.path[:0] = [str(V2), str(ROOT / 'ci/nqc-census')]
from reconcile_settlements import native_edges, withdrawals, WETH, WITHDRAWAL
from reconcile_winner_traces import parse_trace, ARCHIVE_SHA
from reconcile_winner_economics import (
    semantic_receipt, token_flows, flash_event, quantity, address_word,
    TRANSFER, abi_binding,
)
from verify_winner_recovery import canonical, need, sha
from typed_observation_vectors import keccak256

BASE = 'fb49a9c46bb52997c689ba2b7f183c4e536a9cb9'
APPROVAL = '0x' + keccak256(b'Approval(address,address,uint256)').hex()
INPUTS = {
    'receipts': 'additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz',
    'references': 'evidence/economics/replay/weth-cost-reference.jsonl',
    'settlements': 'execution_replay/settlements/settlement-ledger.jsonl',
    'native_edges': 'execution_replay/settlements/native-transfer-edges.jsonl',
    'flashes': 'economic_archives/evidence/tenderly-flash-observations.jsonl',
    'traces': 'execution_replay/inputs/original-winner-traces.zip',
}
DEPENDENCIES = [
    V2 / 'execution_replay/reconcile_settlements.py',
    V2 / 'reconcile_winner_traces.py', V2 / 'reconcile_winner_economics.py',
    V2 / 'verify_winner_recovery.py', ROOT / 'ci/nqc-census/typed_observation_vectors.py',
    ROOT / 'ci/nqc-census/rmc016_aave_event_legs.py',
]


def source(path):
    raw = path.read_bytes()
    name = str(path.relative_to(ROOT))
    expected = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', BASE + ':' + name], text=True).strip()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    need(blob == expected, 'pinned source drift: ' + name)
    return raw


def keyed(rows, key):
    result = {r[key]: r for r in rows}
    need(len(result) == len(rows), 'duplicate input identity')
    return result


def lines(raw):
    return [json.loads(line) for line in raw.splitlines()]


def flash_transfer_check(event, logs):
    """Corroborate the selected Balancer event with exact transfer log legs."""
    need(event['protocol'] == 'BALANCER_V2' and event['asset'] == WETH,
         'unsupported selected flash route')
    sent, repaid = [], []
    principal, fee = int(event['principal_raw']), int(event['event_fee_raw'])
    for log in logs:
        if log['address'] != WETH or not log['topics'] or log['topics'][0] != TRANSFER:
            continue
        need(len(log['topics']) == 3 and re.fullmatch(r'0x[0-9a-f]{64}', log['data']), 'flash Transfer ABI')
        sender, recipient = (address_word(t[2:]) for t in log['topics'][1:])
        amount, index = int(log['data'], 16), quantity(log['logIndex'])
        if (sender, recipient) == (event['emitter'], event['receiver']):
            need(amount == principal, 'flash principal transfer mismatch')
            sent.append(index)
        if (sender, recipient) == (event['receiver'], event['emitter']):
            need(amount == principal + fee, 'flash repayment transfer mismatch')
            repaid.append(index)
    need(len(sent) == len(repaid) == 1 and sent[0] < repaid[0] < event['log_index'],
         'flash transfer population/order')
    return {'principal_log_index': sent[0], 'repayment_log_index': repaid[0],
            'principal_wei': str(principal), 'fee_wei': str(fee),
            'repayment_wei': str(principal + fee), 'lender': event['emitter'],
            'receiver': event['receiver'], 'event_log_index': event['log_index'],
            'scope': 'MATCHED_LOG_LEGS_NOT_BALANCE_PROOF_OR_NQC_ADMISSION'}


def account_flows(receipt, edges, gas):
    """Ledger of observed fields, not a claim of exhaustive account state."""
    need(type(gas) is int and 0 <= gas < 2**256, 'gas integer domain')
    transfers, count, ambiguous = token_flows(receipt['logs'])
    need(ambiguous == 0, 'ambiguous Transfer shape in selected receipt')
    burns, total_burn = defaultdict(int), 0
    for log in receipt['logs']:
        if log['address'] != WETH:
            continue
        topics = log['topics']
        need(topics and topics[0] in {TRANSFER, WITHDRAWAL, APPROVAL},
             'unsupported WETH event; deposits require explicit treatment')
        expected = 2 if topics[0] == WITHDRAWAL else 3
        need(len(topics) == expected and re.fullmatch(r'0x[0-9a-f]{64}', log['data']),
             'WETH event ABI shape')
        for topic in topics[1:]:
            address_word(topic[2:])
        if topics[0] == WITHDRAWAL:
            owner = address_word(topics[1][2:])
            value = int(log['data'], 16)
            burns[owner] += value
            total_burn += value
    matched = Counter((e['target'], int(e['value_wei']))
                      for e in edges if e['weth_withdraw_return'])
    need(matched == withdrawals(receipt), 'withdrawal/native parity')
    native, seen_lines = defaultdict(int), set()
    for e in edges:
        need(e['trace_line'] not in seen_lines, 'duplicate native edge')
        seen_lines.add(e['trace_line'])
        need(e['successful_ancestry'] is True and e['delegatecall'] is False,
             'unsettled native edge')
        amount = int(e['value_wei'])
        need(0 <= amount < 2**256, 'native value domain')
        native[e['caller_context']] -= amount
        native[e['target']] += amount
    need(sum(native.values()) == 0, 'native conservation')
    owners = set(native) | set(burns) | {a for a, _ in transfers} | {receipt['from'], receipt['to']}
    accounts = []
    for owner in sorted(owners):
        weth_transfer = transfers.get((owner, WETH), 0)
        weth_change = weth_transfer - burns[owner]
        debit = gas if owner == receipt['from'] else 0
        accounts.append({
            'address': owner, 'is_transaction_sender': owner == receipt['from'],
            'is_root_execution_account': owner == receipt['to'], 'is_weth_contract': owner == WETH,
            'weth_transfer_log_delta_wei': str(weth_transfer),
            'weth_withdrawal_burn_wei': str(burns[owner]),
            'weth_event_delta_wei': str(weth_change),
            'native_trace_delta_before_gas_wei': str(native[owner]),
            'receipt_gas_debit_wei': str(debit),
            'native_trace_delta_after_gas_wei': str(native[owner] - debit),
            'other_token_log_deltas': [{'asset': token, 'raw_delta': str(value)}
                                     for (address, token), value in sorted(transfers.items())
                                     if address == owner and token != WETH and value != 0],
            'state_balance_delta_proven': False, 'complete_profit_wei': None,
        })
    need(sum(int(a['weth_transfer_log_delta_wei']) for a in accounts) == 0,
         'WETH transfer conservation')
    need(sum(int(a['weth_event_delta_wei']) for a in accounts) == -total_burn,
         'WETH supply/burn conservation')
    need(sum(int(a['receipt_gas_debit_wei']) for a in accounts) == gas
         and sum(int(a['native_trace_delta_after_gas_wei']) for a in accounts) == -gas,
         'receipt gas counted exactly once')
    return accounts, {'erc20_shaped_transfer_logs': count,
                      'weth_withdrawal_events': sum(matched.values()),
                      'weth_withdrawn_wei': str(total_burn)}


def reconcile():
    dependencies = {str(p.relative_to(ROOT)): sha(source(p)) for p in DEPENDENCIES}
    abi_binding()
    raw = {k: source(V2 / p) for k, p in INPUTS.items()}
    need(sha(raw['traces']) == ARCHIVE_SHA, 'trace archive identity')
    references = keyed(lines(raw['references']), 'transaction_hash')
    need(len(references) == 9 and {r['retrospective_rank'] for r in references.values()} == set(range(1, 10)),
         'nine-case population')
    settlements = keyed(lines(raw['settlements']), 'transaction_hash')
    records = [r for r in lines(gzip.decompress(raw['receipts']))
               if r['method'] == 'eth_getTransactionReceipt']
    receipts = keyed([r['result'] for r in records], 'transactionHash')
    need(len(receipts) == len(settlements) == 127 and set(receipts) == set(settlements), 'receipt population')
    retained_edges, retained_flashes = defaultdict(list), defaultdict(list)
    for e in lines(raw['native_edges']):
        retained_edges[e['transaction_hash']].append(e)
    for e in lines(raw['flashes']):
        retained_flashes[e['transaction_hash']].append(e)
    results = []
    with zipfile.ZipFile(V2 / INPUTS['traces']) as archive:
        need(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate trace member')
        for tx, ref in sorted(references.items(), key=lambda item: item[1]['retrospective_rank']):
            settlement, receipt = settlements[tx], receipts[tx]
            need(receipt['status'] == '0x1' and receipt['transactionHash'] == tx
                 and receipt['blockHash'] == ref['block_hash'] == settlement['block_hash']
                 and quantity(receipt['blockNumber']) == ref['block_number'] == settlement['block_number']
                 and receipt['from'] == settlement['gas_payer']
                 and receipt['to'] == settlement['root_execution_account'], 'receipt/ref identity')
            need(quantity(receipt['transactionIndex']) == settlement['transaction_index'], 'transaction position')
            norm = {'transaction_hash': tx, 'block_hash': ref['block_hash'],
                    'block_number': ref['block_number'], 'transaction_index': settlement['transaction_index']}
            semantic = semantic_receipt(receipt, norm)
            trace = archive.read(settlement['trace_member'])
            need(sha(trace) == settlement['trace_sha256'], 'trace member binding')
            trace_gas, nodes = parse_trace(trace)
            edges, excluded = native_edges(nodes, receipt['from'])
            previous = retained_edges[tx]
            need(len(edges) == len(previous) and all(all(old[k] == value for k, value in new.items())
                 for new, old in zip(edges, previous)), 'recomputed native edges differ')
            gas = quantity(receipt['gasUsed']) * quantity(receipt['effectiveGasPrice'])
            blob_gas = quantity(receipt.get('blobGasUsed', '0x0')) * quantity(receipt.get('blobGasPrice', '0x0'))
            need(blob_gas == 0 and trace_gas == quantity(receipt['gasUsed'])
                 and gas == int(settlement['gas_from_existing_receipt_counted_once_wei'])
                 == int(ref['competitor_whole_transaction_gas_wei']), 'gas source binding')
            accounts, counts = account_flows(receipt, edges, gas)
            flashes = [f for log in semantic['logs'] if (f := flash_event(log)) is not None]
            need(flashes == retained_flashes[tx], 'recognized flash observation differs')
            root = next(a for a in accounts if a['is_root_execution_account'])
            sender = next(a for a in accounts if a['is_transaction_sender'])
            gross = int(ref['collateral_weth_wei']) - int(ref['debt_weth_wei'])
            results.append({
                'transaction_hash': tx, 'block_number': ref['block_number'], 'block_hash': ref['block_hash'],
                'retrospective_rank': ref['retrospective_rank'], 'scope': 'WHOLE_TRANSACTION_OBSERVATIONS_NOT_ISOLATED_LIQUIDATION_PNL',
                'receipt_sha256': sha(canonical(receipt)), 'trace_member': settlement['trace_member'],
                'trace_sha256': sha(trace), 'selected_weth_leg_gross_difference_wei': str(gross),
                'root_account': root, 'transaction_sender': sender, 'accounts': accounts,
                'root_weth_transfer_delta_minus_selected_leg_gross_wei': str(int(root['weth_transfer_log_delta_wei']) - gross),
                'native_edges': edges, 'excluded_native_values': len(excluded),
                'recognized_flash_events': flashes,
                'recognized_flash_transfer_checks': [flash_transfer_check(f, semantic['logs']) for f in flashes],
                'unrecognized_financing_routes_and_obligations_resolved': False,
                'observed_counts': counts, 'whole_transaction_gas_wei': str(gas),
                'ownership_aggregation_performed': False, 'other_assets_converted_or_summed': False,
                'receipt_gas_subtracted_from_every_liquidation': False,
                'state_balance_proofs_verified': False, 'complete_costs_proven': False,
                'complete_profit_wei': None, 'nqc_executable_value_admitted': False,
                'classification': 'INSUFFICIENT_EVIDENCE',
            })
    ledger = b''.join(canonical(row) for row in results)
    report = {'schema': 'nqc-nine-weth-account-cashflow-readback-v1',
              'status': 'ACCOUNT_SEPARATED_OBSERVATIONS_NOT_PROFIT', 'source_commit': BASE,
              'consumer_sha256': sha(Path(__file__).read_bytes()),
              'dependency_sha256': dependencies,
              'inputs': {k: {'path': INPUTS[k], 'bytes': len(b), 'sha256': sha(b)} for k, b in raw.items()},
              'transactions': len(results), 'account_rows': sum(len(r['accounts']) for r in results),
              'native_edges': sum(len(r['native_edges']) for r in results),
              'weth_withdrawal_events': sum(r['observed_counts']['weth_withdrawal_events'] for r in results),
              'root_weth_flow_differs_from_selected_leg_gross_ranks': [r['retrospective_rank'] for r in results
                  if int(r['root_weth_transfer_delta_minus_selected_leg_gross_wei']) != 0],
              'ledger_sha256': sha(ledger), 'network_requests': 0, 'gas_spent': False,
              'complete_profit_proven': False, 'independent_certification': False, 'census_closed': False}
    return ledger, report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    ledger, report = reconcile()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'ledger.jsonl').write_bytes(ledger)
    (args.out / 'report.json').write_bytes(canonical(report))
    print(json.dumps(report, sort_keys=True))
