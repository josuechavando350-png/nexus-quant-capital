#!/usr/bin/env python3
"""Offline replay of a captured third-party transaction on a loopback-only Anvil.

The captured contracts/storage are real; Anvil is NOT Nitro and has no DA meter.
No remote RPC argument, signer, fork endpoint or broadcast path is accepted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent


class Local:
    def __init__(self, port):
        self.url = f'http://127.0.0.1:{port}'
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def rpc(self, method, params):
        req = urllib.request.Request(self.url,
            data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
            headers={'Content-Type': 'application/json'})
        with self.http.open(req, timeout=20) as response:
            result = json.load(response)
        if 'error' in result:
            raise RuntimeError((method, result['error']))
        return result['result']


def load_capture(path):
    capture = json.loads((path / 'capture.json').read_text())
    assert capture['status'] == 'HISTORICAL_PROVIDER_TRACE_CAPTURED_NOT_NQC_REPLAY'
    for record in capture['requests']:
        if 'response_file' in record:
            assert hashlib.sha256((path / record['response_file']).read_bytes()).hexdigest() == record['response_sha256']
    read = lambda name: json.loads((path / name).read_text())['result']
    return (read('03-transaction.json'), read('04-receipt.json'), read('05-block.json'),
            read('07-call-trace.json'), read('08-prestate.json'), read('09-state-diff.json'))


def restore(local, prestate):
    for address, state in prestate.items():
        if state.get('code'):
            local.rpc('anvil_setCode', [address, state['code']])
        if 'balance' in state:
            local.rpc('anvil_setBalance', [address, state['balance']])
        if 'nonce' in state:
            local.rpc('anvil_setNonce', [address, hex(state['nonce'])])
        for slot, value in state.get('storage', {}).items():
            local.rpc('anvil_setStorageAt', [address, slot, value])


def log_identity(log):
    return (log['address'].lower(), [t.lower() for t in log['topics']], log['data'].lower())


def compare(local, original, expected_trace, expected_diff, receipt, trace):
    assert int(receipt['status'], 16) == 1, 'historical transaction failed locally'
    assert trace.get('output') == expected_trace.get('output'), 'return data mismatch'
    assert list(map(log_identity, receipt['logs'])) == list(map(log_identity, original['logs'])), 'ordered logs mismatch'
    checked = 0
    # Storage changes include zeroed/deleted slots, which Geth omits from post.
    for address in set(expected_diff['pre']) | set(expected_diff['post']):
        if address.lower().startswith('0xa4b0'):
            continue  # ArbOS native accounting is outside Anvil's EVM model.
        before = expected_diff['pre'].get(address, {}).get('storage', {})
        after = expected_diff['post'].get(address, {}).get('storage', {})
        for slot in set(before) | set(after):
            actual = local.rpc('eth_getStorageAt', [address, slot, 'latest'])
            assert int(actual, 16) == int(after.get(slot, '0x0'), 16), (address, slot, 'state mismatch')
            checked += 1
    return {'status': 'HISTORICAL_CONTRACT_EXECUTION_REPRODUCED_ON_ANVIL',
            'ordered_logs_match': len(receipt['logs']), 'changed_contract_storage_slots_match': checked,
            'return_data_match': True, 'local_transaction_gas': int(receipt['gasUsed'], 16),
            'historical_nitro_receipt_gas': int(original['gasUsed'], 16),
            'local_is_nitro': False, 'da_measured': False, 'state_root_verified': False,
            'nqc_executor_replayed': False, 'nqc_revenue_realized': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--anvil', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), 'new output path required'
    args.out.mkdir(parents=True)
    pin = json.loads((HERE.parent / 'robinhood-aa-20261016/toolchain.json').read_text())
    assert hashlib.sha256(args.anvil.read_bytes()).hexdigest() == pin['binary_sha256']['anvil']
    tx, original, block, expected_trace, prestate, diff = load_capture(HERE / 'evidence/provider-capture')
    local = Local(18566)
    cmd = [str(args.anvil), '--host', '127.0.0.1', '--port', '18566', '--chain-id', '4663',
           '--hardfork', 'osaka', '--number', str(int(block['l1BlockNumber'], 16) - 1),
           '--timestamp', str(int(block['timestamp'], 16) - 1), '--gas-limit', '30000000', '--silent']
    with (args.out / 'anvil.log').open('w') as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError('Anvil failed to start')
                try:
                    version = local.rpc('web3_clientVersion', [])
                    assert version.lower().startswith('anvil')
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Anvil startup timeout')
            restore(local, prestate)
            local.rpc('anvil_setCoinbase', [block['miner']])
            local.rpc('anvil_setNextBlockBaseFeePerGas', [block['baseFeePerGas']])
            local.rpc('evm_setNextBlockTimestamp', [int(block['timestamp'], 16)])
            local.rpc('anvil_impersonateAccount', [tx['from']])
            request = {key: tx[key] for key in ['from', 'to', 'gas', 'nonce', 'value', 'input',
                                                'maxFeePerGas', 'maxPriorityFeePerGas']}
            identity = local.rpc('eth_sendTransaction', [request])
            receipt = None
            for _ in range(100):
                receipt = local.rpc('eth_getTransactionReceipt', [identity])
                if receipt is not None:
                    break
                time.sleep(0.05)
            assert receipt is not None, 'local receipt timeout'
            trace = local.rpc('debug_traceTransaction', [identity, {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}}])
            for name, value in [('receipt.json', receipt), ('trace.json', trace)]:
                (args.out / name).write_text(json.dumps(value, indent=2) + '\n')
            report = compare(local, original, expected_trace, diff, receipt, trace)
            report.update(local_client=version, hardfork='osaka',
                          restored_accounts=len(prestate),
                          restored_storage_slots=sum(len(s.get('storage', {})) for s in prestate.values()),
                          local_block_number_is_parent_chain_height=True)
            (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2))
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
