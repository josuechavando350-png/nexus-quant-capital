#!/usr/bin/env python3
"""Fixed backward extension, forward catch-up, and same-block read comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from support import (HERE, need, canonical, qty, Reader, Journal, registry,
                     get_header, canonical_check, update_registry, authenticate, snapshot)
from backfill import merge
import lens


class PhaseReader(Reader):
    phase = 'verify'

    def group(self, queries, label, batch=True):
        return super().group(queries, self.phase + '-' + label, batch)


def creation_snapshot(reader, journal, block, addresses, policy, round_index):
    journal.append('creation_started', {'round': round_index, 'block': block})
    record_index = len(reader.records)
    started = time.monotonic_ns()
    output = lens.call(reader, block, addresses, f'observe-r{round_index}-creation')
    finished = time.monotonic_ns()
    state = lens.parse(block, addresses, output, policy)
    canonical_check(reader, block, f'r{round_index}-creation-canonical')
    result = {'round': round_index, 'mode': 'creation', 'block': block, 'state': state,
              'record_index': record_index, 'started_ns': started, 'input_finished_ns': finished,
              'input_elapsed_ms': (finished - started) / 10**6}
    journal.append('creation_completed', result)
    return result


def run(reader, journal, policy, registration, source_bytes):
    need(hashlib.sha256(source_bytes).hexdigest() == policy['source_registry_file_sha256'], 'SOURCE_FILE_HASH')
    original = json.loads(source_bytes)
    existing = original['state']
    need(registry.digest(existing) == original['sha256'], 'SOURCE_REGISTRY_HASH')
    registry.validate(existing, policy)
    need(existing['status'] == 'valid_prefix', 'INVALID_SOURCE_REGISTRY')
    first, last = policy['backfill_from_block'], policy['backfill_through_block']
    need(last == existing['from_block'] - 1 and last - first + 1 == policy['backfill_blocks'], 'FIXED_BACKFILL_WINDOW')
    (reader.folder / 'source-registry.json').write_bytes(source_bytes)
    journal.append('registered', {'policy': policy, 'registration_commit': registration,
                                  'source_registry_sha256': original['sha256'], 'production_authorization': False})
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, existing['checkpoint'], 'source-checkpoint')
    boundary = get_header(reader, last, 'backfill-boundary')
    need(boundary == existing['segments'][0]['start'], 'SOURCE_BOUNDARY_REORG')
    reader.phase = 'backfill'
    journal.append('backfill_started', {'first': first, 'last': last, 'anchor': boundary})
    older = update_registry(reader, journal, policy, reader.folder / 'older-registry.json', registry.new(first), boundary)
    combined = merge(older, existing, policy)
    reader.phase = 'verify'
    canonical_check(reader, existing['checkpoint'], 'source-after-backfill')
    journal.append('backfill_merged', {'older_registry_sha256': registry.digest(older),
                                     'merged_registry_sha256': registry.digest(combined),
                                     'source_registry_sha256': registry.digest(existing)})
    registry.save(reader.folder / 'merged-before-catchup.json', combined)
    reader.phase = 'catchup'
    head = get_header(reader, 'latest', 'head')
    anchor = get_header(reader, head['number'] - policy['confirmation_buffer_blocks'], 'anchor')
    journal.append('catchup_started', {'anchor': anchor})
    combined = update_registry(reader, journal, policy, reader.folder / 'registry.json', combined, anchor)
    cohort = registry.freeze(combined, anchor['number'], policy)
    frozen = journal.append('cohort_frozen', cohort)
    (reader.folder / 'cohort.json').write_bytes(canonical(cohort))
    reader.phase = 'observe'
    authenticate(reader, anchor)
    prior_height = anchor['number']
    for index, order in enumerate(policy['paired_read_order']):
        block = get_header(reader, 'latest', f'r{index}-head')
        head_received = reader.records[-1]['received_ns']
        need(block['number'] > prior_height and block['timestamp'] >= frozen['recorded_wall_ns'] // 10**9,
             'NON_PROSPECTIVE_OR_REPEATED_HEAD')
        prior_height = block['number']
        results = []
        for mode in order:
            if mode == 'creation':
                result = creation_snapshot(reader, journal, block, cohort['addresses'], policy, index)
            else:
                need(mode == 'batch', 'READ_MODE')
                result = snapshot(reader, journal, block, cohort['addresses'], policy, mode, index)
            results.append(result)
        need(results[0]['state'] == results[1]['state'], 'SAME_BLOCK_LENS_BATCH_PARITY_FAILED')
        journal.append('paired_comparison', {'round': index, 'block': block, 'order': order,
                       'exact_state_parity': True,
                       'input_ms': {x['mode']: x['input_elapsed_ms'] for x in results},
                       'first_mode': order[0],
                       'head_to_first_inputs_ms': (results[0]['input_finished_ns'] - head_received) / 10**6,
                       'head_to_second_inputs_ms': (results[1]['input_finished_ns'] - head_received) / 10**6,
                       'within_assumed_budget_first_mode': results[0]['input_finished_ns'] - head_received <= policy['freshness_budget_ms_assumed'] * 10**6})
        print(json.dumps({'round': index, 'borrowers': len(cohort['addresses']), 'parity': True,
                          'creation_ms': next(x['input_elapsed_ms'] for x in results if x['mode'] == 'creation'),
                          'batch_ms': next(x['input_elapsed_ms'] for x in results if x['mode'] == 'batch')}), flush=True)
    journal.append('completed', {'rpc_calls': reader.count, 'http_requests': len(reader.records),
                                'route_simulations': 0, 'live_broadcasts': 0, 'realized_profit': None})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--registration-commit', required=True)
    args = parser.parse_args()
    need(re.fullmatch('[0-9a-f]{40}', args.registration_commit), 'REGISTRATION_COMMIT')
    lock = json.loads((HERE / 'registration-sources.json').read_text())
    for name, expected in lock['files'].items():
        need(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, 'REGISTERED_SOURCE_CHANGED_' + name)
    policy = json.loads((HERE / 'policy.json').read_text())
    source = (HERE.parent.parent / policy['source_registry_path']).read_bytes()
    reader = PhaseReader(args.out, max_requests=policy['max_requests'], max_seconds=policy['max_run_seconds'])
    journal = Journal(reader.folder)
    try:
        run(reader, journal, policy, args.registration_commit, source)
    except Exception as error:
        journal.append('stopped', {'exception': type(error).__name__, 'reason': str(error)[:250],
                                   'rpc_calls': reader.count, 'http_requests': len(reader.records), 'realized_profit': None})
        print(json.dumps({'status': 'stopped', 'reason': str(error)[:250]}), flush=True)
        return 1
    print(json.dumps({'status': 'completed', 'rpc_calls': reader.count, 'http_requests': len(reader.records)}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
