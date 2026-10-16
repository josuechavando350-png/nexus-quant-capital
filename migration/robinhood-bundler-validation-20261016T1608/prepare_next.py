"""Offline proposal only; not used by the registered runner or captured pilot.

Keep native Shanghai precompiles active by moving their passive account state
into genesis. Never replace signature validation or change a signed operation.
A future runner/protocol must register and test this integration before capture.
"""
import copy
from validation import fixture, CASES
from run_local import genesis


def preserve_native_precompiles(case, initial_genesis):
    case, initial_genesis = copy.deepcopy(case), copy.deepcopy(initial_genesis)
    moved = []
    for address in list(case['stateOverrides']):
        if not 1 <= int(address, 16) <= 9:
            continue
        state = case['stateOverrides'][address]
        if set(state) - {'balance', 'nonce', 'state'} or state.get('state', {}):
            raise ValueError('non-passive native-precompile override requires review')
        key = address.removeprefix('0x')
        if key in initial_genesis['alloc'] or address in initial_genesis['alloc']:
            raise ValueError('genesis allocation collision')
        allocation = {k: state[k] for k in ('balance', 'nonce') if k in state}
        if 'balance' not in allocation:
            allocation['balance'] = '0x0'
        initial_genesis['alloc'][key] = allocation
        del case['stateOverrides'][address]
        moved.append({'address': address, 'genesis_allocation': allocation})
    return case, initial_genesis, moved


if __name__ == '__main__':
    import json
    proposals = {}
    for name in CASES:
        case, initial, moved = preserve_native_precompiles(fixture(name), genesis())
        proposals[name] = {'genesis': initial, 'moved': moved,
                           'native_precompile_overrides_remaining': [a for a in case['stateOverrides'] if 1 <= int(a, 16) <= 9],
                           'executed': False}
    print(json.dumps(proposals, indent=2))
