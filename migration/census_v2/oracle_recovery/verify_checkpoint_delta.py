#!/usr/bin/env python3
"""Verify a later closed-file delta anchored to the exact checkpoint-002 prefix."""
import argparse
from datetime import datetime
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

import collect as c
import resume
import verify_continuation as full

BASE_ARCHIVE_SHA = '913b4c530d53207e450ff72e21ad0a0b420af0b80574faee329c161f3daca18c'
BASE_READBACK_SHA = '96b872955193c762bc0de9d62b317fd9bd7804571adff527741a7bfc673542ef'
BASE_CLOSED_FILES = 43
BASE_BLOCKS = 43000
PRODUCER_COMMIT = 'c163b876d3310855f1db45bfc3ab4189b24d865b'


def verify(evidence, primary, base_readback):
    checkpoint_raw = (evidence / 'progress.json').read_bytes()
    checkpoint = json.loads(checkpoint_raw)
    base_raw = Path(base_readback).read_bytes()
    base = json.loads(base_raw)
    c.need(c.sha(base_raw) == BASE_READBACK_SHA, 'base readback commitment')
    c.need(base['schema'] == 'nqc-oracle-continuation-readback-v1'
           and base['new_blocks_verified'] == BASE_BLOCKS
           and base['closed_files_verified'] == BASE_CLOSED_FILES
           and base['full_secondary_price_coverage'] is False, 'base checkpoint scope')
    parts = json.loads((Path(__file__).parent / 'sequential-checkpoint-002.parts.json').read_bytes())
    c.need(parts['sha256'] == BASE_ARCHIVE_SHA and parts['bytes'] == 15143401, 'base archive commitment')
    c.need(checkpoint['schema'] == 'nqc-oracle-sequential-continuation-v1'
           and checkpoint['producer_repository'] == 'josuechavando350-png/nexus-quant-capital'
           and checkpoint['producer_commit'] == PRODUCER_COMMIT, 'producer scope')
    for name, expected in [('resume.py', checkpoint['resume_source_sha256']),
                           ('collect.py', resume.COLLECTOR_SHA),
                           ('resume-plan.json', resume.PLAN_SHA),
                           ('assets.json', resume.ASSETS_SHA)]:
        c.need(c.sha((evidence / name).read_bytes()) == expected, 'captured source/input identity')
    c.need((evidence / 'resume.py').read_bytes() == Path(resume.__file__).read_bytes()
           and (evidence / 'collect.py').read_bytes() == Path(c.__file__).read_bytes(), 'current source parity')
    plan = json.loads((evidence / 'resume-plan.json').read_bytes())
    numbers = resume.plan_blocks(plan)
    c.need(checkpoint['requested_blocks'] == len(numbers)
           and checkpoint['plan_sha256'] == resume.PLAN_SHA
           and plan['already_covered_blocks'] == 5170, 'plan binding')
    completed = checkpoint['completed_files']
    c.need(len(completed) > BASE_CLOSED_FILES, 'no new closed files')
    c.need(completed[:BASE_CLOSED_FILES] == base['closed_file_commitments'], 'base prefix commitments changed')
    c.need(all(item['complete'] for item in completed), 'incomplete file listed as closed')

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

    last_received = datetime.fromisoformat(base['latest_received_at'])
    delta_commitments, receipts, batches = [], [], 0
    observed = BASE_BLOCKS
    for item in completed[BASE_CLOSED_FILES:]:
        c.need(item['plan_offset'] == observed
               and item['file'] == f'capture-{observed:06d}.jsonl.gz', 'delta order')
        raw = (evidence / item['file']).read_bytes()
        c.need((len(raw), c.sha(raw)) == (item['bytes'], item['sha256']), 'delta capture commitment')
        chunk = numbers[observed:observed + 1000]
        c.need(item['requested_blocks'] == item['observed_blocks'] == len(chunk), 'delta chunk conservation')
        rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
        c.need(len(rows) == (len(chunk) + 9) // 10, 'delta batch conservation')
        for i, record in enumerate(rows):
            batch = chunk[i * 10:i * 10 + 10]
            sent, received = full.verify_prices(record, batch, hashes, data, expected)
            c.need(sent >= last_received, 'delta chronology')
            last_received = received
            receipts.append(record['received_at'])
            batches += 1
        observed += len(chunk)
        delta_commitments.append(item)
    c.need(checkpoint['failure'] is None
           and checkpoint['status'] in {'RUNNING', 'COMPLETE_REQUESTED_MISSING_BLOCKS'},
           'healthy checkpoint state')
    c.need(BASE_BLOCKS < observed <= checkpoint['observed_blocks'] < observed + 1000
           and checkpoint['observed_blocks'] <= len(numbers), 'counter bounds')
    terminal = checkpoint['status'] == 'COMPLETE_REQUESTED_MISSING_BLOCKS'
    if terminal:
        c.need(observed == len(numbers) and checkpoint['failure'] is None
               and checkpoint['attempted_rpc_calls'] == observed + 3
               and checkpoint['attempted_http_requests'] == (observed + 9) // 10 + 3,
               'terminal conservation')
    c.need(checkpoint['census_certified'] is False and checkpoint['gas_spent'] is False
           and checkpoint['historical_decision_time_observation'] is False, 'expanded authority')
    return {'schema': 'nqc-oracle-continuation-delta-readback-v1',
            'status': 'PASS_WITH_EXPLICIT_LIMITS', 'producer_commit': PRODUCER_COMMIT,
            'verifier_sha256': c.sha(Path(__file__).read_bytes()),
            'checkpoint_sha256': c.sha(checkpoint_raw), 'base_archive_sha256': BASE_ARCHIVE_SHA,
            'base_readback_sha256': BASE_READBACK_SHA, 'plan_sha256': resume.PLAN_SHA,
            'base_closed_files': BASE_CLOSED_FILES, 'base_blocks_verified': BASE_BLOCKS,
            'delta_closed_files_verified': len(delta_commitments),
            'delta_file_commitments': delta_commitments,
            'delta_blocks_verified': observed - BASE_BLOCKS,
            'delta_price_values_matched': (observed - BASE_BLOCKS) * 67,
            'total_continuation_blocks_verified': observed,
            'total_price_values_matched': observed * 67,
            'cross_operator_mismatches': 0, 'delta_earliest_received_at': min(receipts),
            'latest_received_at': max(receipts),
            'secondary_union_verified_blocks': plan['already_covered_blocks'] + observed,
            'secondary_missing_blocks': len(numbers) - observed,
            'current_capture_counter': checkpoint['observed_blocks'],
            'entire_continuation_verified': terminal,
            'full_secondary_price_coverage': terminal and observed == len(numbers),
            'original_decision_time_proven': False,
            'independent_underlying_nodes_proven': False,
            'census_certified': False, 'gas_spent': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['evidence', 'primary', 'base-readback', 'out']:
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    result = verify(args.evidence, args.primary, args.base_readback)
    with args.out.open('xb') as stream:
        stream.write(c.canon(result))
    print(json.dumps({k: v for k, v in result.items() if k != 'delta_file_commitments'}, sort_keys=True))
