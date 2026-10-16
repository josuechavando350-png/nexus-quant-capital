"""PR24 fixture integration preserving native precompiles and original signatures."""
import copy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = HERE.parent/'robinhood-bundler-validation-20261016T1608'
sys.path.insert(0, str(PREVIOUS))
import validation as prior
from prepare_next import preserve_native_precompiles
from run_local import genesis as original_genesis
from audit_stopped import failed_op

read = prior.read
PM = prior.PM
NATIVE = '0x'+'0'*39+'1'
CASES = ('original_31s_unstaked', 'invalid_signature', '31s_stake_fixture',
         '1s_stake_fixture', '31s_zero_deposit', '31s_zero_budget')


def zero_signature(calldata):
    """Only destroy the existing 65-byte signature; never create a signature."""
    raw = bytearray.fromhex(calldata.removeprefix('0x'))
    assert raw[:4].hex() == 'c3bce009'
    root = 4 + int.from_bytes(raw[4:36], 'big')
    signature = root + int.from_bytes(raw[root+8*32:root+9*32], 'big')
    size = int.from_bytes(raw[signature:signature+32], 'big')
    assert size == 65 and signature+32+96 == len(raw)
    start = signature+32
    raw[start:start+65] = bytes(65)
    return '0x'+raw.hex(), {'byte_start':start, 'byte_end_exclusive':start+65}


def fixture(name):
    if name not in CASES:
        raise ValueError('unknown registered control')
    source_name = prior.CASES[0] if name == 'invalid_signature' else name
    case, initial, moved = preserve_native_precompiles(prior.fixture(source_name), original_genesis())
    case['case'] = name
    case['native_precompile_state_moved_to_genesis'] = moved
    if name == 'invalid_signature':
        case['transaction']['data'], case['signature_negative_control'] = zero_signature(case['transaction']['data'])
    if any(1 <= int(a,16) <= 9 for a in case['stateOverrides']):
        raise ValueError('native precompile remains overridden')
    return case, initial


def cases_and_genesis():
    cases = []
    initial = None
    for name in CASES:
        case, candidate = fixture(name)
        if initial is not None and candidate != initial:
            raise ValueError('controls require different genesis')
        initial = candidate
        cases.append(case)
    return cases, initial


def native_return(trace):
    positions = [i for i,c in enumerate(trace['calls']) if c.get('to') == NATIVE]
    assert len(positions) == 1, 'expected one native ecrecover call'
    call = trace['calls'][positions[0]]
    result = trace['calls'][positions[0]+1]
    assert call['type'] == 'STATICCALL' and result['type'] == 'RETURN'
    assert result['gasUsed'] == 3000, 'native ecrecover gas differs'
    return result


def summarize(case, trace):
    if case['case'] == 'invalid_signature':
        assert trace['calls'][-1]['type'] == 'REVERT'
        decoded = failed_op(trace['calls'][-1]['data'])
        assert decoded == {'op_index':0, 'reason':'AA23 reverted',
                           'inner':'0x'+prior.keccak256(b'ECDSAInvalidSignature()')[:4].hex()}
        native = native_return(trace)
        assert native['data'] == '0x'
        assert not any(x['topLevelTargetAddress'].lower() == PM for x in trace['callsFromEntryPoint'])
        return {'case':case['case'], 'terminal_type':'REVERT', 'expected_invalid_signature':decoded,
                'native_ecrecover':native, 'paymaster_reached':False,
                'full_bundler_admission_proven':False, 'funding_available_proven':False}
    result = prior.summarize(case,trace)
    if case['case'] in prior.CASES[:3]:
        native = native_return(trace)
        assert len(bytes.fromhex(native['data'][2:])) == 32 and int(native['data'],16) != 0
        result['native_ecrecover'] = native
        result['paymaster_reached'] = True
    return result
