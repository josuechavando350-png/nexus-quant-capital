#!/usr/bin/env python3
"""Read the original V2 inventory and measure scoped Aave conversion topology.

Paths are structural witnesses at one anchor, never executable quotes, funded
opportunities, global route absences, or economic admission.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = '3c8e9117f09ea3c6a076ab57e30642f8a165a0fe'
SCOPE = 'ETHEREUM_D08_UNISWAP_V2_DIRECT_OR_TWO_HOP_AT_SINGLE_ANCHOR'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(x):
    return (json.dumps(x, sort_keys=True, separators=(',', ':')) + '\n').encode()


def pinned(path):
    raw = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
        BASE + ':' + str(path.relative_to(ROOT))], text=True).strip()
    need(blob == expected, 'pinned source changed: ' + str(path))
    return raw


def records(z, name, entries, verified):
    h = hashlib.sha256(); size = 0
    with z.open('closeout/' + name) as stream:
        for raw in stream:
            h.update(raw); size += len(raw)
            yield json.loads(raw)
    need((h.hexdigest(), size) == (entries[name]['sha256'], entries[name]['bytes']),
         'member identity: ' + name)
    verified[name] = {'sha256': h.hexdigest(), 'bytes': size}


def add_edge(row, endpoints, graph, seen_edges):
    a, b = row['token0'], row['token1']
    need(a != b and a < b, 'noncanonical token pair')
    need((a, b) not in seen_edges, 'duplicate factory token pair')
    seen_edges.add((a, b))
    reserves = row['reserves'][:2]
    need(len(reserves) == 2 and all(type(v) is str and v.isdecimal() and int(v) > 0
                                  for v in reserves), 'positive integer reserves required')
    need(row['factory_membership'] is True, 'factory membership required')
    fee = row['fee_semantics']['swap_fee_bps']
    need(type(fee) is int and 0 <= fee < 10000, 'swap fee bounds')
    witness = {'pair': row['pair'], 'market_id': row['market_id'],
               'index': row['index'], 'token0': a, 'token1': b,
               'reserve0': reserves[0], 'reserve1': reserves[1], 'swap_fee_bps': fee}
    if a in endpoints:
        graph[a][b] = witness
    if b in endpoints:
        graph[b][a] = witness


def routes(endpoints, graph):
    result = []
    for a, b in itertools.permutations(sorted(endpoints), 2):
        left, right = graph[a], graph[b]
        direct = left.get(b)
        common = sorted(set(left).intersection(right) - {a, b})
        paths = ([{'tokens': [a, b], 'pools': [direct]}] if direct else [])
        paths += [{'tokens': [a, mid, b], 'pools': [left[mid], right[mid]]}
                  for mid in common[:3]]
        result.append({'collateral_asset': a, 'debt_asset': b,
            'direct_paths': int(direct is not None), 'two_hop_paths': len(common),
            'two_hop_intermediaries_sha256': sha(canon(common)),
            'path_examples': paths, 'example_limit_two_hop': 3,
            'structural_status': 'PATH_PRESENT_UNPROVEN_EXECUTION' if direct or common
                                 else 'NO_PATH_WITHIN_DECLARED_TOPOLOGY_SCOPE',
            'scope': SCOPE, 'execution_admitted': False, 'complete_net_pnl': None})
    return result


def overlay(candidates, route_rows, endpoints):
    by_route = {(r['collateral_asset'], r['debt_asset']): r for r in route_rows}
    result = []; seen = set()
    for row in sorted(candidates, key=lambda x: x['pair_id']):
        need(row['pair_id'] not in seen, 'duplicate candidate identity')
        seen.add(row['pair_id'])
        a, b = row['collateral_asset'], row['debt_asset']
        need(a in endpoints and b in endpoints, 'candidate asset outside Aave inventory')
        status = row['classification']
        need(status in {'NON_EXECUTABLE', 'INSUFFICIENT_EVIDENCE'}, 'unexpected existing admission')
        need(row['admitted_executable_value_mxn_centavos'] == 0
             and row['net_profit_estimate_mxn_centavos'] is None, 'unexpected positive source value')
        if a == b:
            observation = {'structural_status': 'SAME_ASSET_NO_COLLATERAL_TO_DEBT_SWAP_REQUIRED',
                           'direct_paths': None, 'two_hop_paths': None}
        else:
            r = by_route[(a, b)]
            observation = {k: r[k] for k in ['structural_status', 'direct_paths', 'two_hop_paths']}
        result.append({'pair_id': row['pair_id'], 'borrower': row['borrower'],
            'collateral_asset': a, 'debt_asset': b, 'topology_observation': observation,
            'original_classification': status, 'classification_after_topology': status,
            'original_reasons': row['reasons'], 'scope': SCOPE,
            'admitted_executable_value_mxn_centavos': 0, 'complete_net_pnl': None,
            'global_route_absence_proven': False, 'native_gas_funded': False})
    return result


def build(d08, out):
    need(not out.exists(), 'output already exists')
    source_raw = pinned(HERE / 'evidence/historical-readback.json')
    source = json.loads(source_raw)['stages']['d08']
    h = hashlib.sha256(); size = 0
    with d08.open('rb') as stream:
        for raw in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(raw); size += len(raw)
    need((h.hexdigest(), size) == (source['archive_sha256'], source['archive_bytes']), 'D08 archive identity')
    verified = {}; all_ids = set(); indices = {'AAVE_V3': set(), 'UNISWAP_V2': set()}
    addresses = {'AAVE_V3': set(), 'UNISWAP_V2': set()}
    stages = Counter(); aave = {}
    with zipfile.ZipFile(d08) as z:
        need(len(z.namelist()) == len(set(z.namelist())) == source['members'], 'archive inventory')
        manifest_raw = z.read('closeout/evidence-manifest.json'); manifest = json.loads(manifest_raw)
        need((manifest['code_commit'], manifest['code_tree']) ==
             (source['code_commit'], source['code_tree']), 'producer identity')
        entries = {r['path']: r for r in manifest['artifacts']}
        need(len(entries) == len(manifest['artifacts']), 'duplicate manifest entry')
        state, = list(records(z, 'state-summary.json', entries, verified))
        for row in records(z, 'market-state-manifest.jsonl', entries, verified):
            p = row['protocol']; need(p in indices, 'unexpected protocol')
            ident = row['market_id']; index = row['reserve_id'] if p == 'AAVE_V3' else row['index']
            address = row['asset'] if p == 'AAVE_V3' else row['pair']
            need(ident not in all_ids and index not in indices[p] and address not in addresses[p],
                 'duplicate market identity/index/address')
            all_ids.add(ident); indices[p].add(index); addresses[p].add(address)
            stages[(p, row['stage_state_reconstructable'])] += 1
            if p == 'AAVE_V3': aave[address] = row
        need(len(aave) == state['aave_markets'] == 67, 'Aave scope')
        need(len(indices['UNISWAP_V2']) == state['v2_markets'] == 523424, 'V2 scope')
        for p in indices: need(indices[p] == set(range(len(indices[p]))), 'index coverage')
        need(state['observation_anchor']['block_number'] == 26095351, 'anchor mismatch')
        graph = defaultdict(dict); seen_edges = set(); selection = Counter()
        for row in records(z, 'market-state-manifest.jsonl', entries, verified):
            if row['protocol'] != 'UNISWAP_V2': continue
            if row['stage_state_reconstructable'] != 'ADVANCE':
                selection['STATE_RECONSTRUCTION_REJECTED'] += 1; continue
            if row['liquidity_state'] != 'LIQUID':
                selection['ZERO_LIQUIDITY_IN_ADVANCING_STATE'] += 1; continue
            n = int(row['token0'] in aave) + int(row['token1'] in aave)
            selection[f'POSITIVE_RESERVES_{n}_AAVE_ENDPOINTS'] += 1
            add_edge(row, aave, graph, seen_edges)
        need(sum(selection.values()) == 523424, 'pool partition conservation')
        token_evidence = {}
        for row in records(z, 'token-admission.jsonl', entries, verified):
            if row['token'] in aave and 'AAVE_RESERVE_UNDERLYING' in row['roles']:
                need(row['token'] not in token_evidence, 'duplicate reserve token role')
                token_evidence[row['token']] = row
        need(set(token_evidence) == set(aave), 'Aave token role coverage')
    route_rows = routes(set(aave), graph)
    candidate_raw = pinned(HERE / 'evidence/candidate-classifications.jsonl')
    candidates = [json.loads(raw) for raw in candidate_raw.splitlines()]
    need(len(candidates) == 474 and len({r['borrower'] for r in candidates}) == 400, 'D12 population scope')
    candidate_rows = overlay(candidates, route_rows, aave)
    assets = [{'asset': a, 'reserve_id': aave[a]['reserve_id'], 'market_id': aave[a]['market_id'],
               'adjacent_selected_v2_pools': len(graph[a]),
               'd12_pairs_requiring_asset': sum(a in {r['collateral_asset'], r['debt_asset']} for r in candidates),
               'd12_insufficient_pairs_requiring_asset': sum(a in {r['collateral_asset'], r['debt_asset']}
                   and r['classification'] == 'INSUFFICIENT_EVIDENCE' for r in candidates),
               'token_evidence': token_evidence[a], 'execution_admitted': False}
              for a in sorted(aave)]
    route_bytes = b''.join(canon(r) for r in route_rows)
    outputs = {'routes.jsonl.gz': gzip.compress(route_bytes, mtime=0),
               'assets.jsonl': b''.join(canon(r) for r in assets),
               'd12-routing-overlay.jsonl': b''.join(canon(r) for r in candidate_rows)}
    report = {'schema': 'nqc-aave-v2-routing-topology-v1', 'scope': SCOPE,
        'source_commit': BASE, 'consumer_sha256': sha(Path(__file__).read_bytes()),
        'source': source, 'historical_readback_sha256': sha(source_raw),
        'manifest_sha256': sha(manifest_raw), 'verified_members': verified,
        'anchor': state['observation_anchor'], 'pool_partition': dict(sorted(selection.items())),
        'aave_assets': len(aave), 'aave_assets_with_selected_v2_neighbor': sum(bool(graph[a]) for a in aave),
        'aave_assets_without_selected_v2_neighbor': sorted(a for a in aave if not graph[a]),
        'distinct_directed_asset_conversions': len(route_rows),
        'conversion_status_counts': dict(sorted(Counter(r['structural_status'] for r in route_rows).items())),
        'directed_conversions_with_direct_path': sum(r['direct_paths'] > 0 for r in route_rows),
        'directed_conversions_with_two_hop_path': sum(r['two_hop_paths'] > 0 for r in route_rows),
        'd12_source_sha256': sha(candidate_raw),
        'd12_topology_counts': dict(sorted(Counter(r['topology_observation']['structural_status'] for r in candidate_rows).items())),
        'd12_classification_counts_unchanged': dict(sorted(Counter(r['classification_after_topology'] for r in candidate_rows).items())),
        'd12_classification_by_topology': [{'classification': k[0], 'topology': k[1], 'pairs': n}
            for k, n in sorted(Counter((r['classification_after_topology'],
                r['topology_observation']['structural_status']) for r in candidate_rows).items())],
        'aave_reserve_token_compatibility_counts': dict(sorted(Counter(token_evidence[a]['execution_compatibility']['status'] for a in aave).items())),
        'uncompressed_routes_sha256': sha(route_bytes),
        'outputs': {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in sorted(outputs.items())},
        'path_count_is_opportunity_count': False, 'reserves_are_executable_depth': False,
        'token_execution_proven': False, 'funding_proven': False, 'capture_proven': False,
        'full_costs_proven': False, 'admitted_executable_value_mxn_centavos': 0,
        'complete_net_pnl': None, 'global_route_absence_proven': False,
        'independent_certification': False, 'new_rpc_requests': 0, 'census_closed': False}
    out.mkdir(parents=True)
    for n, b in outputs.items(): (out / n).write_bytes(b)
    (out / 'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--d08', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = build(args.d08, args.out)
    print(json.dumps({k: result[k] for k in ['pool_partition', 'conversion_status_counts',
        'd12_topology_counts', 'aave_reserve_token_compatibility_counts']}, sort_keys=True))
