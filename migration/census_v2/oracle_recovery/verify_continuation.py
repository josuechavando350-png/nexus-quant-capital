#!/usr/bin/env python3
"""Verify closed continuation checkpoints without counting an open capture file."""
import argparse
from datetime import datetime
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

import collect as c
import resume

PRODUCER_COMMIT = 'c163b876d3310855f1db45bfc3ab4189b24d865b'


def exchange(record):
    c.need(record['url'] == c.ENDPOINT and record['http_status'] == 200
           and record['transport_error'] is None, 'unsuccessful/substituted transport')
    for field in ['request', 'response']:
        c.need(c.sha(record[field + '_body'].encode()) == record[field + '_sha256'], 'body digest')
    sent, received = [datetime.fromisoformat(record[k]) for k in ['sent_at', 'received_at']]
    c.need(sent.tzinfo is not None and received.tzinfo is not None and sent <= received, 'request chronology')
    return json.loads(record['request_body']), record['response_body'], sent, received


def verify_prices(record, batch, hashes, data, expected):
    requests, body, sent, received = exchange(record)
    c.need(requests == [c.price_request(n, hashes[n - c.START], data) for n in batch],
           'request plan/hash/canonicality/calldata')
    actual = c.decode_batch(body, requests)
    for n in batch:
        c.need(actual[n] == expected(n), 'price vector mismatch')
    return sent, received


def verify(evidence, primary):
    checkpoint_raw = (evidence / 'progress.json').read_bytes()
    checkpoint = json.loads(checkpoint_raw)
    c.need(checkpoint['schema'] == 'nqc-oracle-sequential-continuation-v1'
           and checkpoint['producer_repository'] == 'josuechavando350-png/nexus-quant-capital'
           and checkpoint['producer_commit'] == PRODUCER_COMMIT, 'producer scope')
    for name, expected in [('resume.py', checkpoint['resume_source_sha256']), ('collect.py', resume.COLLECTOR_SHA),
                           ('resume-plan.json', resume.PLAN_SHA), ('assets.json', resume.ASSETS_SHA)]:
        c.need(c.sha((evidence / name).read_bytes()) == expected, 'captured source/input identity')
    c.need((evidence / 'resume.py').read_bytes() == Path(resume.__file__).read_bytes()
           and (evidence / 'collect.py').read_bytes() == Path(c.__file__).read_bytes(), 'current source parity')
    plan = json.loads((evidence / 'resume-plan.json').read_bytes())
    numbers = resume.plan_blocks(plan)
    c.need(checkpoint['requested_blocks'] == len(numbers) and checkpoint['plan_sha256'] == resume.PLAN_SHA,
           'checkpoint plan binding')
    hashes = c.block_bindings(primary)
    data = c.calldata(json.loads((evidence / 'assets.json').read_bytes()))
    @lru_cache(maxsize=16)
    def primary_chunk(a):
        b = min(c.END, a + 49)
        doc = json.loads((primary / f'chunk-{a:08d}-{b:08d}.json').read_bytes())
        changes = {x['block_number']: x for x in doc['changes']}
        c.need(len(changes) == len(doc['changes']), 'primary duplicate transition')
        prices, result, digest = [None] * 67, [], hashlib.sha256()
        for n, (timestamp, parent) in zip(range(a, b + 1), doc['headers']):
            for i, value in changes.get(n, {}).get('changed', []):
                prices[i] = int(value)
            c.need(all(type(v) is int and 0 < v < 2**256 for v in prices), 'primary vector')
            digest.update(n.to_bytes(8, 'big') + timestamp.to_bytes(8, 'big') + bytes.fromhex(parent[2:]))
            digest.update(b''.join(v.to_bytes(32, 'big') for v in prices))
            result.append(prices.copy())
        c.need(digest.hexdigest() == doc['digest_sha256'], 'primary observation digest')
        return result
    def expected(n):
        a = c.START + ((n - c.START) // 50) * 50
        return primary_chunk(a)[n - a]

    with gzip.open(evidence / 'anchors.jsonl.gz', 'rb') as stream:
        anchors = [json.loads(line) for line in stream]
    c.need(len(anchors) == 3, 'anchor inventory')
    last_received = None
    for i, record in enumerate(anchors):
        requests, body, sent, received = exchange(record)
        method, params, value = [
            ('eth_chainId', [], '0x1'),
            ('eth_getBlockByNumber', [hex(c.START), False], (c.START, c.START_HASH)),
            ('eth_getBlockByNumber', [hex(c.END), False], (c.END, c.END_HASH)),
        ][i]
        c.need(requests == {'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}, 'anchor request')
        response = json.loads(body)
        c.need(response.get('id') == i and 'error' not in response, 'anchor response')
        actual = response['result']
        c.need((actual if i == 0 else (int(actual['number'], 16), actual['hash'])) == value, 'anchor value')
        c.need(last_received is None or sent >= last_received, 'sequential anchor chronology')
        last_received = received
    observed, batches, receipts, commitments = 0, 0, [], []
    ignored = []
    for item in checkpoint['completed_files']:
        if not item['complete']:
            ignored.append(item['file'])
            continue
        c.need(not ignored and item['plan_offset'] == observed
               and item['file'] == f'capture-{observed:06d}.jsonl.gz', 'closed checkpoint order')
        raw = (evidence / item['file']).read_bytes()
        c.need(c.sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'closed capture commitment')
        chunk = numbers[observed:observed + 1000]
        c.need(item['requested_blocks'] == item['observed_blocks'] == len(chunk), 'chunk conservation')
        rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
        c.need(len(rows) == (len(chunk) + 9) // 10, 'captured batch conservation')
        for i, record in enumerate(rows):
            batch = chunk[i * 10:i * 10 + 10]
            sent, received = verify_prices(record, batch, hashes, data, expected)
            c.need(sent >= last_received, 'sequential capture chronology')
            last_received = received
            receipts.append(record['received_at'])
            batches += 1
        observed += len(chunk)
        commitments.append(item)
    c.need(0 < observed <= checkpoint['observed_blocks'] <= len(numbers), 'checkpoint counter bounds')
    full = checkpoint['status'] == 'COMPLETE_REQUESTED_MISSING_BLOCKS'
    if full:
        c.need(observed == len(numbers) and not ignored and checkpoint['failure'] is None
               and checkpoint['attempted_rpc_calls'] == observed + 3
               and checkpoint['attempted_http_requests'] == batches + 3, 'terminal acquisition conservation')
    c.need(checkpoint['census_certified'] is False and checkpoint['gas_spent'] is False
           and checkpoint['historical_decision_time_observation'] is False, 'expanded authority')
    return {'schema': 'nqc-oracle-continuation-readback-v1', 'status': 'PASS_WITH_EXPLICIT_LIMITS',
            'producer_commit': checkpoint['producer_commit'], 'verifier_sha256': c.sha(Path(__file__).read_bytes()),
            'checkpoint_sha256': c.sha(checkpoint_raw), 'plan_sha256': resume.PLAN_SHA,
            'closed_files_verified': len(commitments), 'closed_file_commitments': commitments,
            'new_blocks_verified': observed, 'price_values_matched': observed * 67,
            'cross_operator_mismatches': 0, 'earliest_received_at': min(receipts), 'latest_received_at': max(receipts),
            'secondary_union_verified_blocks': plan['already_covered_blocks'] + observed,
            'secondary_missing_blocks': len(numbers) - observed,
            'current_capture_counter': checkpoint['observed_blocks'],
            'ignored_incomplete_files': ignored, 'entire_continuation_verified': full,
            'full_secondary_price_coverage': full and observed == len(numbers),
            'original_decision_time_proven': False, 'independent_underlying_nodes_proven': False,
            'census_certified': False, 'gas_spent': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['evidence', 'primary', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.evidence, args.primary)
    with args.out.open('xb') as stream:
        stream.write(c.canon(result))
    print(json.dumps({k: v for k, v in result.items() if k != 'closed_file_commitments'}, sort_keys=True))
