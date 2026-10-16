"""Pure fixture preparation and strict decoding. Not a bundler rule implementation."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'ci/nqc-census'))
from typed_observation_vectors import keccak256

EP = '0x0000000071727de22e5e9d8baf0edac6f37da032'
PM = '0xb7a5bd0345ef1cc5e66bf61bdec17d2461fbd968'
DEPOSIT = '0x'+keccak256(int(PM, 16).to_bytes(32, 'big')+bytes(32)).hex()
STAKE = '0x'+(int(DEPOSIT, 16)+1).to_bytes(32, 'big').hex()
SLOT1 = '0x'+(1).to_bytes(32, 'big').hex()
CASES = ('original_31s_unstaked', '31s_stake_fixture', '1s_stake_fixture',
         '31s_zero_deposit', '31s_zero_budget')


def word(n):
    return '0x'+n.to_bytes(32, 'big').hex()


def read(path):
    return json.loads(path.read_text())


def fixture(case):
    if case not in CASES:
        raise ValueError('unknown case')
    variant = 'local' if case == '1s_stake_fixture' else 'local-31'
    source = HERE.parent/'robinhood-sponsor-window-20261016/evidence'/variant/'simulation-input.json'
    data = read(source)
    original = read(HERE.parent/'robinhood-real-state-replay-20261016/evidence/nitro-phase5/02-nqc-plain-eoa-prestate.json')['result']
    overrides = {}
    for address, state in original.items():
        item = {k: state[k] for k in ('code', 'balance') if k in state}
        if 'nonce' in state:
            item['nonce'] = hex(state['nonce']) if isinstance(state['nonce'], int) else state['nonce']
        item['state'] = state.get('storage', {}).copy()
        overrides[address.lower()] = item
    for address, change in data['state_overrides'].items():
        item = overrides.setdefault(address, {'state': {}})
        for k in ('code', 'balance', 'nonce'):
            if k in change:
                item[k] = change[k]
        if 'state' in change:
            item['state'] = change['state'].copy()
        item['state'].update(change.get('stateDiff', {}))
    assert int(overrides[EP]['state'][DEPOSIT], 16) == 10**17
    # Explicit lab assumptions for additional stake fields; not live-chain funding.
    staked = case != 'original_31s_unstaked'
    stake = 10**18 if staked else 0
    delay = 86400 if staked else 0
    overrides[EP]['state'][STAKE] = word(int(staked) | (stake << 8) | (delay << 120))
    overrides[EP]['balance'] = hex(10**17 + stake)
    if case == '31s_zero_deposit':
        overrides[EP]['state'][DEPOSIT] = word(0)
    if case == '31s_zero_budget':
        overrides[PM]['state'][SLOT1] = word(0)
    artifact = read(HERE/'build/simulation-artifact.json')
    methods = artifact['evm']['methodIdentifiers']
    signature = 'simulateValidation((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes))'
    assert methods[signature] == keccak256(signature.encode())[:4].hex()
    overrides[EP]['code'] = '0x'+artifact['evm']['deployedBytecode']['object']
    raw = bytes.fromhex(data['transaction']['data'][2:])
    assert raw[:4].hex() == '765e827f'
    params = raw[4:]; start = int.from_bytes(params[:32], 'big')
    array = params[start:]; assert int.from_bytes(array[:32], 'big') == 1
    tup = array[32+int.from_bytes(array[32:64], 'big'):]
    calldata = '0x'+methods[signature]+(32).to_bytes(32, 'big').hex()+tup.hex()
    return {'case': case, 'transaction': {'from': '0x'+'00'*20, 'to': EP, 'data': calldata, 'gas': hex(580000)},
            'stateOverrides': overrides, 'window': data['window_fixture'],
            'stake_fixture_wei': stake, 'unstake_delay_fixture_seconds': delay,
            'source': str(source.relative_to(ROOT))}


def decode_result(raw):
    data = bytes.fromhex(raw.removeprefix('0x'))
    def at(offset):
        if offset < 0 or offset+32 > len(data) or offset % 32:
            raise ValueError('invalid ABI word offset')
        return int.from_bytes(data[offset:offset+32], 'big')
    if at(0) != 32:
        raise ValueError('unexpected tuple offset')
    root = 32
    if at(root) != 320:
        raise ValueError('unexpected ReturnInfo offset')
    info = root+at(root)
    if at(info+128) != 160:
        raise ValueError('unexpected context offset')
    size = at(info+160)
    if size != 0 or len(data) != info+192:
        raise ValueError('expected exact empty paymaster context')
    packed = at(info+96)
    return {'preop_gas': at(info), 'prefund_wei': at(info+32),
            'account_validation_data': at(info+64), 'paymaster_validation_data': packed,
            'paymaster_aggregator': '0x'+(packed & (2**160-1)).to_bytes(20, 'big').hex(),
            'valid_after': packed >> 208, 'valid_until': (packed >> 160) & (2**48-1),
            'paymaster_context_bytes': size, 'sender_stake_wei': at(root+32),
            'sender_unstake_delay': at(root+64), 'paymaster_stake_wei': at(root+160),
            'paymaster_unstake_delay': at(root+192), 'aggregator': at(root+224)}


def summarize(case, trace):
    if not isinstance(trace, dict) or not trace.get('calls'):
        raise ValueError('tracer output missing')
    terminal = trace['calls'][-1]
    result = {'case': case['case'], 'terminal_type': terminal['type'],
              'full_bundler_admission_proven': False, 'funding_available_proven': False}
    data = terminal['data']
    if case['case'] in ('31s_zero_deposit', '31s_zero_budget'):
        reason = b'AA31' if case['case'] == '31s_zero_deposit' else b'BUDGET_POLICY'
        if terminal['type'] != 'REVERT' or reason not in bytes.fromhex(data[2:]):
            raise ValueError('expected negative validation control missing')
        result['expected_revert_marker'] = reason.decode()
        return result
    if terminal['type'] != 'RETURN':
        raise ValueError('unexpected EVM validation revert')
    decoded = decode_result(data)
    assert decoded['account_validation_data'] == 0 and decoded['aggregator'] == 0
    assert int(decoded['paymaster_aggregator'], 16) == 0
    assert decoded['prefund_wei'] == case['window']['budget_wei']
    assert decoded['valid_after'] == case['window']['valid_after'] and decoded['valid_until'] == case['window']['valid_until']
    assert decoded['paymaster_stake_wei'] == case['stake_fixture_wei']
    assert decoded['paymaster_unstake_delay'] == case['unstake_delay_fixture_seconds']
    levels = [x for x in trace['callsFromEntryPoint'] if x['topLevelTargetAddress'].lower() == PM]
    assert len(levels) == 1
    access = levels[0]['access'][PM]
    slot = SLOT1
    assert slot in access['reads'] and slot in access['writes']
    result.update(decoded=decoded, paymaster_storage=access, paymaster_opcodes=levels[0]['opcodes'])
    return result
