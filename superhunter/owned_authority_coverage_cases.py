"""Versioned input-only OWNED conditions and explicit counter-controls.

This is a separate corpus, not an extension of the historical detection cases.
Expected event indices are authored constants, never derived by the analyzer.
"""
from copy import deepcopy

from .owned_authority_cases import event

PROFILE = 'owned-temporal-input-counter-controls-v1'
CORPUS_VERSION = 1


def cases() -> list[dict]:
    grant, revoke = event('grant'), event('revoke')
    use = event('use', generation=1)
    pairs = (
        ('use_without_control',
         [use], {'use_without_control': [0]},
         [grant, use], {'current_grant_use': [1]}),
        ('current_grant_use',
         [grant, use], {'current_grant_use': [1]},
         [grant, event('use', generation=2)], {}),
        ('revoked_grant_use',
         [grant, revoke, use], {'revoked_grant_use': [2]},
         [grant, revoke, event('use', generation=2)], {}),
        ('stale_grant_after_regrant_use',
         [grant, revoke, grant, use], {'stale_grant_after_regrant_use': [3]},
         [grant, revoke, grant, event('use', generation=3)],
         {'current_grant_use': [3], 'current_grant_after_revocation_use': [3]}),
        ('principal_mismatch_use',
         [grant, event('use', principal='bob', credential=use['credential'])],
         {'principal_mismatch_use': [1]},
         [grant, use], {'current_grant_use': [1]}),
        ('scope_mismatch_use',
         [grant, event('use', tenant='south', action='write', credential=use['credential'])],
         {'scope_mismatch_use': [1]},
         [grant, use], {'current_grant_use': [1]}),
        ('repeated_current_grant_use',
         [grant, use, use], {'current_grant_use': [1, 2], 'repeated_current_grant_use': [2]},
         [grant, use, grant, event('use', generation=2)], {'current_grant_use': [1, 3]}),
        ('current_grant_after_revocation_use',
         [revoke, grant, event('use', generation=2)],
         {'current_grant_use': [2], 'current_grant_after_revocation_use': [2]},
         [grant, grant, event('use', generation=2)], {'current_grant_use': [2]}),
    )
    conditions = tuple(pair[0] for pair in pairs)
    rows = []
    for condition, present, present_hits, absent, absent_hits in pairs:
        for role, events, expected in (
                ('present', present, present_hits), ('absent', absent, absent_hits)):
            rows.append({'case_id': condition + '--' + role, 'condition': condition,
                         'role': role, 'events': [deepcopy(record) for record in events],
                         'expected_witness_indices': {
                             name: list(expected.get(name, [])) for name in conditions}})
    return rows
