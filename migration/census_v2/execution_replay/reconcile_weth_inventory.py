#!/usr/bin/env python3
"""WETH initial-inventory lower bounds from ordered, authenticated receipt logs.

Conditional event semantics, not state balance proofs or NQC financing admission.
Every account stays separate; pool inventory is never attributed to the operator.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
from pathlib import Path
import re
import subprocess

import reconcile_weth_accounts as accounts
from reconcile_weth_accounts import (
    V2, ROOT, WETH, TRANSFER, WITHDRAWAL, APPROVAL,
    canonical, need, sha, quantity, address_word, semantic_receipt,
)

BASE = '97c65411e8cdd4d3fc48f7d766b3824b6685d9d4'
PINS = ['execution_replay/reconcile_weth_accounts.py',
        'execution_replay/weth-accounts/ledger.jsonl',
        'execution_replay/weth-accounts/report.json']


def pinned(name):
    path = V2 / name
    raw = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    expected = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-parse', BASE + ':' + str(path.relative_to(ROOT))],
        text=True).strip()
    need(blob == expected, 'inventory source drift: ' + name)
    return raw


def ordered_inventory(receipt, normalized, owners):
    """Minimal initial balances for this observed WETH sequence, account by account.

    A debit of q with preceding cumulative delta d needs initial >= q-d.
    Debit precedes credit even in a self-transfer (net-delta-only is insufficient).
    Deposits and unknown WETH events fail closed in this nine-case scope.
    """
    semantic = semantic_receipt(receipt, normalized)
    delta, floors = defaultdict(int), defaultdict(int)
    witnesses, first_credit, operations = {}, {}, []
    owners = set(owners)
    owners.update([receipt['from'], receipt['to']])
    for log in semantic['logs']:
        if log['address'] != WETH:
            continue
        topics = log['topics']
        need(topics and topics[0] in {TRANSFER, WITHDRAWAL, APPROVAL},
             'unsupported WETH inventory event')
        kind = topics[0]
        need(len(topics) == (2 if kind == WITHDRAWAL else 3)
             and re.fullmatch(r'0x[0-9a-f]{64}', log['data']), 'WETH inventory ABI')
        addresses = [address_word(t[2:]) for t in topics[1:]]
        if kind == APPROVAL:
            continue
        sender, amount, index = addresses[0], int(log['data'], 16), quantity(log['logIndex'])
        recipient = addresses[1] if kind == TRANSFER else None
        owners.add(sender)
        before = delta[sender]
        required = max(0, amount - before)
        if required > floors[sender]:
            floors[sender] = required
            witnesses[sender] = {'log_index': index, 'debit_wei': str(amount),
                                 'preceding_event_delta_wei': str(before),
                                 'required_initial_wei': str(required)}
        delta[sender] -= amount
        if recipient is not None:
            owners.add(recipient)
            delta[recipient] += amount
            if amount:
                first_credit.setdefault(recipient, {'log_index': index, 'sender': sender,
                                                    'amount_wei': str(amount)})
        operations.append({'log_index': index, 'kind': 'TRANSFER' if recipient else 'WITHDRAWAL',
                           'sender': sender, 'recipient': recipient, 'amount_wei': str(amount)})
    rows = [{'address': owner, 'is_root_execution_account': owner == receipt['to'],
             'is_transaction_sender': owner == receipt['from'],
             'minimum_initial_weth_wei': str(floors[owner]),
             'final_observed_weth_delta_wei': str(delta[owner]),
             'minimum_implied_by_final_delta_alone_wei': str(max(0, -delta[owner])),
             'ordering_adds_inventory_requirement': floors[owner] > max(0, -delta[owner]),
             'binding_debit': witnesses.get(owner), 'first_incoming_transfer': first_credit.get(owner)}
            for owner in sorted(owners)]
    replay(operations, {r['address']: int(r['minimum_initial_weth_wei']) for r in rows})
    return rows, operations


def replay(operations, initial):
    """Check debit feasibility in the event model; not a state or EVM replay."""
    need(all(type(v) is int and 0 <= v < 2**256 for v in initial.values()),
         'initial inventory integer domain')
    balances = defaultdict(int, initial)
    for op in operations:
        sender, recipient, amount = op['sender'], op['recipient'], int(op['amount_wei'])
        need(balances[sender] >= amount, 'insufficient initial inventory at log ' + str(op['log_index']))
        balances[sender] -= amount
        if recipient is not None:
            balances[recipient] += amount
    return dict(balances)


def reconcile():
    inputs = {name: pinned(name) for name in PINS}
    ledger, account_report = accounts.reconcile()
    need(ledger == inputs[PINS[1]] and canonical(account_report) == inputs[PINS[2]],
         'recomputed account evidence differs')
    receipts_raw = accounts.source(V2 / accounts.INPUTS['receipts'])
    receipts = accounts.keyed([r['result'] for r in accounts.lines(gzip.decompress(receipts_raw))
                              if r['method'] == 'eth_getTransactionReceipt'], 'transactionHash')
    results = []
    for row in accounts.lines(ledger):
        tx = row['transaction_hash']
        receipt = receipts[tx]
        normalized = {k: row[k] for k in ('transaction_hash', 'block_hash', 'block_number')}
        normalized['transaction_index'] = quantity(receipt['transactionIndex'])
        inventory, ops = ordered_inventory(receipt, normalized, [a['address'] for a in row['accounts']])
        expected = {a['address']: a['weth_event_delta_wei'] for a in row['accounts']}
        need({a['address']: a['final_observed_weth_delta_wei'] for a in inventory} == expected,
             'ordered inventory disagrees with account ledger')
        root = next(a for a in inventory if a['is_root_execution_account'])
        results.append({
            **normalized, 'retrospective_rank': row['retrospective_rank'],
            'receipt_sha256': sha(canonical(receipt)), 'root_account': root,
            'accounts': inventory, 'weth_operations': ops,
            'scope': 'CONDITIONAL_WETH_EVENT_SEQUENCE_INITIAL_INVENTORY_LOWER_BOUNDS',
            'classification': 'INSUFFICIENT_EVIDENCE',
            'zero_initial_bound_proves_nqc_financing': False,
            'account_ownership_aggregated': False, 'actual_initial_balances_proven': False,
            'nqc_executable_value_admitted': False, 'complete_profit_wei': None,
        })
    output = b''.join(canonical(r) for r in results)
    report = {
        'schema': 'nqc-weth-initial-inventory-readback-v1',
        'status': 'EVENT_ORDER_LOWER_BOUNDS_NOT_FINANCING_ADMISSION',
        'source_commit': BASE, 'consumer_sha256': sha(Path(__file__).read_bytes()),
        'pinned_inputs': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in inputs.items()},
        'account_readback_sha256': sha(canonical(account_report)),
        'receipt_archive_sha256': sha(receipts_raw), 'ledger_sha256': sha(output),
        'transactions': len(results), 'account_rows': sum(len(r['accounts']) for r in results),
        'weth_operations': sum(len(r['weth_operations']) for r in results),
        'positive_initial_bounds': sum(int(a['minimum_initial_weth_wei']) > 0 for r in results for a in r['accounts']),
        'bounds_exceeding_final_delta': sum(a['ordering_adds_inventory_requirement'] for r in results for a in r['accounts']),
        'root_positive_initial_bound_ranks': [r['retrospective_rank'] for r in results
                                            if int(r['root_account']['minimum_initial_weth_wei']) > 0],
        'network_requests': 0, 'gas_spent': False, 'complete_profit_proven': False,
        'independent_certification': False, 'census_closed': False,
    }
    return output, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    ledger, report = reconcile()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'ledger.jsonl').write_bytes(ledger)
    (args.out / 'report.json').write_bytes(canonical(report))
    print(canonical(report).decode(), end='')
