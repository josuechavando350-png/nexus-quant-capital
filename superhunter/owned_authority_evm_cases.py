"""Fixed own abstract authority machines; no external contract/source inputs.

Principals are bits in a toy command, not authenticated callers. Control-plane
commands are trusted by the local scenario. No credentials, signatures or RPC.
"""
from __future__ import annotations

import re

from . import native_compile as compiler, evm_execution as evm
from . import owned_authority_model as model, owned_authority_cases as corpus
from .safe_io import canonical, strict_json

need, sha = model.need, compiler.sha
SOURCE_FILE, CONTRACT = 'OwnedAuthority.sol', 'OwnedAuthority'
CODEGEN = ('legacy', 'ir_optimized')
PROFILE = 'owned-temporal-authority-two-evm-cancun-v1'
STORAGE = [('phase', '0', 0, 'uint8'), ('accepted', '0', 1, 'uint8'),
           ('enabled', '0', 2, 'uint8'), ('generations', '0', 3, 'uint64'),
           ('effects', '0', 11, 'uint32')]
INITIAL = {'phase': 0, 'accepted': 0, 'enabled': 0,
           'generations': [0] * 8, 'effects': [0] * 4}


def encode(event: dict) -> int:
    model.validate_events([event])
    word = ('grant', 'revoke', 'use').index(event['op'])
    word |= model.PRINCIPALS.index(event['principal']) << 2
    word |= model.TENANTS.index(event['tenant']) << 3
    word |= model.ACTIONS.index(event['action']) << 4
    if event['op'] == 'use':
        credential = event['credential']
        word |= model.PRINCIPALS.index(credential['principal']) << 5
        word |= model.TENANTS.index(credential['tenant']) << 6
        word |= model.ACTIONS.index(credential['action']) << 7
        word |= credential['generation'] << 8
    return word


def schedule(events: list) -> list[dict]:
    """One fixed one-gas probe before the first use, then the unchanged sequence."""
    model.validate_events(events)
    rows, probed = [], False
    for index, event in enumerate(events):
        if event['op'] == 'use' and not probed:
            rows.append({'event_index': index, 'probe': True, 'gas': 1, 'word': encode(event)})
            probed = True
        rows.append({'event_index': index, 'probe': False, 'gas': evm.GAS, 'word': encode(event)})
    need(probed, 'AUTHORITY_EVM_FIXED_PROBE_REQUIRED')
    return rows


def owned_source(variant: str) -> str:
    need(type(variant) is str and variant in model.VARIANTS, 'AUTHORITY_EVM_FIXED_VARIANT')
    revoke = '' if variant == 'revoke_noop' else 'enabled &= ~uint8(1 << key); _advance(key);'
    lookup = ('(credentialKey & 4) | (key & 3)' if variant == 'subject_unbound' else
              '(key & 4) | (credentialKey & 3)' if variant == 'scope_unbound' else 'key')
    bound = ('(credentialKey & 3) == (key & 3)' if variant == 'subject_unbound' else
             '(credentialKey & 4) == (key & 4)' if variant == 'scope_unbound' else
             'credentialKey == key')
    age = 'true' if variant == 'stale_credential' else 'uint8(word >> 8) == uint8(generations >> (lookupKey * 8))'
    decision = 'false' if variant == 'false_deny' else f'(enabled & uint8(1 << lookupKey)) != 0 && ({bound}) && ({age})'
    increment = 2 if variant == 'double_effect' else 1
    return f'''// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
// OWNED abstract finite model. Principals are untrusted bits, not msg.sender.
// Only the closed local test harness supplies trusted control commands.
contract OwnedAuthority {{
    uint8 public phase;
    uint8 public accepted;
    uint8 public enabled;
    uint64 public generations;
    uint32 public effects;
    function _advance(uint8 key) private {{
        uint8 next = uint8(generations >> (key * 8)) + 1;
        generations = (generations & ~(uint64(255) << (key * 8))) | (uint64(next) << (key * 8));
    }}
    function _allows(uint256 word, uint8 key) private view returns (bool) {{
        uint8 credentialKey = uint8(((word >> 5) & 1) * 4 + ((word >> 6) & 1) * 2 + ((word >> 7) & 1));
        uint8 lookupKey = {lookup};
        return {decision};
    }}
    function step(uint256 word) external returns (bool) {{
        require(word < 65536 && phase < 64);
        uint8 op = uint8(word & 3);
        require(op <= 2);
        uint8 key = uint8(((word >> 2) & 1) * 4 + ((word >> 3) & 1) * 2 + ((word >> 4) & 1));
        accepted = 1;
        if (op == 0) {{
            require(word >> 5 == 0);
            enabled |= uint8(1 << key); _advance(key);
        }} else if (op == 1) {{
            require(word >> 5 == 0);
            {revoke}
        }} else {{
            require(word >> 8 <= 64);
            accepted = _allows(word, key) ? 1 : 0;
            if (accepted == 1) {{
                uint8 shift = (key & 3) * 8;
                uint8 next = uint8(effects >> shift) + {increment};
                effects = (effects & ~(uint32(255) << shift)) | (uint32(next) << shift);
            }}
        }}
        phase += 1;
        return accepted == 1;
    }}
}}
'''


def compile_input(variant: str, codegen: str) -> dict:
    need(type(codegen) is str and codegen in CODEGEN, 'AUTHORITY_EVM_CODEGEN')
    settings = {'optimizer': {'enabled': codegen != 'legacy', 'runs': 200},
                'evmVersion': 'cancun', 'modelChecker': {'engine': 'none'},
                'outputSelection': {'*': {'': ['ast'], '*': ['abi', 'storageLayout',
                    'evm.bytecode', 'evm.deployedBytecode', 'evm.methodIdentifiers']}}}
    if codegen == 'ir_optimized':
        settings['viaIR'] = True
    return {'language': 'Solidity', 'sources': {SOURCE_FILE: {'content': owned_source(variant)}},
            'settings': settings}


def compile_owned(image: bytes, variant: str, codegen: str) -> dict:
    inp = compile_input(variant, codegen)
    output, stderr = compiler._execute(image, 'compile', canonical(inp))
    need(not stderr and compiler.classify_output(inp, output)['status'] ==
         'SOLC_COMPILATION_COMPLETED', 'AUTHORITY_EVM_COMPILATION')
    obj = strict_json(output)
    need(set(obj['contracts']) == {SOURCE_FILE} and
         set(obj['contracts'][SOURCE_FILE]) == {CONTRACT}, 'AUTHORITY_EVM_CONTRACT')
    contract = obj['contracts'][SOURCE_FILE][CONTRACT]
    layout = contract['storageLayout']
    need([(r['label'], r['slot'], r['offset'], layout['types'][r['type']]['label'])
          for r in layout['storage']] == STORAGE, 'AUTHORITY_EVM_LAYOUT')
    methods = contract['evm']['methodIdentifiers']
    need(set(methods) == {'phase()', 'accepted()', 'enabled()', 'generations()', 'effects()', 'step(uint256)'}
         and all(type(v) is str and re.fullmatch('[0-9a-f]{8}', v) for v in methods.values()),
         'AUTHORITY_EVM_SELECTORS')
    birth, runtime = contract['evm']['bytecode'], contract['evm']['deployedBytecode']
    for item in (birth, runtime):
        need(type(item['object']) is str and len(item['object']) % 2 == 0 and
             re.fullmatch('[0-9a-f]+', item['object']) and not item['linkReferences'],
             'AUTHORITY_EVM_BYTECODE')
    need(not runtime['immutableReferences'], 'AUTHORITY_EVM_IMMUTABLES')
    return {'contract': contract, 'record': {'variant': variant, 'codegen': codegen,
        'source_sha256': sha(owned_source(variant).encode()), 'input_sha256': sha(canonical(inp)),
        'output_sha256': sha(output), 'creation_sha256': sha(bytes.fromhex(birth['object'])),
        'runtime_sha256': sha(bytes.fromhex(runtime['object']))}}


def validate_state(state: dict) -> None:
    need(type(state) is dict and set(state) == set(INITIAL), 'AUTHORITY_EVM_STATE_SCHEMA')
    for name, maximum in (('phase', 64), ('accepted', 1), ('enabled', 255)):
        need(type(state[name]) is int and 0 <= state[name] <= maximum, 'AUTHORITY_EVM_STATE_BOUNDS')
    for name, count, maximum in (('generations', 8, 64), ('effects', 4, 128)):
        values = state[name]
        need(type(values) is list and len(values) == count and
             all(type(v) is int and 0 <= v <= maximum for v in values), 'AUTHORITY_EVM_STATE_BOUNDS')


def decode_word(word: int) -> dict:
    need(type(word) is int and 0 <= word < 2**120, 'AUTHORITY_EVM_STORAGE_WORD')
    state = {'phase': word & 255, 'accepted': (word >> 8) & 255, 'enabled': (word >> 16) & 255,
             'generations': [(word >> (24 + 8 * i)) & 255 for i in range(8)],
             'effects': [(word >> (88 + 8 * i)) & 255 for i in range(4)]}
    validate_state(state)
    return state


def decode(alloc: dict, contract: dict) -> dict:
    need(type(alloc) is dict and evm.RECEIVER in alloc, 'AUTHORITY_EVM_ACCOUNT')
    account = alloc[evm.RECEIVER]
    need(account['code'] == '0x' + contract['evm']['deployedBytecode']['object'], 'AUTHORITY_EVM_RUNTIME')
    storage = account['storage']
    need(type(storage) is dict and set(storage) <= {evm.SLOT}, 'AUTHORITY_EVM_STORAGE_KEYS')
    return decode_word(int(storage.get(evm.SLOT, '0x0'), 16))


def inventory() -> list[tuple[dict, str]]:
    return [(case, codegen) for case in corpus.cases() for codegen in CODEGEN]
