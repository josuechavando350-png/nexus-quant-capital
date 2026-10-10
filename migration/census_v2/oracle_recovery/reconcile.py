#!/usr/bin/env python3
"""Reconcile new direct calls against immutable historical primary observations."""
import argparse
from datetime import datetime
import gzip
import json
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))
from reconcile_oracle_chunks import ARCHIVE_SHA, observations
from collect import (START, END, START_HASH, END_HASH, ENDPOINT, PRIMARY_PIN, ASSET_SOURCE_PIN,
                     canon, sha, need, calldata, price_request, decode_batch)

CAPTURE_BUNDLES = {
    'pilot': ('oracle-pilot-evidence.zip', 'eef4643d627d3d27b6fd0acaa54afb94dbfdf794bf5b91832acb2b930e53dc35', 413568, 37),
    'remaining': ('oracle-rate-limited-evidence.zip', 'efe884429fdc43af0231406ab951acb23a864ee21812849fa49b0ab323a03318', 490206, 220),
}


def captured_identity(directory):
    need(directory.name in CAPTURE_BUNDLES, 'unknown captured acquisition')
    filename, digest, size, count = CAPTURE_BUNDLES[directory.name]
    archive = HERE / filename
    need(archive.stat().st_size == size and sha(archive.read_bytes()) == digest, 'capture archive commitment')
    root = directory.parent
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        need(len(names) == len(set(names)) == count and set(names) ==
             {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}, 'extracted capture inventory')
        for name in names:
            rel = Path(name)
            need(not rel.is_absolute() and '..' not in rel.parts, 'unsafe archived capture path')
            path = root / rel
            need(not path.is_symlink() and path.read_bytes() == z.read(name), 'extracted capture bytes')
    return {'file': filename, 'sha256': digest, 'bytes': size, 'members': count}


def exchange(record, allow_failed=False):
    need(record['url'] == ENDPOINT, 'substituted transport')
    if not allow_failed:
        need(record['http_status'] == 200 and record['transport_error'] is None, 'unsuccessful transport')
    for field in ['request', 'response']:
        need(sha(record[field + '_body'].encode('utf-8')) == record[field + '_sha256'],
             field + ' body commitment')
    sent, received = [datetime.fromisoformat(record[k]) for k in ['sent_at', 'received_at']]
    need(sent.tzinfo is not None and received.tzinfo is not None and sent <= received,
         'acquisition chronology')
    need(sent.year == 2026 and sent.month == 10 and sent.day >= 9, 'current acquisition date')
    need(type(record['elapsed_seconds']) in (int, float) and record['elapsed_seconds'] >= 0,
         'elapsed request time')
    return json.loads(record['request_body']), record['response_body']


def validate_record(record, expected, data, seen):
    requests, body = exchange(record)
    need(isinstance(requests, list) and 1 <= len(requests) <= 10, 'request batch bounds')
    ids = []
    for request in requests:
        n = request.get('id')
        need(type(n) is int and n in expected and n not in seen and n not in ids,
             'unknown or duplicate requested block')
        block_hash, prices = expected[n]
        need(request == price_request(n, block_hash, data), 'price request/hash/calldata/canonicality')
        ids.append(n)
    need(ids == list(range(ids[0], ids[-1] + 1)), 'request sequence')
    decoded = decode_batch(body, requests)
    for n, prices in decoded.items():
        need(prices == expected[n][1], 'cross-operator price vector mismatch')
    seen.update(decoded)
    return ids


def source_assets(asset_document, d08):
    digest, assets = __import__('hashlib').sha256(), []
    with zipfile.ZipFile(d08) as z, z.open('closeout/market-state-manifest.jsonl') as stream:
        for raw in stream:
            digest.update(raw)
            row = json.loads(raw)
            if row.get('protocol') == 'AAVE_V3' and row.get('lifecycle') == 'CURRENT':
                assets.append((int(row['reserve_id']), row['asset'].lower()))
    need(digest.hexdigest() == ASSET_SOURCE_PIN, 'D08 asset member commitment')
    need([a for _, a in sorted(assets)] == asset_document['assets'], 'D08 asset order/substitution')


def preflight(root):
    source = (root / 'NqcAaveOraclePriceBlockBatch.sol').read_bytes()
    original = (root / 'NqcAaveOraclePriceBlockBatch.bin').read_bytes()
    need(sha(source) == '069d513fd2d47b1496b3256e284e8637969658178d856b7ece2b5e2a67e91150'
         and sha(original) == 'eb66f7a4ea40b79e94cc0f27cbecd62ff99039f91fa42c3b310b7cf234fc20b6', 'helper source/initcode pins')
    compiler = json.loads((root / 'compiler-pin.json').read_bytes())
    need(compiler['sha256'] == '0xfb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'
         and compiler['version'] == '0.8.24', 'compiler release pin')
    inputs = json.loads((root / 'compiler-input.json').read_bytes())
    outputs = json.loads((root / 'compiler-output.json').read_bytes())
    need(inputs['sources']['NqcAaveOraclePriceBlockBatch.sol']['content'].encode() == source, 'compiler source input')
    compiled = outputs['contracts']['NqcAaveOraclePriceBlockBatch.sol']['NqcAaveOraclePriceBlockBatch']['evm']['bytecode']['object']
    need(compiled == original.decode().strip() == (root / 'compiled-initcode.bin').read_text().strip(), 'exact compiled initcode')
    header = json.loads((root / 'header-response.json').read_bytes())['result']
    helper = json.loads((root / 'helper-response.json').read_bytes())['result'][2:]
    words = [int(helper[i:i + 64], 16) for i in range(0, len(helper), 64)]
    direct = json.loads((root / 'direct-response.json').read_bytes())['result']
    from collect import decode_prices
    need(len(words) == 73 and words[:2] == [32, 71] and words[2] == START
         and words[3] == int(header['timestamp'], 16) and words[5] == int(header['parentHash'], 16)
         and header['hash'] == START_HASH and words[6:] == decode_prices(direct), 'helper/direct/header comparison')
    need(words[4] == 0 and int(header['baseFeePerGas'], 16) == 38880936, 'retained helper basefee discrepancy')
    need(json.loads((root / 'canonical-response.json').read_bytes())['result'] == direct, 'canonical direct preflight')
    batch_error = json.loads((root / 'batch-response.json').read_bytes())
    need(batch_error['error']['code'] == -32600 and 'maximum allowed is 10' in batch_error['error']['message'], 'batch-limit diagnostic')
    return {'helper_initcode_recompiled_byte_identically': True, 'compiler_version': '0.8.24',
            'source_sha256': sha(source), 'compiler_binary_sha256': compiler['sha256'][2:],
            'helper_direct_price_values_matched': 67, 'helper_basefee_wei': 0,
            'header_basefee_wei': 38880936, 'helper_basefee_used_as_gas_quote': False,
            'twenty_call_batch_rejected': True, 'collector_batch_limit': 10}


def reconcile(primary_archive, d08, directories):
    need(sha(primary_archive.read_bytes()) == ARCHIVE_SHA, 'original oracle archive commitment')
    expected, retained_secondary = {}, set()
    pins, previous = [], None
    with zipfile.ZipFile(primary_archive) as z:
        for a in range(START, END + 1, 50):
            name = f'chunk-{a:08d}-{min(END, a + 49):08d}.json'
            raw = z.read('drpc/' + name)
            pins.append({'name': name, 'sha256': sha(raw)})
            rows = observations(json.loads(raw))
            if 'nodies/' + name in z.namelist():
                need(observations(json.loads(z.read('nodies/' + name))) == rows, 'retained secondary mismatch')
                retained_secondary.update(r['block_number'] for r in rows)
            for row in rows:
                if previous:
                    need(row['block_number'] == previous['block_number'] + 1, 'primary continuity')
                    expected[previous['block_number']] = (row['parent_hash'], previous['prices'])
                previous = row
        expected[END] = (END_HASH, previous['prices'])
    need(sha(canon(pins)) == PRIMARY_PIN and expected[START][0] == START_HASH, 'primary hash binding')
    seen, receipts, ranges, sources, failed_requests = set(), [], [], [], []
    diagnostics = None
    for directory in directories:
        bundle = captured_identity(directory)
        if directory.name == 'pilot':
            diagnostics = preflight(directory.parent)
        report = json.loads((directory / 'acquisition.json').read_bytes())
        full = report['status'] == 'COMPLETE_REQUESTED_RANGE'
        need((full and report['failures'] == []) or
             (report['status'] == 'INCOMPLETE' and len(report['failures']) == 1), 'acquisition failure accounting')
        need(report['collector_sha256'] == sha((directory / 'collector.py').read_bytes())
             == sha((HERE / 'collect.py').read_bytes()), 'collector source identity')
        assets_raw = (directory / 'assets.json').read_bytes()
        need(sha(assets_raw) == report['asset_document_sha256'], 'asset document commitment')
        document = json.loads(assets_raw)
        source_assets(document, d08)
        data = calldata(document)
        anchor_records = [json.loads(line) for line in gzip.decompress((directory / 'anchors.jsonl.gz').read_bytes()).splitlines()]
        need(len(anchor_records) == 3, 'anchor inventory')
        for i, record in enumerate(anchor_records):
            req, body = exchange(record)
            method, params = [('eth_chainId', []), ('eth_getBlockByNumber', [hex(START), False]),
                              ('eth_getBlockByNumber', [hex(END), False])][i]
            need(req == {'jsonrpc': '2.0', 'id': i, 'method': method, 'params': params}, 'anchor request')
            response = json.loads(body)
            need(response.get('jsonrpc') == '2.0' and response.get('id') == i and 'error' not in response, 'anchor response')
            value = response['result']
            if i == 0:
                need(value == '0x1', 'Ethereum chain')
            else:
                n, h = (START, START_HASH) if i == 1 else (END, END_HASH)
                need((int(value['number'], 16), value['hash']) == (n, h), 'anchor hash')
        before, count, attempted, nonfailed_file_blocks = set(seen), 0, 0, 0
        files = report['completed_files']
        listed = {x['file']: x for x in files}
        failed_files = {f'capture-{a:08d}-{b:08d}.jsonl.gz' for a, b in
                        [failure['range'] for failure in report['failures']]}
        need(set(listed).isdisjoint(failed_files) and set(listed) | failed_files ==
             {p.name for p in directory.glob('capture-*.jsonl.gz')}
             and len(files) == len(listed), 'capture file inventory')
        for name in sorted(set(listed) | failed_files):
            path = directory / name
            need(path.parent == directory and not path.is_symlink(), 'unsafe capture path')
            raw = path.read_bytes()
            item = listed.get(name)
            if item:
                need(len(raw) == item['bytes'] and sha(raw) == item['sha256'], 'capture file commitment')
            observed = []
            for line in gzip.decompress(raw).splitlines():
                record = json.loads(line)
                requests, body = exchange(record, allow_failed=True)
                count += 1
                attempted += len(requests)
                if record['http_status'] != 200:
                    need(name in failed_files and record['http_status'] == 429
                         and record['transport_error'] == 'HTTP Error 429: Too Many Requests', 'unexpected acquisition failure')
                    error = json.loads(body)
                    need(error['error']['code'] == -32005 and
                         dict(record['response_headers']).get('Retry-After') == '60', 'rate-limit evidence')
                    need(all(q == price_request(q['id'], expected[q['id']][0], data) for q in requests), 'failed request identity')
                    failed_requests.append({'http_status': 429, 'received_at': record['received_at'],
                                            'retry_after_seconds': 60, 'requests': len(requests),
                                            'request_sha256': record['request_sha256'],
                                            'response_sha256': record['response_sha256']})
                    continue
                ids = validate_record(record, expected, data, seen)
                observed.extend(ids)
                receipts.append(record['received_at'])
            a, b = [int(x) for x in name.removeprefix('capture-').removesuffix('.jsonl.gz').split('-')]
            need(observed == list(range(a, a + len(observed))) and len(observed) <= b - a + 1,
                 'capture block sequence')
            if item:
                need(len(observed) == item['observed_blocks'], 'capture block conservation')
                nonfailed_file_blocks += len(observed)
            if full:
                need(len(observed) == b - a + 1, 'complete file coverage')
        requested = set(range(report['start_block'], report['end_block'] + 1))
        need((seen - before <= requested) and (not full or seen - before == requested)
             and nonfailed_file_blocks == report['observed_blocks_in_successful_files'],
             'requested range conservation')
        need(report['attempted_rpc_calls'] == attempted + 3
             and report['attempted_http_requests'] == count + 3, 'call conservation')
        need(report['census_certified'] is False and report['gas_spent'] is False
             and report['historical_decision_time_observation'] is False, 'expanded authority')
        ranges.append({'requested': [report['start_block'], report['end_block']],
                       'status': report['status'], 'actual_observed_blocks': len(seen - before)})
        sources.append({'acquisition_sha256': sha((directory / 'acquisition.json').read_bytes()),
                        'collector_sha256': report['collector_sha256'], 'bundle': bundle})
    coverage = seen | retained_secondary
    return {'schema': 'nqc-direct-oracle-reconciliation-v1', 'status': 'PASS_WITH_EXPLICIT_LIMITS',
            'original_archive_sha256': ARCHIVE_SHA, 'primary_chunk_commitment': PRIMARY_PIN,
            'new_direct_observed_blocks': len(seen), 'assets_per_block': 67,
            'matched_new_price_values': len(seen) * 67, 'retained_secondary_blocks': len(retained_secondary),
            'secondary_union_blocks': len(coverage), 'secondary_missing_blocks': END - START + 1 - len(coverage),
            'ranges': sorted(ranges, key=lambda r: r['requested']),
            'earliest_received_at': min(receipts), 'latest_received_at': max(receipts),
            'failed_requests': failed_requests, 'full_requested_acquisition_complete': not failed_requests,
            'full_secondary_price_coverage': len(coverage) == END - START + 1,
            'preflight_diagnostics': diagnostics,
            'cross_operator_price_mismatches': 0, 'source_reports': sources,
            'new_requests_bound_to_canonical_block_hash': True,
            'historical_primary_rpc_transport_authenticated': False,
            'independent_underlying_nodes_proven': False, 'full_header_lineage_reconstructed': False,
            'transaction_prestate_prices_proven': False, 'historical_decision_time_observation': False,
            'gas_cost_derived_from_helper_basefee': False, 'gas_spent': False, 'census_certified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--primary-archive', type=Path, required=True)
    parser.add_argument('--d08', type=Path, required=True)
    parser.add_argument('--acquisition', action='append', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = reconcile(args.primary_archive, args.d08, args.acquisition)
    with args.out.open('xb') as stream:
        stream.write(canon(result))
    print(json.dumps(result, sort_keys=True))
