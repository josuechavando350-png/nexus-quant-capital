#!/usr/bin/env python3
"""Sequential continuation of a pinned missing-block plan after Retry-After."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import json
from pathlib import Path
import re
import signal
import time

import collect as c

PLAN_SHA = 'a2b1345f3f6f59ff26e385b8a899c008d3509fd683a3e93718c8075b64194dec'
COLLECTOR_SHA = 'b9112088a9b4ccc8742fe656362fae88c0a37b12b6f8232d78ddf294ae79d56c'
ASSETS_SHA = '7e5f97cbdd20a3154af9e862465c999658d3ee67a4c795ec9c570ebfd8cd98d2'


def plan_blocks(plan):
    c.need(plan['schema'] == 'nqc-oracle-missing-block-plan-v1'
           and plan['endpoint'] == c.ENDPOINT and plan['workers'] == 1
           and plan['maximum_batch_size'] == 10 and plan['interval_seconds'] >= 1.1,
           'plan scope/rate')
    result, previous = [], c.START - 1
    for pair in plan['missing_ranges']:
        c.need(isinstance(pair, list) and len(pair) == 2 and all(type(n) is int for n in pair), 'range shape')
        a, b = pair
        c.need(c.START <= a <= b <= c.END and a > previous, 'range order/overlap/bounds')
        result.extend(range(a, b + 1))
        previous = b
    c.need(len(result) == plan['missing_blocks'] == 209866
           and plan['already_covered_blocks'] + len(result) == c.END - c.START + 1,
           'plan conservation')
    return result


def retry_after_elapsed(plan, instant):
    last = datetime.fromisoformat(plan['previous_rate_limit_received_at'])
    c.need(last.tzinfo is not None and instant.tzinfo is not None, 'rate-limit timezone')
    c.need(instant >= last + timedelta(seconds=plan['previous_retry_after_seconds']), 'Retry-After not elapsed')


def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(c.canon(value))
    tmp.replace(path)


def execute(args, clock=time.monotonic, pause=time.sleep):
    plan_raw = args.plan.read_bytes()
    c.need(c.sha(plan_raw) == PLAN_SHA, 'missing-block plan identity')
    c.need(c.sha(Path(c.__file__).read_bytes()) == COLLECTOR_SHA, 'original collector identity')
    c.need(c.sha(args.assets.read_bytes()) == ASSETS_SHA, 'original asset list identity')
    c.need(re.fullmatch(r'[0-9a-f]{40}', args.producer_commit) is not None, 'producer commit shape')
    plan = json.loads(plan_raw)
    numbers = plan_blocks(plan)
    retry_after_elapsed(plan, datetime.now(timezone.utc))
    # Fixed lock prevents overlapping continuation workers on this device.
    lock = open('/tmp/nqc-census-oracle-resume.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    args.out.mkdir(parents=True, exist_ok=False)
    for src, name in [(args.plan, 'resume-plan.json'), (args.assets, 'assets.json'),
                      (Path(__file__), 'resume.py'), (Path(c.__file__), 'collect.py')]:
        (args.out / name).write_bytes(src.read_bytes())
    hashes = c.block_bindings(args.primary)
    data = c.calldata(json.loads(args.assets.read_bytes()))
    acq = c.Acquisition(args.out)
    started, deadline, next_send = c.now(), clock() + 24 * 3600, clock()
    state = {'schema': 'nqc-oracle-sequential-continuation-v1', 'status': 'RUNNING',
             'producer_repository': 'josuechavando350-png/nexus-quant-capital',
             'producer_commit': args.producer_commit, 'started_at': started,
             'plan_sha256': PLAN_SHA, 'resume_source_sha256': c.sha(Path(__file__).read_bytes()),
             'collector_sha256': COLLECTOR_SHA, 'asset_document_sha256': ASSETS_SHA,
             'requested_blocks': len(numbers), 'observed_blocks': 0,
             'attempted_http_requests': 0, 'attempted_rpc_calls': 0,
             'workers': 1, 'minimum_request_interval_seconds': plan['interval_seconds'],
             'maximum_batch_size': 10, 'maximum_runtime_seconds': 86400,
             'completed_files': [], 'failure': None, 'census_certified': False,
             'gas_spent': False, 'new_subscriptions': False,
             'historical_decision_time_observation': False}
    atomic_json(args.out / 'progress.json', state)

    def interrupted(signum, frame):
        raise InterruptedError('continuation interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)

    def request(payload, stream):
        nonlocal next_send
        c.need(clock() < deadline, '24-hour continuation budget exhausted')
        delay = max(0, next_send - clock())
        if delay:
            pause(delay)
        next_send = clock() + plan['interval_seconds']
        return acq.request(payload, stream)

    try:
        with gzip.open(args.out / 'anchors.jsonl.gz', 'wb') as stream:
            for i, (method, params, expected) in enumerate([
                ('eth_chainId', [], '0x1'),
                ('eth_getBlockByNumber', [hex(c.START), False], (c.START, c.START_HASH)),
                ('eth_getBlockByNumber', [hex(c.END), False], (c.END, c.END_HASH)),
            ]):
                payload = {'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}
                response = json.loads(request(payload, stream))
                c.need(response.get('jsonrpc') == '2.0' and response.get('id') == i
                       and 'error' not in response, 'anchor identity/error')
                value = response['result']
                c.need((value if i == 0 else (int(value['number'], 16), value['hash'])) == expected, 'anchor value')
        # Files contain at most 1,000 requested blocks; each flush is recoverable.
        for offset in range(0, len(numbers), 1000):
            chunk = numbers[offset:offset + 1000]
            path = args.out / f'capture-{offset:06d}.jsonl.gz'
            observed = 0
            try:
                with gzip.open(path, 'wb', compresslevel=6) as stream:
                    for index in range(0, len(chunk), 10):
                        batch = chunk[index:index + 10]
                        payload = [c.price_request(n, hashes[n - c.START], data) for n in batch]
                        c.decode_batch(request(payload, stream), payload)
                        observed += len(batch)
                        state['observed_blocks'] += len(batch)
                        state['last_successful_block'] = batch[-1]
                        state['last_successful_response_at'] = c.now()
                        state['attempted_http_requests'] = acq.http_requests
                        state['attempted_rpc_calls'] = acq.calls
                        atomic_json(args.out / 'progress.json', state)
            finally:
                raw = path.read_bytes()
                state['completed_files'].append({'file': path.name, 'bytes': len(raw),
                    'sha256': c.sha(raw), 'requested_blocks': len(chunk), 'observed_blocks': observed,
                    'complete': observed == len(chunk), 'plan_offset': offset})
            atomic_json(args.out / 'progress.json', state)
            print(json.dumps({'observed_blocks': state['observed_blocks'], 'requested_blocks': len(numbers),
                              'completed_files': len(state['completed_files']), 'last_block': chunk[-1]}, sort_keys=True), flush=True)
        c.need(state['observed_blocks'] == len(numbers), 'final block conservation')
        state['status'] = 'COMPLETE_REQUESTED_MISSING_BLOCKS'
    except Exception as exc:
        state['status'] = 'STOPPED_INCOMPLETE'
        state['failure'] = {'type': type(exc).__name__, 'message': str(exc), 'recorded_at': c.now()}
    finally:
        state['finished_at'] = c.now()
        state['attempted_http_requests'] = acq.http_requests
        state['attempted_rpc_calls'] = acq.calls
        atomic_json(args.out / 'progress.json', state)
        atomic_json(args.out / 'acquisition.json', state)
        print(json.dumps({k: v for k, v in state.items() if k != 'completed_files'}, sort_keys=True), flush=True)
        lock.close()
    return 0 if state['status'] == 'COMPLETE_REQUESTED_MISSING_BLOCKS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ['plan', 'primary', 'assets', 'out']:
        parser.add_argument('--' + field, required=True, type=Path)
    parser.add_argument('--producer-commit', required=True)
    raise SystemExit(execute(parser.parse_args()))
