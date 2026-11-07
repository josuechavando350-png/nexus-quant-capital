"""Eleven known OWNED model/sequence cases; labels never enter the detector."""
from copy import deepcopy


def event(op, principal='alice', tenant='north', action='read', generation=None, credential=None):
    if op == 'use' and credential is None:
        credential = {'principal': principal, 'tenant': tenant, 'action': action,
                      'generation': generation}
    return {'op': op, 'principal': principal, 'tenant': tenant, 'action': action,
            'credential': deepcopy(credential)}


def cases() -> list[dict]:
    grant, revoke, use = event('grant'), event('revoke'), event('use', generation=1)
    repeat = [grant, use, use, use]
    rotation = [grant, use, revoke, use, grant, use, event('use', generation=3)]
    bob = event('use', principal='bob', generation=1, credential=use['credential'])
    scope = event('use', tenant='south', action='write', generation=1, credential=use['credential'])
    other_grant = event('grant', principal='bob', tenant='south', action='write')
    other_use = event('use', principal='bob', tenant='south', action='write', generation=1)
    other_revoke = event('revoke', principal='bob', tenant='south', action='write')
    rows = [
        ('clean_rotation', 'correct', rotation, 'negative', False),
        ('clean_scope', 'correct', [grant, bob, scope, other_grant, other_use, use], 'negative', False),
        ('clean_repeat', 'correct', repeat, 'negative', False),
        ('clean_revoked', 'correct', [other_grant, other_use, other_revoke, other_use, other_use], 'negative', False),
        ('ignored_revocation', 'revoke_noop', [grant, use, revoke, use], 'positive', True),
        ('stale_after_regrant', 'stale_credential', [grant, revoke, grant, use], 'positive', True),
        ('subject_binding', 'subject_unbound', [grant, bob], 'positive', True),
        ('scope_binding', 'scope_unbound', [grant, scope], 'positive', True),
        ('double_effect', 'double_effect', [grant, use], 'positive', True),
        ('valid_denied', 'false_deny', [grant, use], 'positive', True),
        # Same observations as clean_repeat: the seeded revocation defect is
        # present in the model but this sequence never exercises revocation.
        ('latent_revocation', 'revoke_noop', repeat, 'positive', False),
    ]
    return deepcopy([{'case_id': name, 'variant': variant, 'events': sequence,
                      'truth': truth, 'seeded_defect_exercised': exercised}
                     for name, variant, sequence, truth, exercised in rows])
