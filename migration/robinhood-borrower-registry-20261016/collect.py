#!/usr/bin/env python3
"""Finite registry update and pinned state-read experiment; no execution route."""
import argparse
import json
from pathlib import Path
import time

from common import (HERE, need, canonical, qty, header, pin, view, position_data,
                    MARKET, MORPHO, ORACLE, IRM, BORROW, MARKET_PARAMS, words,
                    encode, screen, Journal)
from rpc_batch import Reader
import registry


def get_header(reader, number, label):
    raw = reader.call('eth_getBlockByNumber', [hex(number) if type(number) is int else number, False], label)
    result = header(raw, reader.records[-1]['received_wall_ns'] if number == 'latest' else None)
    need(number == 'latest' or result['number'] == number, 'WRONG_HEADER_HEIGHT')
    return result


def canonical_check(reader, block, label):
    need(get_header(reader, block['number'], label) == block, 'CANONICAL_HEADER_CHANGED')


def update_registry(reader, journal, policy, path, state, anchor):
    need(state['status'] == 'valid_prefix', 'INVALIDATED_REGISTRY_NEEDS_REBUILD')
    if state['checkpoint']:
        observed = get_header(reader, state['through_block'], 'resume-checkpoint')
        if observed != state['checkpoint']:
            state = registry.invalidate(state, observed)
            registry.save(path, state)
            journal.append('registry_invalidated', state['invalidation'])
            raise ValueError('REGISTRY_REORG_REBUILD_REQUIRED')
        start = observed
    else:
        start = get_header(reader, state['from_block'] - 1, 'registry-start')
    need(state['through_block'] <= anchor['number'], 'REGISTRY_AHEAD_OF_ANCHOR')
    segments = (anchor['number'] - state['through_block'] + policy['shard_blocks'] - 1) // policy['shard_blocks']
    need(segments <= policy['max_segments_per_run'], 'CATCHUP_TOO_LARGE_NO_SKIPPED_GAP')
    for first in range(state['through_block'] + 1, anchor['number'] + 1, policy['shard_blocks']):
        end_number = min(anchor['number'], first + policy['shard_blocks'] - 1)
        end = get_header(reader, end_number, f'end-before-{end_number}')
        params = [{'address': MORPHO, 'topics': [BORROW, MARKET], 'fromBlock': hex(first), 'toBlock': hex(end_number)}]
        logs = reader.call('eth_getLogs', params, f'logs-{first}')
        # Validate ABI/capacity before constructing requests from returned logs.
        from common import enrollment
        parsed = enrollment(logs, first, end, policy)
        heights = sorted({e['block'] for e in parsed['events']})
        raw_headers = reader.many([('eth_getBlockByNumber', [hex(n), False]) for n in heights + [end_number]], f'confirm-{end_number}')
        checked = [header(raw) for raw in raw_headers]
        need([b['number'] for b in checked] == heights + [end_number] and checked[-1] == end, 'SEGMENT_REORG')
        candidate = registry.append(state, first, start, end, logs, checked[:-1], policy)
        # No persistent promotion if the run's target has changed canonical identity.
        # Its final check also protects segments already stored, on completion.
        state = candidate
        registry.save(path, state)
        journal.append('registry_segment', {'first': first, 'end': end_number, 'events': len(logs),
                                          'registry_sha256': registry.digest(state)})
        print(json.dumps({'indexed_through': end_number, 'events_this_segment': len(logs),
                          'rpc_calls': reader.count}), flush=True)
        start = end
    try:
        canonical_check(reader, anchor, 'anchor-after-index')
    except Exception:
        # A failed check is not proof of reorg, but prevents using the prefix as a cohort.
        invalid = registry.invalidate(state, {'reason': 'anchor_check_failed_or_unavailable'})
        registry.save(path, invalid)
        journal.append('registry_invalidated', invalid['invalidation'])
        raise
    return state


def authenticate(reader, block):
    original = json.loads((HERE.parent / 'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json').read_text())['result']
    queries = [('eth_getCode', [a, pin(block)]) for a in [MORPHO, ORACLE, IRM]]
    queries.append(view(block, MORPHO, '0x2c3c9157' + MARKET[2:]))
    result = reader.many(queries, 'authenticate')
    need(result[:3] == [original[a]['code'] for a in [MORPHO, ORACLE, IRM]], 'CONTRACT_RUNTIME_CHANGED')
    need(words(result[3], 5) == MARKET_PARAMS, 'MARKET_IDENTITY_CHANGED')


def state_queries(block, addresses):
    return [view(block, MORPHO, '0x5c60e39a' + MARKET[2:]), view(block, ORACLE, '0xa035b1fe')] + \
           [view(block, MORPHO, position_data(a)) for a in addresses]


def derive(block, addresses, raw, rate_raw, policy):
    need(len(raw) == len(addresses) + 2, 'POSITION_COUNT')
    market, price, rate = words(raw[0], 6), words(raw[1], 1)[0], words(rate_raw, 1)[0]
    positions = [words(item, 3) for item in raw[2:]]
    rows = [{'borrower': a, 'position': pos, 'screen': screen(pos, market, rate, price, block['timestamp'], policy)}
            for a, pos in zip(addresses, positions)]
    observed = sum(pos[1] for pos in positions)
    total = market[3]
    need(observed <= total, 'COHORT_DEBT_SHARES_EXCEED_MARKET')
    return {'market': market, 'price': price, 'rate': rate, 'positions': rows,
            'coverage': {'observed_borrow_shares': observed, 'total_borrow_shares': total,
                         'missing_borrow_shares': total - observed,
                         'debt_share_coverage_bps_floor': observed * 10000 // total if total else None,
                         'all_positive_debt_shares_accounted_at_this_block': total > 0 and observed == total,
                         'historical_event_coverage_complete': False},
            'positive_debt_accounts': sum(pos[1] > 0 for pos in positions),
            'screen_candidate_count': sum(row['screen']['screen_candidate'] for row in rows),
            'computed_unhealthy_count': sum(row['screen']['computed_unhealthy'] for row in rows),
            'profitable_opportunities': None, 'realized_profit': None}


def snapshot(reader, journal, block, addresses, policy, mode, round_index):
    journal.append('snapshot_started', {'round': round_index, 'mode': mode, 'block': block})
    first_record = len(reader.records)
    started = time.monotonic_ns()
    raw = reader.many(state_queries(block, addresses), f'r{round_index}-{mode}-state', mode)
    market = words(raw[0], 6)
    rate = reader.call(*view(block, IRM, encode('0x8c00bf6b', *MARKET_PARAMS, *market)), f'r{round_index}-{mode}-rate')
    input_finished = time.monotonic_ns()
    state = derive(block, addresses, raw, rate, policy)
    canonical_check(reader, block, f'r{round_index}-{mode}-canonical')
    result = {'round': round_index, 'mode': mode, 'block': block, 'state': state,
              'first_record': first_record, 'last_record': len(reader.records) - 1,
              'started_ns': started, 'input_finished_ns': input_finished,
              'input_elapsed_ms': (input_finished - started) / 10**6,
              'canonical_check_included': False}
    journal.append('snapshot_completed', result)
    return result


def run(reader, journal, policy, registration, path, state=None):
    journal.append('registered', {'policy': policy, 'registration_commit': registration,
                                  'prior_registry_sha256': registry.digest(state) if state else None})
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    latest = get_header(reader, 'latest', 'initial-head')
    anchor = get_header(reader, latest['number'] - policy['confirmation_buffer_blocks'], 'index-anchor')
    if state is None: state = registry.new(anchor['number'] - policy['seed_lookback_blocks'] + 1)
    else: (reader.folder / 'registry-input.json').write_bytes(canonical(state))
    journal.append('index_target', {'anchor': anchor, 'start_state': state})
    state = update_registry(reader, journal, policy, path, state, anchor)
    cohort = registry.freeze(state, anchor['number'], policy)
    frozen = journal.append('cohort_frozen', cohort)
    (reader.folder / 'cohort.json').write_bytes(canonical(cohort))
    authenticate(reader, anchor)
    for index in range(policy['rounds']):
        block = get_header(reader, 'latest', f'r{index}-head')
        header_received = reader.records[-1]['received_ns']
        need(block['number'] > anchor['number'] and block['timestamp'] >= frozen['recorded_wall_ns'] // 10**9,
             'SNAPSHOT_NOT_AFTER_COHORT_FREEZE')
        batch = snapshot(reader, journal, block, cohort['addresses'], policy, 'batch', index)
        journal.append('freshness', {'round': index,
                                    'after_header_input_ms': (batch['input_finished_ns'] - header_received) / 10**6,
                                    'within_assumed_budget': batch['input_finished_ns'] - header_received <= policy['freshness_budget_ms_assumed'] * 10**6})
        if index == policy['sequential_comparison_round']:
            sequential = snapshot(reader, journal, block, cohort['addresses'], policy, 'sequential', index)
            need(sequential['state'] == batch['state'], 'SAME_BLOCK_STATE_PARITY_FAILED')
            journal.append('same_block_comparison', {'round': index, 'exact_state_parity': True,
                           'batch_input_ms': batch['input_elapsed_ms'], 'sequential_input_ms': sequential['input_elapsed_ms'],
                           'fixed_order': 'batch_then_sequential', 'independent_repeated_benchmark': False})
    journal.append('completed', {'rpc_calls': reader.count, 'http_requests': len(reader.records),
                                'route_simulations': 0, 'profitability_measured': False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--registration-commit', required=True)
    parser.add_argument('--resume-registry', type=Path)
    args = parser.parse_args()
    policy = json.loads((HERE / 'policy.json').read_text())
    import re
    need(re.fullmatch('[0-9a-f]{40}', args.registration_commit), 'REGISTRATION_COMMIT')
    state = registry.load(args.resume_registry, policy) if args.resume_registry else None
    # Copy-on-write: never overwrite an earlier run or its registry.
    reader = Reader(args.out, max_requests=policy['max_requests'], max_seconds=policy['max_run_seconds'])
    journal = Journal(reader.folder)
    try:
        run(reader, journal, policy, args.registration_commit, reader.folder / 'registry.json', state)
    except Exception as error:
        journal.append('stopped', {'exception': type(error).__name__, 'reason': str(error)[:250],
                                   'rpc_calls': reader.count, 'http_requests': len(reader.records),
                                   'profitability_measured': False})
        print(json.dumps({'status': 'stopped', 'exception': type(error).__name__, 'reason': str(error)[:250]}), flush=True)
        return 1
    print(json.dumps({'status': 'completed', 'rpc_calls': reader.count, 'http_requests': len(reader.records)}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
