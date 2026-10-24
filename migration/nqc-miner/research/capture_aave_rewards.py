#!/usr/bin/env python3
"""Read-only, block-hash-pinned rewards proxy/implementation capture and replay."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request
import capture_aave_dependencies as dependencies

probe = dependencies.probe
identity = dependencies.conditions.identity
DIRECTORY = identity.MODULE / 'evidence/aave-rewards-20261023'
REWARDS = '0x8164cc65827dcfe994ab23944cbc90e0aa80bfcb'
PROVIDERS = {'ethereum-blast': 'https://eth-mainnet.public.blastapi.io', 'ethereum-drpc': 'https://eth.drpc.org/'}


def plans():
    return [{'block': p['block'], 'event_anchor': p['event_anchor']} for p in dependencies.plans()]


def validate_params(provider, method, args):
    probe.check(provider in PROVIDERS, 'provider')
    if method == 'eth_chainId':
        probe.check(args == [], 'chain parameters')
    elif method == 'eth_getBlockByNumber':
        probe.check(len(args) == 2 and args[1] is False and (args[0] == 'finalized' or re.fullmatch(r'0x[1-9a-f][0-9a-f]*', args[0])), 'header parameters')
    else:
        probe.check(method in {'eth_getCode', 'eth_getStorageAt'}, 'read-only method')
        probe.check(len(args) == (3 if method == 'eth_getStorageAt' else 2), 'parameter count')
        dependencies.conditions.address(args[0])
        pin = args[-1]
        probe.check(isinstance(pin, dict) and set(pin) == {'blockHash', 'requireCanonical'} and pin['requireCanonical'] is True and isinstance(pin['blockHash'], str) and re.fullmatch(r'0x[0-9a-f]{64}', pin['blockHash']) and int(pin['blockHash'], 16), 'block pin')
        if method == 'eth_getStorageAt':
            probe.check(args[0] == REWARDS and args[1] == probe.SLOT, 'rewards proxy/slot')


class Rpc:
    def __init__(self):
        self.sequence, self.last = 0, 0

    def __call__(self, provider, method, args):
        validate_params(provider, method, args)
        time.sleep(max(0, .125 - (time.monotonic() - self.last)))
        self.last = time.monotonic(); self.sequence += 1
        request = {'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': args}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        req = urllib.request.Request(PROVIDERS[provider], data=json.dumps(request).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'nqc-miner-rewards-research'})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            raw = response.read(1_048_577)
        probe.check(len(raw) <= 1_048_576, 'oversize response')
        value = json.loads(raw)
        probe.check(value.get('jsonrpc') == '2.0' and type(value.get('id')) is int and value['id'] == self.sequence and 'result' in value and 'error' not in value, 'RPC envelope')
        return {'request': request, 'response': value}


def capture_one(plan, query):
    block, event = plan['block'], plan['event_anchor']
    records, observations = [], []
    def read(provider, method, args):
        validate_params(provider, method, args)
        r = query(provider, method, args); value = r['response']['result']
        if method == 'eth_getBlockByNumber':
            value = {k: value[k] for k in ('number', 'hash', 'parentHash', 'timestamp')}
        records.append({'provider_id': provider, 'request': r['request'], 'response': {**r['response'], 'result': value}})
        return value
    def verify(provider, header):
        probe.check(probe.same(probe.header(read(provider, 'eth_getBlockByNumber', [hex(header['number']), False])), header), 'header changed')
    for provider in PROVIDERS:
        probe.check(read(provider, 'eth_chainId', []) == '0x1', 'chain')
        finalized = probe.header(read(provider, 'eth_getBlockByNumber', ['finalized', False]))
        probe.check(finalized['number'] >= event['number'], 'finality')
        verify(provider, block); verify(provider, event)
        pin = {'blockHash': block['hash'], 'requireCanonical': True}
        slot = read(provider, 'eth_getStorageAt', [REWARDS, probe.SLOT, pin])
        target = probe.implementation(slot)
        proxy = read(provider, 'eth_getCode', [REWARDS, pin])
        runtime = read(provider, 'eth_getCode', [target, pin])
        observations.append({'proxy': REWARDS, 'implementation': target, 'slot_word': slot, 'proxy_runtime': proxy, 'implementation_runtime': runtime, 'proxy_sha256': probe.sha(probe.code_bytes(proxy)), 'implementation_sha256': probe.sha(probe.code_bytes(runtime))})
        verify(provider, block); verify(provider, event); verify(provider, finalized)
    probe.check(probe.same(*observations), 'rewards dependency disagreement')
    for provider in PROVIDERS:
        verify(provider, block); verify(provider, event)
    return {'schema': 'nqc-miner-aave-rewards-observation-v1', **plan, **observations[0], 'records': records, 'state_authenticated': False, 'transaction_prestate': False, 'source_match_verified': False, 'external_behavior_verified': False, 'executable_eligibility_verified': False, 'activation_allowed': False}


def replay(directory=DIRECTORY / 'public'):
    manifest = probe.load(directory / 'manifest.json')
    probe.check(manifest['complete'] is True and manifest['capture_sha256'] == probe.sha(Path(__file__).read_bytes()), 'rewards capture integrity')
    probe.check(len(manifest['observations']) == 3, 'rewards coverage')
    results, sequence = [], 0
    for i, (entry, plan) in enumerate(zip(manifest['observations'], plans())):
        probe.check(entry['file'] == f'rewards-{i:03d}.json', 'rewards path')
        path = directory / entry['file']
        probe.check(probe.sha(path.read_bytes()) == entry['sha256'], 'rewards capture hash')
        original = probe.load(path); records = iter(original['records'])
        def query(provider, method, args):
            nonlocal sequence
            sequence += 1; r = next(records); q, a = r['request'], r['response']
            probe.check(r['provider_id'] == provider and q['method'] == method and probe.same(q['params'], args), 'rewards request mismatch')
            probe.check(q['jsonrpc'] == a['jsonrpc'] == '2.0' and type(q['id']) is int and type(a['id']) is int and q['id'] == a['id'] == sequence and 'error' not in a, 'rewards response identity')
            return {'request': q, 'response': a}
        result = capture_one(plan, query)
        probe.check(next(records, None) is None and probe.same(result, original), 'rewards replay mismatch')
        results.append(result)
    probe.check(sequence == manifest['requests'] == 72, 'rewards request coverage')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    probe.check(not any(p.is_symlink() for p in (args.output, *args.output.parents)), 'output symlink')
    args.output.mkdir(parents=True, exist_ok=False)
    rpc, entries = Rpc(), []; start = datetime.now(timezone.utc).isoformat()
    for i, plan in enumerate(plans()):
        try:
            result = capture_one(plan, rpc); name = f'rewards-{i:03d}.json'; probe.save(args.output / name, result)
            entries.append({'file': name, 'sha256': probe.sha((args.output / name).read_bytes())})
        except Exception as error:
            probe.save(args.output / 'failure.json', {'index': i, 'error_type': type(error).__name__, 'complete': False}); raise
    probe.save(args.output / 'manifest.json', {'schema': 'nqc-miner-aave-rewards-capture-v1', 'complete': True, 'observations': entries, 'requests': rpc.sequence, 'capture_sha256': probe.sha(Path(__file__).read_bytes()), 'started_at_utc': start, 'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_source_events': 0})
    print(json.dumps({'complete': True, 'requests': rpc.sequence, 'implementations': list({probe.load(args.output / e['file'])['implementation'] for e in entries})}))


if __name__ == '__main__': main()
