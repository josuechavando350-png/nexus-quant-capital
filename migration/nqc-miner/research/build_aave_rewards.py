#!/usr/bin/env python3
"""Compile unchanged second-proxy/rewards sources and bind historical runtimes."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import re
import aave_runtime_identity as identity
import audit_aave_dependencies as dependencies
import build_aave_proxy_execution as first_proxy
import capture_aave_rewards as capture

DIRECTORY = capture.DIRECTORY
SPECS = {
    'second-proxy': ('0x2edff5af94334fbd7c38ae318edf1c40e072b73b', '0.8.22+commit.4fc1097e', {'_admin': first_proxy.ADMIN}),
    'rewards-proxy': (capture.REWARDS, '0.8.10+commit.fc410830', {'_admin': '0x2f39d218133afab8f2b819b1066c7e434ad94e9e'}),
    'rewards-implementation': ('0xe7b67f44ea304dd7f6d215b13686637ff64cd2b2', '0.8.10+commit.fc410830', {'EMISSION_MANAGER': '0x223d844fc4b006d67c0cdbd39371a9f73f69d974'}),
}
check = identity.check


def explorer_input(raw):
    html = raw.decode()
    check(len(raw) <= 5_000_000 and re.search(r'Compiler Version[\s\S]{0,500}v0\.8\.22\+commit\.4fc1097e', html), 'explorer compiler identity')
    matches = re.findall(r"var editor_contractJsonData = '((?:\\.|[^'\\])*)'", html)
    check(len(matches) == 1, 'explorer source literal')
    token, parts, i = matches[0], [], 0
    while i < len(token):
        if token[i] == '\\':
            check(i + 1 < len(token), 'unterminated escape')
            following = token[i + 1]
            check(following in '\"\\/bfnrtu\'`', 'unsupported JS escape')
            parts.append(token[i:i + 2] if following in '\"\\/bfnrtu' else following); i += 2
        else:
            parts.append(token[i]); i += 1
    value = json.loads(json.loads('"' + ''.join(parts) + '"'))
    check(set(value) == {'language', 'sources'} and value['language'] == 'Solidity', 'explorer source shape')
    value['settings'] = json.loads(value['sources'].pop('settings.json')['content'])
    check(value['settings']['evmVersion'] == 'shanghai' and value['settings']['viaIR'] is False and value['settings']['optimizer'] == {'enabled': True, 'runs': 200}, 'second proxy profile')
    check(value['settings']['metadata'] == {'useLiteralContent': False, 'bytecodeHash': 'none', 'appendCBOR': True}, 'second proxy metadata')
    return value


def source_input(profile):
    name = profile['name']
    check(name in SPECS and (profile['address'], profile['compiler_version'], profile['immutables']) == SPECS[name], 'fixed contract identity')
    index = identity.read_json(identity.EVIDENCE / 'compiler-list.json.gz')
    compiler = [b for b in index['builds'] if b['longVersion'] == profile['compiler_version']]
    check(len(compiler) == 1 and compiler[0]['sha256'] == '0x' + profile['compiler_sha256'], 'official compiler identity')
    manifest = identity.read_json(DIRECTORY / 'retrieval.json')
    entry = next(e for e in manifest['sources'] if e['name'] == ('second-proxy-explorer' if name == 'second-proxy' else name))
    expected_file = 'second-proxy-explorer.html.gz' if name == 'second-proxy' else name + '.json.gz'
    expected_url = 'https://etherscan.io/address/' + profile['address'] + '#code' if name == 'second-proxy' else 'https://sourcify.dev/server/v2/contract/1/' + profile['address'] + '?fields=all'
    check(entry['file'] == expected_file and entry['url'] == expected_url, 'source location')
    raw = gzip.decompress((DIRECTORY / 'sources' / expected_file).read_bytes())
    check(identity.sha(raw) == entry['sha256'], 'source retrieval hash')
    if name == 'second-proxy':
        value = explorer_input(raw)
        source = {'address': profile['address'], 'chainId': '1', 'sources': value['sources'], 'stdJsonInput': value, 'compilation': {'compilerVersion': profile['compiler_version'], 'fullyQualifiedName': profile['target'], 'compilerSettings': value['settings']}}
    else:
        source = json.loads(raw)
    return dependencies.compilation_input(source, profile)


def render(output, profile):
    check(not any(e.get('severity') == 'error' for e in output.get('errors', [])), 'compiler error')
    path, name = profile['target'].rsplit(':', 1); contract = output['contracts'][path][name]
    code = contract['evm']['deployedBytecode']; check(not code['linkReferences'], 'unexpected links')
    data = bytearray.fromhex(code['object']); declarations = {}
    def visit(node):
        if isinstance(node, dict):
            if node.get('nodeType') == 'VariableDeclaration' and node.get('mutability') == 'immutable': declarations[str(node['id'])] = node['name']
            for v in node.values(): visit(v)
        elif isinstance(node, list):
            for v in node: visit(v)
    visit(output['sources'])
    refs = code['immutableReferences']
    check(len(refs) == len(profile['immutables']) and {declarations.get(k) for k in refs} == set(profile['immutables']), 'immutable coverage')
    edits, used = [], set()
    for key, locations in refs.items():
        name = declarations[key]; word = int(profile['immutables'][name], 16).to_bytes(32, 'big')
        check(bool(locations), 'empty immutable references')
        for ref in locations:
            start, size = ref['start'], ref['length']
            check(type(start) is int and type(size) is int and start >= 0 and size == 32 and start + size <= len(data), 'immutable bounds')
            positions = set(range(start, start + size))
            check(not positions & used and data[start:start + size] == bytes(size), 'immutable overlap/nonzero')
            used.update(positions); data[start:start + size] = word
            edits.append({'offset': start, 'length': size, 'name': name, 'value': '0x' + word.hex()})
    return {'runtime_code': '0x' + data.hex(), 'runtime_sha256': identity.sha(data), 'storage_layout': contract['storageLayout'], 'substitutions': edits, 'implementation_address': profile['address'], 'compiler_output_sha256': profile['compiler_output_sha256']}


def retained_inputs():
    profiles = identity.read_json(DIRECTORY / 'profiles.json')['contracts']
    check(len(profiles) == 3 and {p['name'] for p in profiles} == set(SPECS), 'profile coverage')
    outputs = {}
    for p in profiles:
        value = source_input(p)
        check(value == identity.read_json(DIRECTORY / 'compiler' / (p['name'] + '-input.json.gz')), 'compiler input identity')
        raw = gzip.decompress((DIRECTORY / 'compiler' / (p['name'] + '-output.json.gz')).read_bytes())
        check(identity.sha(raw) == p['compiler_output_sha256'], 'compiler output identity')
        outputs[p['name']] = json.loads(raw)
    return profiles, outputs


def audit(profiles, outputs, rewards, tokens):
    contracts = {p['name']: render(outputs[p['name']], p) for p in profiles}
    check([h['block']['number'] for h in rewards] == list(identity.BLOCKS), 'rewards historical coverage')
    check(len(rewards) == 3 and len(tokens) == 3, 'sample coverage')
    for h, plan in zip(tokens, capture.dependencies.plans()):
        check(h['block'] == plan['block'] and h['event_anchor'] == plan['event_anchor'], 'token source binding')
    for h, plan in zip(rewards, capture.plans()):
        check(h['block'] == plan['block'] and h['event_anchor'] == plan['event_anchor'] and len(h['records']) == 24, 'rewards source binding')
        check(h['proxy'] == SPECS['rewards-proxy'][0] and h['implementation'] == SPECS['rewards-implementation'][0], 'historical rewards implementation')
        check(capture.probe.implementation(h['slot_word']) == h['implementation'], 'rewards slot target')
        for provider in capture.PROVIDERS:
            rows = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getStorageAt']
            check(len(rows) == 1 and rows[0]['response']['result'] == h['slot_word'] and rows[0]['request']['params'] == [h['proxy'], capture.probe.SLOT, {'blockHash': h['block']['hash'], 'requireCanonical': True}], 'rewards provider slot/pin')
        for name, key, address in [('rewards-proxy', 'proxy_runtime', h['proxy']), ('rewards-implementation', 'implementation_runtime', h['implementation'])]:
            runtime = contracts[name]['runtime_code']; check(h[key] == runtime, 'historical rewards runtime mismatch')
            for provider in capture.PROVIDERS:
                rows = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getCode' and r['request']['params'][0] == address]
                check(len(rows) == 1 and rows[0]['response']['result'] == runtime and rows[0]['request']['params'][1] == {'blockHash': h['block']['hash'], 'requireCanonical': True}, 'rewards provider code/pin')
    proxy = contracts['second-proxy']; samples = []
    check(proxy['runtime_sha256'] == first_proxy.EXCLUDED_SHA, 'second proxy runtime identity')
    for h in tokens:
        for t in h['tokens']:
            if t['proxy_sha256'] != first_proxy.EXCLUDED_SHA: continue
            check(t['proxy_runtime'] == proxy['runtime_code'], 'second proxy observed code')
            check(capture.probe.implementation(t['slot_word']) == t['implementation'], 'second proxy slot target')
            for provider in capture.probe.PROVIDERS:
                rows = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getCode' and r['request']['params'][0] == t['proxy']]
                check(len(rows) == 1 and rows[0]['response']['result'] == proxy['runtime_code'] and rows[0]['request']['params'][1] == {'blockHash': h['block']['hash'], 'requireCanonical': True}, 'second proxy provider code/pin')
                slots = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getStorageAt' and r['request']['params'][0] == t['proxy']]
                check(len(slots) == 1 and slots[0]['response']['result'] == t['slot_word'] and slots[0]['request']['params'][1:] == [capture.probe.SLOT, {'blockHash': h['block']['hash'], 'requireCanonical': True}], 'second proxy provider slot/pin')
            samples.append({'block': h['block'], 'proxy': t['proxy'], 'kind': t['kind'], 'implementation': t['implementation'], 'implementation_slot_word': t['slot_word'], 'proxy_contract': 'AuditedDebtProxy2'})
    check(len(samples) == 2 and len({s['proxy'] for s in samples}) == 2, 'second proxy coverage')
    return contracts, samples


def fixture():
    profiles, outputs = retained_inputs()
    rewards = capture.replay(); tokens = capture.dependencies.replay()
    contracts, samples = audit(profiles, outputs, rewards, tokens)
    result = first_proxy.retained_fixture()
    for s in result['proxy_samples']: s['proxy_contract'] = 'AuditedDebtProxy'
    result['proxy_samples'] += samples; result['excluded_proxy_samples'] = []
    result['schema'] = 'nqc-miner-aave-rewards-execution-fixture-v1'
    result['previous_proxy_fixture_sha256'] = identity.sha((identity.MODULE / 'fixtures/aave_proxy_execution.json').read_bytes())
    del result['contracts']['RewardsProbe']
    for source, name in [('second-proxy', 'AuditedDebtProxy2'), ('rewards-proxy', 'RealRewardsProxy'), ('rewards-implementation', 'RewardsController')]: result['contracts'][name] = contracts[source]
    result['rewards_controller_synthetic'] = False
    result['rewards_proxy_synthetic'] = False
    result['rewards_parameters_synthetic'] = True
    result['rewards_historical_runtime_verified'] = True
    result['historical_state_authenticated'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler-directory', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    profiles = identity.read_json(DIRECTORY / 'profiles.json')['contracts']
    for p in profiles:
        value = source_input(p)
        raw, stderr = dependencies.compile_source(args.compiler_directory / ('solc-' + p['compiler_version'].split('+')[0]), value, p)
        p['compiler_output_sha256'] = identity.sha(raw)
        runtime = render(json.loads(raw), p)
        for suffix, data in [('input.json.gz', identity.encoded(value)), ('output.json.gz', raw)]: (args.output / (p['name'] + '-' + suffix)).write_bytes(gzip.compress(data, mtime=0))
        (args.output / (p['name'] + '.stderr')).write_bytes(stderr)
        print(json.dumps({'contract': p['name'], 'bytes': (len(runtime['runtime_code']) - 2)//2, 'sha256': runtime['runtime_sha256']}))
    (DIRECTORY / 'profiles.json').write_bytes(identity.encoded({'contracts': profiles}))


if __name__ == '__main__': main()
