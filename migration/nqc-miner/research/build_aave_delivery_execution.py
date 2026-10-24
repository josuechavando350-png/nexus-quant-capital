#!/usr/bin/env python3
"""Execute both original collateral-delivery branches followed by observed USDC payment."""
import argparse
import gzip
import json
from pathlib import Path
import build_aave_payment_execution as payment

identity = payment.identity
DIRECTORY = identity.MODULE / 'evidence/aave-delivery-execution-20261023'
NAME = 'fixtures/AaveDeliveryExecutionHarness.sol'
CONTRACT = 'AaveDeliveryExecutionHarness'
SIGNATURE = payment.SIGNATURE[:-2] + ',bool))'


def harness_input():
    value, harness, segments = payment.harness_input()
    original = value['sources'][payment.underlying.transfer.SOURCE_PATH]['content']
    start = '    if (params.receiveAToken) {'
    identity.check(original.count(start) == 1, 'unique original delivery branch')
    a = original.index(start)
    branch = original[a:original.index('    // Transfer fee to treasury', a)]
    identity.check('if (params.collateralAsset == params.debtAsset)' in branch, 'original cache branch retained')
    def replace(old, new):
        nonlocal harness
        identity.check(harness.count(old) == 1, 'unique delivery wrapper edit: ' + old[:60])
        harness = harness.replace(old, new)
    replace(payment.CONTRACT, CONTRACT)
    replace('uint256 collateralFactor; uint128 collateralDeficit;',
        'uint256 collateralFactor; uint128 collateralDeficit; bool receiveAToken;')
    replace('    params.liquidator = input.liquidator;',
        '    params.liquidator = input.liquidator;\n    params.receiveAToken = input.receiveAToken;')
    replace('    // Original full collateral helper: rate update, aToken burn and actual WETH transfer.\n'
        '    LiquidationLogic._burnCollateralATokens(collateralReserve, params, vars);\n', branch)
    # Preserve the original if/else bytes, forwarding its internal call unchanged.
    helper = '''
  function _burnCollateralATokens(
    DataTypes.ReserveData storage reserve,
    DataTypes.ExecuteLiquidationCallParams memory params,
    LiquidationLogic.LiquidationCallLocalVars memory vars
  ) internal {
    LiquidationLogic._burnCollateralATokens(reserve, params, vars);
  }
'''
    identity.check(harness.endswith('}\n'), 'wrapper contract boundary')
    harness = harness[:-2] + helper + '}\n'
    replace('uint256[27]', 'uint256[25]')
    # Diagnostic WETH reads must not introduce a WETH dependency on the aToken path.
    replace('      UnderlyingView(params.collateralAsset).balanceOf(input.aToken),\n'
        '      UnderlyingView(params.collateralAsset).balanceOf(params.liquidator),\n', '')
    replace('interface UnderlyingView { function balanceOf(address) external view returns (uint256); }\n', '')
    segments['unchanged_collateral_delivery_branch'] = identity.sha(branch.encode())
    value['sources'].pop(payment.NAME)
    value['sources'][NAME] = {'content': harness}
    value['settings']['outputSelection'] = {NAME: {CONTRACT:
        ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout']}}
    return value, harness, segments


def fixture(value, raw):
    expected, harness, segments = harness_input()
    identity.check(value == expected, 'delivery compiler input identity')
    out = json.loads(raw)
    identity.check(not any(e.get('severity') == 'error' for e in out.get('errors', [])), 'delivery compile errors')
    c = out['contracts'][NAME][CONTRACT]
    code = c['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'delivery deployment references')
    p = payment.DIRECTORY / 'compiler'
    result = payment.fixture(identity.read_json(p / 'harness-input.json.gz'),
        gzip.decompress((p / 'harness-output.json.gz').read_bytes()),
        {n: gzip.decompress((p / (n + '-output.json.gz')).read_bytes()) for n in payment.PROFILES})
    result['contracts'].pop(payment.CONTRACT)
    result['contracts'][CONTRACT] = {'runtime_code': '0x' + code['object'],
        'runtime_sha256': identity.sha(bytes.fromhex(code['object'])),
        'storage_layout': c['storageLayout'], 'selectors': c['evm']['methodIdentifiers']}
    result.update(schema='nqc-miner-aave-delivery-execution-fixture-v1',
        compiler_input_sha256=identity.sha(identity.encoded(value)),
        compiler_output_sha256=identity.sha(raw), harness_source_sha256=identity.sha(harness.encode()),
        extracted_segments=segments,
        previous_payment_fixture_sha256=identity.sha((identity.MODULE / 'fixtures/aave_payment_execution.json').read_bytes()),
        receive_atoken_only=False, receive_underlying_only=False,
        both_collateral_delivery_modes_executed=True, collateral_delivery_mode_supplied=True,
        same_asset_cache_branch_executed=False, weth_balance_diagnostic_reads=False)
    return result


def build(compiler, output):
    value, harness, _ = harness_input()
    raw, err = identity.compile_source(compiler, value)
    result = fixture(value, raw)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('input.json.gz', identity.encoded(value)), ('output.json.gz', raw)]:
        (output / name).write_bytes(gzip.compress(data, mtime=0))
    (output / 'compiler.stderr').write_bytes(err)
    (identity.MODULE / NAME).write_text(harness)
    (identity.MODULE / 'fixtures/aave_delivery_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes': len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'same_asset_cache_branch_executed': False, 'historical_state_authenticated': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    build(args.compiler, args.output)
