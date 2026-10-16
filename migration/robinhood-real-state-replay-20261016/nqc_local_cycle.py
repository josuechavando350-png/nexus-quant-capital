#!/usr/bin/env python3
"""Local NQC handleOps integration on captured protocol state; no remote writes.

New NQC address storage not touched by the original tx is initially unknown/zero.
Remote read-only Nitro simulation is required to validate that counterfactual.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from local_replay import HERE, Local, load_capture, restore

EP = '0x0000000071727de22e5e9d8baf0edac6f37da032'
USDG = '0x5fc5360d0400a0fd4f2af552add042d716f1d168'
ARBSYS = '0x0000000000000000000000000000000000000064'
BUNDLER = '0x000000000000000000000000000000000000beef'
KEY = '0x' + '1234'.rjust(64, '0')  # PUBLIC TEST KEY; local fixture signatures only.
OPTYPE = '(address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes)'


def decode_op(raw):
    value = bytes.fromhex(raw[2:])
    value = value[int.from_bytes(value[:32], 'big'):]
    fields = []
    for i in range(9):
        word = value[i * 32:(i + 1) * 32]
        if i in (2, 3, 7, 8):
            offset = int.from_bytes(word, 'big')
            size = int.from_bytes(value[offset:offset + 32], 'big')
            fields.append('0x' + value[offset + 32:offset + 32 + size].hex())
        elif i == 0:
            fields.append('0x' + word[-20:].hex())
        elif i in (1, 5):
            fields.append(str(int.from_bytes(word, 'big')))
        else:
            fields.append('0x' + word.hex())
    return fields


def run(local, args, block, prestate):
    def cast(*items):
        return subprocess.check_output([str(args.foundry_bin / 'cast'), *map(str, items)], text=True).strip()
    def calldata(signature, *items):
        return cast('calldata', signature, *items)
    def call(address, data):
        return local.rpc('eth_call', [{'to': address, 'data': data}, 'latest'])
    def addresscall(address, signature):
        return '0x' + call(address, calldata(signature))[-40:]
    def uintcall(address, signature, *items):
        return int(call(address, calldata(signature, *items)), 16)
    def send(request, timestamp):
        local.rpc('anvil_setNextBlockBaseFeePerGas', [block['baseFeePerGas']])
        local.rpc('evm_setNextBlockTimestamp', [timestamp])
        identity = local.rpc('eth_sendTransaction', [request])
        for _ in range(100):
            receipt = local.rpc('eth_getTransactionReceipt', [identity])
            if receipt is not None:
                return identity, receipt
            time.sleep(0.05)
        raise RuntimeError('local receipt timeout')
    restore(local, prestate)
    sender = local.rpc('eth_accounts', [])[0]
    runtime = json.loads((HERE.parent / 'robinhood-aa-20261016/evidence/runtime.json').read_text())['runtime']
    assert hashlib.sha256(bytes.fromhex(runtime[2:])).hexdigest() == '674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5'
    local.rpc('anvil_setCode', [EP, runtime])
    local.rpc('anvil_setStorageAt', [EP, '0x' + '0' * 63 + '2', '0x' + '0' * 63 + '1'])
    height = int(block['number'], 16)
    local.rpc('anvil_setCode', [ARBSYS, '0x63' + height.to_bytes(4, 'big').hex() + '60005260206000f3'])
    artifact = json.loads((args.build / 'robinhood/out/NqcHistoricalScenario.sol/NqcHistoricalScenario.json').read_text())
    owner = cast('wallet', 'address', '--private-key', KEY)
    init = artifact['bytecode']['object'] + cast('abi-encode', 'f(address,address)', EP, owner)[2:]
    _, deployed = send({'from': sender, 'data': init, 'value': hex(10**17),
                        'gas': hex(16000000), 'gasPrice': block['baseFeePerGas']}, int(block['timestamp'], 16) - 1)
    assert int(deployed['status'], 16) == 1, 'local fixture deployment failed'
    scene = deployed['contractAddress']
    addresses = {name: addresscall(scene, name + '()') for name in ['account', 'paymaster', 'router', 'executor']}
    morpho = '0x9d53d5e3bd5e8d4cbfa6db1ca238aea02e651010'
    pool = '0x59f95461e68e0c77605299791e1449f175165b54'
    wsnet = '0x63c12667638f2ae6fc6ae09b43d98ec84a8586ea'
    snet = '0xb773ec2c326b7f98a5a83fc098825492f020a4c7'
    net = '0xca9c78dd337a67f6e0077f65f5e9218719d30edf'
    staking = '0xb078cc304a0b264c5f3680dc0488954accd02e87'
    position_data = calldata('position(bytes32,address)',
        '0xaa586d26a6fe62d9c0f0948fede6e2130500ac7a655587447e2d4a37e6330589',
        '0x689afbae02a62d10e9a20a6f76b08d94eb7361f0')
    before_position = call(morpho, position_data)
    before_reserves = call(pool, calldata('getReserves()'))
    snapshot = local.rpc('evm_snapshot', [])
    topic = cast('keccak', 'UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)')
    records = []
    for label, profit, minimum, expect in [
        ('success', 32000000, 226094796, True),
        ('minimum_profit_reject', 40000000, 226094796, False),
        ('tax_omission_quote_reject', 32000000, 237986092, False),
    ]:
        assert local.rpc('evm_revert', [snapshot])
        snapshot = local.rpc('evm_snapshot', [])
        fields = decode_op(call(scene, calldata('unsignedOp(uint256,uint256,uint256,uint256)', height, profit, minimum, 1500000)))
        unsigned = '(' + ','.join(fields) + ')'
        op_hash = call(EP, calldata('getUserOpHash(' + OPTYPE + ')', unsigned))
        fields[8] = cast('wallet', 'sign', '--private-key', KEY, op_hash)
        data = calldata('handleOps(' + OPTYPE + '[],address)', '[(' + ','.join(fields) + ')]', BUNDLER)
        before = uintcall(EP, 'balanceOf(address)', addresses['paymaster'])
        request = {'from': sender, 'to': EP, 'data': data, 'value': '0x0', 'gas': hex(4000000),
                   'gasPrice': hex(int(block['baseFeePerGas'], 16) + 1000000)}
        identity, receipt = send(request, int(block['timestamp'], 16))
        trace = local.rpc('debug_traceTransaction', [identity, {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}}])
        touched = local.rpc('debug_traceTransaction', [identity, {'tracer': 'prestateTracer'}])
        event = next((x for x in receipt['logs'] if x['address'].lower() == EP and x['topics'][0] == topic), None)
        (args.out / (label + '-receipt.json')).write_text(json.dumps(receipt, indent=2) + '\n')
        (args.out / (label + '-trace.json')).write_text(json.dumps(trace, indent=2) + '\n')
        assert event is not None and int(receipt['status'], 16) == 1, 'bundle validation failed'
        words = [int(event['data'][2 + i * 64:2 + (i + 1) * 64], 16) for i in range(4)]
        debit = before - uintcall(EP, 'balanceOf(address)', addresses['paymaster'])
        surplus = uintcall(USDG, 'balanceOf(address)', addresses['account'])
        record = {'case': label, 'success': bool(words[1]), 'gas_used': int(receipt['gasUsed'], 16),
                  'sponsor_debit_wei': debit, 'billed_gas': words[3], 'surplus_usdg_raw': surplus}
        records.append(record)
        (args.out / 'progress.json').write_text(json.dumps(records, indent=2) + '\n')
        assert bool(words[1]) == expect, ('unexpected result', label)
        assert debit == words[2] > 0
        assert (surplus >= profit) if expect else surplus == 0
        if not expect:
            assert call(morpho, position_data) == before_position, 'failed position did not roll back'
            assert call(pool, calldata('getReserves()')) == before_reserves, 'failed reserves did not roll back'
        else:
            assert call(morpho, position_data) != before_position, 'successful position did not change'
        for address in [addresses['executor'], addresses['router']]:
            for token in [USDG, wsnet, snet, net]:
                assert uintcall(token, 'balanceOf(address)', address) == 0, 'stranded asset'
        for token, owner_address, spender in [
            (USDG, addresses['executor'], morpho),
            (wsnet, addresses['executor'], addresses['router']),
            (snet, addresses['router'], staking),
        ]:
            assert uintcall(token, 'allowance(address,address)', owner_address, spender) == 0, 'leftover approval'
        if label == 'success':
            own = set(addresses.values()) | {EP}
            overrides = {}
            for address in own:
                state = touched[address]
                overrides[address] = {'code': local.rpc('eth_getCode', [address, 'latest']),
                                      'balance': state.get('balance', '0x0'),
                                      'stateDiff': state.get('storage', {})}
            assert set(overrides).isdisjoint(set(prestate)), 'fixture collided with historical route'
            (args.out / 'nitro-simulation-input.json').write_text(json.dumps({
                'transaction': request, 'state_overrides': overrides, 'addresses': addresses,
                'scope': 'COUNTERFACTUAL_NQC_FIXTURES_AND_PREFUNDED_EP_ONLY',
                'parent_state_timestamp_differs_by_one_second': True,
                'historical_protocol_state_overridden': False,
                'local_arbsys_stub_excluded_from_remote_overrides': True}, indent=2) + '\n')
            (args.out / 'nqc-local-prestate.json').write_text(json.dumps(touched, indent=2) + '\n')
    report = {'status': 'LOCAL_NQC_REAL_PROTOCOL_WITNESS_CYCLE', 'records': records, 'addresses': addresses,
              'failed_position_and_reserves_rollback_checked': True,
              'executor_and_router_four_token_balances_zero_checked': True,
              'three_route_allowances_cleared_checked': True,
              'new_address_external_storage_defaults_not_independently_verified': True,
              'protocol_prices_liquidity_and_balances_synthetic': False,
              'nqc_contracts_and_sponsor_funding_hypothetical': True,
              'arbsys_is_local_stub': True, 'nitro_da_measured': False, 'real_revenue': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--foundry-bin', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists()
    args.out.mkdir(parents=True)
    pin = json.loads((HERE.parent / 'robinhood-aa-20261016/toolchain.json').read_text())
    for name in ['anvil', 'cast']:
        assert hashlib.sha256((args.foundry_bin / name).read_bytes()).hexdigest() == pin['binary_sha256'][name]
    _, _, block, _, prestate, _ = load_capture(HERE / 'evidence/provider-capture')
    local = Local(18567)
    cmd = [str(args.foundry_bin / 'anvil'), '--host', '127.0.0.1', '--port', '18567', '--chain-id', '4663',
           '--hardfork', 'osaka', '--number', str(int(block['l1BlockNumber'], 16) - 2),
           '--timestamp', str(int(block['timestamp'], 16) - 100), '--gas-limit', '30000000', '--silent']
    with (args.out / 'anvil.log').open('w') as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError('Anvil failed to start')
                try:
                    assert local.rpc('web3_clientVersion', []).lower().startswith('anvil')
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('local startup timeout')
            run(local, args, block, prestate)
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
