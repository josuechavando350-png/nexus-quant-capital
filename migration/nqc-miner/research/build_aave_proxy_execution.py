#!/usr/bin/env python3
"""Reproduce one deployed token-proxy family and compose audited debt execution.

Only code/slot observations are historical; execution state is synthetic.
The second retained proxy family is explicitly excluded.
"""
import argparse
import copy
import gzip
import json
from pathlib import Path
import aave_runtime_identity as identity
import audit_aave_dependencies as dependencies
import capture_aave_dependencies as capture

DIRECTORY = identity.MODULE / 'evidence/aave-token-proxy-execution-20261023'
ADDRESS = '0x72e95b8931767c79ba4eee721354d6e99a61d004'
ADMIN = '0x64b761d848206f447fe2dd461b0c635ec39ebb27'
RUNTIME_SHA = 'e02c1a7633263e5c7c9dc7ccd2d504fc274c006f66780830ecf06171b3eb0b9b'
EXCLUDED_SHA = '2fbea219fecfea10d2b21f2be30a5101d9bf4a3fdce068f1206a18e225995c01'
check = identity.check


def inputs():
    profile = identity.read_json(DIRECTORY / 'profile.json')
    check(profile['address'] == ADDRESS and profile['admin'] == ADMIN and profile['immutables'] == ['_admin'], 'proxy profile identity')
    check(profile['compiler_version'] == '0.8.10+commit.fc410830', 'proxy compiler version')
    check(profile['compiler_sha256'] == 'c7effacf28b9d64495f81b75228fbf4266ac0ec87e8f1adc489ddd8a4dd06d89', 'proxy compiler checksum')
    raw = gzip.decompress((DIRECTORY / 'source.json.gz').read_bytes())
    retrieval = identity.read_json(DIRECTORY / 'retrieval.json')
    check(retrieval['url'] == 'https://sourcify.dev/server/v2/contract/1/' + ADDRESS + '?fields=all' and retrieval['sha256'] == identity.sha(raw), 'proxy source retrieval')
    value = dependencies.compilation_input(json.loads(raw), profile)
    return profile, value


def render(output, profile):
    check(not any(e.get('severity') == 'error' for e in output.get('errors', [])), 'proxy compiler error')
    path, name = profile['target'].rsplit(':', 1)
    contract = output['contracts'][path][name]
    code = contract['evm']['deployedBytecode']
    check(not code['linkReferences'], 'proxy library links')
    refs = code['immutableReferences']
    declarations = {}
    def visit(node):
        if isinstance(node, dict):
            if node.get('nodeType') == 'VariableDeclaration' and node.get('mutability') == 'immutable':
                declarations[str(node['id'])] = node['name']
            for v in node.values(): visit(v)
        elif isinstance(node, list):
            for v in node: visit(v)
    visit(output['sources'])
    check(len(refs) == 1 and [declarations.get(k) for k in refs] == ['_admin'], 'proxy immutable coverage')
    data = bytearray.fromhex(code['object'])
    edits, used = [], set()
    word = int(ADMIN, 16).to_bytes(32, 'big')
    for ref in next(iter(refs.values())):
        start, size = ref['start'], ref['length']
        check(type(start) is int and type(size) is int and start >= 0 and size == 32 and start + size <= len(data), 'proxy immutable bounds')
        positions = set(range(start, start + size))
        check(not positions & used and data[start:start + size] == bytes(size), 'proxy immutable overlap/nonzero')
        used.update(positions); data[start:start + size] = word
        edits.append({'offset': start, 'length': size, 'name': '_admin', 'value': '0x' + word.hex()})
    check(len(edits) == 6 and len(data) == 2400 and identity.sha(data) == RUNTIME_SHA, 'proxy full runtime identity')
    return {'runtime_code': '0x' + data.hex(), 'runtime_sha256': identity.sha(data), 'storage_layout': contract['storageLayout'], 'substitutions': edits, 'admin': ADMIN, 'implementation_slot': capture.probe.SLOT}


def fixture_from(output, profile, histories):
    proxy = render(output, profile)
    samples, excluded = [], []
    for h in histories:
        for t in h['tokens']:
            if t['proxy_sha256'] != RUNTIME_SHA:
                check(t['proxy_sha256'] == EXCLUDED_SHA, 'unknown excluded family')
                excluded.append({'block': h['block']['number'], 'proxy': t['proxy'], 'runtime_sha256': t['proxy_sha256']})
                continue
            check(t['proxy_runtime'] == proxy['runtime_code'], 'proxy observed code mismatch')
            check(capture.probe.implementation(t['slot_word']) == t['implementation'], 'proxy slot target mismatch')
            for provider in capture.probe.PROVIDERS:
                rows = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getCode' and r['request']['params'][0] == t['proxy']]
                check(len(rows) == 1 and rows[0]['response']['result'] == proxy['runtime_code'], 'proxy provider code mismatch')
                check(rows[0]['request']['params'][1] == {'blockHash': h['block']['hash'], 'requireCanonical': True}, 'proxy provider block pin')
                slots = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getStorageAt' and r['request']['params'][0] == t['proxy']]
                check(len(slots) == 1 and slots[0]['response']['result'] == t['slot_word'], 'proxy provider slot mismatch')
                check(slots[0]['request']['params'][1:] == [capture.probe.SLOT, {'blockHash': h['block']['hash'], 'requireCanonical': True}], 'proxy slot pin')
            samples.append({'block': h['block'], 'proxy': t['proxy'], 'kind': t['kind'], 'implementation': t['implementation'], 'implementation_slot_word': t['slot_word']})
    check(len(samples) == 10 and len({s['proxy'] for s in samples}) == 6 and len(excluded) == 2, 'proxy family coverage')
    previous_path = identity.MODULE / 'fixtures/aave_debt_execution.json'
    previous = identity.read_json(previous_path)
    result = copy.deepcopy(previous)
    result['schema'] = 'nqc-miner-aave-token-proxy-execution-fixture-v1'
    result['previous_fixture_sha256'] = identity.sha(previous_path.read_bytes())
    del result['contracts']['SyntheticDebtProxy']
    result['contracts']['AuditedDebtProxy'] = proxy
    profiles, _, outputs = dependencies.retained_inputs()
    p = next(p for p in profiles if ':ATokenInstance' in p['target'])
    runtime, edits = dependencies.render_runtime(outputs[p['address']], p)
    path, name = p['target'].rsplit(':', 1)
    result['contracts']['ATokenInstance'] = {'runtime_code': runtime, 'runtime_sha256': identity.sha(bytes.fromhex(runtime[2:])), 'implementation_address': p['address'], 'substitutions': edits, 'compiler_output_sha256': p['compiler_output_sha256'], 'storage_layout': outputs[p['address']]['contracts'][path][name]['storageLayout']}
    result['proxy_synthetic'] = False
    result['proxy_code_runtime_match_verified'] = True
    result['proxy_samples'] = samples
    result['excluded_proxy_samples'] = excluded
    result['proxy_compiler_output_sha256'] = profile['compiler_output_sha256']
    result['proxy_compiler_sha256'] = profile['compiler_sha256']
    result['complete_liquidation_verified'] = False
    return result


def retained_fixture():
    profile, value = inputs()
    check(value == identity.read_json(DIRECTORY / 'compiler/input.json.gz'), 'proxy compiler input mismatch')
    raw = gzip.decompress((DIRECTORY / 'compiler/output.json.gz').read_bytes())
    check(identity.sha(raw) == profile['compiler_output_sha256'], 'proxy compiler output hash')
    profiles, _, outputs = dependencies.retained_inputs()
    histories = capture.replay()
    dependencies.audit(histories, profiles, outputs)
    return fixture_from(json.loads(raw), profile, histories)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile, value = inputs()
    raw, stderr = dependencies.compile_source(args.compiler, value, profile)
    profile['compiler_output_sha256'] = identity.sha(raw)
    fixture = fixture_from(json.loads(raw), profile, capture.replay())
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('input.json.gz', identity.encoded(value)), ('output.json.gz', raw)]:
        (args.output / name).write_bytes(gzip.compress(data, mtime=0))
    (args.output / 'compiler.stderr').write_bytes(stderr)
    (DIRECTORY / 'profile.json').write_bytes(identity.encoded(profile))
    (identity.MODULE / 'fixtures/aave_proxy_execution.json').write_bytes(identity.encoded(fixture))
    print(json.dumps({'runtime_bytes': 2400, 'historical_samples': 10, 'distinct_proxies': 6, 'provider_comparisons': 20, 'excluded_proxies': 2, 'state_authenticated': False}))


if __name__ == '__main__':
    main()
