#!/usr/bin/env python3
"""Offline reconstruction from saved requests, raw replies and chained journal."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from support import (HERE, need, canonical, qty, header, pin, validate, decode, registry,
                     MORPHO, ORACLE, IRM, MARKET, MARKET_PARAMS, words, encode, derive)
from common import BORROW, view
from collect import state_queries
from backfill import merge
import lens


def audit(folder, expected_policy=None):
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
    need(policy == (expected_policy or json.loads((HERE / 'policy.json').read_text())), 'REGISTERED_POLICY_CHANGED')
    cohort_rows = [r for r in rows if r['kind'] == 'cohort_frozen']
    need(len(cohort_rows) <= 1, 'ONE_COHORT')
    cohort = cohort_rows[0]['data'] if cohort_rows else None
    creation_starts = {f'observe-r{r["data"]["round"]}-creation': r for r in rows if r['kind'] == 'creation_started'}
    ids, decoded, by_label = [], [], {}
    total_bytes = 0
    for index, row in enumerate(requests):
        need(row['label'] not in by_label, 'DUPLICATE_LABEL'); by_label[row['label']] = index
        payload = row['payload']; entries = payload if type(payload) is list else [payload]
        need(1 <= len(entries) <= policy['batch_width'], 'BATCH_WIDTH')
        if row.get('kind') == 'fixed_creation_view':
            need(cohort is not None and type(payload) is dict and row['label'] in creation_starts, 'CREATION_COHORT_BINDING')
            start = creation_starts[row['label']]
            tx, block_pin = lens.query(start['data']['block'], cohort['addresses'])
            need(set(payload) == {'jsonrpc', 'id', 'method', 'params'} and payload['method'] == 'eth_call' and
                 payload['params'] == [tx, block_pin] and row['cohort'] == cohort['addresses'], 'EXACT_CREATION_QUERY')
            need(row['started_ns'] >= start['recorded_ns'] > cohort_rows[0]['recorded_ns'], 'CREATION_BEFORE_FREEZE')
        else:
            need('kind' not in row, 'UNKNOWN_RPC_KIND')
            for item in entries: validate(item['method'], item['params'])
        for item in entries:
            need(item['jsonrpc'] == '2.0' and type(item['id']) is int, 'REQUEST_ENVELOPE'); ids.append(item['id'])
        need(row['started_ns'] <= row['finished_ns'], 'RPC_CLOCK')
        need(row['started_ns'] <= rows[0]['recorded_ns'] + policy['max_run_seconds'] * 10**9, 'RPC_START_AFTER_TIME_BUDGET')
        if 'response_file' in row:
            need(Path(row['response_file']).name == row['response_file'], 'RAW_PATH')
            raw = (folder / row['response_file']).read_bytes()
            total_bytes += len(raw)
            need(len(raw) <= 2*1024*1024 and total_bytes <= 32*1024*1024, 'RAW_BYTE_BUDGET')
            need(hashlib.sha256(raw).hexdigest() == row['response_sha256'], 'RAW_RESPONSE_HASH')
            need(row['started_ns'] <= row['received_ns'] <= row['finished_ns'], 'RESPONSE_CLOCK')
            try: result = decode(payload, raw)
            except Exception:
                need('exception' in row and index == len(requests)-1 and rows[-1]['kind'] == 'stopped', 'UNEXPLAINED_RPC_FAILURE')
                result = None
            else: need('exception' not in row, 'UNEXPECTED_RECORDED_EXCEPTION')
        else:
            need('exception' in row and index == len(requests)-1 and rows[-1]['kind'] == 'stopped', 'MISSING_RAW_REPLY'); result = None
        decoded.append(result)
    need(ids == list(range(1, len(ids)+1)) and len(ids) <= policy['max_requests'], 'RPC_IDS_OR_COUNT')

    def single(label, method=None, params=None):
        i = by_label[label]; entry = requests[i]['payload']
        need(type(entry) is dict, 'EXPECTED_SINGLE')
        if method is not None: need(entry['method'] == method and entry['params'] == params, 'RPC_REQUEST_BINDING')
        need(decoded[i] is not None, 'RPC_UNAVAILABLE')
        return decoded[i][0]

    def block_at(label, number):
        return header(single(label, 'eth_getBlockByNumber', [hex(number) if type(number) is int else number, False]))

    source_bytes = (folder / 'source-registry.json').read_bytes()
    need(hashlib.sha256(source_bytes).hexdigest() == policy['source_registry_file_sha256'], 'SOURCE_FILE_HASH')
    source = registry.load(folder / 'source-registry.json', policy)
    need(registry.digest(source) == rows[0]['data']['source_registry_sha256'], 'SOURCE_REGISTRY_BINDING')
    need(qty(single('verify-chain', 'eth_chainId', [])) == policy['chain_id'], 'CHAIN_ID')
    state, older, anchor, phase = None, None, None, None
    merge_proven = False
    for row in rows:
        kind, data = row['kind'], row['data']
        if kind == 'backfill_started':
            need(block_at('verify-source-checkpoint', source['through_block']) == source['checkpoint'], 'SOURCE_CANONICAL')
            boundary = block_at('verify-backfill-boundary', policy['backfill_through_block'])
            need(data == {'first': policy['backfill_from_block'], 'last': policy['backfill_through_block'], 'anchor': boundary} and
                 boundary == source['segments'][0]['start'] and data['last'] == source['from_block']-1 and
                 data['last']-data['first']+1 == policy['backfill_blocks'], 'BACKFILL_SELECTION_OR_BOUNDARY')
            phase, anchor = 'backfill', boundary
            state = registry.new(data['first'])
        elif kind == 'registry_segment':
            need(phase in {'backfill', 'catchup'}, 'SEGMENT_PHASE')
            first, end_number = data['first'], data['end']
            start = state['checkpoint'] or block_at(phase + '-registry-start', state['from_block']-1)
            need(first == state['through_block'] + 1 and end_number == min(anchor['number'], first+policy['shard_blocks']-1), 'FIXED_SHARD')
            end = block_at(f'{phase}-end-before-{end_number}', end_number)
            logs = single(f'{phase}-logs-{first}', 'eth_getLogs', [{'address': MORPHO, 'topics': [BORROW, MARKET],
                          'fromBlock': hex(first), 'toBlock': hex(end_number)}])
            heights = sorted({qty(log['blockNumber']) for log in logs}); wanted = heights + [end_number]
            checked = []
            for offset in range(0, len(wanted), policy['batch_width']):
                i = by_label[f'{phase}-confirm-{end_number}-{offset}']
                expected = [('eth_getBlockByNumber', [hex(n), False]) for n in wanted[offset:offset+policy['batch_width']]]
                need(type(requests[i]['payload']) is list and
                     [(q['method'], q['params']) for q in requests[i]['payload']] == expected and decoded[i] is not None, 'CONFIRM_REQUESTS')
                checked.extend(header(raw) for raw in decoded[i])
            need([h['number'] for h in checked] == wanted and checked[-1] == end, 'SEGMENT_CANONICAL')
            state = registry.append(state, first, start, end, logs, checked[:-1], policy)
            need(data['events'] == len(logs) and data['registry_sha256'] == registry.digest(state), 'SEGMENT_JOURNAL')
        elif kind == 'backfill_merged':
            need(phase == 'backfill' and state['through_block'] == anchor['number'], 'BACKFILL_COMPLETE')
            need(block_at('backfill-anchor-after-index', anchor['number']) == anchor, 'BACKFILL_ANCHOR')
            need(block_at('verify-source-after-backfill', source['through_block']) == source['checkpoint'], 'SOURCE_CHANGED')
            older = state; state = merge(older, source, policy)
            need(data == {'older_registry_sha256': registry.digest(older), 'merged_registry_sha256': registry.digest(state),
                          'source_registry_sha256': registry.digest(source)}, 'MERGED_JOURNAL')
            need(registry.load(folder / 'older-registry.json', policy) == older and
                 registry.load(folder / 'merged-before-catchup.json', policy) == state, 'MERGED_FILES')
            merge_proven = True
        elif kind == 'catchup_started':
            need(merge_proven, 'CATCHUP_WITHOUT_MERGE'); phase = 'catchup'
            latest = block_at('catchup-head', 'latest'); anchor = data['anchor']
            need(anchor == block_at('catchup-anchor', latest['number']-policy['confirmation_buffer_blocks']), 'CATCHUP_ANCHOR')
            if cohort_rows: need(block_at('catchup-resume-checkpoint', state['through_block']) == state['checkpoint'], 'CATCHUP_RESUME')
        elif kind == 'registry_invalidated':
            state = registry.invalidate(state, data['observed'])
        elif kind == 'cohort_frozen':
            need(phase == 'catchup' and merge_proven and state['through_block'] == anchor['number'], 'FREEZE_COMPLETE')
            need(block_at('catchup-anchor-after-index', anchor['number']) == anchor, 'FREEZE_CANONICAL')
            need(data == registry.freeze(state, anchor['number'], policy) and
                 json.loads((folder / 'cohort.json').read_text()) == data, 'COHORT_RECONSTRUCTION')
    if state is not None:
        persisted = folder / ('registry.json' if phase == 'catchup' else 'older-registry.json')
        if persisted.exists(): need(registry.load(persisted, policy) == state, 'PERSISTED_REGISTRY_DIFFERS')

    snapshots, comparisons = [], []
    for row in rows:
        if row['kind'] in {'snapshot_completed', 'creation_completed'}:
            need(cohort is not None and row['recorded_ns'] > cohort_rows[0]['recorded_ns'], 'SNAPSHOT_BEFORE_FREEZE')
            data = row['data']; block = data['block']; index, mode = data['round'], data['mode']; addresses = cohort['addresses']
            need(block == block_at(f'observe-r{index}-head', 'latest') and block['number'] > cohort['through_block'] and
                 block['timestamp'] >= cohort_rows[0]['recorded_wall_ns'] // 10**9, 'PROSPECTIVE_HEADER')
            if mode == 'creation':
                begin = data['record_index']; need(by_label[f'observe-r{index}-creation'] == begin, 'CREATION_RECORD')
                need(decoded[begin] is not None and lens.parse(block, addresses, decoded[begin][0], policy) == data['state'], 'CREATION_DERIVATION')
                last_input = begin
            else:
                need(mode == 'batch', 'BATCH_MODE'); begin, end = data['first_record'], data['last_record']
                result, actual = [], []
                for j in range(begin, end-1):
                    packet = requests[j]; need(type(packet['payload']) is list and decoded[j] is not None, 'BATCH_STATE_REPLY')
                    actual.extend((q['method'], q['params']) for q in packet['payload']); result.extend(decoded[j])
                need(actual == state_queries(block, addresses), 'STATE_REQUEST_BINDING')
                rate = single(f'observe-r{index}-batch-rate', *view(block, IRM, encode('0x8c00bf6b', *MARKET_PARAMS, *words(result[0], 6))))
                need(data['state'] == derive(block, addresses, result, rate, policy), 'STATE_DERIVATION')
                need(by_label[f'observe-r{index}-batch-rate'] == end-1, 'RATE_RECORD'); last_input = end-1
            canonical_index = by_label[f'observe-r{index}-{mode}-canonical']
            need(block_at(f'observe-r{index}-{mode}-canonical', block['number']) == block, 'SNAPSHOT_CANONICAL')
            need(cohort_rows[0]['recorded_ns'] < data['started_ns'] <= requests[begin]['started_ns'] and
                 requests[last_input]['received_ns'] <= data['input_finished_ns'] <= requests[canonical_index]['started_ns'] and
                 data['input_elapsed_ms'] == (data['input_finished_ns']-data['started_ns'])/10**6, 'INPUT_CLOCK')
            snapshots.append(data)
        elif row['kind'] == 'paired_comparison':
            data = row['data']; pair = [s for s in snapshots if s['round'] == data['round']]
            order = policy['paired_read_order'][data['round']]
            need(len(pair) == 2 and [s['mode'] for s in pair] == order and pair[0]['state'] == pair[1]['state'] and
                 pair[0]['block'] == pair[1]['block'] == data['block'] and pair[0]['input_finished_ns'] < pair[1]['started_ns'], 'PAIR_PARITY_OR_ORDER')
            received = requests[by_label[f'observe-r{data["round"]}-head']]['received_ns']
            elapsed = (pair[0]['input_finished_ns']-received)/10**6
            need(data == {'round': pair[0]['round'], 'block': pair[0]['block'], 'order': order, 'exact_state_parity': True,
                          'input_ms': {s['mode']: s['input_elapsed_ms'] for s in pair}, 'first_mode': order[0],
                          'head_to_first_inputs_ms': elapsed, 'head_to_second_inputs_ms': (pair[1]['input_finished_ns']-received)/10**6,
                          'within_assumed_budget_first_mode': elapsed <= policy['freshness_budget_ms_assumed']}, 'PAIR_METRICS')
            comparisons.append(data)
    if snapshots:
        i = by_label['observe-authenticate-0']
        expected = [('eth_getCode', [a, pin(anchor)]) for a in [MORPHO, ORACLE, IRM]] + [view(anchor, MORPHO, '0x2c3c9157'+MARKET[2:])]
        need([(q['method'], q['params']) for q in requests[i]['payload']] == expected, 'AUTH_REQUESTS')
        original = json.loads((HERE.parent / 'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json').read_text())['result']
        need(decoded[i][:3] == [original[a]['code'] for a in [MORPHO, ORACLE, IRM]] and words(decoded[i][3], 5) == MARKET_PARAMS, 'RUNTIME_OR_MARKET_CHANGED')
    if rows[-1]['kind'] == 'completed':
        need(len(comparisons) == policy['rounds'] and len(snapshots) == 2*policy['rounds'], 'INCOMPLETE_EXPERIMENT')
        heights = [x['block']['number'] for x in comparisons]
        need(heights == sorted(set(heights)), 'REPEATED_OR_UNORDERED_HEAD')
    need(rows[-1]['data']['rpc_calls'] == len(ids) and rows[-1]['data']['http_requests'] == len(requests), 'TERMINAL_COUNTS')
    times = [(r['received_ns']-r['started_ns'])/10**6 for r in requests if 'received_ns' in r]
    return {'status': rows[-1]['kind'], 'terminal': rows[-1]['data'], 'registration': rows[0]['data']['registration_commit'],
            'rpc_calls': len(ids), 'http_requests': len(requests), 'rpc_errors': sum('exception' in r for r in requests),
            'elapsed_seconds': (rows[-1]['recorded_ns']-rows[0]['recorded_ns'])/10**9,
            'http_latency_ms': {'min': min(times), 'median': statistics.median(times), 'max': max(times)} if times else None,
            'backfill_merged': merge_proven, 'older_registry_sha256': registry.digest(older) if older else None,
            'registry': {'from_block': state['from_block'], 'through_block': state['through_block'], 'status': state['status'],
                         'events': sum(len(s['events']) for s in state['segments']), 'segments': len(state['segments'])} if state else None,
            'cohort': cohort, 'snapshots': snapshots, 'comparisons': comparisons,
            'route_simulations': 0, 'realized_capture_rate': None, 'realized_profit': None, 'provider_count': 1,
            'independent_state_proofs': False, 'journal_last_sha256': previous}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder', type=Path); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); result = audit(args.folder); args.out.write_bytes(canonical(result))
    print(json.dumps({k: result[k] for k in ['status', 'rpc_calls', 'http_requests', 'registry', 'realized_profit']}))
