#!/usr/bin/env python3
"""Compose original reserve updates, derived balances and initial validation with payment."""
import argparse
import gzip
import json
from pathlib import Path
import build_aave_delivery_execution as delivery

identity = delivery.identity
DIRECTORY = identity.MODULE / 'evidence/aave-prelude-execution-20261023'
NAME = 'fixtures/AavePreludeExecutionHarness.sol'
CONTRACT = 'AavePreludeExecutionHarness'
START = '(uint128,uint128,uint128,uint128,uint128,uint40,uint256,uint40)'
SIGNATURE = 'calculate((uint256,uint128,uint128,uint16,uint256,address,address,uint256,uint256,uint256,uint256,uint256,uint16,uint128,uint128,bool,' + START + ',' + START + ',uint256))'
COLLATERAL_DEBT = '0xea51d7853eefb32b6ee06b1c12e6dcca88be0ffe'


def harness_input():
    value, harness, segments = delivery.harness_input()
    original = value['sources'][delivery.payment.underlying.transfer.SOURCE_PATH]['content']
    a = original.index('    vars.debtReserveCache = debtReserve.cache();')
    cache = original[a:original.index('\n    (\n      vars.totalCollateralInBaseCurrency', a)]
    a = original.index('    vars.borrowerScaledCollateralBalance = IAToken(')
    validation = original[a:original.index('\n    if (\n      params.borrowerEModeCategory', a)]
    def replace(old, new):
        nonlocal harness
        identity.check(harness.count(old) == 1, 'unique prelude wrapper edit: ' + old[:60])
        harness = harness.replace(old, new)
    replace(delivery.CONTRACT, CONTRACT)
    imports = '\n'.join('import {' + n + '} from "' + identity.PREFIX +
        'protocol/libraries/logic/' + n + '.sol";' for n in ['ReserveLogic', 'ValidationLogic'])
    replace('contract ' + CONTRACT + ' {', imports + '\ncontract ' + CONTRACT + ' {\n  using ReserveLogic for DataTypes.ReserveData;')
    a = harness.index('  struct Input {'); b = harness.index('  function calculate(', a)
    harness = harness[:a] + '''  struct Start {
    uint128 liquidityIndex; uint128 borrowIndex; uint128 liquidityRate; uint128 borrowRate;
    uint128 accrued; uint40 lastUpdate; uint256 configuration; uint40 grace;
  }
  struct Input {
    uint256 repayment; uint128 deficit; uint128 virtualBalance; uint16 debtId; uint256 config;
    address aToken; address liquidator; uint256 amount; uint256 fee;
    uint256 price; uint256 unit; uint256 totalBase; uint16 collateralId;
    uint128 collateralVirtual; uint128 collateralDeficit; bool receiveAToken;
    Start debtStart; Start collateralStart; uint256 health;
  }
''' + harness[b:]
    for line in [
        'vars.collateralReserveCache.aTokenAddress = input.aToken;',
        'vars.collateralReserveCache.nextLiquidityIndex = input.index;',
        'vars.borrowerScaledCollateralBalance = IAToken(input.aToken).scaledBalanceOf(params.borrower);',
        'vars.debtReserveCache.aTokenAddress = 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c;',
        'vars.collateralReserveCache.nextScaledVariableDebt = input.collateralScaledDebt;',
        'vars.collateralReserveCache.nextVariableBorrowIndex = input.collateralBorrowIndex;',
        'vars.collateralReserveCache.reserveFactor = input.collateralFactor;',
        'vars.debtReserveCache.nextScaledVariableDebt = input.cached;',
        'vars.debtReserveCache.nextVariableBorrowIndex = input.debtIndex;',
        'vars.debtReserveCache.nextLiquidityIndex = 1e27;',
        'vars.debtReserveCache.reserveFactor = input.factor;',
        'vars.debtReserveCache.variableDebtTokenAddress = 0x72E95b8931767C79bA4EeE721354d6E99a61D004;',
    ]:
        replace('    ' + line + '\n', '')
    prelude = '''    _initialize(debtReserve, input.debtStart,
      0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c, 0x72E95b8931767C79bA4EeE721354d6E99a61D004);
    _initialize(collateralReserve, input.collateralStart,
      input.aToken, 0xeA51d7853EEFb32b6ee06b1C12E6dcCA88Be0fFE);
''' + cache + '''
    // Aggregate GenericLogic health calculation remains omitted; health is explicitly supplied.
    vars.healthFactor = input.health;
''' + validation + '\n'
    replace('    bool hasNoCollateralLeft;', prelude + '    bool hasNoCollateralLeft;')
    replace('params.borrower, params.debtAsset, input.debt, input.repayment,',
        'params.borrower, params.debtAsset, vars.borrowerReserveDebt, vars.actualDebtToLiquidate,')
    replace('input.debt - input.repayment', 'vars.borrowerReserveDebt - vars.actualDebtToLiquidate')
    replace('// Synthetic composition omits initial validation and the multi-reserve _burnBadDebt branch.',
        '// Aggregate health/amount calculation and multi-reserve _burnBadDebt remain omitted.')
    replace('uint256[25]', 'uint256[37]')
    replace('IERC20(params.debtAsset).allowance(params.liquidator, address(this))];',
        '''IERC20(params.debtAsset).allowance(params.liquidator, address(this)),
      uint256(debtReserve.liquidityIndex), uint256(debtReserve.variableBorrowIndex),
      uint256(debtReserve.accruedToTreasury), uint256(debtReserve.lastUpdateTimestamp),
      uint256(collateralReserve.liquidityIndex), uint256(collateralReserve.variableBorrowIndex),
      uint256(collateralReserve.accruedToTreasury), uint256(collateralReserve.lastUpdateTimestamp),
      vars.borrowerReserveDebt, vars.borrowerCollateralBalance,
      vars.debtReserveCache.currScaledVariableDebt, vars.collateralReserveCache.currScaledVariableDebt];''')
    helper = '''
  // Synthetic initial reserve storage; original cache reads the observed token implementations.
  function _initialize(DataTypes.ReserveData storage reserve, Start memory start,
    address aToken, address vToken) internal {
    reserve.liquidityIndex = start.liquidityIndex;
    reserve.variableBorrowIndex = start.borrowIndex;
    reserve.currentLiquidityRate = start.liquidityRate;
    reserve.currentVariableBorrowRate = start.borrowRate;
    reserve.accruedToTreasury = start.accrued;
    reserve.lastUpdateTimestamp = start.lastUpdate;
    reserve.configuration.data = start.configuration;
    reserve.liquidationGracePeriodUntil = start.grace;
    reserve.aTokenAddress = aToken;
    reserve.variableDebtTokenAddress = vToken;
  }
'''
    identity.check(harness.endswith('}\n'), 'prelude contract boundary')
    harness = harness[:-2] + helper + '}\n'
    segments['unchanged_cache_and_update_order'] = identity.sha(cache.encode())
    segments['unchanged_derived_balances_and_validation'] = identity.sha(validation.encode())
    value['sources'].pop(delivery.NAME)
    value['sources'][NAME] = {'content': harness}
    value['settings']['outputSelection'] = {NAME: {CONTRACT: ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout']}}
    return value, harness, segments


def fixture(value, raw):
    expected, harness, segments = harness_input()
    identity.check(value == expected, 'prelude input identity')
    out = json.loads(raw)
    identity.check(not any(e.get('severity') == 'error' for e in out.get('errors', [])), 'prelude compiler errors')
    c = out['contracts'][NAME][CONTRACT]; code = c['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'prelude references')
    p = delivery.DIRECTORY / 'compiler'
    result = delivery.fixture(identity.read_json(p / 'input.json.gz'), gzip.decompress((p / 'output.json.gz').read_bytes()))
    samples = [p for p in result['proxy_samples'] if p['proxy'] == COLLATERAL_DEBT]
    identity.check(len(samples) == 2 and all(p['kind'] == 'v_token' and p['proxy_contract'] == 'AuditedDebtProxy'
        and p['implementation'] == '0xb27c52c7f84819e3157993489741cb60786ae330' for p in samples), 'observed collateral debt routing')
    result['contracts'].pop(delivery.CONTRACT)
    result['contracts'][CONTRACT] = {'runtime_code': '0x' + code['object'],
        'runtime_sha256': identity.sha(bytes.fromhex(code['object'])),
        'selectors': c['evm']['methodIdentifiers'], 'storage_layout': c['storageLayout']}
    result.update(schema='nqc-miner-aave-prelude-execution-fixture-v1',
        compiler_input_sha256=identity.sha(identity.encoded(value)), compiler_output_sha256=identity.sha(raw),
        harness_source_sha256=identity.sha(harness.encode()), extracted_segments=segments,
        previous_delivery_fixture_sha256=identity.sha((identity.MODULE / 'fixtures/aave_delivery_execution.json').read_bytes()),
        initial_reserve_updates_executed=True, initial_health_validation_executed=True,
        selected_debt_derived_from_scaled_balance=True, collateral_balance_derived_from_scaled_balance=True,
        scaled_totals_read_from_observed_token_code=True, health_factor_supplied=True,
        aggregate_account_data_calculation_executed=False, collateral_variable_debt_token=COLLATERAL_DEBT)
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
    (identity.MODULE / 'fixtures/aave_prelude_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes': len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'health_factor_supplied': True, 'historical_state_authenticated': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); build(args.compiler, args.output)
