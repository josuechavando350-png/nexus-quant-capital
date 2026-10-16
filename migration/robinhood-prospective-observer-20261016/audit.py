#!/usr/bin/env python3
"""Offline reconciliation; incomplete collection is not evidence of no opportunities."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

import read_rpc as rpc
from model import words, screen, size, MARKET_PARAMS, encode
from observer import read, route_context, route_transaction, enrollment, native_fee, economic_hypothesis


def journal_rows(path):
    rows, previous = [], '0' * 64
    for index, line in enumerate(path.read_bytes().splitlines()):
        row = json.loads(line)
        digest = row.pop('sha256')
        rpc.need(row['sequence'] == index and row['previous_sha256'] == previous and
                 hashlib.sha256(rpc.canonical(row)).hexdigest() == digest, 'JOURNAL_HASH_CHAIN_MISMATCH')
        rpc.need(not rows or row['recorded_ns'] >= rows[-1]['recorded_ns'], 'JOURNAL_TIME_REVERSED')
        row['sha256'] = digest; previous = digest; rows.append(row)
    rpc.need(rows and rows[0]['kind'] == 'registration' and rows[-1]['kind'] == 'stop', 'INCOMPLETE_JOURNAL')
    return rows


def audit(folder):
    rows = journal_rows(folder / 'journal.jsonl')
    registration = rows[0]['data']; policy = registration['policy']
    rpc.need(hashlib.sha256(rpc.canonical(policy)).hexdigest() == registration['policy_sha256'], 'POLICY_HASH_MISMATCH')
    requests = read(folder / 'requests.json')
    records, results = {}, {}
    for index, record in enumerate(requests, 1):
        request = record['request']; rpc.validate(request['method'], request['params'])
        rpc.need(request['id'] == index and record['started_ns'] <= record['finished_ns'], 'REQUEST_ORDER_OR_TIME')
        records[index] = record
        if 'response_file' not in record: continue
        raw = (folder / record['response_file']).read_bytes()
        rpc.need(hashlib.sha256(raw).hexdigest() == record['response_sha256'], 'RESPONSE_DIGEST_MISMATCH')
        response = json.loads(raw)
        rpc.need(response.get('jsonrpc') == '2.0' and response.get('id') == index, 'RESPONSE_ID_MISMATCH')
        if 'result' in response: results[index] = response['result']
    rpc.need(len(requests) <= policy['maximum_rpc_requests'], 'REQUEST_LIMIT_EXCEEDED')
    frozen_rows = [r for r in rows if r['kind'] == 'cohort_frozen']
    snapshots = {r['data']['round']: r for r in rows if r['kind'] == 'snapshot'}
    completed = {r['data']['round'] for r in rows if r['kind'] == 'round_complete'}
    decisions = [r for r in rows if r['kind'] == 'decision']
    if frozen_rows:
        rpc.need(len(frozen_rows) == 1, 'COHORT_CHANGED')
        frozen = frozen_rows[0]
        cohort = frozen['data']
        anchor_record = next(r for r in requests if r['label'] == 'cohort-anchor')
        anchor = rpc.header(results[anchor_record['request']['id']])
        rpc.need(cohort['from_block'] == anchor['number'] - policy['lookback_blocks'] + 1, 'COHORT_WINDOW_CHANGED')
        logs = [log for r in requests if r['label'].startswith('cohort-events-') for log in results[r['request']['id']]]
        rpc.need(enrollment(logs, cohort['from_block'], anchor, policy) == cohort, 'COHORT_DIFFERS_FROM_EVENTS')
    else:
        rpc.need(not snapshots and not decisions, 'DECISION_WITHOUT_FROZEN_COHORT')
        cohort = None
    for snapshot_row in snapshots.values():
        s = snapshot_row['data']; block = s['block']; ids = s['input_request_ids']
        head_record = next(r for r in requests if r['label'] == f"round-{s['round']}-header")
        rpc.need(rpc.header(results[head_record['request']['id']], head_record['received_wall_ns']) == block and
                 s['received_ns'] == head_record['received_ns'], 'SNAPSHOT_HEADER_MISMATCH')
        rpc.need(snapshot_row['recorded_ns'] > frozen['recorded_ns'] and block['number'] > cohort['through_block'] and
                 block['timestamp'] >= frozen['recorded_wall_ns'] // 10**9, 'NONPROSPECTIVE_SNAPSHOT')
        rpc.need(list(s['positions']) == cohort['addresses'], 'COHORT_MEMBERS_CHANGED')
        rpc.need(len(ids) == 3 + len(cohort['addresses']), 'MISSING_SNAPSHOT_INPUT')
        expected_calls = [(rpc.MORPHO, '0x5c60e39a' + rpc.MARKET[2:], s['market']),
                          (rpc.ORACLE, '0xa035b1fe', [s['price']]),
                          (rpc.IRM, encode('0x8c00bf6b', *MARKET_PARAMS, *s['market']), [s['rate']])]
        expected_calls.extend((rpc.MORPHO, encode('0x93c52062', int(rpc.MARKET, 16), int(a, 16)), s['positions'][a]) for a in cohort['addresses'])
        for identity, (to, data, values) in zip(ids, expected_calls):
            r = records[identity]
            rpc.need(r['request']['method'] == 'eth_call' and r['request']['params'] ==
                     [{'to': to, 'data': data}, {'blockHash': block['hash'], 'requireCanonical': True}], 'SNAPSHOT_REQUEST_CONTEXT')
            rpc.need(words(results[identity], len(values)) == values and r['received_ns'] <= s['inputs_finished_ns'] <= snapshot_row['recorded_ns'], 'FUTURE_OR_CHANGED_SNAPSHOT_INPUT')
    for row in decisions:
        d = row['data']; s = snapshots[d['round']]['data']; block = s['block']
        rpc.need(d['borrower'] in s['positions'] and d['source_hash'] == block['hash'] and
                 d['input_request_ids'] == s['input_request_ids'] and
                 s['inputs_finished_ns'] <= d['decision_ns'] <= row['recorded_ns'], 'FUTURE_DECISION_INPUT')
        expected = screen(s['positions'][d['borrower']], s['market'], s['rate'], s['price'], block['timestamp'], policy)
        rpc.need(d['screen'] == expected and d['production_authorization'] is False, 'DECISION_SCREEN_MISMATCH')
        age = d['decision_ns'] - s['received_ns']
        rpc.need(d['received_ns'] == s['received_ns'] and d['decision_age_ms'] == age / 10**6 and
                 d['stale_under_assumed_budget'] is (age > policy['max_decision_age_ms_assumed'] * 10**6), 'DECISION_AGE_MISMATCH')
        for simulation in d['simulations']:
            ident = simulation['request_id']; request = records[ident]['request']; trace = results[ident]
            rpc.need(request['method'] == 'debug_traceCall' and request['params'][1] == {'blockHash': block['hash'], 'requireCanonical': True}, 'TRACE_USED_OTHER_STATE')
            rpc.need(d['sizing'] == size(expected, s['price'], policy) and
                     request['params'][0] == d['transaction'] == route_transaction(block, d['borrower'], d['sizing'], policy), 'PREPARED_PAYLOAD_CHANGED')
            config = request['params'][2]
            rpc.need(config['stateOverrides'] == route_context(), 'PROTOCOL_OR_FIXTURE_STATE_CHANGED')
            projection = simulation['projection_seconds']
            rpc.need(projection in [0, policy['projection_seconds']] and config.get('blockOverrides') ==
                     ({'time': hex(block['timestamp'] + projection)} if projection else None), 'UNDECLARED_PROJECTION')
            success = not bool(trace.get('error'))
            rpc.need(simulation['success'] is success and simulation['surplus_usdg_raw'] ==
                     (words(trace['output'], 1)[0] if success else None), 'TRACE_RESULT_MISMATCH')
            rpc.need(native_fee(trace) == simulation['native_route_simulation_fee'] and
                     records[ident]['received_ns'] == simulation['simulation_finished_ns'] <= d['decision_ns'], 'TRACE_TIME_OR_FEE_MISMATCH')
        successful = [x['surplus_usdg_raw'] for x in d['simulations'] if x['success']]
        if successful:
            rpc.need(d['economics_hypothesis'] == economic_hypothesis(min(successful), policy), 'ECONOMICS_CHANGED')
    decision_index = {(r['data']['source_hash'], r['data']['borrower']): r['data'] for r in decisions}
    outcome_keys = set()
    for row in (r for r in rows if r['kind'] == 'outcome'):
        outcome = row['data']; key = (outcome['source_hash'], outcome['borrower'])
        rpc.need(key in decision_index and key not in outcome_keys, 'UNKNOWN_OR_DUPLICATE_OUTCOME')
        outcome_keys.add(key); d = decision_index[key]
        rpc.need(any(s['success'] for s in d['simulations']), 'OUTCOME_WITHOUT_SUCCESSFUL_CANDIDATE')
        if outcome['status'] == 'RIGHT_CENSORED_RUN_ENDED':
            rpc.need(outcome['survival'] is None, 'CENSORED_OUTCOME_NOT_UNKNOWN')
            continue
        block = outcome['next_observed_block']
        candidates = [r for r in requests if r['label'].startswith('round-') and r['label'].endswith('-header') and
                      rpc.header(results[r['request']['id']]) == block]
        rpc.need(len(candidates) == 1 and candidates[0]['received_ns'] > d['decision_ns'], 'OUTCOME_HEADER_NOT_AFTER_DECISION')
        delta = block['number'] - d['source_block']
        if outcome['status'] == 'DEADLINE_PASSED_BEFORE_NEXT_OBSERVED_HEAD':
            rpc.need(delta > policy['valid_through_blocks_after_source'] and
                     outcome['unobserved_intermediate_blocks'] == delta - 1 and outcome['survival_at_intermediate_blocks'] is None,
                     'UNOBSERVED_GAP_MISCLASSIFIED')
        else:
            rpc.need(outcome['status'] == 'EXACT_PAYLOAD_RECHECK' and 0 < delta <= policy['valid_through_blocks_after_source'], 'INVALID_RECHECK_DEADLINE')
            simulation = outcome['simulation']; r = records[simulation['request_id']]; tx, block_pin, config = r['request']['params']
            trace = results[simulation['request_id']]
            rpc.need(r['request']['method'] == 'debug_traceCall' and tx == d['transaction'] and
                     block_pin == {'blockHash': block['hash'], 'requireCanonical': True} and
                     config['stateOverrides'] == route_context() and 'blockOverrides' not in config, 'RECHECK_PAYLOAD_OR_STATE_CHANGED')
            success = not bool(trace.get('error'))
            rpc.need(simulation['success'] is success and simulation['surplus_usdg_raw'] ==
                     (words(trace['output'], 1)[0] if success else None) and native_fee(trace) == simulation['native_route_simulation_fee'] and
                     d['decision_ns'] < r['received_ns'] <= row['recorded_ns'], 'RECHECK_RESULT_OR_TIME_CHANGED')
    for r in (x for x in rows if x['kind'] == 'round_complete'):
        d = r['data']; s = snapshots[d['round']]['data']
        matching = [x['data'] for x in decisions if x['data']['round'] == d['round']]
        rpc.need(len(matching) == len(s['positions']) == d['observed_borrowers'], 'ROUND_DECISION_COUNT_MISMATCH')
        signals = sum(x['screen']['screen_candidate'] for x in matching)
        rpc.need(d['candidate_count'] == signals and d['no_signal'] is ((signals == 0) if matching else None), 'ROUND_SIGNAL_COUNT_MISMATCH')
        confirm = next(x for x in requests if x['label'] == f"round-{d['round']}-canonical")
        rpc.need(rpc.header(results[confirm['request']['id']]) == s['block'] == d['block'], 'ROUND_CANONICAL_HEADER_MISMATCH')
    stop = rows[-1]['data']
    complete = stop['status'] == 'FINITE_PILOT_COMPLETE'
    rpc.need(stop['requests'] == len(requests) and stop['broadcasts'] == 0, 'STOP_COUNTER_MISMATCH')
    valid_decisions = [r['data'] for r in decisions if r['data']['round'] in completed]
    latencies = [(r['received_ns'] - r['started_ns']) / 10**6 for r in requests if 'received_ns' in r]
    complete_rounds = [r['data'] for r in rows if r['kind'] == 'round_complete']
    return {'status': stop['status'], 'reason': stop['reason'], 'registration_commit': registration['registration_commit'],
            'cohort_size': len(cohort['addresses']) if cohort else None,
            'cohort_borrow_event_count': len(cohort['events']) if cohort else None,
            'completed_rounds': len(completed), 'requested_rounds': policy['rounds'],
            'borrower_state_observations': len(valid_decisions),
            'screen_candidate_observations': sum(d['screen']['screen_candidate'] for d in valid_decisions),
            'successful_route_simulations': sum(x['success'] for d in valid_decisions for x in d['simulations']),
            'reverted_route_simulations': sum(not x['success'] for d in valid_decisions for x in d['simulations']),
            'candidates_skipped_by_capacity': sum(d['status'] == 'CANDIDATE_NOT_SIMULATED_CAPACITY_LIMIT' for d in valid_decisions),
            'empty_cohort_rounds': sum(r['observed_borrowers'] == 0 for r in complete_rounds),
            'nonempty_cohort_rounds_without_signal': sum(r['no_signal'] is True for r in complete_rounds),
            'stale_decisions_under_assumed_budget': sum(d['stale_under_assumed_budget'] for d in valid_decisions),
            'outcomes': [r['data'] for r in rows if r['kind'] == 'outcome'],
            'requests': len(requests), 'request_latency_ms': {'min': min(latencies), 'median': statistics.median(latencies), 'max': max(latencies)} if latencies else None,
            'last_journal_sha256': rows[-1]['sha256'], 'complete_with_nonempty_cohort': complete and bool(cohort and cohort['addresses']),
            'realized_capture_rate': None, 'realized_net_profit': None, 'production_authorization': False,
            'full_aa_costs_measured_prospectively': False, 'external_funding_committed': False,
            'source_count': 1, 'state_proofs_verified': False, 'broadcasts': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.folder)
    args.out.write_bytes(rpc.canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
