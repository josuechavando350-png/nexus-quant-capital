"""Closed synthetic authority model; abstract records, not real credentials.

No issuer authentication, signatures, services, targets, code loading or network.
Grant/revoke events are trusted local control-plane commands of this toy profile.
"""
from copy import deepcopy

PROFILE = 'owned-temporal-authority-v1'
PRINCIPALS, TENANTS, ACTIONS = ('alice', 'bob'), ('north', 'south'), ('read', 'write')
VARIANTS = ('correct', 'revoke_noop', 'stale_credential', 'subject_unbound',
            'scope_unbound', 'double_effect', 'false_deny')
MAX_EVENTS = 64
EFFECT_KEYS = tuple(t + '.' + a for t in TENANTS for a in ACTIONS)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def validate_events(events: list) -> None:
    need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, 'AUTHORITY_EVENT_BUDGET')
    for event in events:
        need(type(event) is dict and set(event) ==
             {'op', 'principal', 'tenant', 'action', 'credential'}, 'AUTHORITY_EVENT_SCHEMA')
        need(type(event['op']) is str and event['op'] in ('grant', 'revoke', 'use'),
             'AUTHORITY_OPERATION')
        for name, values in (('principal', PRINCIPALS), ('tenant', TENANTS), ('action', ACTIONS)):
            need(type(event[name]) is str and event[name] in values, 'AUTHORITY_FIXED_SCOPE')
        credential = event['credential']
        if event['op'] != 'use':
            need(credential is None, 'AUTHORITY_CONTROL_CREDENTIAL')
            continue
        need(type(credential) is dict and set(credential) ==
             {'principal', 'tenant', 'action', 'generation'}, 'AUTHORITY_CREDENTIAL_SCHEMA')
        for name, values in (('principal', PRINCIPALS), ('tenant', TENANTS), ('action', ACTIONS)):
            need(type(credential[name]) is str and credential[name] in values,
                 'AUTHORITY_FIXED_CREDENTIAL_SCOPE')
        need(type(credential['generation']) is int and
             0 <= credential['generation'] <= MAX_EVENTS, 'AUTHORITY_GENERATION')


def simulate(variant: str, events: list) -> dict:
    """Execute only one of seven own finite model implementations.

    The resulting trace deliberately omits variant, case ID and truth label.
    """
    need(type(variant) is str and variant in VARIANTS, 'AUTHORITY_OWN_VARIANT')
    validate_events(events)
    events = deepcopy(events)
    grants, rows = {}, []
    effects = {key: 0 for key in EFFECT_KEYS}
    for index, event in enumerate(events):
        key = (event['principal'], event['tenant'], event['action'])
        before = dict(effects)
        accepted = True
        if event['op'] in ('grant', 'revoke'):
            enabled, generation = grants.get(key, (False, 0))
            if event['op'] == 'grant':
                grants[key] = (True, generation + 1)
            elif variant != 'revoke_noop':
                grants[key] = (False, generation + 1)
        else:
            credential = event['credential']
            lookup = key
            if variant == 'subject_unbound':
                lookup = (credential['principal'], event['tenant'], event['action'])
            if variant == 'scope_unbound':
                lookup = (event['principal'], credential['tenant'], credential['action'])
            enabled, generation = grants.get(lookup, (False, 0))
            accepted = (enabled and
                (variant == 'subject_unbound' or credential['principal'] == event['principal']) and
                (variant == 'scope_unbound' or
                 (credential['tenant'], credential['action']) == (event['tenant'], event['action'])) and
                (variant == 'stale_credential' or credential['generation'] == generation))
            if variant == 'false_deny':
                accepted = False
            if accepted:
                effects[event['tenant'] + '.' + event['action']] += 2 if variant == 'double_effect' else 1
        rows.append({'index': index, 'accepted': accepted, 'effects_before': before,
                     'effects_after': dict(effects)})
    return {'schema_version': 1, 'profile': PROFILE, 'events': events, 'observations': rows}
