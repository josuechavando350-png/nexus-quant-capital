#!/usr/bin/env python3
"""Offline reconstruction of registry coverage and state-read comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from common import (HERE, need, canonical, qty, header, pin, view, position_data,
                    MARKET_PARAMS, MORPHO, ORACLE, IRM, MARKET, words, encode)
from rpc_batch import decode, validate
from collect import derive, state_queries
import registry


def audit(folder):
    folder = Path(folder)
    requests = json.loads((folder / 'requests.json').read_text())
    rows = [json.loads(line) for line in (folder / 'journal.jsonl').read_text().splitlines()]
    previous = '0' * 64
    for index, row in enumerate(rows):
        unsigned = {k: v for k, v in row.items() if k != 'sha256'}
        need(row['sequence'] == index and row['previous_sha256'] == previous and
             hashlib.sha256(canonical(unsigned)).hexdigest() == row['sha256'], 'JOURNAL_HASH_CHAIN')
        if index: need(rows[index - 1]['recorded_ns'] <= row['recorded_ns'], 'JOURNAL_CLOCK_ORDER')
        previous = row['sha256']
    need(rows and rows[0]['kind'] == 'registered' and rows[-1]['kind'] in {'completed', 'stopped'}, 'TERMINAL_JOURNAL')
    policy = rows[0]['data']['policy']
    need(policy == json.loads((HERE / 'policy.json').read_text()), 'REGISTERED_POLICY_CHANGED')
    ids, decoded, by_label = [], [], {}
    for index, row in enumerate(requests):
        need(row['label'] not in by_label, 'DUPLICATE_LABEL')
        by_label[row['label']] = index
        payload = row['payload']
        entries = payload if type(payload) is list else [payload]
        need(1 <= len(entries) <= policy['batch_width'], 'BATCH_WIDTH')
        for item in entries:
            validate(item['method'], item['params']); ids.append(item['id'])
        need(row['started_ns'] <= row['finished_ns'], 'RPC_CLOCK')
        if 'response_file' in row:
            need(Path(row['response_file']).name == row['response_file'], 'RAW_PATH')
            raw = (folder / row['response_file']).read_bytes()
            need(hashlib.sha256(raw).hexdigest() == row['response_sha256'], 'RAW_RESPONSE_HASH')
            need(row['started_ns'] <= row['received_ns'] <= row['finished_ns'], 'RESPONSE_CLOCK')
            try:
                result = decode(payload, raw)
                need('exception' not in row, 'UNEXPECTED_RECORDED_EXCEPTION')
            except Exception:
                need('exception' in row and index == len(requests) - 1 and rows[-1]['kind'] == 'stopped', 'UNEXPLAINED_RPC_FAILURE')
                result = None
        else:
            need('exception' in row and index == len(requests) - 1 and rows[-1]['kind'] == 'stopped', 'MISSING_RAW_REPLY')
            result = None
        decoded.append(result)
    need(ids == list(range(1, len(ids) + 1)) and len(ids) <= policy['max_requests'], 'RPC_IDS_OR_COUNT')

    def single(label, method=None, params=None):
        i = by_label[label]
        entry = requests[i]['payload']
        need(type(entry) is dict, 'EXPECTED_SINGLE')
        if method is not None: need(entry['method'] == method and entry['params'] == params, 'RPC_REQUEST_BINDING')
        need(decoded[i] is not None, 'RPC_UNAVAILABLE')
        return decoded[i][0]

    need(qty(single('chain', 'eth_chainId', [])) == policy['chain_id'], 'CHAIN_ID')
    targets = [row for row in rows if row['kind'] == 'index_target']
    state = None
    cohort_rows = [row for row in rows if row['kind'] == 'cohort_frozen']
    if targets:
        need(len(targets) == 1, 'ONE_INDEX_TARGET')
        target = targets[0]['data']
        state = target['start_state']
        registry.validate(state, policy)
        anchor = header(single('index-anchor'))
        latest = header(single('initial-head'))
        need(anchor == target['anchor'] and anchor['number'] == latest['number'] - policy['confirmation_buffer_blocks'], 'ANCHOR_RULE')
        prior_hash = rows[0]['data']['prior_registry_sha256']
        if prior_hash is None:
            need(state == registry.new(anchor['number'] - policy['seed_lookback_blocks'] + 1), 'SEED_SELECTION_CHANGED')
        else:
            need(registry.digest(state) == prior_hash and state == json.loads((folder / 'registry-input.json').read_text()), 'RESUME_SOURCE')
            if cohort_rows:
                need(header(single('resume-checkpoint', 'eth_getBlockByNumber', [hex(state['through_block']), False])) == state['checkpoint'], 'RESUME_CHECKPOINT')
        for row in [r for r in rows if r['kind'] == 'registry_segment']:
            first, end_number = row['data']['first'], row['data']['end']
            start = state['checkpoint'] or header(single('registry-start'))
            end = header(single(f'end-before-{end_number}', 'eth_getBlockByNumber', [hex(end_number), False]))
            from common import BORROW
            logs = single(f'logs-{first}', 'eth_getLogs', [{'address': MORPHO, 'topics': [BORROW, MARKET],
                          'fromBlock': hex(first), 'toBlock': hex(end_number)}])
            heights = sorted({qty(log['blockNumber']) for log in logs})
            all_headers = []
            for offset in range(0, len(heights) + 1, policy['batch_width']):
                i = by_label[f'confirm-{end_number}-{offset}']
                wanted = heights + [end_number]
                expected = [('eth_getBlockByNumber', [hex(n), False]) for n in wanted[offset:offset + 4]]
                actual = [(q['method'], q['params']) for q in requests[i]['payload']]
                need(actual == expected and decoded[i] is not None, 'CONFIRM_REQUESTS')
                all_headers.extend(header(raw) for raw in decoded[i])
            need(all_headers[-1] == end, 'END_NOT_CANONICAL')
            state = registry.append(state, first, start, end, logs, all_headers[:-1], policy)
            need(row['data']['events'] == len(logs) and row['data']['registry_sha256'] == registry.digest(state), 'SEGMENT_JOURNAL')
        if cohort_rows:
            need(len(cohort_rows) == 1 and header(single('anchor-after-index', 'eth_getBlockByNumber', [hex(anchor['number']), False])) == anchor,
                 'FREEZE_ANCHOR')
            need(cohort_rows[0]['data'] == registry.freeze(state, anchor['number'], policy), 'COHORT_RECONSTRUCTION')
            need(json.loads((folder / 'cohort.json').read_text()) == cohort_rows[0]['data'], 'COHORT_FILE')
        invalidations = [r for r in rows if r['kind'] == 'registry_invalidated']
        if invalidations:
            state = registry.invalidate(state, invalidations[-1]['data']['observed'])
        if (folder / 'registry.json').exists():
            need(registry.load(folder / 'registry.json', policy) == state, 'PERSISTED_REGISTRY_DIFFERS')
    snapshots, comparison, freshness = [], [], []
    for row in rows:
        if row['kind'] == 'snapshot_completed':
            need(len(cohort_rows) == 1 and row['recorded_ns'] > cohort_rows[0]['recorded_ns'], 'SNAPSHOT_BEFORE_FREEZE')
            data = row['data']; block = data['block']; index = data['round']; mode = data['mode']
            addresses = cohort_rows[0]['data']['addresses']
            need(block == header(single(f'r{index}-head', 'eth_getBlockByNumber', ['latest', False])), 'SNAPSHOT_HEADER')
            need(block['number'] > cohort_rows[0]['data']['through_block'] and
                 block['timestamp'] >= cohort_rows[0]['recorded_wall_ns'] // 10**9, 'SNAPSHOT_NOT_PROSPECTIVE')
            begin, end = data['first_record'], data['last_record']
            need(requests[begin]['started_ns'] >= cohort_rows[0]['recorded_ns'], 'FUTURE_LEAK')
            group_rows = requests[begin:end - 1]
            result, actual = [], []
            for j, packet in enumerate(group_rows, begin):
                q = packet['payload'] if type(packet['payload']) is list else [packet['payload']]
                need((type(packet['payload']) is list) == (mode == 'batch'), 'SNAPSHOT_READ_MODE')
                actual.extend((item['method'], item['params']) for item in q)
                need(decoded[j] is not None, 'MISSING_STATE_REPLY'); result.extend(decoded[j])
            need(actual == state_queries(block, addresses), 'STATE_REQUEST_BINDING')
            market = words(result[0], 6)
            rate = single(f'r{index}-{mode}-rate', *view(block, IRM, encode('0x8c00bf6b', *MARKET_PARAMS, *market)))
            need(data['state'] == derive(block, addresses, result, rate, policy), 'STATE_DERIVATION')
            need(header(single(f'r{index}-{mode}-canonical', 'eth_getBlockByNumber', [hex(block['number']), False])) == block, 'SNAPSHOT_CANONICAL')
            need(data['started_ns'] <= requests[begin]['started_ns'] and
                 requests[end - 1]['received_ns'] <= data['input_finished_ns'] <= requests[end]['started_ns'], 'INPUT_CLOCK')
            need(data['input_elapsed_ms'] == (data['input_finished_ns'] - data['started_ns']) / 10**6, 'ELAPSED_METRIC')
            snapshots.append(data)
        elif row['kind'] == 'same_block_comparison':
            data = row['data']
            pair = [s for s in snapshots if s['round'] == data['round']]
            need(len(pair) == 2 and [s['mode'] for s in pair] == ['batch', 'sequential'] and
                 pair[0]['state'] == pair[1]['state'], 'PARITY_NOT_PROVEN')
            need(data['exact_state_parity'] is True and data['batch_input_ms'] == pair[0]['input_elapsed_ms'] and
                 data['sequential_input_ms'] == pair[1]['input_elapsed_ms'], 'COMPARISON_METRICS')
            comparison.append(data)
        elif row['kind'] == 'freshness':
            data = row['data']
            snapshot = next(s for s in snapshots if s['round'] == data['round'] and s['mode'] == 'batch')
            head_row = requests[by_label[f'r{data["round"]}-head']]
            elapsed = (snapshot['input_finished_ns'] - head_row['received_ns']) / 10**6
            need(elapsed == data['after_header_input_ms'] and data['within_assumed_budget'] == (elapsed <= policy['freshness_budget_ms_assumed']), 'FRESHNESS_METRICS')
            freshness.append(data)
    if rows[-1]['kind'] == 'completed':
        need(len(snapshots) == policy['rounds'] + 1 and len(freshness) == policy['rounds'] and len(comparison) == 1, 'INCOMPLETE_EXPERIMENT')
        auth_index = by_label['authenticate-0']
        expected = [('eth_getCode', [a, pin(target['anchor'])]) for a in [MORPHO, ORACLE, IRM]] + [view(target['anchor'], MORPHO, '0x2c3c9157' + MARKET[2:])]
        need([(q['method'], q['params']) for q in requests[auth_index]['payload']] == expected, 'AUTH_REQUESTS')
        original = json.loads((HERE.parent / 'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json').read_text())['result']
        need(decoded[auth_index][:3] == [original[a]['code'] for a in [MORPHO, ORACLE, IRM]] and words(decoded[auth_index][3], 5) == MARKET_PARAMS, 'RUNTIME_OR_MARKET_CHANGED')
    times = [(r['received_ns'] - r['started_ns']) / 10**6 for r in requests if 'received_ns' in r]
    return {'status': rows[-1]['kind'], 'terminal': rows[-1]['data'], 'registration': rows[0]['data']['registration_commit'],
            'rpc_calls': len(ids), 'http_requests': len(requests), 'rpc_errors': sum('exception' in r for r in requests),
            'elapsed_seconds': (rows[-1]['recorded_ns'] - rows[0]['recorded_ns']) / 10**9,
            'http_latency_ms': {'min': min(times), 'median': statistics.median(times), 'max': max(times)} if times else None,
            'registry': {'from_block': state['from_block'], 'through_block': state['through_block'], 'status': state['status'],
                         'events': sum(len(s['events']) for s in state['segments']), 'segments': len(state['segments'])} if state else None,
            'cohort': cohort_rows[0]['data'] if cohort_rows else None,
            'snapshots': snapshots, 'comparisons': comparison, 'freshness': freshness,
            'route_simulations': 0, 'realized_capture_rate': None, 'realized_profit': None,
            'provider_count': 1, 'independent_state_proofs': False, 'journal_last_sha256': previous}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.folder)
    args.out.write_bytes(canonical(result))
    print(json.dumps({k: result[k] for k in ['status', 'rpc_calls', 'http_requests', 'registry', 'realized_profit']}))
