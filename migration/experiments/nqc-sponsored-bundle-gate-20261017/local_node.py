"""Finite child-node owner: unsigned requests, no fork, keys or public endpoints."""
import contextlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'morpho-sponsor-e2e-20261017'))
import run_e2e as ref
ref.HERE = HERE  # Redirect diagnostics only; original files remain immutable.

@contextlib.contextmanager
def node(binary, artifacts=None, pool_override=False, order='fifo'):
    binary = Path(binary).resolve()
    assert ref.digest(binary.read_bytes()) == '10c1c727d6c1de973aeb160e59875b9a9a23464d6e74149ee8abb30b3500311b'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    command = [str(binary), '--accounts', '0', '--host', '127.0.0.1', '--port', str(port),
               '--chain-id', '31337', '--hardfork', 'cancun', '--timestamp', '1800000000',
               '--base-fee', '1000000000', '--order', order]
    if pool_override:
        command += ['--disable-pool-balance-checks']
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        lab = ref.Lab(f'http://127.0.0.1:{port}', artifacts or {})
        lab.command = command
        for _ in range(100):
            try:
                lab.rpc('web3_clientVersion'); break
            except (OSError, ref.RPCError):
                time.sleep(.05)
        else:
            raise RuntimeError('local child failed to start')
        assert lab.rpc('eth_chainId') == '0x7a69' and lab.rpc('eth_accounts') == []
        yield lab
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=10)

def save(name, obj):
    path = HERE / 'evidence' / (name + '.json')
    path.write_text(json.dumps(obj, separators=(',', ':')) + '\n')
    return {'file': path.name, 'sha256': ref.digest(path.read_bytes())}

def probe(binary):
    results = []
    for override in (False, True):
        for funding in (True, False):
            with node(binary, pool_override=override) as lab:
                s = lab.actors['sponsor_and_topup_financier']; o = lab.actors['nqc_sender_and_beneficiary']
                lab.rpc('anvil_setBalance', [s, hex(ref.E)])
                lab.rpc('evm_setAutomine', [False])
                requests = []
                def submit(sender, to, value):
                    request = {'from': sender, 'to': to, 'value': hex(value), 'gas': hex(21000),
                               'maxFeePerGas': hex(3*10**9), 'maxPriorityFeePerGas': hex(10**9), 'nonce': '0x0'}
                    item = {'request': request}
                    try:
                        item['hash'] = lab.rpc('eth_sendUnsignedTransaction', [request])
                    except ref.RPCError as exc:
                        item['error'] = str(exc)
                    requests.append(item)
                if funding:
                    submit(s, o, 10**16)
                submit(o, lab.actors['simulated_builder'], 1)
                lab.rpc('anvil_setNextBlockBaseFeePerGas', [hex(10**9)])
                lab.rpc('evm_mine')
                for item in requests:
                    if item.get('hash'):
                        item['receipt'] = lab.rpc('eth_getTransactionReceipt', [item['hash']])
                        if item['receipt']:
                            try:
                                item['state_diff'] = lab.rpc('debug_traceTransaction', [item['hash'],
                                    {'tracer': 'prestateTracer', 'tracerConfig': {'diffMode': True}}])
                            except ref.RPCError as exc:
                                item['state_diff_error'] = str(exc)
                results.append({'pool_balance_check_disabled': override, 'funding_present': funding,
                                'command': lab.command, 'transactions': requests, 'final': lab.snapshot()})
    save('pool-admission-probe', results)
    print(json.dumps([{'override': r['pool_balance_check_disabled'], 'funding': r['funding_present'],
          'included': sum(bool(t.get('receipt')) for t in r['transactions']),
          'errors': [t['error'] for t in r['transactions'] if 'error' in t]} for r in results]))

if __name__ == '__main__':
    probe(sys.argv[1])
