#!/usr/bin/env python3
"""Bounded new history window; frozen cohort; three single-call observations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from continuation import (HERE, need, canonical, qty, registry, PhaseReader, Journal,
                          get_header, canonical_check, update_registry, authenticate,
                          merge, creation_snapshot)


def source_state(policy, source_bytes):
    need(hashlib.sha256(source_bytes).hexdigest() == policy['source_registry_file_sha256'], 'SOURCE_FILE_HASH')
    original = json.loads(source_bytes)
    need(set(original) == {'state', 'sha256'} and registry.digest(original['state']) == original['sha256'], 'SOURCE_REGISTRY_HASH')
    state = original['state']; registry.validate(state, policy)
    need(state['status'] == 'valid_prefix', 'INVALID_SOURCE_REGISTRY')
    need(policy['backfill_through_block'] == state['from_block']-1 and
         policy['backfill_through_block']-policy['backfill_from_block']+1 == policy['backfill_blocks'], 'FIXED_BACKFILL_WINDOW')
    need(policy['read_mode'] == 'creation' and policy['rounds'] == 3 and policy['creation_call_gas_limit'] == 2000000, 'FIXED_OBSERVATION_POLICY')
    return state


def run(reader, journal, policy, registration, source_bytes):
    existing = source_state(policy, source_bytes)
    (reader.folder/'source-registry.json').write_bytes(source_bytes)
    journal.append('registered', {'policy': policy, 'registration_commit': registration,
                                  'source_registry_sha256': registry.digest(existing), 'production_authorization': False})
    need(qty(reader.call('eth_chainId', [], 'chain')) == policy['chain_id'], 'WRONG_CHAIN')
    canonical_check(reader, existing['checkpoint'], 'source-checkpoint')
    first, last = policy['backfill_from_block'], policy['backfill_through_block']
    boundary = get_header(reader, last, 'backfill-boundary')
    need(boundary == existing['segments'][0]['start'], 'SOURCE_BOUNDARY_REORG')
    reader.phase = 'backfill'
    journal.append('backfill_started', {'first': first, 'last': last, 'anchor': boundary})
    older = update_registry(reader, journal, policy, reader.folder/'older-registry.json', registry.new(first), boundary)
    combined = merge(older, existing, policy)
    reader.phase = 'verify'
    canonical_check(reader, existing['checkpoint'], 'source-after-backfill')
    registry.save(reader.folder/'merged-before-catchup.json', combined)
    journal.append('backfill_merged', {'older_registry_sha256': registry.digest(older),
                                     'merged_registry_sha256': registry.digest(combined),
                                     'source_registry_sha256': registry.digest(existing)})
    reader.phase = 'catchup'
    head = get_header(reader, 'latest', 'head')
    anchor = get_header(reader, head['number']-policy['confirmation_buffer_blocks'], 'anchor')
    journal.append('catchup_started', {'anchor': anchor})
    combined = update_registry(reader, journal, policy, reader.folder/'registry.json', combined, anchor)
    registry.save(reader.folder/'registry.json', combined)
    cohort = registry.freeze(combined, anchor['number'], policy)
    frozen = journal.append('cohort_frozen', cohort)
    (reader.folder/'cohort.json').write_bytes(canonical(cohort))
    reader.phase = 'observe'; authenticate(reader, anchor)
    prior_height = anchor['number']
    for index in range(policy['rounds']):
        block = get_header(reader, 'latest', f'r{index}-head')
        head_record = reader.records[-1]
        need(block['number'] > prior_height and block['timestamp'] >= frozen['recorded_wall_ns']//10**9, 'NON_PROSPECTIVE_OR_REPEATED_HEAD')
        prior_height = block['number']
        result = creation_snapshot(reader, journal, block, cohort['addresses'], policy, index)
        verified = time.monotonic_ns()
        journal.append('observation_completed', {'round': index, 'block': block,
            'verification_finished_ns': verified,
            'head_to_inputs_ms': (result['input_finished_ns']-head_record['received_ns'])/10**6,
            'head_to_verified_ms': (verified-head_record['received_ns'])/10**6,
            'header_request_to_verified_ms': (verified-head_record['started_ns'])/10**6,
            'read_with_canonical_ms': (verified-result['started_ns'])/10**6,
            'within_assumed_input_budget': result['input_finished_ns']-head_record['received_ns'] <= policy['freshness_budget_ms_assumed']*10**6,
            'within_assumed_verified_budget': verified-head_record['received_ns'] <= policy['freshness_budget_ms_assumed']*10**6})
        print(json.dumps({'round': index, 'borrowers': len(cohort['addresses']), 'input_ms': result['input_elapsed_ms'],
                          'verified_after_header_ms': (verified-head_record['received_ns'])/10**6,
                          'candidates': result['state']['screen_candidate_count']}), flush=True)
    journal.append('completed', {'rpc_calls': reader.count, 'http_requests': len(reader.records),
                                'route_simulations': 0, 'live_broadcasts': 0, 'realized_profit': None})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--registration-commit',required=True)
    args=parser.parse_args();need(re.fullmatch('[0-9a-f]{40}',args.registration_commit),'REGISTRATION_COMMIT')
    lock=json.loads((HERE/'registration-sources.json').read_text())
    for name,expected in lock['files'].items():
        need(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==expected,'REGISTERED_SOURCE_CHANGED_'+name)
    policy=json.loads((HERE/'policy.json').read_text());source=(HERE.parent.parent/policy['source_registry_path']).read_bytes()
    source_state(policy,source)
    reader=PhaseReader(args.out,max_requests=policy['max_requests'],max_seconds=policy['max_run_seconds']);journal=Journal(reader.folder)
    try: run(reader,journal,policy,args.registration_commit,source)
    except Exception as error:
        journal.append('stopped',{'exception':type(error).__name__,'reason':str(error)[:250],
                                 'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
        print(json.dumps({'status':'stopped','reason':str(error)[:250]}),flush=True);return 1
    print(json.dumps({'status':'completed','rpc_calls':reader.count,'http_requests':len(reader.records)}),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
