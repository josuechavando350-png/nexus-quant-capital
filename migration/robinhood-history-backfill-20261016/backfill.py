"""Prepend authenticated history, preserving the earlier registry as a source."""
import copy
from support import need, registry


def merge(older, existing, policy):
    registry.validate(older, policy); registry.validate(existing, policy)
    need(older['status'] == existing['status'] == 'valid_prefix', 'INVALID_REGISTRY_STATUS')
    need(older['through_block'] + 1 == existing['from_block'], 'BACKFILL_GAP_OR_OVERLAP')
    need(existing['segments'] and older['checkpoint'] == existing['segments'][0]['start'], 'BACKFILL_BOUNDARY_HASH')
    # Rebuild linkage only in a fresh value. Raw logs, headers and events remain identical.
    result = copy.deepcopy(older)
    for segment in existing['segments']:
        result = registry.append(result, segment['first'], segment['start'], segment['end'],
                                 segment['raw_logs'], segment['event_headers'], policy)
    registry.validate(result, policy)
    return result
