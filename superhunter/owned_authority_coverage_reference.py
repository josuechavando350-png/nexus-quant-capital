"""History-query coverage reference for fixed, synthetic authority records.

No simulation, observations, detector decisions, variant or truth labels enter
this calculation. It shares the input specification, not incremental state.
"""
from .owned_authority_model import validate_events


def coverage(events: list) -> dict[str, list[int]]:
    validate_events(events)
    hits = {name: [] for name in (
        'use_without_control', 'current_grant_use', 'revoked_grant_use',
        'stale_grant_after_regrant_use', 'principal_mismatch_use',
        'scope_mismatch_use', 'repeated_current_grant_use',
        'current_grant_after_revocation_use')}
    fields = ('principal', 'tenant', 'action')
    for index, event in enumerate(events):
        if event['op'] != 'use':
            continue
        credential = event['credential']
        principal = credential['principal'] == event['principal']
        scope = all(credential[f] == event[f] for f in ('tenant', 'action'))
        if not principal:
            hits['principal_mismatch_use'].append(index)
        if not scope:
            hits['scope_mismatch_use'].append(index)
        if not (principal and scope):
            continue
        history = [p for p in events[:index] if p['op'] != 'use' and
                   all(p[f] == event[f] for f in fields)]
        generation = credential['generation']
        if not history:
            hits['use_without_control'].append(index)
            continue
        was_revoked = (0 < generation <= len(history) and
                       history[generation - 1]['op'] == 'grant' and
                       any(p['op'] == 'revoke' for p in history[generation:]))
        if was_revoked:
            name = ('revoked_grant_use' if history[-1]['op'] == 'revoke'
                    else 'stale_grant_after_regrant_use')
            hits[name].append(index)
        if history[-1]['op'] != 'grant' or generation != len(history):
            continue
        hits['current_grant_use'].append(index)
        if any(p['op'] == 'revoke' for p in history):
            hits['current_grant_after_revocation_use'].append(index)
        for previous_index, previous in enumerate(events[:index]):
            if previous['op'] != 'use' or not all(previous[f] == event[f] for f in fields):
                continue
            token = previous['credential']
            if token['generation'] != generation or not all(token[f] == event[f] for f in fields):
                continue
            controls = [p for p in events[:previous_index] if p['op'] != 'use' and
                        all(p[f] == event[f] for f in fields)]
            if len(controls) == generation and controls[-1]['op'] == 'grant':
                hits['repeated_current_grant_use'].append(index)
                break
    return hits
