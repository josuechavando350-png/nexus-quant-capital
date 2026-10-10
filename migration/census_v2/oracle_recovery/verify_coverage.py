#!/usr/bin/env python3
"""Offline, set-exact coverage readback; never a Census terminal authority."""
import argparse
from datetime import datetime
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import collect as c
import resume
import reconcile as earlier
import verify_continuation as continuation

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
BASE = '5f13f585a84048af7d1a3cd383aa9d2dacacfca2'
WINDOW = set(range(c.START, c.END + 1))


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            c.need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def ranges(numbers):
    result = []
    for n in sorted(numbers):
        if result and result[-1][1] + 1 == n:
            result[-1][1] = n
        else:
            result.append([n, n])
    return result


def covered_before(original, directories):
    """Enumerate actual authenticated records, not a summary's block counter.

    Called only after earlier.reconcile has checked every source and vector.
    Retained/direct overlaps are intentionally unioned, never added twice.
    """
    retained, direct = set(), set()
    with zipfile.ZipFile(original) as archive:
        for name in archive.namelist():
            if name.startswith('nodies/chunk-'):
                doc = strict(archive.read(name))
                numbers = set(range(doc['start_block'], doc['end_block'] + 1))
                c.need(retained.isdisjoint(numbers), 'duplicate retained block')
                retained.update(numbers)
    for directory in directories:
        for path in sorted(directory.glob('capture-*.jsonl.gz')):
            for raw in gzip.decompress(path.read_bytes()).splitlines():
                record = strict(raw)
                if record['http_status'] != 200:
                    continue  # Failure was authenticated by earlier.reconcile.
                requests = strict(record['request_body'])
                numbers = [q['id'] for q in requests]
                c.need(all(type(n) is int for n in numbers)
                       and len(numbers) == len(set(numbers))
                       and direct.isdisjoint(numbers), 'duplicate direct block')
                direct.update(numbers)
    return retained, direct


def exact_partition(prior, plan, closed_count):
    c.need(prior <= WINDOW and len(prior) == plan['already_covered_blocks'], 'prior block set')
    planned = resume.plan_blocks(plan)
    c.need(set(planned) == WINDOW - prior, 'plan is not exact prior complement')
    c.need(type(closed_count) is int and 0 < closed_count <= len(planned), 'closed count bounds/type')
    closed = set(planned[:closed_count])
    c.need(prior.isdisjoint(closed), 'continuation repeats prior coverage')
    covered = prior | closed
    return covered, WINDOW - covered


def checkpoint_contract(directory):
    raw = (directory / 'progress.json').read_bytes()
    doc = strict(raw)
    c.need(doc['status'] in {'RUNNING', 'STOPPED_INCOMPLETE', 'COMPLETE_REQUESTED_MISSING_BLOCKS'},
           'unknown acquisition status')
    c.need(type(doc['workers']) is int and doc['workers'] == 1
           and type(doc['maximum_batch_size']) is int and doc['maximum_batch_size'] == 10
           and type(doc['minimum_request_interval_seconds']) in (int, float)
           and doc['minimum_request_interval_seconds'] >= 1.1, 'worker/rate/batch contract')
    c.need(doc['collector_sha256'] == resume.COLLECTOR_SHA
           and doc['asset_document_sha256'] == resume.ASSETS_SHA
           and doc['new_subscriptions'] is False, 'source or authority contract')
    for key in ['requested_blocks', 'observed_blocks', 'attempted_http_requests', 'attempted_rpc_calls']:
        c.need(type(doc[key]) is int and doc[key] >= 0, 'counter bounds/type')
    start = datetime.fromisoformat(doc['started_at'])
    c.need(start.tzinfo is not None, 'start timezone')
    resume.retry_after_elapsed(strict((directory / 'resume-plan.json').read_bytes()), start)
    closed = 0
    for item in doc['completed_files']:
        c.need(type(item['complete']) is bool, 'complete flag type')
        for key in ['plan_offset', 'bytes', 'requested_blocks', 'observed_blocks']:
            c.need(type(item[key]) is int and item[key] >= 0, 'file counter bounds/type')
        if item['complete']:
            closed += item['observed_blocks']
    terminal = doc['status'] == 'COMPLETE_REQUESTED_MISSING_BLOCKS'
    acquisition = directory / 'acquisition.json'
    if terminal or doc['status'] == 'STOPPED_INCOMPLETE':
        c.need(acquisition.is_file() and acquisition.read_bytes() == raw,
               'terminal progress/acquisition identity')
        c.need(datetime.fromisoformat(doc['finished_at']) >= start, 'finish chronology')
    else:
        c.need(not acquisition.exists() and doc['failure'] is None, 'running/final state conflict')
    if terminal:
        c.need(doc['failure'] is None and closed == doc['observed_blocks'] == doc['requested_blocks'],
               'terminal closed-block conservation')
    elif doc['status'] == 'STOPPED_INCOMPLETE':
        c.need(isinstance(doc['failure'], dict) and bool(doc['failure']), 'missing preserved failure')
    return doc, terminal


def event_scope(report):
    c.need(all(type(report['scope'][key]) is int for key in
               ['chain_id', 'start_block', 'end_block', 'covered_blocks']), 'event scope integer types')
    c.need(report['scope'] == {'chain_id': 1, 'protocol': 'AAVE_V3_ETHEREUM',
                              'start_block': c.START, 'end_block': c.END, 'covered_blocks': len(WINDOW)}
           and report['status'] == 'COMPLETE_EXECUTED_EVENT_WINDOW_AND_FULL_RECEIPT_PARITY'
           and report['executed_liquidation_events'] == 139
           and report['winner_transactions'] == report['full_semantic_receipt_log_matches'] == 127
           and report['full_window_event_commitments_match'] is True, 'event/receipt coverage scope')
    c.need((report['new_log_operator'], report['original_log_operator'],
            report['new_receipt_operator'], report['comparison_receipt_operator']) ==
           ('BlockPI', 'Blockscout', 'dRPC', 'Tenderly'), 'event/receipt operator identity')
    c.need(report['real_market_census_closed'] is False, 'inherited terminal authority')


def source_bindings():
    result = []
    for relative in ['oracle_recovery/collect.py', 'oracle_recovery/resume.py',
                     'oracle_recovery/reconcile.py', 'oracle_recovery/verify_continuation.py',
                     'reconcile_oracle_chunks.py', 'reconcile_temporal_core.py',
                     'verify_server_recovery.py', 'full_window_recovery/reconcile.py']:
        path = V2 / relative
        expected = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE + ':' + str(path.relative_to(ROOT))])
        c.need(path.read_bytes() == expected, 'pinned consumer dependency changed: ' + relative)
        result.append({'path': str(path.relative_to(ROOT)), 'sha256': c.sha(expected)})
    return result


def verify(original, d08, pilot, partial, checkpoint, primary, full_window):
    dependencies = source_bindings()
    doc, terminal = checkpoint_contract(checkpoint)
    prior = earlier.reconcile(original, d08, [pilot, partial])
    plan = strict((checkpoint / 'resume-plan.json').read_bytes())
    c.need(c.sha(c.canon(prior)) == plan['source_reconciliation_sha256'], 'prior reconciliation commitment')
    retained, direct = covered_before(original, [pilot, partial])
    c.need(len(retained) == prior['retained_secondary_blocks']
           and len(direct) == prior['new_direct_observed_blocks'], 'prior record conservation')
    current = continuation.verify(checkpoint, primary)
    covered, missing = exact_partition(retained | direct, plan, current['new_blocks_verified'])
    c.need(len(covered) == current['secondary_union_verified_blocks']
           and len(missing) == current['secondary_missing_blocks'], 'coverage readback disagreement')
    # Separate module identity avoids colliding with the oracle module named reconcile.
    spec = importlib.util.spec_from_file_location('nqc_coverage_full_window', V2 / 'full_window_recovery/reconcile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    events = module.reconcile(full_window)
    event_scope(events)
    complete = not missing and terminal and current['entire_continuation_verified'] is True
    c.need(complete == current['full_secondary_price_coverage'], 'terminal coverage disagreement')
    # Block coordinates make both missing coverage and overlaps independently inspectable.
    partition = {'retained_secondary_ranges': ranges(retained), 'direct_capture_ranges': ranges(direct),
                 'prior_overlap_ranges': ranges(retained & direct),
                 'closed_continuation_ranges': ranges(set(resume.plan_blocks(plan)[:current['new_blocks_verified']])),
                 'verified_secondary_union_ranges': ranges(covered), 'missing_ranges': ranges(missing)}
    report = {
        'schema': 'nqc-historical-coverage-gate-v1',
        'status': 'HISTORICAL_COVERAGE_READY_FOR_REVIEW' if complete else 'PARTIAL_COVERAGE_NOT_A_MILESTONE',
        'consumer_sha256': c.sha(Path(__file__).read_bytes()), 'dependency_base_commit': BASE,
        'dependency_source_bindings': dependencies,
        'scope': {'chain_id': 1, 'start_block': c.START, 'end_block': c.END, 'assets': 67},
        'prior_readback_sha256': c.sha(c.canon(prior)),
        'continuation_readback_sha256': c.sha(c.canon(current)),
        'event_receipt_readback_sha256': c.sha(c.canon(events)),
        'partition_sha256': c.sha(c.canon(partition)),
        'original_oracle_archive_sha256': earlier.ARCHIVE_SHA,
        'retained_secondary_blocks': len(retained), 'earlier_direct_blocks': len(direct),
        'prior_overlap_not_double_counted': len(retained & direct),
        'closed_continuation_blocks': current['new_blocks_verified'],
        'closed_continuation_prices_matched': current['price_values_matched'],
        'captured_but_not_verified_blocks': doc['observed_blocks'] - current['new_blocks_verified'],
        'verified_secondary_union_blocks': len(covered), 'missing_secondary_blocks': len(missing),
        'unique_matched_price_coordinates': len(covered) * 67,
        'oracle_operators': ['dRPC', 'Nodies'], 'price_mismatches': 0,
        'executed_events': 139, 'complete_receipts': 127,
        'terminal_acquisition_exact_file_present': terminal,
        'milestone_10_coverage_ready': complete, 'milestone_15_ready': False, 'milestone_20_ready': False,
        'census_closed': False, 'independent_authority_acceptance': False,
        'original_decision_time_observation_proven': False,
        'independent_underlying_nodes_proven': False, 'full_header_lineage_proven': False,
        'capture_or_profit_admitted': False, 'gas_spent': False,
        'earlier_failure_records_preserved': prior['failed_requests'],
        'continuation_status': doc['status'], 'continuation_failure': doc['failure'],
        'notification_sent': False,
    }
    return {'report.json': report, 'partition.json': partition, 'prior-readback.json': prior,
            'continuation-readback.json': current, 'event-receipt-readback.json': events}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['original', 'd08', 'pilot', 'partial', 'checkpoint', 'primary', 'full-window', 'out']:
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    reports = verify(args.original, args.d08, args.pilot, args.partial, args.checkpoint,
                     args.primary, args.full_window)
    for name, report in reports.items():
        with (args.out / name).open('xb') as stream:
            stream.write(c.canon(report))
    print(json.dumps(reports['report.json'], sort_keys=True))
