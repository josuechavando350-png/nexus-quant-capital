#!/usr/bin/env python3
"""Post-run diagnostics; never changes enrollment or the registered policy."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from audit import audit, journal_rows
from model import accrue
from read_rpc import canonical


def diagnose(folder):
    report = audit(folder)
    rows = journal_rows(folder / 'journal.jsonl')
    snapshots = [r['data'] for r in rows if r['kind'] == 'snapshot']
    samples = []
    intervals = []
    for index, s in enumerate(snapshots):
        assets, _ = accrue(s['market'], s['rate'], s['block']['timestamp'])
        samples.append({'block': s['block']['number'], 'timestamp': s['block']['timestamp'],
                        'stored_market_borrow_assets_usdg': str(Decimal(s['market'][2]) / 10**6),
                        'modeled_accrued_market_borrow_assets_usdg': str(Decimal(assets) / 10**6),
                        'input_acquisition_after_header_ms': (s['inputs_finished_ns'] - s['received_ns']) / 10**6,
                        'borrowers_observed': len(s['positions'])})
        if index:
            previous = snapshots[index-1]['block']
            blocks = s['block']['number'] - previous['number']
            seconds = s['block']['timestamp'] - previous['timestamp']
            intervals.append({'blocks_between_sampled_heads': blocks, 'header_timestamp_delta_seconds': seconds,
                              'mean_ms_per_block_over_interval': str(Decimal(seconds * 1000) / blocks),
                              'unobserved_intermediate_blocks': blocks - 1,
                              'individual_block_latency_measured': False})
    return {'analysis_is_post_run': True, 'registered_selection_rules_changed': False,
            'cohort_size': report['cohort_size'], 'completed_rounds': report['completed_rounds'],
            'empty_recent_cohort_with_nonzero_market_debt': report['cohort_size'] == 0 and bool(snapshots) and all(s['market'][2] > 0 for s in snapshots),
            'rounds': samples, 'sampled_head_intervals': intervals,
            'request_latency_ms': report['request_latency_ms'],
            'duration_seconds': (rows[-1]['recorded_ns'] - rows[0]['recorded_ns']) / 10**9,
            'measurement_scope': 'This execution environment, one public demo, sequential reads; not a provider SLA or sequencer latency.',
            'full_route_prospective_success_observed': report['successful_route_simulations'] > 0,
            'capture_rate_estimate': None, 'profit_estimate': None,
            'next_required_measurement': 'Freeze a persistent borrower registry from independent prior events, then test fresh state acquisition and exact-payload survival with adequate data access.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.folder)
    args.out.write_bytes(canonical(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
