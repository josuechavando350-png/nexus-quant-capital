#!/usr/bin/env python3
"""Post-registration reporting only; never changes the cohort or RPC requests."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from common import canonical
from audit_capture import audit
import registry


def units(raw):
    return str(Decimal(raw) / Decimal(10**6))


def summary(folder):
    report = audit(folder)
    journal = [json.loads(line) for line in (folder / 'journal.jsonl').read_text().splitlines()]
    snapshots = [x for x in report['snapshots'] if x['mode'] == 'batch']
    registered = next(x['data'] for x in journal if x['kind'] == 'registered')
    state = registry.load(folder / 'registry.json', registered['policy']) if (folder / 'registry.json').exists() else None
    result = {'status': report['status'], 'registration_commit': report['registration'],
              'started_utc': datetime.fromtimestamp(journal[0]['recorded_wall_ns'] / 10**9, timezone.utc).isoformat(),
              'finished_utc': datetime.fromtimestamp(journal[-1]['recorded_wall_ns'] / 10**9, timezone.utc).isoformat(),
              'elapsed_seconds': report['elapsed_seconds'], 'rpc_calls': report['rpc_calls'],
              'http_requests': report['http_requests'], 'provider_errors': report['rpc_errors'],
              'registry': report['registry'], 'cohort_size': len(report['cohort']['addresses']) if report['cohort'] else None,
              'http_latency_ms': report['http_latency_ms'], 'comparisons': report['comparisons'],
              'batch_rounds': [], 'distinct_snapshot_hashes': len({s['block']['hash'] for s in snapshots}),
              'route_simulations': 0, 'realized_profit': None, 'realized_capture_rate': None,
              'funded_capacity_wei': 0, 'live_broadcasts': 0}
    if state and state['segments']:
        result['indexed_interval_chain_seconds'] = state['checkpoint']['timestamp'] - state['segments'][0]['start']['timestamp']
    for snapshot in snapshots:
        s = snapshot['state']; coverage = s['coverage']
        total = coverage['total_borrow_shares']
        result['batch_rounds'].append({'round': snapshot['round'], 'block': snapshot['block']['number'],
            'block_hash': snapshot['block']['hash'], 'stored_market_debt_usdg': units(s['market'][2]),
            'observed_accrued_debt_usdg_sum': units(sum(p['screen']['debt_usdg_raw'] for p in s['positions'])),
            'coverage': coverage,
            'coverage_pct': str(Decimal(coverage['observed_borrow_shares']) * 100 / Decimal(total)) if total else None,
            'positive_debt_accounts': s['positive_debt_accounts'], 'near_threshold_accounts': s['screen_candidate_count'],
            'computed_unhealthy_accounts': s['computed_unhealthy_count'], 'input_elapsed_ms': snapshot['input_elapsed_ms'],
            'after_header_input_ms': next(f['after_header_input_ms'] for f in report['freshness'] if f['round'] == snapshot['round']),
            'unindexed_tail_blocks': snapshot['block']['number'] - report['registry']['through_block'],
            'minimum_health_margin_bps_floor': min((p['screen']['health_margin_bps_floor'] for p in s['positions'] if p['screen']['debt_usdg_raw'] > 0), default=None)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = summary(args.folder)
    args.out.write_bytes(canonical(result))
    print(json.dumps(result, indent=2))
