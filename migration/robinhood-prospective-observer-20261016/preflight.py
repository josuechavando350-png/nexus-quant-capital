#!/usr/bin/env python3
"""Two public reads to test whether fresh prospective data is available."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from read_rpc import Reader, canonical, header, qty, need


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    reader = Reader(args.out, limit=2)
    report = {'kind': 'FRESHNESS_PREFLIGHT_NOT_OPPORTUNITY_SAMPLE', 'started_wall_ns': time.time_ns(),
              'reader_source_sha256': hashlib.sha256(Path(__file__).with_name('read_rpc.py').read_bytes()).hexdigest(),
              'live_transactions': 0, 'opportunities_evaluated': 0}
    try:
        report['chain_id'] = qty(reader.call('eth_chainId', [], 'chain'))
        need(report['chain_id'] == 4663, 'WRONG_CHAIN')
        raw = reader.call('eth_getBlockByNumber', ['latest', False], 'latest-header')
        report['header'] = header(raw)
        report['header_age_seconds_at_receipt'] = reader.records[-1]['received_wall_ns'] // 10**9 - report['header']['timestamp']
        header(raw, reader.records[-1]['received_wall_ns'])
        report['status'] = 'FRESH_SINGLE_ENDPOINT_AVAILABLE'
    except Exception as error:
        report['status'] = 'BLOCKED'
        report['reason'] = type(error).__name__ + ': ' + str(error)[:180]
    report['requests'] = reader.count
    report['finished_wall_ns'] = time.time_ns()
    (args.out / 'report.json').write_bytes(canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
