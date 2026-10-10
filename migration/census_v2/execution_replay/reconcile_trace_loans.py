#!/usr/bin/env python3
"""Corroborate retained flashLoan/transfer/callback/transferFrom trace observations.

Rendered method labels are retained evidence, not a deployed-code/ABI proof.
Matching token logs do not establish NQC funding rights, liquidity or full costs.
"""
import argparse
from collections import Counter
import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile

import reconcile_weth_accounts as source
from reconcile_weth_accounts import (
    V2, ROOT, canonical, need, sha, quantity, address_word, semantic_receipt,
    TRANSFER, parse_trace, ARCHIVE_SHA,
)

BASE = '59f4f9e83d015f5f14466cee88a5e9dbfa049665'
LENDER = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
ADDRESS = r'(0x[0-9a-fA-F]{40})'
AMOUNT = r'([0-9]+)(?: \[[^]]+\])?'
DATA = r'(0x(?:[0-9a-fA-F]{2})*)'
LOAN = re.compile(ADDRESS + r'::flashLoan\(' + ADDRESS + ', ' + AMOUNT + ', ' + DATA + r'\)')
SEND = re.compile(ADDRESS + r'::transfer\(' + ADDRESS + ', ' + AMOUNT + r'\)')
REPAY = re.compile(ADDRESS + r'::transferFrom\(' + ADDRESS + ', ' + ADDRESS + ', ' + AMOUNT + r'\)')
CALLBACK = re.compile(ADDRESS + r'::onMorphoFlashLoan\(' + AMOUNT + ', ' + DATA + r'\)')


def pin_consumer():
    path = Path(source.__file__)
    raw = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                       BASE + ':' + str(path.relative_to(ROOT))], text=True).strip()
    need(blob == expected, 'trace loan source consumer drift')
    return sha(raw)


def contexts(nodes, sender):
    owners, callers = [], []
    for index, node in enumerate(nodes):
        parent = node['parent']
        need(parent is None or 0 <= parent < index, 'invalid trace parent')
        caller = sender if parent is None else owners[parent]
        target = re.match(ADDRESS + '::', node['body'])
        precompile = re.match(r'PRECOMPILES::(identity|ecrecover)\(', node['body'])
        need(target is not None or precompile is not None, 'unknown trace context')
        need('[callcode]' not in node['body'].lower(), 'CALLCODE context unsupported')
        delegated = '[delegatecall]' in node['body']
        owners.append(caller if delegated else target[1].lower() if target else 'precompile')
        callers.append(caller)
    return callers


def match_loans(nodes, receipt, normalized):
    logs = semantic_receipt(receipt, normalized)['logs']
    callers = contexts(nodes, receipt['from'])
    loans, consumed = [], set()
    for index, node in enumerate(nodes):
        if not node['body'].lower().startswith(LENDER + '::flashloan('):
            continue
        match = LOAN.fullmatch(node['body'])
        need(match is not None, 'rendered loan ABI shape')
        lender, asset, amount, data = match.groups()
        lender, asset, amount, data = lender.lower(), asset.lower(), int(amount), data.lower()
        need(0 < amount < 2**256, 'loan amount domain')
        need(node['successful_ancestry'] is True, 'unsettled loan frame')
        borrower = callers[index]
        children = [n for n in nodes if n['parent'] == index]
        need(len(children) == 3 and all(n['successful_ancestry'] is True for n in children),
             'loan child population or settlement')
        sent, callback, repaid = (pattern.fullmatch(n['body']) for pattern, n in
                                  zip((SEND, CALLBACK, REPAY), children))
        need(sent is not None and callback is not None and repaid is not None,
             'loan child call shape or order')
        need((sent[1].lower(), sent[2].lower(), int(sent[3])) == (asset, borrower, amount),
             'principal call mismatch')
        need((callback[1].lower(), int(callback[2]), callback[3].lower()) == (borrower, amount, data),
             'callback mismatch')
        need((repaid[1].lower(), repaid[2].lower(), repaid[3].lower(), int(repaid[4]))
             == (asset, borrower, lender, amount), 'repayment call mismatch')
        delivered, returned = [], []
        for log in logs:
            if log['address'] != asset or not log['topics'] or log['topics'][0] != TRANSFER:
                continue
            need(len(log['topics']) == 3 and re.fullmatch(r'0x[0-9a-f]{64}', log['data']),
                 'loan asset Transfer ABI')
            frm, to = (address_word(t[2:]) for t in log['topics'][1:])
            value, log_index = int(log['data'], 16), quantity(log['logIndex'])
            if (frm, to, value) == (lender, borrower, amount):
                delivered.append(log_index)
            if (frm, to, value) == (borrower, lender, amount):
                returned.append(log_index)
        need(len(delivered) == len(returned) == 1 and delivered[0] < returned[0],
             'principal/repayment receipt population or order')
        need(not ({delivered[0], returned[0]} & consumed), 'receipt leg reused for multiple loans')
        consumed.update([delivered[0], returned[0]])
        loans.append({
            'trace_line': node['line'], 'lender': lender, 'borrower': borrower, 'asset': asset,
            'principal_raw': str(amount), 'repayment_raw': str(amount),
            'matched_transfer_difference_raw': '0', 'complete_financing_fee_raw': None,
            'trace_method_label': 'flashLoan', 'callback_method_label': 'onMorphoFlashLoan',
            'callback_data_sha256': sha(bytes.fromhex(data[2:])),
            'principal_call_line': children[0]['line'], 'callback_call_line': children[1]['line'],
            'repayment_call_line': children[2]['line'],
            'principal_log_index': delivered[0], 'repayment_log_index': returned[0],
            'successful_trace_ancestry': True,
            'scope': 'RENDERED_CALL_SEQUENCE_CORROBORATED_BY_UNIQUE_RECEIPT_TRANSFER_LEGS',
            'deployed_code_and_abi_proven': False, 'complete_token_balances_proven': False,
            'nqc_funding_admitted': False,
        })
    return loans


def reconcile():
    consumer_pin = pin_consumer()
    dependencies = {str(p.relative_to(ROOT)): sha(source.source(p)) for p in source.DEPENDENCIES}
    raw = {name: source.source(V2 / source.INPUTS[name]) for name in ('receipts', 'settlements', 'traces')}
    need(sha(raw['traces']) == ARCHIVE_SHA, 'trace archive identity')
    receipts = source.keyed([r['result'] for r in source.lines(gzip.decompress(raw['receipts']))
                            if r['method'] == 'eth_getTransactionReceipt'], 'transactionHash')
    settlements = source.keyed(source.lines(raw['settlements']), 'transaction_hash')
    need(len(receipts) == len(settlements) == 127 and receipts.keys() == settlements.keys(),
         'full winner population differs')
    results = []
    with zipfile.ZipFile(V2 / source.INPUTS['traces']) as archive:
        need(len(archive.namelist()) == len(set(archive.namelist())) == 255, 'trace archive inventory')
        for tx, row in sorted(settlements.items(), key=lambda item:
                              (item[1]['block_number'], item[1]['transaction_index'])):
            receipt = receipts[tx]
            need(receipt['status'] == '0x1' and receipt['blockHash'] == row['block_hash']
                 and quantity(receipt['blockNumber']) == row['block_number']
                 and quantity(receipt['transactionIndex']) == row['transaction_index']
                 and receipt['from'] == row['gas_payer'] and receipt['to'] == row['root_execution_account'],
                 'trace/receipt identity differs')
            trace = archive.read(row['trace_member'])
            need(sha(trace) == row['trace_sha256'], 'trace member identity')
            gas, nodes = parse_trace(trace)
            need(gas == quantity(receipt['gasUsed']) and
                 gas * quantity(receipt['effectiveGasPrice']) == int(row['gas_from_existing_receipt_counted_once_wei']),
                 'receipt gas binding')
            normalized = {k: row[k] for k in ('transaction_hash', 'block_hash', 'block_number', 'transaction_index')}
            loans = match_loans(nodes, receipt, normalized)
            results.append({**normalized, 'trace_member': row['trace_member'], 'trace_sha256': sha(trace),
                            'receipt_sha256': sha(canonical(receipt)), 'trace_loans': loans,
                            'other_funding_routes_resolved': False, 'classification': 'INSUFFICIENT_EVIDENCE',
                            'nqc_funding_admitted': False, 'complete_profit_wei': None})
    flat = [loan for row in results for loan in row['trace_loans']]
    need(len(flat) == 49 and sum(bool(r['trace_loans']) for r in results) == 46,
         'pinned rendered-loan population differs')
    output = b''.join(canonical(row) for row in results)
    report = {
        'schema': 'nqc-rendered-trace-loan-readback-v1',
        'status': 'RECEIPT_CORROBORATED_HISTORICAL_LOAN_OBSERVATIONS_NOT_NQC_ADMISSION',
        'source_commit': source.BASE, 'source_consumer_commit': BASE,
        'source_consumer_sha256': consumer_pin, 'consumer_sha256': sha(Path(__file__).read_bytes()),
        'dependencies_sha256': dependencies,
        'inputs': {name: {'path': source.INPUTS[name], 'bytes': len(value), 'sha256': sha(value)}
                   for name, value in raw.items()},
        'transactions_scanned': len(results), 'transactions_with_selected_loan_observations': 46,
        'selected_loan_observations': len(flat), 'matched_receipt_transfer_legs': len(flat) * 2,
        'lender': LENDER, 'loans_by_asset': dict(sorted(Counter(loan['asset'] for loan in flat).items())),
        'ledger_sha256': sha(output), 'network_requests': 0, 'gas_spent': False,
        'complete_funding_routes_proven': False, 'independent_certification': False, 'census_closed': False,
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
