"""Reconcile observed Ethereum execution fees without inventing builder payments.

The retained Blockscout responses cover three retrospective WETH winners. They
are indexer observations, not receipt proofs, complete traces or NQC executions.
The reader is offline; acquisition failures never become observed zero costs.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import tempfile

from cashflow_intake import build_cashflow
from evidence_store import admit, audit_store, read_batch
from execution_intake import query_execution_report, store_execution_report
from historical_intake import AUTHORITIES, EVIDENCE, ROOT, build_ledger, need, same, utc
from integrity import canonical, digest, read_regular, strict_json

SCHEMA = 'nqc.omega.inclusion-fee-intake.v1'
CAPTURE_NAME = 'inclusion-fee-capture.json'
CAPTURE_SHA256 = '9d6bdcc2f3a91cb8aced6d64e19938925c497bf59fc92cf1eb402301d7ccd8b8'
REPORT_NAME = 'inclusion-fee-report.json'
BINDING_NAME = 'inclusion-fee-parent.json'
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')


def uint(value):
    need(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value)
         and int(value) < 2**256, 'inclusion_noncanonical_uint256')
    return int(value)


def address(value):
    need(type(value) is str and ADDRESS.fullmatch(value), 'inclusion_invalid_address')
    return value.lower()


def split_execution_fee(gas_used, effective_price, base_fee):
    """Receipt gas already incorporates refunds; priority is INCLUDED in total."""
    gas, price, base = map(uint, (gas_used, effective_price, base_fee))
    need(gas > 0 and price >= base, 'inclusion_invalid_fee_relation')
    need(gas * price < 2**256, 'inclusion_fee_overflow')
    return {'execution_gas_paid_wei': str(gas * price),
            'base_fee_burn_wei': str(gas * base),
            'priority_fee_paid_wei': str(gas * (price - base))}


def load_capture(directory=EVIDENCE):
    raw = read_regular(Path(directory) / CAPTURE_NAME)
    need(digest(raw) == CAPTURE_SHA256, 'inclusion_capture_changed')
    value = strict_json(raw)
    need(canonical(value) == raw, 'inclusion_capture_noncanonical')
    need(value['schema'] == 'nqc.omega.inclusion-fee-capture.v1', 'inclusion_capture_schema')
    return value


def reconcile(cashflow, ledger, capture):
    """Validate all material fields against independently retained receipt data."""
    rows = cashflow['records']
    need(len(rows) == 9 and len({r['transaction_hash'] for r in rows}) == 9,
         'inclusion_cashflow_scope')
    need([r['historical_rank_in_nine'] for r in rows] == list(range(1, 10)),
         'inclusion_rank_order')
    source = {r['transaction_hash']: r for r in ledger['records']}
    need(len(source) == len(ledger['records']) == 127, 'inclusion_ledger_scope')
    observations = capture['records']
    need(type(observations) is list and len(observations) == 6, 'inclusion_capture_count')
    by_key = {}
    for item in observations:
        need(type(item['rank']) is int and item['rank'] in (1, 2, 3)
             and item['kind'] in ('transaction', 'block'), 'inclusion_capture_scope')
        key = (item['rank'], item['kind'])
        need(key not in by_key, 'inclusion_duplicate_capture')
        need(item['response'].get('pagination') is None, 'inclusion_paginated_observation')
        by_key[key] = item
    need(set(by_key) == {(r, k) for r in (1, 2, 3) for k in ('transaction', 'block')},
         'inclusion_capture_inventory')
    result = []
    for row in rows:
        rank, tx_hash = row['historical_rank_in_nine'], row['transaction_hash']
        original = source[tx_hash]
        need(original['block_hash'] == row['block_hash']
             and original['block_number'] == row['block_number'], 'inclusion_source_anchor')
        witness = None
        if rank <= 3:
            tx_capture, block_capture = (by_key[(rank, kind)] for kind in ('transaction', 'block'))
            same(tx_capture['request'], {'tool': 'get_transaction_info', 'chain_id': '1',
                 'transaction_hash': tx_hash}, 'inclusion_transaction_request')
            same(block_capture['request'], {'tool': 'get_block_info', 'chain_id': '1',
                 'number_or_hash': row['block_hash']}, 'inclusion_block_request')
            tx = tx_capture['response']['data']
            block = block_capture['response']['data']['block_details']
            need(type(tx['block_number']) is int and type(tx['position']) is int
                 and type(block['height']) is int, 'inclusion_anchor_types')
            need(tx['block_number'] == block['height'] == row['block_number']
                 and tx['position'] == original['transaction_index']
                 and block['hash'] == row['block_hash'], 'inclusion_observed_anchor')
            need(tx['timestamp'] == block['timestamp']
                 and utc(tx['timestamp']) <= utc(capture['capture_recorded_at']),
                 'inclusion_observation_time')
            need(tx['status'] == 'ok' and tx['result'] == 'success'
                 and tx['is_pending_update'] is False and block['is_pending_update'] is False,
                 'inclusion_unsettled_observation')
            # This capture is type-2 only. Do not silently apply it to blob/L2 fees.
            need(type(tx['type']) is int and tx['type'] == 2, 'inclusion_unsupported_tx_type')
            receipt = original['receipt']
            need(uint(receipt['blob_gas_wei']) == 0, 'inclusion_blob_fee_outside_scope')
            need(tx['gas_used'] == receipt['gas_used']
                 and tx['gas_price'] == receipt['effective_gas_price_wei'],
                 'inclusion_receipt_disagreement')
            need(tx['base_fee_per_gas'] == block['base_fee_per_gas'], 'inclusion_base_fee_disagreement')
            split = split_execution_fee(tx['gas_used'], tx['gas_price'], block['base_fee_per_gas'])
            cap, tip_cap = uint(tx['max_fee_per_gas']), uint(tx['max_priority_fee_per_gas'])
            need(uint(tx['gas_price']) == min(cap, uint(block['base_fee_per_gas']) + tip_cap),
                 'inclusion_effective_price_mismatch')
            need(tx['fee'] == {'type': 'actual', 'value': split['execution_gas_paid_wei']}
                 and receipt['execution_gas_wei'] == split['execution_gas_paid_wei']
                 and receipt['total_gas_paid_wei'] == split['execution_gas_paid_wei']
                 and row['full_transaction_gas_wei'] == split['execution_gas_paid_wei'],
                 'inclusion_total_fee_mismatch')
            need(tx['transaction_burnt_fee'] == split['base_fee_burn_wei']
                 and tx['priority_fee'] == split['priority_fee_paid_wei'], 'inclusion_fee_split_mismatch')
            witness = {**split, 'gas_used': tx['gas_used'], 'effective_gas_price_wei': tx['gas_price'],
                'base_fee_per_gas_wei': block['base_fee_per_gas'],
                'transaction_sender': address(tx['from']),
                'event_liquidator_address': row['liquidator_address'],
                'block_fee_recipient': address(block['miner']['hash']),
                'fee_recipient_builder_identity': None,
                'transaction_capture_sha256': digest(canonical(tx_capture)),
                'block_capture_sha256': digest(canonical(block_capture)),
                'original_receipt_evidence_sha256': receipt['receipt_evidence_sha256'],
                'priority_fee_is_included_in_execution_gas': True,
                'direct_fee_recipient_transfer_wei': None,
                'total_builder_compensation_wei': None,
                'builder_share_of_bonus_wad': None,
                'full_internal_trace_available': False,
                'observation_scope': 'INDEXER_FEE_FIELDS_MATCH_RETAINED_DRPC_RECEIPT_FIELDS',
                'transaction_block_hash_returned_by_transaction_tool': False,
                'independent_full_receipt_parity': False}
        result.append({'transaction_hash': tx_hash, 'historical_rank_in_nine': rank,
            'block_number': row['block_number'], 'block_hash': row['block_hash'],
            'cashflow_record_commitment': row['record_commitment_sha256'],
            'inclusion_status': 'EXECUTION_FEE_SPLIT_OBSERVED' if witness else 'UNOBSERVED',
            'fee_witness': witness, 'complete_costs': False, 'complete_net_profit_wei': None,
            'nqc_execution': False, 'titan_coverage_proven': False})
    return result


def build_inclusion_report(directory=EVIDENCE, root=ROOT):
    capture = load_capture(directory)
    cashflow, ledger = build_cashflow(directory, root), build_ledger(directory, root)
    rows = reconcile(cashflow, ledger, capture)
    observed = [r['fee_witness'] for r in rows if r['fee_witness'] is not None]
    report = {'schema': SCHEMA, 'status': 'HISTORICAL_INCLUSION_FEES_PARTIAL',
        'scope': 'TOP_THREE_RETROSPECTIVE_WETH_WINNERS_WITHIN_NINE_CASE_SAMPLE',
        'cashflow_report_commitment': cashflow['report_commitment_sha256'],
        'historical_ledger_commitment': ledger['ledger_commitment_sha256'],
        'capture_sha256': CAPTURE_SHA256, 'capture_recorded_at': capture['capture_recorded_at'],
        'trust_basis': 'REVIEWED_CONNECTED_BLOCKSCOUT_CAPTURE_NOT_CRYPTOGRAPHIC_RECEIPT_PROOF',
        'records': rows, 'acquisition_failures': copy.deepcopy(capture['acquisition_failures']),
        'summary': {'historical_corpus_transactions': 127, 'weth_sample_transactions': 9,
            'execution_fee_split_observations': len(observed), 'unobserved_weth_rows': 9-len(observed),
            'observed_zero_priority_fee_rows': sum(w['priority_fee_paid_wei'] == '0' for w in observed),
            'execution_gas_paid_wei_observed_subset': str(sum(int(w['execution_gas_paid_wei']) for w in observed)),
            'base_fee_burn_wei_observed_subset': str(sum(int(w['base_fee_burn_wei']) for w in observed)),
            'priority_fee_paid_wei_observed_subset': str(sum(int(w['priority_fee_paid_wei']) for w in observed)),
            'direct_builder_payment_observations': 0, 'complete_paid_cost_rows': 0,
            'titan_covered_executions': 0},
        'fee_formula_source': 'https://eips.ethereum.org/EIPS/eip-1559',
        'live_acquisition_during_replay': False, 'current_market_coverage_proven': False,
        'authorities': dict(AUTHORITIES)}
    report['report_commitment_sha256'] = digest(canonical(report))
    return report


def verify_inclusion_report(report, directory=EVIDENCE, root=ROOT):
    expected = build_inclusion_report(directory, root)
    same(report, expected, 'inclusion_report_differs_from_sources')
    return expected


def store_inclusion_report(path, root=ROOT):
    upstream = store_execution_report(path, root)
    parent = upstream['batch']; objects = read_batch(path, parent)
    objects[CAPTURE_NAME] = read_regular(Path(root)/'omega/evidence'/CAPTURE_NAME)
    with tempfile.TemporaryDirectory(prefix='omega-inclusion-admit-') as tmp:
        for name, raw in objects.items(): (Path(tmp)/name).write_bytes(raw)
        report = build_inclusion_report(Path(tmp), root)
    objects[REPORT_NAME] = canonical(report)
    objects[BINDING_NAME] = canonical({'execution_batch': parent})
    return {'batch': admit(path, objects, parents=[parent]), 'parent': parent,
            'root_batch': upstream['parents']['ledger'], 'report': report}


def query_inclusion_report(path, batch, root=ROOT):
    objects = read_batch(path, batch)
    binding = strict_json(objects[BINDING_NAME])
    need(set(binding) == {'execution_batch'}, 'inclusion_parent_inventory')
    parent = binding['execution_batch']
    same(audit_store(path)['dependencies'].get(batch), [parent], 'inclusion_missing_declared_parent')
    query_execution_report(path, parent, root)
    inherited = read_batch(path, parent)
    need(set(objects) == set(inherited) | {CAPTURE_NAME, REPORT_NAME, BINDING_NAME},
         'inclusion_batch_inventory')
    need(all(objects[n] == b for n, b in inherited.items()), 'inclusion_inherited_bytes_changed')
    with tempfile.TemporaryDirectory(prefix='omega-inclusion-query-') as tmp:
        for name, raw in objects.items(): (Path(tmp)/name).write_bytes(raw)
        return verify_inclusion_report(strict_json(objects[REPORT_NAME]), Path(tmp), root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = build_inclusion_report()
    if args.output:
        with args.output.open('xb') as stream: stream.write(canonical(report))
    print(json.dumps({'status': report['status'], **report['summary'],
                     'report_commitment_sha256': report['report_commitment_sha256']}, sort_keys=True))


if __name__ == '__main__': main()
