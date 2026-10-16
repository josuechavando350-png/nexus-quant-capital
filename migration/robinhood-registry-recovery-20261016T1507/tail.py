"""PR12 updater copied verbatim; only registry binding uses the new capacity. No history scan."""
import json
import capacity_registry as registry
from collect import get_header, canonical_check
from common import need, header, MORPHO, BORROW, MARKET

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
