#!/usr/bin/env python3
"""Offline readback of complete historical logs and receipt observations.

Actual acquisition bytes and current receive times are kept distinct from
historical event time, underlying-node independence and execution admission.
"""
import argparse
import gzip
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'ci/nqc-census'), str(V2), str(V2 / 'additional_evidence')]
from recover_historical_rpc import canonical, decode_response, need, PROVIDERS, sha
from verify_winner_recovery import rpc_records, parse, gather, sortkey
from rmc016_resume_verified_receipts import authenticated_drpc_checkpoint
from rmc016_two_operator_receipts import receipt_normalized
from rmc016_aave_event_legs import authentic_source, bind_logs
from reconcile_additional import origin_check
from rmc016_tenderly_receipt_crosscheck import reconcile as tenderly_reconcile
from reconcile_winner_economics import semantic_receipt
from replay_historical_regressions import blob

BASE = 'cb4db600301c49196eac6e3b45e308c8b1d09e8b'
ARCHIVE_SHA = 'f5683de132f26671e62ee31a82c9e1c05fcaf2ff8e7a0a8ad2a0c447bc9efeeb'
SOURCE_FILES = {
    'migration/census_v2/recover_historical_rpc.py',
    'ci/nqc-census/rmc016_two_operator_receipts.py',
    'ci/nqc-census/rmc016_collect_winner_events.py',
    'ci/nqc-census/rmc016_probe_historical_rpc.py',
    'ci/nqc-census/rmc016_resume_verified_receipts.py',
}


def source_identity(evidence):
    packed = HERE / 'complete-historical-evidence.zip'
    need(packed.stat().st_size == 665007 and sha(packed.read_bytes()) == ARCHIVE_SHA,
         'captured acquisition archive changed')
    with zipfile.ZipFile(packed) as z:
        names = z.namelist()
        need(len(names) == len(set(names)) == 699 and set(names) ==
             {str(p.relative_to(evidence)) for p in evidence.rglob('*') if p.is_file()},
             'captured acquisition inventory mismatch')
        for name in names:
            rel = Path(name)
            need(not rel.is_absolute() and '..' not in rel.parts, 'unsafe captured path')
            target = evidence / rel
            need(not target.is_symlink() and target.read_bytes() == z.read(name),
                 'captured acquisition bytes differ: ' + name)
    manifest = parse((evidence / 'source-manifest.json').read_bytes())
    need(manifest['producer_repository'] == 'josuechavando350-png/nexus-quant-capital'
         and manifest['producer_commit'] == BASE and len(manifest['files']) == 5
         and {r['path'] for r in manifest['files']} == SOURCE_FILES,
         'collector source identity mismatch')
    seen = set()
    for row in manifest['files']:
        rel = Path(row['path'])
        need(not rel.is_absolute() and '..' not in rel.parts and row['path'] not in seen,
             'unsafe or duplicate collector source path')
        seen.add(row['path'])
        raw = (evidence / rel).read_bytes()
        expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', BASE + ':' + row['path']],
                                           text=True).strip()
        need(blob(raw) == expected == row['git_blob'] and len(raw) == row['bytes']
             and sha(raw) == row['sha256'] and (ROOT / rel).read_bytes() == raw,
             'collector source bytes changed')
    return manifest


def records_for(directory, provider_id, mode):
    report = parse((directory / 'recovery-report.json').read_bytes())
    expected_status = 'FULL_WINDOW_EVENTS_MATCH' if mode == 'logs' else 'FULL_RECEIPT_CHECKPOINT_MATCH'
    need(report['status'] == expected_status and report['provider_id'] == provider_id
         and report['mode'] == mode and report['real_market_census_closed'] is False
         and report['original_decision_time_observation_proven'] is False,
         'incomplete acquisition or expanded authority')
    need(report['verifier_sha256'] == sha((V2 / 'recover_historical_rpc.py').read_bytes()),
         'collector digest changed')
    need(report['source_event_zip_sha256'] == sha((V2 / 'economic_archives/inputs/11524139188.zip').read_bytes())
         and report['checkpoint_zip_sha256'] == sha((V2 / 'economic_archives/inputs/11524199698.zip').read_bytes()),
         'collector original source pins changed')
    records = rpc_records(directory, allow_partial=False)
    provider = next(p for p in PROVIDERS if p[0] == provider_id)
    need(len(records) == report['rpc_calls'] and len(records) <= 1200, 'request budget/count mismatch')
    for row, req, result in records:
        need((row['provider_id'], row['operator'], row['url']) == provider,
             'RPC operator or endpoint substitution')
    return report, records, provider


def compare_full_receipts(records, receipts, events, ids, tenderly):
    found, commitments = {}, []
    for row, request, raw in records:
        need(request['method'] == 'eth_getTransactionReceipt' and len(request['params']) == 1,
             'unexpected receipt request')
        tx = request['params'][0]
        need(tx in receipts and tx not in found and tx in tenderly, 'missing/duplicate receipt identity')
        normalized = receipt_normalized(tx, events[tx], raw)
        need(normalized == receipts[tx], 'original normalized receipt mismatch')
        sem = semantic_receipt(raw, normalized)
        need(sem == semantic_receipt(tenderly[tx], normalized), 'full cross-operator receipt/log mismatch')
        found[tx] = normalized
        commitments.append({'transaction_hash': tx, 'semantic_sha256': sha(canonical(sem)),
                            'drpc_request_sha256': row['request_sha256'],
                            'drpc_response_sha256': row['response_sha256'],
                            'drpc_received_at': row['received_at']})
    need(list(found) == ids and len(found) == 127, 'incomplete or reordered receipt population')
    return found, commitments


def reconcile(evidence):
    sources = source_identity(evidence)
    event_zip = V2 / 'economic_archives/inputs/11524139188.zip'
    drpc_zip = V2 / 'economic_archives/inputs/11524199698.zip'
    receipts, events, ids = authenticated_drpc_checkpoint(drpc_zip, event_zip)
    expected = sorted([e for rows in events.values() for e in rows], key=sortkey)
    log_dir = evidence / 'blockpi-full-window'
    receipt_dir = evidence / 'drpc-full-receipts'
    log_report, log_records, provider = records_for(log_dir, 'blockpi', 'logs')
    cursor = iter(log_records)
    def replay(url, method, params):
        row, request, result = next(cursor)
        need(row['url'] == url and request['method'] == method and request['params'] == params,
             'log replay request changed')
        return result
    discovery, observed, observed_ids, _ = gather(provider, call=replay, chunk=1024,
                                                 call_budget=1200, min_rpc_interval=0)
    need(next(cursor, None) is None and discovery['coverage_complete'] is True
         and observed == expected and observed_ids == ids, 'full historical event population mismatch')
    need(canonical(discovery) == (log_dir / 'discovery-report.json').read_bytes()
         and b''.join(canonical(r) for r in observed) == (log_dir / 'verified-events.jsonl').read_bytes(),
         'collector/replay log outputs differ')
    raw_logs = [log for _, request, response in log_records if request['method'] == 'eth_getLogs'
                for log in response]
    original_events, _ = authentic_source(event_zip)
    legs = bind_logs(original_events, b''.join(canonical(r) for r in raw_logs))
    origin_check()
    tenderly_raw = gzip.decompress((V2 / 'additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz').read_bytes())
    exchanges = [parse(line) for line in tenderly_raw.splitlines()]
    tenderly_reconcile(event_zip, drpc_zip, exchanges)
    tenderly = {r['params'][0]: r['result'] for r in exchanges if r['method'] == 'eth_getTransactionReceipt'}
    receipt_report, receipt_records, _ = records_for(receipt_dir, 'drpc', 'receipts')
    found, commitments = compare_full_receipts(receipt_records, receipts, events, ids, tenderly)
    need((receipt_dir / 'verified-receipts.jsonl').read_bytes() == b''.join(canonical(found[t]) for t in ids),
         'collector/replay receipt outputs differ')
    preflight = parse((evidence / 'preflight/result.json').read_bytes())
    request = (evidence / 'preflight/request.json').read_bytes()
    response = (evidence / 'preflight/response.json').read_bytes()
    need(sha(request) == preflight['request_sha256'] and sha(response) == preflight['response_sha256']
         and preflight['status'] == 'READ_ONLY_ETHEREUM_ACCESS_CONFIRMED'
         and decode_response(response, 1) == '0x1', 'read-only preflight mismatch')
    return {
        'schema': 'nqc-complete-historical-window-recovery-v1',
        'status': 'COMPLETE_EXECUTED_EVENT_WINDOW_AND_FULL_RECEIPT_PARITY',
        'producer_repository': sources['producer_repository'], 'producer_repository_id': 1411047452,
        'collector_base_commit': BASE, 'consumer_sha256': sha(Path(__file__).read_bytes()),
        'acquisition_archive_sha256': ARCHIVE_SHA, 'acquisition_archive_members': 699,
        'source_manifest_sha256': sha((evidence / 'source-manifest.json').read_bytes()),
        'scope': {'chain_id': 1, 'protocol': 'AAVE_V3_ETHEREUM',
                  'start_block': 25880316, 'end_block': 26095351, 'covered_blocks': 215036},
        'executed_liquidation_events': len(observed), 'winner_transactions': len(ids),
        'new_log_operator': 'BlockPI', 'original_log_operator': 'Blockscout',
        'full_window_event_commitments_match': True, 'decoded_liquidation_legs': len(legs),
        'decoded_liquidation_legs_sha256': sha(b''.join(canonical(r) for r in legs)),
        'new_receipt_operator': 'dRPC', 'comparison_receipt_operator': 'Tenderly',
        'full_semantic_receipt_log_matches': len(found), 'receipt_commitments': commitments,
        'historical_competitor_gas_wei': str(sum(int(r['total_gas_paid_wei']) for r in found.values())),
        'raw_http_json_request_response_bytes_preserved_for_new_acquisitions': True,
        'new_per_request_receive_times_preserved': True,
        'acquisitions': [{'directory': d.name, 'manifest_sha256': sha((d / 'manifest.json').read_bytes()),
                          'rpc_calls': len(rs), 'first_sent_at': rs[0][0]['sent_at'],
                          'last_received_at': rs[-1][0]['received_at']}
                         for d, rs in ((log_dir, log_records), (receipt_dir, receipt_records))],
        'old_failed_or_partial_acquisitions_relabelled': False,
        'original_drpc_failed_parent_promoted': False,
        'independent_underlying_execution_nodes_proven': False,
        'full_oracle_or_canonical_header_lineage_completed': False,
        'original_decision_time_observation_proven': False,
        'failed_and_unexecuted_opportunity_universe_complete': False,
        'complete_costs_or_nqc_capture_proven': False,
        'active_mxn_2000_policy_changed': False, 'gas_spent_by_acquisition_wei': '0',
        'new_workflow_or_independent_certification_issued': False, 'real_market_census_closed': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    need(not args.out.exists(), 'append-only report required')
    report = reconcile(args.evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(report))
    print(report['status'])
