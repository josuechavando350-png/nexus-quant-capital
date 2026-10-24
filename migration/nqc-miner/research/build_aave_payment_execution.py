#!/usr/bin/env python3
"""Compose original debt payment with complete observed USDC proxy/runtime.

The Pool entrypoint and storage are synthetic. Compiler metadata differences,
missing initial validation and omitted multi-reserve bad-debt branch stay open.
"""
import argparse
import copy
import gzip
import json
from pathlib import Path
from posixpath import normpath, dirname
import re
import subprocess
import tempfile
import build_aave_underlying_execution as underlying
import capture_aave_payment as capture

identity = underlying.identity
DIRECTORY = capture.DIRECTORY
NAME = 'fixtures/AavePaymentExecutionHarness.sol'
CONTRACT = 'AavePaymentExecutionHarness'
SIGNATURE = underlying.SIGNATURE
PROFILES = {
    'usdc-proxy': (capture.USDC, '0.4.24+commit.e67f0147',
        '665675b9e0431c2572d59d6a7112afbdc752732ea0ce9aecf1a1855f28e02a09', 2186, 43),
    'usdc-implementation': (capture.IMPLEMENTATION, '0.6.12+commit.27d51765',
        'f6cb519b01dabc61cab4c184a3db11aa591d18151e362fcae850e42cffdfb09a', 23464, 53),
}


def usdc_input(name):
    address, version, checksum, _, _ = PROFILES[name]
    raw = gzip.decompress((DIRECTORY / (name + '-source.json.gz')).read_bytes())
    entries = identity.read_json(DIRECTORY / 'retrieval.json')['records']
    entry = next(e for e in entries if e['file'] == name + '-source.json.gz')
    identity.check(entry['sha256'] == identity.sha(raw) and entry['raw_bytes'] == len(raw) and
        entry['url'] == 'https://sourcify.dev/server/v2/contract/1/' + address + '?fields=all', 'USDC retrieval')
    source = json.loads(raw)
    identity.check(source['chainId'] == '1' and source['address'].lower() == address and
        source['compilation']['compilerVersion'] == version, 'USDC source identity')
    index = identity.read_json(identity.EVIDENCE / 'compiler-list.json.gz')
    entry = next(b for b in index['builds'] if b['longVersion'] == version)
    identity.check(entry['sha256'] == '0x' + checksum, 'compiler identity')
    value = copy.deepcopy(source['stdJsonInput'])
    identity.check(value['sources'] == source['sources'] and
        value['settings'] == source['compilation']['compilerSettings'], 'USDC original sources/settings')
    file, contract = source['compilation']['fullyQualifiedName'].rsplit(':', 1)
    value['settings']['outputSelection'] = {file: {contract:
        ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout'], '': ['ast']}}
    return source, value


def compile_usdc(compiler, name, value):
    _, version, checksum, _, _ = PROFILES[name]
    identity.check(identity.sha(compiler.read_bytes()) == checksum, 'USDC compiler checksum')
    result = subprocess.run([str(compiler), '--version'], capture_output=True, check=True)
    identity.check(version in result.stdout.decode(), 'USDC compiler version')
    with tempfile.TemporaryDirectory(prefix='nqc-usdc-') as cwd:
        result = subprocess.run([str(compiler), '--standard-json'], input=identity.encoded(value),
            cwd=cwd, capture_output=True, timeout=120)
    identity.check(result.returncode == 0, 'USDC compiler exit')
    output = json.loads(result.stdout)
    identity.check(not any(e.get('severity') == 'error' for e in output.get('errors', [])), 'USDC compile errors')
    return result.stdout, result.stderr


def audit_usdc(name, source, output, history):
    address, _, checksum, size, footer = PROFILES[name]
    file, contract = source['compilation']['fullyQualifiedName'].rsplit(':', 1)
    c = output['contracts'][file][contract]
    code = c['evm']['deployedBytecode']
    compiled = bytes.fromhex(code['object'])
    observed = bytes.fromhex(source['runtimeBytecode']['onchainBytecode'][2:])
    identity.check(not code['linkReferences'] and not code.get('immutableReferences'), 'USDC unresolved references')
    prefix = bytes.fromhex('a165627a7a72305820' if footer == 43 else 'a2646970667358221220')
    suffix = bytes.fromhex('0029' if footer == 43 else '64736f6c634300060c0033')
    for data in [compiled, observed]:
        identity.check(len(data) == size and data[-footer:].startswith(prefix) and
            data.endswith(suffix), 'USDC CBOR structure/length')
    identity.check(compiled[:-footer] == observed[:-footer], 'USDC executable mismatch')
    identity.check(compiled != observed, 'retained USDC metadata mismatch expected')
    identity.check('0x' + compiled.hex() == source['runtimeBytecode']['recompiledBytecode'], 'USDC independent compiler result')
    identity.check(len(history) == 3, 'USDC historical coverage')
    for h, plan in zip(history, capture.prior.plans()):
        identity.check(h['block'] == plan['block'] and h['event_anchor'] == plan['event_anchor'] and
            h['asset'] == capture.USDC and h['a_token'] == capture.ATOKEN, 'USDC historical binding')
        identity.check(capture.probe.implementation(h['underlying_slot_word']) == capture.USDC and
            capture.probe.implementation(h['implementation_slot_word']) == capture.IMPLEMENTATION, 'USDC routing')
        r = h['runtimes'][address]
        identity.check(r == {'runtime_code': '0x' + observed.hex(), 'runtime_bytes': size,
            'runtime_sha256': identity.sha(observed)}, 'USDC historical full runtime')
        pin = {'blockHash': h['block']['hash'], 'requireCanonical': True}
        for provider in capture.PROVIDERS:
            rows = [r for r in h['records'] if r['provider_id'] == provider]
            for method, args, result in [
                ('eth_getCode', [address, pin], '0x' + observed.hex()),
                ('eth_getStorageAt', [capture.USDC, capture.IMPLEMENTATION_SLOT, pin], h['implementation_slot_word']),
                ('eth_getStorageAt', [capture.USDC, capture.ADMIN_SLOT, pin], h['admin_slot_word']),
                ('eth_getStorageAt', [capture.ATOKEN, '0x3d', pin], h['underlying_slot_word']),
            ]:
                matches = [r for r in rows if r['request']['method'] == method and r['request']['params'] == args]
                identity.check(len(matches) == 1 and matches[0]['response']['result'] == result, 'USDC provider binding')
    result = {'address': address, 'runtime_code': '0x' + observed.hex(),
        'runtime_sha256': identity.sha(observed), 'compiled_runtime_sha256': identity.sha(compiled),
        'compiler_sha256': checksum, 'executable_prefix_bytes': size - footer,
        'executable_prefix_sha256': identity.sha(compiled[:-footer]),
        'compiled_metadata': '0x' + compiled[-footer:].hex(), 'observed_metadata': '0x' + observed[-footer:].hex(),
        'full_runtime_recompiled': False, 'metadata_hash_equal': False, 'executable_prefix_equal': True,
        'runtime_from_complete_historical_capture': True, 'historical_state_authenticated': False,
        'selectors': c['evm']['methodIdentifiers']}
    if name == 'usdc-implementation':
        layout = c['storageLayout']
        expected = [('paused', '1', 20, 't_bool'), ('balanceAndBlacklistStates', '9', 0, 't_mapping(t_address,t_uint256)'),
            ('allowed', '10', 0, 't_mapping(t_address,t_mapping(t_address,t_uint256))')]
        for label, slot, offset, kind in expected:
            fields = [s for s in layout['storage'] if s['label'] == label]
            identity.check(len(fields) == 1 and (fields[0]['slot'], fields[0]['offset'], fields[0]['type']) ==
                (slot, offset, kind), 'USDC executed storage layout')
        result['storage_layout'] = layout
        result['linked_signature_library_executed'] = False
    else:
        declarations = []
        def visit(node):
            if isinstance(node, dict):
                if node.get('nodeType') == 'VariableDeclaration' and node.get('name') in ('IMPLEMENTATION_SLOT', 'ADMIN_SLOT'):
                    declarations.append((node['name'], node.get('constant'), node['value'].get('value')))
                for v in node.values(): visit(v)
            elif isinstance(node, list):
                for v in node: visit(v)
        visit(output['sources'][file]['ast'])
        identity.check(sorted(declarations) == sorted([
            ('IMPLEMENTATION_SLOT', True, capture.IMPLEMENTATION_SLOT), ('ADMIN_SLOT', True, capture.ADMIN_SLOT)]), 'USDC proxy slot constants')
        result.update(implementation_slot=capture.IMPLEMENTATION_SLOT, admin_slot=capture.ADMIN_SLOT,
            observed_admin_slot_word=history[0]['admin_slot_word'])
    return result


def harness_input():
    value, harness, segments = underlying.harness_input()
    original = value['sources'][underlying.transfer.SOURCE_PATH]['content']
    a = original.index('    // Transfers the debt asset being repaid to the aToken')
    b = original.index('\n  }', a)
    payment = original[a:b]
    identity.check('safeTransferFrom(' in payment and 'emit IPool.LiquidationCall(' in payment, 'original payment/event')
    harness = harness.replace(underlying.CONTRACT, CONTRACT)
    imports = []
    # Import paths are copied from the original LiquidationLogic source, not guessed.
    for name in ['IERC20', 'GPv2SafeERC20', 'IPool']:
        path = re.search(r"import \{" + name + r"\} from '([^']+)';", original).group(1)
        if path.startswith('.'):
            resolved = normpath(dirname(underlying.transfer.SOURCE_PATH) + '/' + path)
        else:
            matches = [k for k in value['sources'] if k.endswith('/' + path)]
            identity.check(len(matches) == 1, 'unique original library import')
            resolved = matches[0]
        identity.check(resolved in value['sources'], 'original import resolution')
        imports.append('import {' + name + '} from "' + resolved + '";')
    harness = harness.replace('interface UnderlyingView', '\n'.join(imports) + '\ninterface UnderlyingView')
    harness = harness.replace('  using TokenMath', '  using GPv2SafeERC20 for IERC20;\n  using TokenMath')
    harness = harness.replace('    vars.actualCollateralToLiquidate = input.amount;',
        '    vars.actualCollateralToLiquidate = input.amount;\n    vars.actualDebtToLiquidate = input.repayment;\n' +
        '    vars.debtReserveCache.aTokenAddress = 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c;')
    harness = harness.replace('    IAToken token =',
        '    // Synthetic composition omits initial validation and the multi-reserve _burnBadDebt branch.\n' + payment + '\n\n    IAToken token =')
    harness = harness.replace('uint256[24]', 'uint256[27]')
    harness = harness.replace('UnderlyingView(params.collateralAsset).balanceOf(params.liquidator)];',
        'UnderlyingView(params.collateralAsset).balanceOf(params.liquidator),\n' +
        '      IERC20(params.debtAsset).balanceOf(params.liquidator),\n' +
        '      IERC20(params.debtAsset).balanceOf(vars.debtReserveCache.aTokenAddress),\n' +
        '      IERC20(params.debtAsset).allowance(params.liquidator, address(this))];')
    segments['unchanged_payment_and_liquidation_event'] = identity.sha(payment.encode())
    value['sources'].pop(underlying.NAME)
    value['sources'][NAME] = {'content': harness}
    value['settings']['outputSelection'] = {NAME: {CONTRACT: ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout']}}
    return value, harness, segments


def fixture(value, raw, usdc_raw):
    expected, harness, segments = harness_input()
    identity.check(value == expected, 'payment harness input identity')
    out = json.loads(raw)
    identity.check(not any(e.get('severity') == 'error' for e in out.get('errors', [])), 'payment compiler errors')
    c = out['contracts'][NAME][CONTRACT]
    code = c['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'payment harness references')
    ud = underlying.DIRECTORY / 'compiler'
    result = underlying.fixture(identity.read_json(ud / 'harness-input.json.gz'),
        gzip.decompress((ud / 'harness-output.json.gz').read_bytes()), gzip.decompress((ud / 'weth-output.json.gz').read_bytes()))
    result['contracts'].pop(underlying.CONTRACT)
    result['contracts'][CONTRACT] = {'runtime_code': '0x' + code['object'],
        'runtime_sha256': identity.sha(bytes.fromhex(code['object'])), 'storage_layout': c['storageLayout'],
        'selectors': c['evm']['methodIdentifiers']}
    history = capture.replay()
    for name in PROFILES:
        source, expected = usdc_input(name)
        identity.check(expected == identity.read_json(DIRECTORY / 'compiler' / (name + '-input.json.gz')), 'USDC input identity')
        result['contracts'][name] = audit_usdc(name, source, json.loads(usdc_raw[name]), history)
    result.update(schema='nqc-miner-aave-payment-execution-fixture-v1',
        compiler_input_sha256=identity.sha(identity.encoded(value)), compiler_output_sha256=identity.sha(raw),
        harness_source_sha256=identity.sha(harness.encode()), extracted_segments=segments,
        previous_underlying_fixture_sha256=identity.sha((identity.MODULE / 'fixtures/aave_underlying_execution.json').read_bytes()),
        usdc_compiler_output_sha256={n: identity.sha(r) for n, r in usdc_raw.items()},
        debt_payment_executed=True, liquidation_event_executed=True, multi_reserve_bad_debt_executed=False,
        aave_token_proxy_runtime_match_verified=True, proxy_code_runtime_match_verified=False,
        usdc_full_source_runtime_match=False, historical_state_authenticated=False, activation_allowed=False)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler-directory', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    raws = {}
    for name, (_, version, _, _, _) in PROFILES.items():
        _, value = usdc_input(name)
        raw, err = compile_usdc(args.compiler_directory / ('solc-' + version.split('+')[0]), name, value)
        raws[name] = raw
        for suffix, data in [('input', identity.encoded(value)), ('output', raw)]:
            (args.output / (name + '-' + suffix + '.json.gz')).write_bytes(gzip.compress(data, mtime=0))
        (args.output / (name + '.stderr')).write_bytes(err)
    value, harness, _ = harness_input()
    raw, err = identity.compile_source(args.compiler_directory / 'solc-0.8.27', value)
    for suffix, data in [('input', identity.encoded(value)), ('output', raw)]:
        (args.output / ('harness-' + suffix + '.json.gz')).write_bytes(gzip.compress(data, mtime=0))
    (args.output / 'harness.stderr').write_bytes(err)
    result = fixture(value, raw, raws)
    (identity.MODULE / NAME).write_text(harness)
    (identity.MODULE / 'fixtures/aave_payment_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'harness_bytes': len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'USDC_full_source_runtime_match': False, 'USDC_executable_prefix_equal': True}))


if __name__ == '__main__':
    main()
