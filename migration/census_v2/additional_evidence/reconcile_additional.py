#!/usr/bin/env python3
"""Offline supplemental research; preserves V2 policy, classifications and authority."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'ci/nqc-census'), str(V2)]

from rmc016_winner_net_audit import canonical, digest, parse_json, require
from rmc016_tenderly_receipt_crosscheck import reconcile as receipts_reconcile
from rmc015_full_window_incidence import reconcile as window_reconcile
from rmc015_material_frontier import audit as original_frontier
from verify_winner_recovery import PINS, transport

D08_SHA = '9431ea07144ae78e68e0ffcc7f650fa32068ee63fb53ca41ff8a062b87845913'
D09_SHA = '9aa6a4beb3ebc90f40d07d1889f84c1bcf94b3dea90b0e7b596dc6ff70fda0f6'
BASE = '81a268b93841f5d5df5970c547363c6c00dd76ef'


def origin_check():
    origin = parse_json((HERE / 'origins.json').read_bytes())
    require(origin['destination_repository'] == 'josuechavando350-png/nexus-quant-capital'
            and origin['destination_repository_id'] == 1411047452
            and origin['destination_base_commit'] == BASE, 'destination identity mismatch')
    seen = set()
    for row in origin['files']:
        rel = Path(row['path'])
        require(not rel.is_absolute() and '..' not in rel.parts and row['path'] not in seen,
                'unsafe or duplicate evidence path')
        seen.add(row['path'])
        raw = (HERE / rel).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256']
                and blob == row['git_blob'], 'research source byte mismatch: ' + row['path'])
    require(len(seen) == 9, 'incomplete research origin set')
    return origin


def join_v2_ledger(exchanges, ledger_bytes):
    rows = [parse_json(line) for line in ledger_bytes.splitlines()]
    by_tx = {row['transaction_hash']: row for row in rows}
    require(len(by_tx) == len(rows) == 127, 'V2 transaction membership mismatch')
    found = set()
    total = 0
    new_payers = []
    for exchange in exchanges:
        if exchange['method'] != 'eth_getTransactionReceipt':
            continue
        raw = exchange['result']
        tid = exchange['params'][0]
        require(tid in by_tx and tid not in found, 'V2 transaction substitution')
        found.add(tid)
        row = by_tx[tid]
        gas = row['historical_gas']
        paid = int(raw['gasUsed'], 16) * int(raw['effectiveGasPrice'], 16)
        require(raw['transactionHash'].lower() == tid and raw['blockHash'].lower() == row['block_hash']
                and int(raw['blockNumber'], 16) == row['block_number']
                and int(raw['transactionIndex'], 16) == row['transaction_index'], 'V2 block/position mismatch')
        require(str(int(raw['gasUsed'], 16)) == gas['gas_used']
                and str(int(raw['effectiveGasPrice'], 16)) == gas['effective_gas_price_wei']
                and str(paid) == gas['whole_transaction_wei'], 'V2 gas mismatch')
        if gas['payer'] is None:
            new_payers.append({'transaction_hash': tid, 'observed_receipt_sender': raw['from'].lower()})
        else:
            require(raw['from'].lower() == gas['payer'], 'V2 known payer mismatch')
        require(gas['counted_times'] == 1 and gas['is_nqc_gas'] is False,
                'historical gas double counting or NQC attribution')
        require(row['classification'] == 'INSUFFICIENT_EVIDENCE'
                and row['complete_realized_net_usd_wad'] is None
                and str(row['admitted_nqc_executable_value_usd_wad']) == '0',
                'unsupported V2 economic promotion')
        total += paid
    require(found == set(by_tx), 'incomplete V2 receipt join')
    return {'transaction_count': len(found), 'ledger_sha256': digest(ledger_bytes),
            'whole_transaction_gas_wei': str(total), 'gas_counted_times_per_transaction': 1,
            'existing_known_payers_matched': len(found) - len(new_payers),
            'previously_unknown_payer_observations': new_payers,
            'incremental_gas_charged_wei': '0', 'economic_classifications_changed': False}


def verify(events, drpc, d08, d09):
    origin = origin_check()
    sources = []
    for pin, archive in zip(PINS[:2], (events, drpc)):
        meta = parse_json((V2 / 'evidence/winner-api' / (str(pin[0]) + '.json')).read_bytes())
        sources.append(transport(pin, meta, archive.read_bytes()))
    exchanges = [parse_json(line) for line in gzip.decompress(
        (HERE / 'recovered-rmc016/tenderly-receipts-20261009.jsonl.gz').read_bytes()).splitlines()]
    receipts = receipts_reconcile(events, drpc, exchanges)
    ledger = (V2 / 'evidence/economics/replay/winner-economic-ledger.jsonl').read_bytes()
    joined = join_v2_ledger(exchanges, ledger)
    require(joined['whole_transaction_gas_wei'] == receipts['gas_paid_wei'], 'cross-report gas mismatch')
    summary, watchers = original_frontier(
        d08, d09, D08_SHA, D09_SHA,
        expected_d08_commit='36c732a36789e1967ce7178010889427ad7cf0f2',
        expected_d09_commit='6db82ca89d4ef3a66a1b236de95670a6967eb3ea',
        emit_watchlist=True, evaluation_start_block=26095352)
    watchlist = b''.join(canonical(row) for row in watchers)
    raw_window = gzip.decompress((HERE / 'recovered-rmc016/full-7200-window-20261009.json.gz').read_bytes())
    documents = parse_json(b'{"documents":' + raw_window.strip() + b'}')['documents']
    window = window_reconcile(documents, watchlist)
    policy = parse_json((V2 / 'capital-policy.json').read_bytes())
    require(policy['currency'] == 'MXN' and policy['operator_gas_budget_centavos'] == 200000,
            'existing V2 peso gas policy changed')
    return {
        'schema': 'nqc-v2-additional-receipt-window-reconciliation-v1',
        'status': 'SUPPLEMENTAL_HISTORICAL_RESEARCH_RECONCILED',
        'producer_repository': origin['destination_repository'],
        'producer_repository_id': 1411047452, 'research_base_commit': BASE,
        'source_recording_origins_sha256': digest((HERE / 'origins.json').read_bytes()),
        'consumer_sha256': digest(Path(__file__).read_bytes()),
        'historical_source_archives': sources,
        'receipt_parity': receipts, 'existing_v2_ledger_join': joined,
        'successor_window': window,
        'private_cohort_source_archives': {'d08_sha256': D08_SHA, 'd09_sha256': D09_SHA},
        'cohort_summary_sha256': digest(canonical(summary)),
        'recording_format': origin['recording_format'],
        'original_http_transport_bytes_preserved': False,
        'per_request_receive_times_preserved': False,
        'original_decision_time_availability_proven': False,
        'independent_underlying_nodes_proven': False,
        'historical_30_day_oracle_coverage_expanded': False,
        'historical_30_day_log_scan_completed_by_this_report': False,
        'gas_policy_sha256': digest((V2 / 'capital-policy.json').read_bytes()),
        'capital_or_execution_admissions_changed': False,
        'new_workflow_or_source_certification_claimed': False,
        'real_market_census_closed': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('events', 'drpc', 'd08', 'd09', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.exists(), 'append-only report required')
    result = verify(args.events, args.drpc, args.d08, args.d09)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(result))
    print(result['status'])
