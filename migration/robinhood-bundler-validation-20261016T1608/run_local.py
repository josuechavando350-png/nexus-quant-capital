"""Bounded, read-only Geth validation traces on literal loopback, with no signer.

This does NOT execute the full bundler parser, reputation manager or mempool.
No public RPC endpoint parameter exists. No transaction submission is permitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import urllib.error

from validation import HERE, ROOT, EP, CASES, fixture, read, summarize

URL = 'http://127.0.0.1:18569'
ALLOWED = {'web3_clientVersion', 'eth_chainId', 'eth_getBlockByNumber', 'debug_traceCall'}
MAX_BYTES = 2 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def verify_lock():
    for name, sha in read(HERE/'sources.json')['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha:
            raise ValueError('locked input changed: '+name)


class LocalJournal:
    def __init__(self, out, start):
        self.out, self.start, self.last, self.failed, self.rows = out, start, None, False, []
        # Explicit loopback bypass only; no change to external proxy/CA settings.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def rpc(self, method, params):
        if self.failed or method not in ALLOWED or len(self.rows) >= 512:
            raise ValueError('local method/budget/stop guard')
        wait = max(0, 0.350 - (time.monotonic()-self.last)) if self.last is not None else 0
        if time.monotonic()-self.start + wait + 20 > 900:
            self.failed = True
            raise ValueError('global local-capture deadline')
        if wait:
            time.sleep(wait)
        number = len(self.rows)+1
        req = {'jsonrpc': '2.0', 'id': number, 'method': method, 'params': params}
        row = {'request': req, 'file': f'{number:02d}-{method}.json', 'wait_seconds': wait}
        self.rows.append(row)
        self.last = time.monotonic()
        row['dispatch_seconds'] = self.last-self.start
        try:
            request = urllib.request.Request(URL, data=json.dumps(req).encode(), headers={'Content-Type': 'application/json'})
            with self.http.open(request, timeout=20) as response:
                body = response.read(MAX_BYTES+1)
                row['http_status'] = response.status
            (self.out/row['file']).write_bytes(body)
            row['response_sha256'] = hashlib.sha256(body).hexdigest()
            if len(body) > MAX_BYTES:
                raise ValueError('response byte limit')
            obj = json.loads(body)
            if obj.get('id') != number or 'error' in obj or 'result' not in obj:
                raise ValueError('local RPC error or invalid envelope')
            return obj['result']
        except urllib.error.HTTPError as error:
            self.failed = True
            body = error.read(MAX_BYTES+1)
            (self.out/row['file']).write_bytes(body)
            row.update(http_status=error.code, error='HTTPError', response_sha256=hashlib.sha256(body).hexdigest())
            raise
        except Exception as error:
            self.failed = True
            row['error'] = type(error).__name__+': '+str(error)
            raise
        finally:
            row['end_seconds'] = time.monotonic()-self.start
            save(self.out/'requests.json', self.rows)


def genesis():
    config = {'chainId': 4663, 'terminalTotalDifficulty': 0, 'shanghaiTime': 0}
    for name in ('homesteadBlock', 'eip150Block', 'eip155Block', 'eip158Block', 'byzantiumBlock',
                 'constantinopleBlock', 'petersburgBlock', 'istanbulBlock', 'berlinBlock', 'londonBlock', 'mergeNetsplitBlock'):
        config[name] = 0
    return {'config': config, 'nonce': '0x0', 'timestamp': hex(1789786800), 'extraData': '0x',
            'gasLimit': hex(30000000), 'difficulty': '0x0', 'mixHash': '0x'+'00'*32,
            'coinbase': '0x'+'00'*20, 'baseFeePerGas': hex(67514000), 'alloc': {}}


def run(geth, out, registration):
    if out.exists():
        raise ValueError('new output directory required')
    verify_lock()
    pin = read(HERE/'toolchain.json')
    if hashlib.sha256(geth.read_bytes()).hexdigest() != pin['geth_sha256']:
        raise ValueError('Geth binary differs')
    # The named commit must contain exactly the locked bytes, not just be an ancestor.
    lock = read(HERE/'sources.json')
    for name, sha in lock['files'].items():
        blob = subprocess.check_output(['git', 'show', registration+':'+name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != sha:
            raise ValueError('registration content differs')
    out.mkdir(parents=True)
    start = time.monotonic()
    journal = LocalJournal(out, start)
    report = {'status': 'STARTED', 'registration_commit': registration, 'cases': [],
              'public_rpc_methods': 0, 'transactions_sent': 0, 'full_bundler_executed': False,
              'scope': 'Upstream collector on local Geth EVM; NOT parser or mempool admission; NOT Nitro.'}
    save(out/'genesis.json', genesis())
    # Deterministic public auth fixture for an unused loopback-only engine API.
    (out/'engine.jwt.fixture').write_text('11'*32+'\n')
    process = None
    try:
        cmd = [str(geth), '--datadir', str(out/'db'), 'init', str(out/'genesis.json')]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        (out/'geth-init.log').write_text(result.stdout+result.stderr)
        result.check_returncode()
        cmd = [str(geth), '--datadir', str(out/'db'), '--networkid', '4663', '--maxpeers', '0',
               '--nodiscover', '--discovery.dns', '', '--nat', 'none', '--port', '0',
               '--netrestrict', '127.0.0.0/8', '--ipcdisable', '--http', '--http.addr', '127.0.0.1',
               '--http.port', '18569', '--http.api', 'eth,net,web3,debug', '--http.vhosts', '127.0.0.1',
               '--authrpc.addr', '127.0.0.1', '--authrpc.port', '18570',
               '--authrpc.jwtsecret', str(out/'engine.jwt.fixture'), '--syncmode', 'full', '--verbosity', '3']
        save(out/'process-commands.json', {'init': result.args, 'server': cmd})
        with (out/'geth.log').open('w') as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('local Geth exited during startup')
                try:
                    with socket.create_connection(('127.0.0.1', 18569), timeout=.1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('local Geth startup deadline')
            version = journal.rpc('web3_clientVersion', [])
            if not version.startswith('Geth/v1.17.8'):
                raise ValueError('unexpected loopback client')
            assert int(journal.rpc('eth_chainId', []), 16) == 4663
            header = journal.rpc('eth_getBlockByNumber', ['latest', False])
            assert int(header['number'], 16) == 0 and int(header['timestamp'], 16) == 1789786800
            report['local_client'] = version
            for name in CASES:
                case = fixture(name)
                save(out/(name+'-input.json'), case)
                params = [case['transaction'], header['hash'], {
                    'tracer': (HERE/'build/tracer.js').read_text(), 'timeout': '10s', 'reexec': 0,
                    'stateOverrides': case['stateOverrides']}]
                trace = journal.rpc('debug_traceCall', params)
                report['cases'].append(summarize(case, trace))
                save(out/'report.json', report)
            final = journal.rpc('eth_getBlockByNumber', ['latest', False])
            assert final['hash'] == header['hash'] and final['stateRoot'] == header['stateRoot']
            report.update(status='LOCAL_VALIDATION_TRACES_COMPLETE_FULL_BUNDLER_BLOCKED',
                          local_genesis_hash=header['hash'], local_state_unchanged=True)
    except Exception as error:
        report.update(status='STOPPED_PREFIX_PRESERVED', error=type(error).__name__+': '+str(error))
        raise
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        report.update(local_rpc_methods=len(journal.rows), elapsed_seconds=time.monotonic()-start)
        save(out/'report.json', report)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--geth', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--registration-commit', required=True)
    args = ap.parse_args()
    run(args.geth.resolve(), args.out.resolve(), args.registration_commit)
