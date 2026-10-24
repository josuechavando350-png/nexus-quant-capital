#!/usr/bin/env python3
"""Read-only USDC proxy/code routing at the three retained Aave blocks."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request
import capture_aave_rewards as prior

probe = prior.probe
identity = prior.identity
DIRECTORY = identity.MODULE / 'evidence/aave-payment-execution-20261023'
USDC = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
IMPLEMENTATION = '0x43506849d7c04f9138d1a2050bbf3a0c054402dd'
ATOKEN = '0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c'
IMPLEMENTATION_SLOT = '0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3'
ADMIN_SLOT = '0x10d6a54a4754c8869d6886b5f5d7fbfa5b4522237ea5c60d11bc4e7a1ff9390b'
PROVIDERS = dict(prior.PROVIDERS)
MAX_REQUESTS = 84


def validate(provider, method, args):
    probe.check(provider in PROVIDERS, 'provider')
    if method == 'eth_chainId':
        probe.check(args == [], 'chain parameters')
    elif method == 'eth_getBlockByNumber':
        probe.check(len(args) == 2 and args[1] is False and
                    (args[0] == 'finalized' or re.fullmatch(r'0x[1-9a-f][0-9a-f]*', args[0])), 'header parameters')
    else:
        probe.check(method in {'eth_getCode', 'eth_getStorageAt'}, 'read-only method')
        allowed = [[USDC], [IMPLEMENTATION]] if method == 'eth_getCode' else [
            [ATOKEN, '0x3d'], [USDC, IMPLEMENTATION_SLOT], [USDC, ADMIN_SLOT]]
        probe.check(args[:-1] in allowed, 'closed address/slot scope')
        pin = args[-1]
        probe.check(isinstance(pin, dict) and set(pin) == {'blockHash', 'requireCanonical'} and
                    pin['requireCanonical'] is True and isinstance(pin['blockHash'], str) and
                    re.fullmatch(r'0x[0-9a-f]{64}', pin['blockHash']) and int(pin['blockHash'], 16), 'canonical pin')


class Rpc:
    def __init__(self):
        self.sequence = 0
        self.last = 0

    def __call__(self, provider, method, args):
        validate(provider, method, args)
        probe.check(self.sequence < MAX_REQUESTS, 'request budget')
        time.sleep(max(0, .125 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        self.sequence += 1
        query = {'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': args}

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        request = urllib.request.Request(PROVIDERS[provider], data=json.dumps(query).encode(),
            headers={'Content-Type': 'application/json', 'User-Agent': 'nqc-miner-payment-research'})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            raw = response.read(1_048_577)
        probe.check(len(raw) <= 1_048_576, 'oversize reply')
        value = json.loads(raw)
        probe.check(value.get('jsonrpc') == '2.0' and type(value.get('id')) is int and
                    value['id'] == self.sequence and 'result' in value and 'error' not in value, 'RPC envelope')
        return {'request': query, 'response': value}


def capture_one(plan, query):
    block, event = plan['block'], plan['event_anchor']
    records, observations = [], []

    def read(provider, method, args):
        validate(provider, method, args)
        pair = query(provider, method, args)
        value = pair['response']['result']
        if method == 'eth_getBlockByNumber':
            value = {k: value[k] for k in ('number', 'hash', 'parentHash', 'timestamp')}
        records.append({'provider_id': provider, 'request': pair['request'],
                        'response': {**pair['response'], 'result': value}})
        return value

    def header(provider, expected):
        actual = probe.header(read(provider, 'eth_getBlockByNumber', [hex(expected['number']), False]))
        probe.check(probe.same(actual, expected), 'header changed')

    for provider in PROVIDERS:
        probe.check(read(provider, 'eth_chainId', []) == '0x1', 'chain')
        finalized = probe.header(read(provider, 'eth_getBlockByNumber', ['finalized', False]))
        probe.check(finalized['number'] >= event['number'], 'finality')
        header(provider, block)
        header(provider, event)
        pin = {'blockHash': block['hash'], 'requireCanonical': True}
        underlying = read(provider, 'eth_getStorageAt', [ATOKEN, '0x3d', pin])
        probe.check(probe.implementation(underlying) == USDC, 'aToken underlying')
        proxy = read(provider, 'eth_getCode', [USDC, pin])
        implementation = read(provider, 'eth_getStorageAt', [USDC, IMPLEMENTATION_SLOT, pin])
        probe.check(probe.implementation(implementation) == IMPLEMENTATION, 'unexpected implementation')
        admin = read(provider, 'eth_getStorageAt', [USDC, ADMIN_SLOT, pin])
        probe.implementation(admin)
        code = read(provider, 'eth_getCode', [IMPLEMENTATION, pin])
        runtimes = {address: {'runtime_code': value, 'runtime_bytes': len(probe.code_bytes(value)),
                             'runtime_sha256': probe.sha(probe.code_bytes(value))}
                    for address, value in [(USDC, proxy), (IMPLEMENTATION, code)]}
        observations.append({'underlying_slot_word': underlying, 'implementation_slot_word': implementation,
                             'admin_slot_word': admin, 'runtimes': runtimes})
        header(provider, block)
        header(provider, event)
        header(provider, finalized)
    probe.check(probe.same(*observations), 'provider disagreement')
    for provider in PROVIDERS:
        header(provider, block)
        header(provider, event)
    return {'schema': 'nqc-miner-usdc-observation-v1', **plan, 'asset': USDC, 'a_token': ATOKEN,
            **observations[0], 'records': records, 'historical_state_authenticated': False,
            'transaction_prestate': False, 'activation_allowed': False}


def replay(directory=None):
    directory = directory or DIRECTORY / 'public'
    manifest = probe.load(directory / 'manifest.json')
    probe.check(manifest['complete'] is True and
                manifest['capture_sha256'] == probe.sha(Path(__file__).read_bytes()), 'capture integrity')
    probe.check(len(manifest['observations']) == 3, 'coverage')
    sequence, results = 0, []
    for n, (entry, plan) in enumerate(zip(manifest['observations'], prior.plans())):
        probe.check(entry['file'] == f'usdc-{n:03d}.json', 'capture path')
        path = directory / entry['file']
        probe.check(probe.sha(path.read_bytes()) == entry['sha256'], 'capture hash')
        original = probe.load(path)
        records = iter(original['records'])

        def query(provider, method, args):
            nonlocal sequence
            sequence += 1
            record = next(records)
            q, a = record['request'], record['response']
            probe.check(record['provider_id'] == provider and q['method'] == method and
                        probe.same(q['params'], args), 'request sequence')
            probe.check(q['jsonrpc'] == a['jsonrpc'] == '2.0' and type(q['id']) is int and
                        type(a['id']) is int and q['id'] == a['id'] == sequence and 'error' not in a, 'response identity')
            return {'request': q, 'response': a}

        result = capture_one(plan, query)
        probe.check(next(records, None) is None and probe.same(result, original), 'capture replay')
        results.append(result)
    probe.check(sequence == manifest['requests'] == MAX_REQUESTS, 'request coverage')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    probe.check(not any(p.is_symlink() for p in (args.output, *args.output.parents)), 'output symlink')
    args.output.mkdir(parents=True, exist_ok=False)
    rpc, entries = Rpc(), []
    start = datetime.now(timezone.utc).isoformat()
    for n, plan in enumerate(prior.plans()):
        try:
            value = capture_one(plan, rpc)
            name = f'usdc-{n:03d}.json'
            probe.save(args.output / name, value)
            entries.append({'file': name, 'sha256': probe.sha((args.output / name).read_bytes())})
        except Exception as error:
            probe.save(args.output / 'failure.json', {'index': n, 'requests': rpc.sequence,
                       'error_type': type(error).__name__, 'complete': False})
            raise
    probe.save(args.output / 'manifest.json', {'schema': 'nqc-miner-usdc-capture-v1', 'complete': True,
        'observations': entries, 'requests': rpc.sequence, 'capture_sha256': probe.sha(Path(__file__).read_bytes()),
        'started_at_utc': start, 'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_liquidation_events': 0})
    print(json.dumps({'complete': True, 'requests': rpc.sequence, 'blocks': 3}))


if __name__ == '__main__':
    main()
