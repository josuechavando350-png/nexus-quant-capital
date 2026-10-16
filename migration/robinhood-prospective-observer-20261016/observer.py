#!/usr/bin/env python3
"""Finite prospective research run, frozen recent-borrow cohort, zero broadcasting."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from read_rpc import (Reader, need, canonical, qty, header, HASH, MORPHO, ORACLE, IRM,
                      MARKET, BORROW, ACCOUNT, EXECUTOR, ROUTER, FIXTURES)
from model import MARKET_PARAMS, encode, words, screen, size

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'robinhood-real-state-replay-20261016'
PRIOR = HERE.parent / 'robinhood-opportunity-economics-20261016'
sys.path.insert(0, str(OLD)); sys.path.insert(0, str(PRIOR))
from audit_result import native_fee, flatten
from economics import evaluate, stringify


def read(path):
    return json.loads(path.read_text())


class Journal:
    def __init__(self, folder):
        self.path = folder / 'journal.jsonl'
        need(not self.path.exists(), 'NEW_JOURNAL_REQUIRED')
        self.previous = '0' * 64
        self.count = 0

    def append(self, kind, data):
        row = {'sequence': self.count, 'previous_sha256': self.previous, 'kind': kind,
               'recorded_ns': time.monotonic_ns(), 'recorded_wall_ns': time.time_ns(), 'data': data}
        row['sha256'] = hashlib.sha256(canonical(row)).hexdigest()
        with self.path.open('ab') as stream:
            stream.write(canonical(row)); stream.flush(); os.fsync(stream.fileno())
        self.count += 1; self.previous = row['sha256']
        return row


def enrollment(logs, first, anchor, policy):
    need(type(logs) is list and len(logs) <= policy['max_logs'], 'COHORT_LOG_LIMIT')
    identities, events = set(), []
    for log in logs:
        topics = log.get('topics', [])
        need(log.get('address', '').lower() == MORPHO and len(topics) == 4 and
             topics[:2] == [BORROW, MARKET] and log.get('removed') is False, 'INVALID_BORROW_EVENT')
        need(all(type(x) is str and HASH.fullmatch(x) for x in topics), 'INVALID_BORROW_TOPICS')
        need(all(int(x[2:26], 16) == 0 and int(x[26:], 16) > 0 for x in topics[2:]), 'INVALID_BORROW_ADDRESS')
        caller, assets, shares = words(log['data'], 3)
        need(0 < caller < 2**160 and assets > 0 and shares > 0, 'INVALID_BORROW_DATA')
        number = qty(log['blockNumber'])
        need(first <= number <= anchor['number'] and HASH.fullmatch(log['blockHash']) and
             HASH.fullmatch(log['transactionHash']), 'EVENT_OUTSIDE_ENROLLMENT')
        event_id = (log['blockHash'], qty(log['transactionIndex']), qty(log['logIndex']))
        need(event_id not in identities, 'DUPLICATE_EVENT')
        identities.add(event_id)
        events.append({'borrower': '0x' + topics[2][-40:], 'block': number,
                       'block_hash': log['blockHash'], 'transaction': log['transactionHash'],
                       'transaction_index': event_id[1], 'log_index': event_id[2]})
    events.sort(key=lambda x: (x['block'], x['transaction_index'], x['log_index']))
    addresses = sorted({e['borrower'] for e in events})
    need(len(addresses) <= policy['max_borrowers'], 'COHORT_TOO_LARGE_NO_TRUNCATION')
    need(len({e['block'] for e in events}) <= policy['max_event_blocks'], 'COHORT_HEADER_LIMIT')
    return {'addresses': addresses, 'events': events, 'from_block': first, 'through_block': anchor['number'],
            'anchor_hash': anchor['hash'], 'selection_uses_health_or_liquidation_outcome': False,
            'complete_active_borrower_universe': False}


def pin(block):
    return {'blockHash': block['hash'], 'requireCanonical': True}


def call_view(reader, block, to, data, label):
    return reader.call('eth_call', [{'to': to, 'data': data}, pin(block)], label)


def check_canonical(reader, block, label):
    again = header(reader.call('eth_getBlockByNumber', [hex(block['number']), False], label))
    need(again == block, 'REORG_OR_HEADER_CHANGED')


def bootstrap(reader, policy):
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    raw = reader.call('eth_getBlockByNumber', ['latest', False], 'cohort-anchor')
    anchor = header(raw, reader.records[-1]['received_wall_ns'])
    first = anchor['number'] - policy['lookback_blocks'] + 1
    need(first > 0, 'ANCHOR_TOO_LOW')
    logs = []
    for i, start in enumerate(range(first, anchor['number'] + 1, policy['log_shard_blocks'])):
        logs.extend(reader.call('eth_getLogs', [{'address': MORPHO, 'topics': [BORROW, MARKET],
                    'fromBlock': hex(start), 'toBlock': hex(min(anchor['number'], start + policy['log_shard_blocks'] - 1))}], f'cohort-events-{i}'))
        need(len(logs) <= policy['max_logs'], 'COHORT_LOG_LIMIT')
    cohort = enrollment(logs, first, anchor, policy)
    for number in sorted({e['block'] for e in cohort['events']}):
        block = header(reader.call('eth_getBlockByNumber', [hex(number), False], f'cohort-block-{number}'))
        need(block['number'] == number and all(e['block_hash'] == block['hash'] for e in cohort['events'] if e['block'] == number),
             'COHORT_EVENT_HEADER_MISMATCH')
    check_canonical(reader, anchor, 'cohort-anchor-confirmed')
    return anchor, cohort


def authenticate_contracts(reader, anchor):
    original = read(OLD / 'evidence/provider-capture/08-prestate.json')['result']
    codes = {}
    for label, address in [('morpho', MORPHO), ('oracle', ORACLE), ('irm', IRM)]:
        code = reader.call('eth_getCode', [address, pin(anchor)], 'code-' + label)
        need(code == original[address]['code'], 'PROTOCOL_CODE_CHANGED_' + label.upper())
        codes[address] = hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()
    for i, address in enumerate(sorted(FIXTURES)):
        need(reader.call('eth_getCode', [address, pin(anchor)], f'fixture-empty-{i}') == '0x', 'FIXTURE_ADDRESS_HAS_LIVE_CODE')
    params = words(call_view(reader, anchor, MORPHO, '0x2c3c9157' + MARKET[2:], 'market-identity'), 5)
    need(params == MARKET_PARAMS, 'MARKET_PARAMS_CHANGED')
    return codes


def route_context():
    archived = read(HERE.parent / 'robinhood-sponsor-window-20261016/evidence/local-31/simulation-input.json')
    return {EXECUTOR: {'code': archived['state_overrides'][EXECUTOR]['code'], 'state': {}},
            ROUTER: {'code': archived['state_overrides'][ROUTER]['code'], 'state': {}},
            ACCOUNT: {'code': '0x', 'balance': hex(10**16), 'nonce': '0x0'}}


def route_transaction(block, address, sizing, policy):
    execution_id = int.from_bytes(hashlib.sha256(canonical([block['hash'], address, sizing])).digest(), 'big')
    data = encode('0x3d47ed94', *MARKET_PARAMS, int(address, 16), sizing['seize_raw'],
                  sizing['max_repay_usdg_raw'], policy['minimum_surplus_usdg_raw'],
                  sizing['predicted_repay_usdg_raw'] + policy['minimum_surplus_usdg_raw'],
                  block['number'] + policy['valid_through_blocks_after_source'], execution_id)
    return {'from': ACCOUNT, 'to': EXECUTOR, 'data': data, 'gas': hex(3000000), 'gasPrice': hex(block['base_fee_wei'])}


def simulate(reader, block, transaction, projection, label):
    config = {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}, 'timeout': '10s',
              'reexec': 0, 'stateOverrides': route_context()}
    if projection: config['blockOverrides'] = {'time': hex(block['timestamp'] + projection)}
    trace = reader.call('debug_traceCall', [transaction, pin(block), config], label)
    fee = native_fee(trace)
    success = not bool(trace.get('error'))
    surplus = words(trace.get('output'), 1)[0] if success else None
    need(not success or not any(f.get('error') for f in flatten(trace)), 'NESTED_ERROR_IN_SUCCESS')
    return {'request_id': reader.count, 'source_hash': block['hash'], 'projection_seconds': projection,
            'success': success, 'surplus_usdg_raw': surplus, 'native_route_simulation_fee': fee,
            'error': trace.get('error'), 'output_prefix': str(trace.get('output', '0x'))[:202],
            'full_account_abstraction_cycle': False, 'simulation_finished_ns': reader.records[-1]['received_ns']}


def economic_hypothesis(surplus, policy):
    assumptions = copy.deepcopy(policy['economics_assumptions_not_quotes'])
    cap = assumptions.pop('success_and_failure_cap_wei')
    return stringify(evaluate(f'{surplus // 10**6}.{surplus % 10**6:06d}',
                              cap, cap, **assumptions))


def run(reader, journal, policy, registration):
    journal.append('registration', {'policy': policy, 'registration_commit': registration,
                                   'policy_sha256': hashlib.sha256(canonical(policy)).hexdigest(),
                                   'production_authorization': False})
    anchor, cohort = bootstrap(reader, policy)
    frozen = journal.append('cohort_frozen', cohort)
    (reader.folder / 'cohort.json').write_bytes(canonical(cohort))
    journal.append('contracts', authenticate_contracts(reader, anchor))
    previous_candidates = []
    previous_block = anchor
    for round_index in range(policy['rounds']):
        prefix = f'round-{round_index}'
        raw = reader.call('eth_getBlockByNumber', ['latest', False], prefix + '-header')
        received_ns = reader.records[-1]['received_ns']
        block = header(raw, reader.records[-1]['received_wall_ns'])
        need(block['number'] > cohort['through_block'] and received_ns > frozen['recorded_ns'], 'OBSERVATION_NOT_AFTER_FREEZE')
        need(block['timestamp'] >= frozen['recorded_wall_ns'] // 10**9, 'BLOCK_PREDATES_COHORT_FREEZE')
        need(block['number'] >= previous_block['number'], 'HEAD_REGRESSED')
        if block['number'] == previous_block['number']:
            need(block['hash'] == previous_block['hash'], 'SAME_HEIGHT_REORG')
            journal.append('duplicate_head', {'round': round_index, 'block': block})
            continue
        check_canonical(reader, previous_block, prefix + '-previous-canonical')
        for previous in previous_candidates:
            # Keep the exact prepared payload and deadline; never grant it a new expiry.
            deadline = previous['block']['number'] + policy['valid_through_blocks_after_source']
            if block['number'] > deadline:
                outcome = {'status': 'DEADLINE_PASSED_BEFORE_NEXT_OBSERVED_HEAD',
                           'unobserved_intermediate_blocks': block['number'] - previous['block']['number'] - 1,
                           'survival_at_intermediate_blocks': None}
            else:
                outcome = {'status': 'EXACT_PAYLOAD_RECHECK', 'simulation': simulate(reader, block, previous['transaction'], 0,
                           prefix + '-recheck-' + previous['borrower'][-8:])}
            journal.append('outcome', {'borrower': previous['borrower'], 'source_hash': previous['block']['hash'],
                                      'next_observed_block': block, **outcome})
        previous_candidates = []
        inputs_start = reader.count + 1
        market = words(call_view(reader, block, MORPHO, '0x5c60e39a' + MARKET[2:], prefix + '-market'), 6)
        price = words(call_view(reader, block, ORACLE, '0xa035b1fe', prefix + '-oracle'), 1)[0]
        rate = words(call_view(reader, block, IRM, encode('0x8c00bf6b', *MARKET_PARAMS, *market), prefix + '-rate'), 1)[0]
        positions = {address: words(call_view(reader, block, MORPHO,
                     encode('0x93c52062', int(MARKET, 16), int(address, 16)), prefix + '-position-' + str(i)), 3)
                     for i, address in enumerate(cohort['addresses'])}
        inputs_finished_ns = reader.records[-1]['received_ns']
        input_ids = list(range(inputs_start, reader.count + 1))
        journal.append('snapshot', {'round': round_index, 'block': block, 'received_ns': received_ns,
                                   'market': market, 'price': price, 'rate': rate, 'positions': positions,
                                   'input_request_ids': input_ids, 'inputs_finished_ns': inputs_finished_ns,
                                   'gap_from_previous_observation': block['number'] - previous_block['number'] - 1})
        selected = 0
        for address, position in positions.items():
            screening = screen(position, market, rate, price, block['timestamp'], policy)
            decision = {'round': round_index, 'borrower': address, 'source_hash': block['hash'],
                        'source_block': block['number'], 'received_ns': received_ns,
                        'input_request_ids': input_ids, 'screen': screening, 'simulations': [],
                        'production_authorization': False, 'full_costs_verified': False,
                        'reasons': ['BUNDLER_ADMISSION_UNPROVEN', 'NO_COMMITTED_FUNDING', 'LATENCY_BUDGET_UNPROVEN']}
            if not screening['screen_candidate']:
                decision['status'] = 'NO_SCREEN_TRIGGER'
            elif selected >= policy['max_trace_candidates_per_round']:
                decision['status'] = 'CANDIDATE_NOT_SIMULATED_CAPACITY_LIMIT'
            else:
                selected += 1
                sizing = size(screening, price, policy)
                decision['sizing'] = sizing
                if sizing is None:
                    decision['status'] = 'CANDIDATE_NO_VALID_SIZE'
                else:
                    transaction = route_transaction(block, address, sizing, policy)
                    journal.append('candidate_prepared', {'round': round_index, 'borrower': address,
                                   'source_hash': block['hash'], 'transaction': transaction, 'sizing': sizing})
                    for projection in [0, policy['projection_seconds']]:
                        decision['simulations'].append(simulate(reader, block, transaction, projection,
                            prefix + '-route-' + address[-8:] + '-p' + str(projection)))
                    decision['status'] = 'CANDIDATE_SIMULATED'
                    decision['transaction'] = transaction
                    valid = [s for s in decision['simulations'] if s['success']]
                    if valid:
                        gross = min(s['surplus_usdg_raw'] for s in valid)
                        decision['economics_hypothesis'] = economic_hypothesis(gross, policy)
                        previous_candidates.append({'borrower': address, 'block': block, 'transaction': transaction})
            decision['decision_ns'] = time.monotonic_ns()
            decision['decision_age_ms'] = (decision['decision_ns'] - received_ns) / 10**6
            decision['stale_under_assumed_budget'] = decision['decision_ns'] - received_ns > policy['max_decision_age_ms_assumed'] * 10**6
            if decision['stale_under_assumed_budget']: decision['reasons'].append('STALE_SNAPSHOT')
            journal.append('decision', decision)
        check_canonical(reader, block, prefix + '-canonical')
        journal.append('round_complete', {'round': round_index, 'block': block, 'observed_borrowers': len(positions),
                                        'candidate_count': sum(screen(p, market, rate, price, block['timestamp'], policy)['screen_candidate'] for p in positions.values()),
                                        'no_signal': (not any(screen(p, market, rate, price, block['timestamp'], policy)['screen_candidate'] for p in positions.values())) if positions else None})
        previous_block = block
        print(json.dumps({'round': round_index, 'block': block['number'], 'borrowers': len(positions),
                          'simulated_candidates': selected, 'requests': reader.count}), flush=True)
        if round_index + 1 < policy['rounds']: time.sleep(policy['pause_between_rounds_seconds'])
    for previous in previous_candidates:
        journal.append('outcome', {'borrower': previous['borrower'], 'source_hash': previous['block']['hash'],
                                  'status': 'RIGHT_CENSORED_RUN_ENDED', 'survival': None})
    return 'FINITE_PILOT_COMPLETE'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--registration-commit', required=True)
    args = parser.parse_args()
    need(len(args.registration_commit) == 40 and all(c in '0123456789abcdef' for c in args.registration_commit), 'REGISTRATION_COMMIT_REQUIRED')
    policy = read(HERE / 'policy.json')
    reader = Reader(args.out)
    journal = Journal(args.out)
    try:
        status = run(reader, journal, policy, args.registration_commit)
        reason = None
    except Exception as error:
        status, reason = 'INCOMPLETE_OR_BLOCKED', type(error).__name__ + ': ' + str(error)[:200]
    journal.append('stop', {'status': status, 'reason': reason, 'requests': reader.count, 'bytes': reader.total,
                            'prospective_capture_rate_measured': False, 'realized_revenue': False, 'broadcasts': 0})
    print(json.dumps({'status': status, 'reason': reason, 'requests': reader.count}), flush=True)


if __name__ == '__main__': main()
