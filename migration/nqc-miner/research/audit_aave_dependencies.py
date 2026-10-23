#!/usr/bin/env python3
"""Reproduce compiler byte equality for the retained token/strategy dependencies.

This does not authenticate state, certify proxy dispatch, or execute liquidation.
"""
import argparse
import copy
import gzip
import json
from pathlib import Path
import posixpath
import re
import subprocess
import tempfile
import capture_aave_dependencies as capture

probe = capture.probe
DIRECTORY = capture.DIRECTORY
READ = capture.conditions.identity.read_json
ENCODE = capture.conditions.identity.encoded
KNOWN_IMMUTABLES = {
    'POOL': probe.POOL,
    '_chainId': '0x1',
    '_addressesProvider': capture.conditions.identity.IMMUTABLES['ADDRESSES_PROVIDER'],
    'TREASURY': '0x464c71f6c2f760dda6093dcb91c24c39e5d6e18c',
    'REWARDS_CONTROLLER': '0x8164cc65827dcfe994ab23944cbc90e0aa80bfcb',
    'ADDRESSES_PROVIDER': capture.conditions.identity.IMMUTABLES['ADDRESSES_PROVIDER'],
}


def compilation_input(source, profile):
    probe.check(str(source['chainId']) == '1' and source['address'].lower() == profile['address'], 'source identity')
    probe.check(probe.sha(ENCODE(source['sources'])) == profile['sources_sha256'], 'source bytes')
    comp = source['compilation']
    probe.check(comp['compilerVersion'] == profile['compiler_version'] and comp['fullyQualifiedName'] == profile['target'], 'compiler/target identity')
    value = copy.deepcopy(source['stdJsonInput'])
    probe.check(value['language'] == 'Solidity' and value['sources'] == source['sources'] and value['settings'] == comp['compilerSettings'], 'standard input disagreement')
    probe.check(probe.sha(ENCODE(value['settings'])) == profile['settings_sha256'], 'compiler settings')
    probe.check(set(value) == {'language','sources','settings'}, 'standard input fields')
    for item in value['sources'].values():
        probe.check(set(item) == {'content'} and isinstance(item['content'], str), 'nonliteral source')
    # Close every import against the supplied virtual source set, including on
    # old solc versions which lack --no-import-callback. No filesystem imports.
    for name, item in value['sources'].items():
        for imported in re.findall(r'\bimport\s+(?:[^;]*?\s+from\s+)?[\'"]([^\'"]+)[\'"]\s*;', item['content']):
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), imported)) if imported.startswith('.') else imported
            options = []
            for mapping in value['settings'].get('remappings', []):
                left, replacement = mapping.split('=', 1)
                context, prefix = left.split(':', 1) if ':' in left else ('', left)
                if name.startswith(context) and resolved.startswith(prefix):
                    options.append((len(prefix), len(context), replacement + resolved[len(prefix):]))
            if options:
                resolved = max(options)[2]
            probe.check(resolved in value['sources'], 'unresolved source import: ' + imported)
    value['settings']['outputSelection'] = {'*': {'*': ['evm.deployedBytecode','storageLayout'], '': ['ast']}}
    return value


def compile_source(compiler, value, profile):
    index = READ(capture.conditions.identity.EVIDENCE / 'compiler-list.json.gz')
    builds = [b for b in index['builds'] if b['longVersion'] == profile['compiler_version']]
    probe.check(len(builds) == 1 and builds[0]['sha256'] == '0x' + profile['compiler_sha256'], 'official compiler index')
    probe.check(not compiler.is_symlink() and probe.sha(compiler.read_bytes()) == profile['compiler_sha256'], 'compiler checksum')
    with tempfile.TemporaryDirectory() as tmp:
        run = subprocess.run([str(compiler.resolve()), '--standard-json'], input=ENCODE(value), capture_output=True, cwd=tmp, timeout=180, check=True)
    probe.check(len(run.stdout) <= 16_000_000 and len(run.stderr) <= 100_000, 'compiler output size')
    return run.stdout, run.stderr


def render_runtime(output, profile):
    probe.check(not any(e.get('severity') == 'error' for e in output.get('errors', [])), 'compiler error')
    path, name = profile['target'].rsplit(':', 1)
    code = output['contracts'][path][name]['evm']['deployedBytecode']
    probe.check(not code.get('linkReferences'), 'unexpected library links')
    text = code['object']
    probe.check(isinstance(text, str) and re.fullmatch(r'(?:[0-9a-f]{2})+', text) and len(text) <= 131072, 'runtime encoding')
    data = bytearray.fromhex(text)
    names = {}
    def visit(node):
        if isinstance(node, dict):
            if node.get('nodeType') == 'VariableDeclaration' and node.get('mutability') == 'immutable':
                names[str(node['id'])] = node['name']
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(output['sources'])
    used, edits, actual_names = set(), [], set()
    for identity, refs in code.get('immutableReferences', {}).items():
        probe.check(identity in names and names[identity] in KNOWN_IMMUTABLES, 'unknown immutable')
        name = names[identity]; actual_names.add(name)
        value = int(KNOWN_IMMUTABLES[name], 16).to_bytes(32, 'big')
        probe.check(len(refs) > 0, 'empty immutable references')
        for ref in refs:
            start, size = ref['start'], ref['length']
            probe.check(type(start) is int and type(size) is int and start >= 0 and size == 32 and start + size <= len(data), 'immutable bounds/width')
            locations = set(range(start, start + size))
            probe.check(not used & locations and data[start:start + size] == bytes(size), 'overlap/nonzero immutable')
            used.update(locations); data[start:start + size] = value
            edits.append({'offset': start, 'length': size, 'name': name, 'value': '0x' + value.hex()})
    probe.check(actual_names == set(profile['immutables']), 'immutable coverage')
    return '0x' + data.hex(), edits


def audit(histories, profiles, outputs):
    probe.check([h['block']['number'] for h in histories] == list(capture.conditions.identity.BLOCKS), 'block coverage')
    for h, plan in zip(histories, capture.plans()):
        probe.check(h['block'] == plan['block'] and h['event_anchor'] == plan['event_anchor'] and h['reserves'] == plan['reserves'], 'historical source binding')
        expected_tokens = [(r['asset'], k, r[k]) for r in plan['reserves'] for k in ('a_token', 'v_token')]
        probe.check([(t['asset'], t['kind'], t['proxy']) for t in h['tokens']] == expected_tokens and len(h['records']) == 44, 'token/record coverage')
        probe.check(h['strategy']['address'] == capture.STRATEGY, 'strategy identity')
    expected = {t['implementation'] for h in histories for t in h['tokens']} | {capture.STRATEGY}
    probe.check({p['address'] for p in profiles} == expected and len(profiles) == len(expected) and set(outputs) == expected, 'implementation coverage')
    results = []
    for p in profiles:
        runtime, edits = render_runtime(outputs[p['address']], p)
        samples = []
        for h in histories:
            targets = [(t['implementation'],t['implementation_runtime'],t['proxy'],t['kind']) for t in h['tokens']]
            targets.append((h['strategy']['address'],h['strategy']['runtime'],None,'strategy'))
            for address, observed, proxy, kind in targets:
                if address != p['address']:
                    continue
                probe.check(runtime == observed, 'runtime mismatch: ' + address)
                # Do not trust the derived observation in isolation: compare each
                # independently retained provider reply at the same block hash.
                for provider in probe.PROVIDERS:
                    matches = [r for r in h['records'] if r['provider_id'] == provider and r['request']['method'] == 'eth_getCode' and r['request']['params'][0] == address]
                    probe.check(bool(matches), 'provider coverage')
                    for r in matches:
                        probe.check(r['request']['params'][1] == {'blockHash': h['block']['hash'], 'requireCanonical': True} and r['response']['result'] == runtime, 'provider runtime mismatch')
                samples.append({'block':h['block']['number'],'proxy':proxy,'kind':kind,'provider_comparisons':2})
        probe.check(bool(samples), 'missing history')
        results.append({'address':p['address'],'target':p['target'],'compiler_version':p['compiler_version'],'runtime_sha256':probe.sha(bytes.fromhex(runtime[2:])),'runtime_bytes':(len(runtime)-2)//2,'metadata_bytes_compared':True,'substitutions':edits,'samples':samples})
    return {'schema':'nqc-miner-aave-dependency-compiled-audit-v1','contracts':results,'token_proxy_observations':12,'strategy_observations':3,'provider_runtime_comparisons':30,'new_source_events':0,'implementation_runtime_match_verified':True,'proxy_dispatch_verified':False,'state_authenticated':False,'transaction_prestate':False,'external_behavior_verified':False,'executable_eligibility_verified':False,'activation_allowed':False}


def retained_inputs():
    profiles = READ(DIRECTORY / 'profiles.json')['contracts']
    inputs, outputs = {}, {}
    for p in profiles:
        address = p['address']
        source = READ(DIRECTORY / 'sources' / (address + '.json.gz'))
        retrieval = READ(DIRECTORY / 'sources' / (address + '.retrieval.json'))
        raw = gzip.decompress((DIRECTORY / 'sources' / (address + '.json.gz')).read_bytes())
        probe.check(retrieval['url'] == 'https://sourcify.dev/server/v2/contract/1/' + address + '?fields=all' and retrieval['sha256'] == probe.sha(raw), 'source retrieval')
        value = compilation_input(source, p)
        probe.check(value == READ(DIRECTORY / 'compiler' / (address + '-input.json.gz')), 'compiler input integrity')
        output_raw = gzip.decompress((DIRECTORY / 'compiler' / (address + '-output.json.gz')).read_bytes())
        probe.check(probe.sha(output_raw) == p['compiler_output_sha256'], 'compiler output integrity')
        inputs[address] = value; outputs[address] = json.loads(output_raw)
    return profiles, inputs, outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profiles, _, outputs = retained_inputs()
    report = audit(capture.replay(), profiles, outputs)
    probe.save(args.output, report)
    print(json.dumps({'contracts':len(report['contracts']),'comparisons':report['provider_runtime_comparisons'],'activation_allowed':False}))


if __name__ == '__main__':
    main()
