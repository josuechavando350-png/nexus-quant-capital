#!/usr/bin/env python3
"""Partition all retained winners without turning selection into profitability."""
import argparse
from collections import Counter
import gzip
import hashlib
from pathlib import Path
import subprocess

import reconcile_weth_accounts as accounts
import reconcile_trace_loans as loans
import reconcile_weth_inventory as inventory
from reconcile_weth_accounts import V2, ROOT, canonical, need, sha, quantity, semantic_receipt, flash_event
from rmc016_aave_event_legs import decode, POOL, TOPIC

BASE = 'a1292b8a46e225934b1e1c5f375418718739a68b'
# The legacy economic ledger predates these two complete receipt backfills.
# Preserve it; report exact discrepancies instead of silently inheriting it.
LEGACY_FLASH_OMISSIONS = {
    '0xfcd28a32be33d1c047b04c5005285c31e5d8dcc92132c4353eebbc9c7426f369': [185],
    '0xfd76e2f691f2b18e4116d41d7842c7717b77674d3092827d58daad3dc6a9c427': [916],
}
PINS = ['execution_replay/reconcile_trace_loans.py', 'execution_replay/trace-loans/ledger.jsonl',
        'execution_replay/trace-loans/report.json', 'execution_replay/reconcile_weth_inventory.py',
        'execution_replay/weth-inventory/ledger.jsonl', 'execution_replay/weth-inventory/report.json',
        'evidence/economics/replay/winner-economic-ledger.jsonl']


def pinned(name):
    path = V2 / name
    raw = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                       BASE + ':' + str(path.relative_to(ROOT))], text=True).strip()
    need(actual == expected, 'strategy input drift: ' + name)
    return raw


def family(legs):
    need(bool(legs), 'empty liquidation family')
    same = [l['collateral_asset'] == l['debt_asset'] for l in legs]
    if len(legs) == 1:
        return 'SINGLE_SAME_ASSET' if same[0] else 'SINGLE_CROSS_ASSET'
    return 'MULTI_SAME_ASSET' if all(same) else 'MULTI_WITH_CROSS_ASSET'


def compare(receipts, economics, trace_rows, inventory_rows, flash_rows):
    receipts = accounts.keyed(receipts, 'transactionHash')
    economic = accounts.keyed(economics, 'transaction_hash')
    trace = accounts.keyed(trace_rows, 'transaction_hash')
    inv = accounts.keyed(inventory_rows, 'transaction_hash')
    need(len(receipts) == len(economic) == len(trace) == 127 and
         receipts.keys() == economic.keys() == trace.keys(), 'strategy population mismatch')
    need(len(inv) == 9 and inv.keys() <= receipts.keys(), 'inventory subset mismatch')
    observed_flash = {(r['transaction_hash'], r['log_index']): r for r in flash_rows}
    need(len(observed_flash) == len(flash_rows) == 22, 'flash population mismatch')
    consumed_flash, output = set(), []
    for tx, e in sorted(economic.items(), key=lambda kv: (kv[1]['block_number'], kv[1]['transaction_index'])):
        receipt = receipts[tx]
        semantic = semantic_receipt(receipt, e)
        need(receipt['status'] == '0x1', 'failed winner receipt')
        need(trace[tx]['receipt_sha256'] == sha(canonical(receipt)), 'trace receipt mismatch')
        legs = [decode(l) for l in receipt['logs'] if l['address'].lower() == POOL
                and l['topics'] and l['topics'][0].lower() == TOPIC]
        need([l['log_index'] for l in legs] == e['liquidation_log_indices'] and
             sorted(l['original_event_commitment_sha256'] for l in legs) == e['event_commitments'],
             'liquidation event commitment mismatch')
        # Independently reconstruct the token-denominated event legs; no USD sum.
        debt, collateral = Counter(), Counter()
        for l in legs:
            debt[l['debt_asset']] += int(l['debt_to_cover_raw'])
            collateral[l['collateral_asset']] += int(l['collateral_liquidated_raw'])
        reconstructed = [{'asset': a, 'debt_repaid_raw': str(debt[a]),
            'collateral_received_event_raw': str(collateral[a]),
            'event_difference_raw': str(collateral[a] - debt[a])} for a in sorted(debt.keys() | collateral.keys())]
        need(reconstructed == e['asset_legs'], 'aggregate event legs mismatch')
        flashes = [r for l in semantic['logs'] if (r := flash_event(l)) is not None]
        for f in flashes:
            key = (tx, f['log_index'])
            need(key not in consumed_flash and observed_flash.get(key) == f, 'flash binding mismatch')
            consumed_flash.add(key)
        current_indices = [f['log_index'] for f in flashes]
        legacy_indices = e['recognized_flash_log_indices']
        if tx in LEGACY_FLASH_OMISSIONS:
            need(legacy_indices == [] and current_indices == LEGACY_FLASH_OMISSIONS[tx], 'known legacy omission changed')
        else:
            need(current_indices == legacy_indices, 'unexpected flash indices mismatch')
        rendered = trace[tx]['trace_loans']
        routes = sorted({f['protocol'] + '_EVENT' for f in flashes} |
                        ({'MORPHO_STYLE_RENDERED_CALL_AND_TRANSFERS'} if rendered else set()))
        root = inv[tx]['root_account'] if tx in inv else None
        gas = quantity(receipt['gasUsed']) * quantity(receipt['effectiveGasPrice'])
        need(gas == int(e['historical_gas']['execution_wei']), 'execution gas mismatch')
        output.append({
            **{k: e[k] for k in ('transaction_hash', 'block_hash', 'block_number', 'transaction_index', 'conflict_set_id')},
            'family': family(legs), 'liquidation_events': legs, 'receipt_sha256': sha(canonical(receipt)),
            'observed_funding_routes': routes, 'recognized_flash_event_count': len(flashes),
            'recognized_flash_log_indices': current_indices, 'legacy_flash_log_indices': legacy_indices,
            'legacy_economic_flash_index_discrepancy': current_indices != legacy_indices,
            'corroborated_rendered_loan_count': len(rendered),
            'no_selected_funding_observation_is_not_proof_of_own_principal': True,
            'funding_inventory_and_access_complete': False,
            'historical_execution_gas_wei': str(gas), 'historical_gas_is_nqc_cost': False,
            'weth_root_minimum_initial_inventory_wei': root['minimum_initial_weth_wei'] if root else None,
            'nqc_execution_admitted': False, 'complete_profit_wei': None,
            'capture_probability': None, 'classification': 'INSUFFICIENT_EVIDENCE',
        })
    need(consumed_flash == observed_flash.keys(), 'unconsumed flash event')
    need(sum(len(r['liquidation_events']) for r in output) == 139, 'full event population mismatch')
    return output


def reconcile():
    inputs = {n: pinned(n) for n in PINS}
    loan_ledger, loan_report = loans.reconcile()
    inv_ledger, inv_report = inventory.reconcile()
    need(loan_ledger == inputs[PINS[1]] and canonical(loan_report) == inputs[PINS[2]], 'loan readback drift')
    need(inv_ledger == inputs[PINS[4]] and canonical(inv_report) == inputs[PINS[5]], 'inventory readback drift')
    receipt_raw = accounts.source(V2 / accounts.INPUTS['receipts'])
    flash_raw = accounts.source(V2 / accounts.INPUTS['flashes'])
    receipts = [r['result'] for r in accounts.lines(gzip.decompress(receipt_raw))
                if r['method'] == 'eth_getTransactionReceipt']
    rows = compare(receipts, accounts.lines(inputs[PINS[6]]), accounts.lines(loan_ledger),
                   accounts.lines(inv_ledger), accounts.lines(flash_raw))
    ledger = b''.join(canonical(r) for r in rows)
    summary = []
    for name in sorted({r['family'] for r in rows}):
        selected = [r for r in rows if r['family'] == name]
        summary.append({'family': name, 'transactions': len(selected),
            'liquidation_events': sum(len(r['liquidation_events']) for r in selected),
            'transactions_with_selected_funding_observation': sum(bool(r['observed_funding_routes']) for r in selected),
            'distinct_collateral_debt_pairs': len({(l['collateral_asset'], l['debt_asset']) for r in selected for l in r['liquidation_events']}),
            'economically_admitted_nqc_transactions': 0})
    report = {'schema': 'nqc-strategy-family-comparison-v1', 'source_commit': BASE,
        'consumer_sha256': sha(Path(__file__).read_bytes()), 'ledger_sha256': sha(ledger),
        'pinned_inputs': {n: {'bytes': len(raw), 'sha256': sha(raw)} for n, raw in inputs.items()},
        'receipt_archive_sha256': sha(receipt_raw), 'flash_observations_sha256': sha(flash_raw),
        'population': '127_RETAINED_EXECUTED_WINNERS_NOT_ALL_OPPORTUNITIES_OR_MARKETS',
        'transactions': len(rows), 'liquidation_events': 139, 'families': summary,
        'distinct_collateral_debt_pairs': len({(l['collateral_asset'], l['debt_asset']) for r in rows for l in r['liquidation_events']}),
        'transactions_with_selected_funding_observation': sum(bool(r['observed_funding_routes']) for r in rows),
        'selected_funding_route_transaction_counts': dict(sorted(Counter(x for r in rows for x in r['observed_funding_routes']).items())),
        'legacy_economic_flash_omissions_backfilled': LEGACY_FLASH_OMISSIONS,
        'legacy_economic_ledger_not_recertified': True,
        'selection_bias_removed': False, 'new_holdout_observations': 0, 'network_requests': 0,
        'success_probability': None, 'census_closed': False, 'economically_admitted_nqc_transactions': 0}
    return ledger, report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', required=True)
    args = p.parse_args(); dst = Path(args.out); dst.mkdir(parents=True, exist_ok=False)
    ledger, report = reconcile()
    (dst / 'ledger.jsonl').write_bytes(ledger); (dst / 'report.json').write_bytes(canonical(report))
    print(canonical(report).decode(), end='')
