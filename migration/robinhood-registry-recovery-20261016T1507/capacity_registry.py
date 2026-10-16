"""PR12 registry copy: separate explicit cumulative event-block capacity.
Original immutable; segment enrollment retains max_event_blocks unchanged.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

from common import need, canonical, enrollment, MARKET


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def new(first):
    need(type(first) is int and first > 0, 'REGISTRY_START')
    return {'schema': 1, 'chain_id': 4663, 'market': MARKET, 'from_block': first,
            'through_block': first - 1, 'checkpoint': None, 'segments': [],
            'status': 'valid_prefix', 'historical_completeness': False}


def validate(state, policy):
    need(type(policy.get('max_registry_event_blocks')) is int and
         policy['max_event_blocks'] <= policy['max_registry_event_blocks'] <= 256, 'REGISTRY_CAPACITY_POLICY')
    need(state['schema'] == 1 and state['chain_id'] == 4663 and state['market'] == MARKET,
         'REGISTRY_IDENTITY')
    need(state['status'] in {'valid_prefix', 'invalidated'} and state['historical_completeness'] is False,
         'REGISTRY_STATUS')
    cursor, prior, events = state['from_block'], None, []
    need(type(cursor) is int and cursor > 0, 'REGISTRY_START')
    for segment in state['segments']:
        need(segment['first'] == cursor and cursor <= segment['end']['number'] < cursor + policy['shard_blocks'], 'REGISTRY_GAP')
        need(segment['previous_segment_sha256'] == (digest(prior) if prior else None), 'SEGMENT_CHAIN')
        need(segment['start']['number'] == cursor - 1, 'SEGMENT_START_HEADER')
        if prior: need(segment['start'] == prior['end'], 'SEGMENT_BOUNDARY_CHANGED')
        parsed = enrollment(segment['raw_logs'], cursor, segment['end'], policy)
        need(parsed['events'] == segment['events'], 'EVENTS_DIFFER_FROM_RAW_LOGS')
        headers = {b['number']: b for b in segment['event_headers']}
        need(len(headers) == len(segment['event_headers']) and set(headers) == {e['block'] for e in parsed['events']}, 'EVENT_HEADERS')
        need(all(headers[e['block']]['hash'] == e['block_hash'] for e in parsed['events']), 'EVENT_HEADER_HASH')
        events.extend(parsed['events'])
        cursor, prior = segment['end']['number'] + 1, segment
    need(state['through_block'] == cursor - 1 and state['checkpoint'] == (prior['end'] if prior else None), 'REGISTRY_CHECKPOINT')
    need(len(events) <= policy['max_logs'] and len({e['block'] for e in events}) <= policy['max_registry_event_blocks'] and
         len({e['borrower'] for e in events}) <= policy['max_borrowers'], 'REGISTRY_CAPACITY_NO_TRIMMING')
    identities = [(e['block_hash'], e['log_index']) for e in events]
    need(len(set(identities)) == len(identities), 'DUPLICATE_REGISTERED_LOG')
    return events


def append(state, first, start, end, logs, event_headers, policy):
    need(state['status'] == 'valid_prefix', 'INVALIDATED_REGISTRY')
    validate(state, policy)
    parsed = enrollment(logs, first, end, policy)
    segment = {'first': first, 'start': start, 'end': end, 'raw_logs': logs,
               'event_headers': event_headers, 'events': parsed['events'],
               'previous_segment_sha256': digest(state['segments'][-1]) if state['segments'] else None}
    result = copy.deepcopy(state)
    result['segments'].append(segment)
    result['through_block'], result['checkpoint'] = end['number'], end
    validate(result, policy)
    return result


def invalidate(state, observed):
    result = copy.deepcopy(state)
    result.update(status='invalidated', invalidation={'expected': state['checkpoint'], 'observed': observed})
    return result


def freeze(state, target, policy):
    events = validate(state, policy)
    need(state['status'] == 'valid_prefix' and state['through_block'] == target, 'INCOMPLETE_OR_INVALIDATED_REGISTRY')
    return {'addresses': sorted({e['borrower'] for e in events}), 'registry_sha256': digest(state),
            'from_block': state['from_block'], 'through_block': state['through_block'],
            'event_count': len(events), 'selection_uses_health_or_liquidation_outcome': False,
            'complete_historical_universe': False}


def save(path, state):
    path = Path(path)
    payload = {'state': state, 'sha256': digest(state)}
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(canonical(payload)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def load(path, policy):
    value = json.loads(Path(path).read_text())
    need(set(value) == {'state', 'sha256'} and digest(value['state']) == value['sha256'], 'REGISTRY_HASH')
    validate(value['state'], policy)
    return value['state']
