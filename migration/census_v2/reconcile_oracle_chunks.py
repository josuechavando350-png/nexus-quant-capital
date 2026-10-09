#!/usr/bin/env python3
"""Reconstruct retained oracle observations without network access."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from reconcile_temporal_core import canon, read_core
from verify_server_recovery import parse, require, sha

ARCHIVE_SHA = 'd73716fa61495906c9cbfdcc4442c25804cd47550a9de0f4a32ca287459e2e50'
START, END = 25880316, 26095351
START_HASH = '0x0b29e0c8c1997f059f82e7fed67e047269f68422ab194d56546c1c9833469d96'


def integer(v, lo=0, hi=2**64):
    require(type(v) is int and lo <= v < hi, 'integer bounds/type')
    return v


def hash_bytes(value):
    require(isinstance(value, str) and re.fullmatch(r'0x[0-9a-f]{64}', value) is not None, 'parent hash shape')
    return bytes.fromhex(value[2:])


def observations(doc):
    a, b = integer(doc['start_block']), integer(doc['end_block'])
    require(a <= b and b - a < 50, 'chunk bounds')
    require(integer(doc['block_count']) == b - a + 1 == len(doc['headers']), 'chunk cardinality')
    changes = doc['changes']
    require(integer(doc['change_count']) == len(changes) and len(changes) > 0, 'change cardinality')
    by_block = {}
    last_change = a - 1
    for row in changes:
        n = integer(row['block_number'])
        require(a <= n <= b and n > last_change, 'change order/duplicate')
        by_block[n] = row
        last_change = n
    require(a in by_block, 'first checkpoint missing')
    prices = [None] * 67
    result = []
    digest = hashlib.sha256()
    for n, header in zip(range(a, b + 1), doc['headers']):
        require(isinstance(header, list) and len(header) == 2, 'header shape')
        ts, parent = integer(header[0]), header[1]
        parent_bytes = hash_bytes(parent)
        if result:
            require(ts > result[-1]['timestamp'], 'timestamp order')
        if n in by_block:
            row = by_block[n]
            require(type(row['timestamp']) is int and row['timestamp'] == ts and row['parent_hash'] == parent, 'change/header mismatch')
            indices = []
            for pair in row['changed']:
                require(isinstance(pair, list) and len(pair) == 2, 'price change shape')
                idx, value = integer(pair[0], 0, 67), pair[1]
                require(isinstance(value, str) and re.fullmatch(r'[1-9][0-9]*', value) is not None, 'price string')
                price = integer(int(value), 1, 2**256)
                require(n == a or prices[idx] != price, 'redundant price change')
                indices.append(idx)
                prices[idx] = price
            require(indices == sorted(set(indices)) and len(indices) > 0, 'duplicate/unordered price indices')
            if n == a:
                require(indices == list(range(67)), 'incomplete checkpoint')
        o = {'block_number': n, 'timestamp': ts, 'parent_hash': parent, 'prices': list(prices)}
        digest.update(n.to_bytes(8, 'big') + ts.to_bytes(8, 'big') + parent_bytes)
        for price in prices:
            digest.update(price.to_bytes(32, 'big'))
        result.append(o)
    require(result[0] == doc['first'] and result[-1] == doc['last'], 'checkpoint endpoints')
    require(digest.hexdigest() == doc['digest_sha256'], 'observation digest mismatch')
    return result


def reconcile(archive, core):
    require(sha(archive.read_bytes()) == ARCHIVE_SHA, 'oracle archive pin')
    original = read_core(core)
    summary = parse(original['full-block-oracle/drpc/provider-summary.json'])
    liquidation_rows = [parse(x) for x in original['rmc016-liquidation-block-price-authority.jsonl'].splitlines()]
    liquidations = {r['block_number']: r for r in liquidation_rows}
    require(len(liquidations) == len(liquidation_rows) == 123, 'liquidation price inventory')
    expected = [f'chunk-{a:08d}-{min(END,a+49):08d}.json' for a in range(START, END+1, 50)]
    transitions, manifest_hash = hashlib.sha256(), hashlib.sha256()
    transition_count = paired_blocks = matched_prices = matched_hashes = 0
    paired_ranges = []
    previous = None
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) == 4397, 'oracle member inventory')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names), 'unsafe member')
        inventory = parse(z.read('recovery-manifest.json'))['files']
        require(len(inventory) == 4396 and {r['member'] for r in inventory} == set(names)-{'recovery-manifest.json'}, 'recovery inventory')
        for row in inventory:
            raw = z.read(row['member'])
            require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'recovery file hash')
        require(z.read('drpc/provider-summary.json') == original['full-block-oracle/drpc/provider-summary.json'], 'historical oracle summary')
        require(sorted(n.removeprefix('drpc/') for n in names if n.startswith('drpc/chunk-')) == expected, 'full provider chunk coverage')
        secondary = {n.removeprefix('nodies/') for n in names if n.startswith('nodies/chunk-')}
        require(len(secondary) == 93 and secondary.issubset(set(expected)), 'partial provider scope')
        for name in expected:
            doc = parse(z.read('drpc/' + name))
            rows = observations(doc)
            require(doc['provider'] == 'drpc' and name == f"chunk-{doc['start_block']:08d}-{doc['end_block']:08d}.json", 'chunk path/provider')
            if name in secondary:
                other = parse(z.read('nodies/' + name))
                require(other['provider'] == 'nodies' and observations(other) == rows, 'provider observation mismatch')
                paired_blocks += len(rows)
                paired_ranges.append([doc['start_block'], doc['end_block']])
            manifest_hash.update(canon({k: doc[k] for k in ['start_block', 'end_block', 'block_count', 'digest_sha256', 'change_count']}))
            for row in rows:
                n = row['block_number']
                if previous is not None:
                    require(n == previous['block_number'] + 1 and row['timestamp'] > previous['timestamp'], 'global continuity')
                    if n == START + 1:
                        require(row['parent_hash'] == START_HASH, 'start anchor mismatch')
                    if n - 1 in liquidations:
                        require(row['parent_hash'] == liquidations[n-1]['block_hash'], 'next-parent liquidation hash mismatch')
                        matched_hashes += 1
                if n in liquidations:
                    ref = liquidations[n]
                    require(row['prices'] == [int(v) for v in ref['prices']] and row['timestamp'] == ref['timestamp']
                            and row['parent_hash'] == ref['parent_hash'], 'liquidation oracle vector mismatch')
                    matched_prices += 1
                diff = [[i, str(v)] for i, v in enumerate(row['prices']) if previous is None or v != previous['prices'][i]]
                if diff:
                    transitions.update(canon({'block_number': n, 'timestamp': row['timestamp'], 'parent_hash': row['parent_hash'], 'changed': diff}))
                    transition_count += 1
                previous = row
        require(previous['block_number'] == END, 'end block')
        require(transitions.hexdigest() == summary['transition_ledger_sha256'] == sha(z.read('drpc/oracle-price-block-transitions.jsonl')), 'rederived transition ledger')
        require(manifest_hash.hexdigest() == summary['chunk_manifest_sha256'], 'rederived chunk manifest')
        require(transition_count == summary['transition_block_count'] and matched_prices == matched_hashes == 123, 'conservation counters')
    return {
        'schema': 'nqc-oracle-chunk-reconciliation-v1', 'status': 'PASS_WITH_EXPLICIT_GAPS',
        'archive_sha256': ARCHIVE_SHA, 'verifier_sha256': sha(Path(__file__).read_bytes()),
        'start_block': START, 'end_block': END, 'primary_blocks': END-START+1, 'primary_chunks': len(expected),
        'assets_per_block': 67, 'recomputed_observation_digests': len(expected)+len(secondary),
        'secondary_chunks': len(secondary), 'secondary_blocks': paired_blocks,
        'secondary_missing_blocks': END-START+1-paired_blocks, 'secondary_ranges': paired_ranges,
        'observed_provider_mismatches': 0, 'transition_rows_rederived': transition_count,
        'transition_ledger_sha256': transitions.hexdigest(), 'chunk_manifest_sha256': manifest_hash.hexdigest(),
        'liquidation_vectors_matched': matched_prices, 'liquidation_hashes_matched_to_next_parent': matched_hashes,
        'canonical_end_hash_proven_by_these_chunks': False,
        'full_canonical_lineage_independently_proven': False,
        'scope': 'RETAINED_HISTORICAL_BLOCK_STATE_NOT_TRANSACTION_PRESTATE',
        'acquisition_received_at_available': False, 'available_to_nqc_before_winner_proven': False,
        'independent_provider_acquisition_authenticated': False, 'full_dual_provider_coverage': False,
        'new_rpc_acquisition': False, 'new_producer_certified': False,
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['archive', 'core', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    try:
        report = reconcile(a.archive, a.core)
    except Exception as e:
        (a.output / 'failure.json').write_bytes(canon({'status': 'FAIL', 'reason': str(e)}))
        raise
    (a.output / 'report.json').write_bytes(canon(report))
    print(json.dumps({k:v for k,v in report.items() if k != 'secondary_ranges'}, sort_keys=True))
