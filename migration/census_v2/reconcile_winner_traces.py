#!/usr/bin/env python3
"""Authenticate historical cast logs and index returned oracle/value calls.

This reads retained text. It does not run cast, acquire receipts, authenticate
the historical RPC execution, reconstruct balance deltas or calculate profit.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import zipfile

from reconcile_temporal_core import CORE_SHA, read_core, canon
from verify_server_recovery import parse, require, sha

ARCHIVE_SHA = '9323bf262e1f9695fcfc68a96a10b1a2e987544d3395c046aa31b13271a60c92'
ORACLE = '0x54586be62e3c3580375ae3723c145253060ca0c2'
CALL = re.compile(r'^(?P<prefix>[ │]*)(?P<branch>[├└]─ )?\[(?P<gas>\d+)\] (?P<body>.+)$')
RETURN = re.compile(r'^(?P<prefix>[ │]*)[├└]─ ← \[(?P<kind>[^]]+)\](?P<body>.*)$')
QUOTE = re.compile(r'^(0x[0-9a-fA-F]{40})::getAssetPrice\((0x[0-9a-fA-F]{40})\) \[staticcall\]$')
VALUE = re.compile(r'^(0x[0-9a-fA-F]{40})::[^\s({]+\{value: ([0-9]+)\}')


def parse_trace(raw):
    text = raw.decode('utf-8')
    require(text.count('Transaction successfully executed.') == 1, 'trace success marker')
    gas = re.findall(r'^Gas used:\s*(\d+)\s*$', text, re.MULTILINE)
    require(len(gas) == 1, 'one transaction gas line')
    nodes, stack = [], []
    for line_number, line in enumerate(text.splitlines(), 1):
        call = CALL.match(line)
        if call:
            require(not call['branch'] or len(call['prefix']) % 4 == 0, 'call indentation')
            depth = len(call['prefix']) // 4 if call['branch'] else 0
            require(depth == len(stack), 'call tree depth')
            node = {'line': line_number, 'body': call['body'], 'parent': stack[-1] if stack else None,
                    'outcome': None, 'return_data': None}
            nodes.append(node)
            stack.append(len(nodes)-1)
            continue
        ret = RETURN.match(line)
        if ret:
            require(len(ret['prefix']) % 4 == 0, 'return indentation')
            depth = len(ret['prefix']) // 4 - 1
            require(depth == len(stack)-1 and stack, 'return tree depth')
            require(ret['kind'] in ['Return', 'Stop', 'Revert'], 'unhandled trace outcome')
            node = nodes[stack.pop()]
            node.update(outcome=ret['kind'], return_data=ret['body'].strip())
    require(not stack and nodes and sum(n['parent'] is None for n in nodes) == 1, 'incomplete trace tree')
    require(nodes[0]['outcome'] in ['Return', 'Stop'], 'root reverted')
    for node in nodes:
        parent = node['parent']
        node['successful_ancestry'] = node['outcome'] in ['Return', 'Stop'] and (
            parent is None or nodes[parent]['successful_ancestry'])
    return int(gas[0]), nodes


def reconcile(archive, core, output):
    require(sha(archive.read_bytes()) == ARCHIVE_SHA, 'winner trace archive pin')
    files = read_core(core)
    original_rows = [parse(x) for x in files['winner-replay/winner-replay-ledger.jsonl'].splitlines()]
    original = {x['transaction_hash']: x for x in original_rows}
    require(len(original) == len(original_rows) == 127, 'winner universe')
    prices = {x['block_number']: x for x in map(parse, files['rmc016-liquidation-block-price-authority.jsonl'].splitlines())}
    reserves = [parse(x) for x in files['start-market-state/nodies.jsonl'].splitlines()]
    assets = {x['asset'].lower(): int(x['reserve_id']) for x in reserves}
    quotes, value_calls, ledger, failures = [], [], [], []
    seen, counts = set(), Counter()
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) == 255, 'trace archive inventory')
        require(all('/' not in n and n not in ['.', '..'] for n in names), 'trace member path')
        manifest = parse(z.read('recovery-manifest.json'))['files']
        require(len(manifest) == 254 and {r['member'] for r in manifest} == set(names)-{'recovery-manifest.json'}, 'trace manifest inventory')
        for row in manifest:
            raw = z.read(row['member'])
            require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'trace manifest hash')
        records = sorted(n for n in names if re.fullmatch(r'[0-9]{4}-[0-9a-f]{16}\.json', n))
        require(len(records) == 127, 'trace record inventory')
        for name in records:
            record_raw = z.read(name)
            record = parse(record_raw)
            tx = record['transaction_hash']
            require(tx in original and tx not in seen, 'unexpected/duplicate transaction')
            require(record_raw == canon(original[tx]), 'original winner record differs')
            seen.add(tx)
            log_name = name.removesuffix('.json') + '.cast.log'
            raw = z.read(log_name)
            require(sha(raw) == record['cast_log_sha256'], 'historical cast log hash')
            gas, nodes = parse_trace(raw)
            require(gas == record['gas_used'], 'trace gas differs')
            block = prices[record['block_number']]
            require(block['block_hash'] == record['block_hash'], 'trace/block price anchor')
            tx_counts = Counter()
            for node in nodes:
                witness = {'transaction_hash': tx, 'block_number': record['block_number'],
                    'block_hash': record['block_hash'], 'trace_member': log_name,
                    'trace_sha256': record['cast_log_sha256'], 'trace_line': node['line']}
                q = QUOTE.fullmatch(node['body'])
                if q:
                    require(q[1].lower() == ORACLE, 'unhandled oracle address')
                    asset = q[2].lower()
                    require(asset in assets and node['outcome'] == 'Return', 'unhandled oracle result')
                    require(re.fullmatch(r'0x[0-9a-fA-F]{64}', node['return_data']) is not None, 'oracle return ABI shape')
                    value = int(node['return_data'], 16)
                    require(value > 0, 'oracle positive quote')
                    reference = int(block['prices'][assets[asset]])
                    quotes.append({**witness, 'oracle': ORACLE, 'asset': asset,
                        'trace_return_units': str(value), 'end_of_block_reference_units': str(reference),
                        'matches_end_of_block': value == reference, 'successful_ancestry': node['successful_ancestry'],
                        'price_used_by_liquidation_proven': False, 'available_before_transaction_proven': False})
                    tx_counts['oracle_calls'] += 1
                    tx_counts['oracle_end_state_mismatches'] += int(value != reference)
                    tx_counts['oracle_calls_in_reverted_subtrees'] += int(not node['successful_ancestry'])
                v = VALUE.match(node['body'])
                if v:
                    value_calls.append({**witness,
                        'target': v[1].lower(), 'rendered_value_wei': v[2],
                        'successful_ancestry': node['successful_ancestry'],
                        'delegatecall': '[delegatecall]' in node['body'], 'root_call': node['parent'] is None,
                        'recipient_role': 'UNATTRIBUTED', 'settled_balance_delta_proven': False})
                    tx_counts['rendered_value_fields'] += 1
                if node['outcome'] == 'Revert':
                    failures.append({**witness, 'call': node['body'],
                        'parent_trace_line': nodes[node['parent']]['line'] if node['parent'] is not None else None,
                        'returned_error': node['return_data'], 'scope': 'REVERTED_FRAME_IN_SUCCESSFUL_HISTORICAL_TRANSACTION',
                        'separate_transaction_gas_charge': False,
                        'treatment': 'EXCLUDE_SUBTREE_FROM_SETTLED_EXECUTION_EVIDENCE'})
                tx_counts['call_frames'] += 1
                tx_counts['reverted_frames'] += int(node['outcome'] == 'Revert')
            counts.update(tx_counts)
            ledger.append({'transaction_hash': tx, 'block_number': record['block_number'],
                'block_hash': record['block_hash'], 'transaction_index': record['transaction_index'],
                'trace_member': log_name, 'trace_sha256': record['cast_log_sha256'],
                'gas_used': gas, 'effective_gas_price_wei': record['effective_gas_price_wei'],
                'observed_transaction_gas_cost_wei': str(gas*int(record['effective_gas_price_wei'])),
                'historical_source_version_claim': record['cast_foundry_version'], 'counts': dict(tx_counts),
                'historical_log_authenticated': True, 'cast_reexecuted_now': False,
                'classification': 'INSUFFICIENT_EVIDENCE', 'nqc_executable_value_usd': '0',
                'reasons': ['HISTORICAL_PRODUCER_LOG_IS_NOT_INDEPENDENT_RPC_AUTHORITY',
                    'NQC_FINANCING_AND_NATIVE_GAS_UNAUTHENTICATED',
                    'COMPLETE_ROUTE_COSTS_AND_SETTLED_PROCEEDS_UNPROVEN',
                    'DECISION_TIME_AND_NQC_CAPTURE_UNPROVEN'],
                'original_nqc_received_at': None, 'current_execution_permitted': False})
    require(seen == set(original), 'missing winners')
    output.mkdir(parents=True, exist_ok=False)
    mismatches = [{**q, 'classification': 'TRACE_QUOTE_VS_BLOCK_END_PRICE_DIFFERENCE',
                   'cause_proven': False, 'treatment': 'KEEP_SEPARATE_STATE_SCOPES_NO_EXECUTION_PRICE_PROMOTION'}
                  for q in quotes if not q['matches_end_of_block']]
    outputs = {}
    for name, rows in [('winner-trace-ledger.jsonl', ledger), ('oracle-call-observations.jsonl', quotes),
                       ('native-value-observations.jsonl', value_calls), ('price-scope-mismatch-ledger.jsonl', mismatches),
                       ('reverted-frame-ledger.jsonl', failures)]:
        raw = b''.join(canon(x) for x in rows)
        (output/name).write_bytes(raw)
        outputs[name] = {'rows': len(rows), 'bytes': len(raw), 'sha256': sha(raw)}
    report = {'schema': 'nqc-winner-trace-readback-v1', 'status': 'READBACK_PASS_WITH_PRICE_SCOPE_MISMATCH' if mismatches else 'RETAINED_LOG_READBACK_PASS',
        'archive_sha256': ARCHIVE_SHA, 'core_archive_sha256': CORE_SHA,
        'verifier_sha256': sha(Path(__file__).read_bytes()),
        'winner_transactions': len(ledger), 'counts': dict(counts), 'outputs': outputs,
        'observed_transaction_gas_cost_wei': str(sum(int(x['observed_transaction_gas_cost_wei']) for x in ledger)),
        'raw_receipt_coverage_increased': False, 'full_receipt_log_reconciliation': False,
        'original_rpc_execution_independently_authenticated': False, 'new_fork_replay': False,
        'rendered_native_values_are_not_net_flows': True, 'complete_pnl_proven': False,
        'decision_time_observations_proven': False, 'new_producer_certified': False, 'census_closed': False}
    (output/'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['archive', 'core', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(reconcile(a.archive, a.core, a.output), sort_keys=True))
