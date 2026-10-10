#!/usr/bin/env python3
"""Recount the retained D08 market inventory; do not certify execution or income."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import zipfile

from analyze_daily_capacity import BASE, HERE, pinned
import reconcile_temporal_core as c


def audit(path):
    readback_raw = pinned(HERE / 'evidence/historical-readback.json')
    source = c.parse(readback_raw)['stages']['d08']
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk); size += len(chunk)
    c.require(digest.hexdigest() == source['archive_sha256'] and
              size == source['archive_bytes'], 'D08 archive identity')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        c.require(len(names) == len(set(names)) == source['members'], 'D08 member inventory')
        manifest_raw = z.read('closeout/evidence-manifest.json')
        manifest = c.parse(manifest_raw)
        c.require(manifest['code_commit'] == source['code_commit'] and
                  manifest['code_tree'] == source['code_tree'], 'D08 producer identity')
        entries = {r['path']: r for r in manifest['artifacts']}
        c.require(len(entries) == len(manifest['artifacts']), 'duplicate manifest entry')
        verified = {}

        def records(name):
            h = hashlib.sha256(); n = 0
            with z.open('closeout/' + name) as stream:
                for line in stream:
                    h.update(line); n += len(line)
                    yield c.parse(line)
            c.require(h.hexdigest() == entries[name]['sha256'] and
                      n == entries[name]['bytes'], 'D08 member identity: ' + name)
            verified[name] = {'sha256': h.hexdigest(), 'bytes': n}

        state, = list(records('state-summary.json'))
        counts = Counter(); stages = Counter(); liquidity = Counter()
        identities = set(); indices = {'AAVE_V3': set(), 'UNISWAP_V2': set()}
        addresses = {'AAVE_V3': set(), 'UNISWAP_V2': set()}
        for row in records('market-state-manifest.jsonl'):
            protocol = row['protocol']
            c.require(protocol in indices, 'unexpected protocol')
            ident = row['market_id']
            c.require(ident not in identities, 'duplicate market identity')
            identities.add(ident)
            index = row['reserve_id'] if protocol == 'AAVE_V3' else row['index']
            address = row['asset'] if protocol == 'AAVE_V3' else row['pair']
            c.require(index not in indices[protocol] and address not in addresses[protocol],
                      'duplicate market index or address')
            indices[protocol].add(index); addresses[protocol].add(address)
            counts[protocol] += 1
            stages[(protocol, row['stage_state_reconstructable'])] += 1
            if protocol == 'UNISWAP_V2':
                liquidity[row['liquidity_state']] += 1
        for protocol, scope, count_key in [('AAVE_V3', 'aave_v3', 'aave_markets'),
                                           ('UNISWAP_V2', 'uniswap_v2', 'v2_markets')]:
            n = state[count_key]
            c.require(indices[protocol] == set(range(n)), 'market index coverage')
            metric, = state['stage_metrics'][scope]
            c.require(counts[protocol] == metric['input'] == n and
                      stages[(protocol, 'ADVANCE')] == metric['advanced'] and
                      n - metric['advanced'] == metric['rejected'] and metric['unknown'] == 0,
                      'market stage conservation')
        c.require(state['observation_anchor']['block_number'] == 26095351 and
                  state['code_commit'] == source['code_commit'] and
                  state['code_tree'] == source['code_tree'], 'state anchor or producer')
    capital_raw = pinned(HERE / 'evidence/capital-stream-readback.json')
    capital = c.parse(capital_raw)
    return {'schema': 'nqc-existing-market-inventory-readback-v1', 'source_commit': BASE,
            'consumer_sha256': c.sha(Path(__file__).read_bytes()),
            'historical_readback_sha256': c.sha(readback_raw), 'source': source,
            'manifest_sha256': c.sha(manifest_raw), 'verified_members': verified,
            'market_rows_recounted': len(identities), 'counts_by_protocol': dict(counts),
            'stages': [{'protocol': p, 'decision': s, 'count': n}
                       for (p, s), n in sorted(stages.items())],
            'uniswap_v2_liquidity_labels': dict(sorted(liquidity.items())),
            'source_state_summary': state,
            'capital_prior_readback': {'report_sha256': c.sha(capital_raw),
                'source_rows': capital['source_rows'], 'source_bytes': capital['source_bytes'],
                'source_sha256': capital['source_sha256'],
                'full_capital_stream_reexecuted_this_review': False,
                'rows_are_distinct_profitable_markets': False},
            'scope': 'EXACT_RETAINED_SINGLE_ANCHOR_STATE_INVENTORY_NOT_30_DAY_ECONOMICS',
            'execution_recertified': False, 'independent_certification': False,
            'profitability_proven': False, 'new_rpc_requests': 0, 'census_closed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--d08', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    report = audit(args.d08)
    with args.output.open('xb') as stream:
        stream.write(c.canon(report))
    print(c.canon({'market_rows_recounted': report['market_rows_recounted'],
                   'counts': report['counts_by_protocol'],
                   'liquidity_labels': report['uniswap_v2_liquidity_labels']}).decode(), end='')
