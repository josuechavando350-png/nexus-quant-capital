"""Closed correct-source-only native profile for the fixed counter-controls.

Shares the existing OWNED correct Solidity source and encoding. The historical
native corpus, injected variants and detection metrics are not extended here.
"""
from copy import deepcopy

from . import owned_authority_evm_cases as base
from . import owned_authority_coverage_cases as inputs
from . import owned_authority_coverage_suite as suite
from .safe_io import canonical

need, sha, model, compiler, evm = base.need, base.sha, base.model, base.compiler, base.evm
CODEGEN, INITIAL = base.CODEGEN, base.INITIAL
PROFILE = 'owned-correct-counter-controls-two-evm-cancun-v1'
VARIANTS = ('correct',)
encode, schedule, decode, decode_word, validate_state = (
    base.encode, base.schedule, base.decode, base.decode_word, base.validate_state)


def fixed_cases() -> list[dict]:
    rows = inputs.cases()
    need(sha(canonical(rows)) == suite.CORPUS_SHA256, 'CORRECT_EVM_CORPUS_IDENTITY')
    return [{'case_id': row['case_id'], 'variant': 'correct', 'events': deepcopy(row['events'])}
            for row in rows]


def inventory() -> list[tuple[dict, str]]:
    return [(case, codegen) for case in fixed_cases() for codegen in CODEGEN]


def owned_source(variant: str) -> str:
    need(type(variant) is str and variant == 'correct', 'CORRECT_EVM_ONLY_CORRECT_SOURCE')
    return base.owned_source('correct')


def compile_input(variant: str, codegen: str) -> dict:
    owned_source(variant)
    return base.compile_input('correct', codegen)


def compile_owned(image: bytes, variant: str, codegen: str) -> dict:
    owned_source(variant)
    return base.compile_owned(image, 'correct', codegen)


def expected_states(case: dict) -> list[dict]:
    """History-based full storage expectations; no native execution/decoding."""
    from . import owned_authority_behavior as behavior
    expected = behavior.expected_trace(case)
    events = case['events']
    states = []
    keys = [(p, t, a) for p in model.PRINCIPALS for t in model.TENANTS for a in model.ACTIONS]
    for index, observation in enumerate(expected['observations']):
        histories = [[event for event in events[:index + 1]
                      if event['op'] in ('grant', 'revoke') and
                      (event['principal'], event['tenant'], event['action']) == key] for key in keys]
        states.append({'phase': index + 1, 'accepted': int(observation['accepted']),
            'enabled': sum((1 << i) for i, history in enumerate(histories)
                           if history and history[-1]['op'] == 'grant'),
            'generations': [len(history) for history in histories],
            'effects': [observation['effects_after'][key] for key in model.EFFECT_KEYS]})
    return states
