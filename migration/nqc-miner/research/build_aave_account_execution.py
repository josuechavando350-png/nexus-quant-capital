#!/usr/bin/env python3
"""Original GenericLogic health/eMode and oracle calls inside synthetic liquidation.

The oracle and all state are synthetic. No authenticated price or Pool claim.
"""
import argparse
import gzip
import json
from pathlib import Path
import build_aave_sizing_execution as sizing

identity = sizing.identity
DIRECTORY = identity.MODULE / 'evidence/aave-account-execution-20261023'
NAME = 'fixtures/AaveAccountExecutionHarness.sol'
CONTRACT = 'AaveAccountExecutionHarness'
ORACLE_CONTRACT = 'SyntheticAccountOracle'
ORACLE = '0x5555555555555555555555555555555555555555'
MODE = '(uint16,uint16,uint16,uint128,bool,uint128)'
SIGNATURE = 'calculate((uint256,uint128,uint128,uint16,uint256,address,address,uint16,uint128,uint128,bool,' + sizing.prelude.START + ',' + sizing.prelude.START + ',uint8,' + MODE + '))'


def harness_input():
    value, harness, segments = sizing.harness_input()
    original = value['sources'][sizing.amount.SOURCE_PATH]['content']
    def replace(old, new):
        nonlocal harness
        identity.check(harness.count(old) == 1, 'unique account wrapper edit: ' + old[:65])
        harness = harness.replace(old, new)
    replace(sizing.CONTRACT, CONTRACT)
    imports = '\n'.join('import {' + n + '} from "' + identity.PREFIX + p + '";' for n, p in [
        ('GenericLogic', 'protocol/libraries/logic/GenericLogic.sol'),
        ('EModeConfiguration', 'protocol/libraries/configuration/EModeConfiguration.sol'),
        ('IPriceOracleGetter', 'interfaces/IPriceOracleGetter.sol')])
    replace('contract ' + CONTRACT + ' {', imports + '\ncontract ' + CONTRACT + ' {')
    replace('  struct Start {', '''  // Copies provide the storage mappings required by original GenericLogic.
  // This is a synthetic Pool layout, not the deployed Pool storage/entrypoint.
  mapping(address => DataTypes.ReserveData) private reservesData;
  mapping(uint256 => address) private reservesList;
  mapping(uint8 => DataTypes.EModeCategory) private eModeCategories;
  struct Mode {
    uint16 ltv; uint16 threshold; uint16 bonus; uint128 collateralBitmap;
    bool isolated; uint128 zeroBitmap;
  }
  struct Start {''')
    replace('address aToken; address liquidator; uint256 price; uint256 debtPrice;\n    uint256 totalBase; uint256 totalDebtBase; uint16 collateralId;',
        'address aToken; address liquidator; uint16 collateralId;')
    replace('Start debtStart; Start collateralStart; uint256 health;',
        'Start debtStart; Start collateralStart; uint8 category; Mode mode;')
    for line in ['vars.totalDebtInBaseCurrency = input.totalDebtBase;', 'vars.debtAssetPrice = input.debtPrice;',
                 'vars.collateralAssetPrice = input.price;', 'vars.totalCollateralInBaseCurrency = input.totalBase;']:
        replace('    ' + line + '\n', '')
    replace('    params.debtToCover = input.debtToCover;', '''    params.debtToCover = input.debtToCover;
    params.priceOracle = 0x5555555555555555555555555555555555555555;
    params.borrowerEModeCategory = input.category;''')
    a = original.index('    (\n      vars.totalCollateralInBaseCurrency')
    account = original[a:original.index('    vars.borrowerScaledCollateralBalance', a)]
    setup = '''    reservesData[params.debtAsset] = debtReserve;
    reservesData[params.collateralAsset] = collateralReserve;
    reservesList[debtReserve.id] = params.debtAsset;
    reservesList[collateralReserve.id] = params.collateralAsset;
    DataTypes.EModeCategory storage mode = eModeCategories[input.category];
    mode.ltv = input.mode.ltv;
    mode.liquidationThreshold = input.mode.threshold;
    mode.liquidationBonus = input.mode.bonus;
    mode.collateralBitmap = input.mode.collateralBitmap;
    mode.isolated = input.mode.isolated;
    mode.ltvzeroBitmap = input.mode.zeroBitmap;
'''
    replace('    // Aggregate GenericLogic health calculation remains omitted; health is explicitly supplied.\n    vars.healthFactor = input.health;\n', setup + account)
    a = original.index('    if (\n      params.borrowerEModeCategory')
    prices = original[a:original.index('    vars.collateralAssetUnit', a)]
    old = '''    // This wrapper models borrowerEModeCategory == 0 only. Prices and totals are supplied.
      vars.liquidationBonus = vars
        .collateralReserveCache
        .reserveConfiguration
        .getLiquidationBonus();
'''
    replace(old, prices)
    replace('// Aggregate health/eMode/oracle lookup and multi-reserve _burnBadDebt remain omitted.',
        '// Multi-reserve _burnBadDebt and actual Pool entry remain omitted; oracle/state are synthetic.')
    replace('uint256[43]', 'uint256[47]')
    replace('computedFee, vars.borrowerReserveDebtInBaseCurrency, vars.borrowerReserveCollateralInBaseCurrency];',
        '''computedFee, vars.borrowerReserveDebtInBaseCurrency, vars.borrowerReserveCollateralInBaseCurrency,
      vars.healthFactor, vars.totalCollateralInBaseCurrency, vars.totalDebtInBaseCurrency, vars.liquidationBonus];''')
    harness += '''
// Explicit test double: supplied prices, not the deployed Aave oracle or Chainlink.
contract SyntheticAccountOracle {
  mapping(address => uint256) private prices;
  bool private blocked;
  function getAssetPrice(address asset) external view returns (uint256) {
    require(!blocked, "synthetic oracle blocked");
    return prices[asset];
  }
}
'''
    segments['unchanged_account_data_call'] = identity.sha(account.encode())
    segments['unchanged_emode_selection_and_price_calls'] = identity.sha(prices.encode())
    segments['generic_logic_source'] = identity.sha(value['sources'][identity.PREFIX + 'protocol/libraries/logic/GenericLogic.sol']['content'].encode())
    value['sources'].pop(sizing.NAME)
    value['sources'][NAME] = {'content': harness}
    value['settings']['outputSelection'] = {NAME: {n: ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout'] for n in [CONTRACT, ORACLE_CONTRACT]}}
    return value, harness, segments


def fixture(value, raw):
    expected, harness, segments = harness_input()
    identity.check(value == expected, 'account input identity')
    out = json.loads(raw)
    identity.check(not any(e.get('severity') == 'error' for e in out.get('errors', [])), 'account compiler errors')
    p = sizing.DIRECTORY / 'compiler'
    result = sizing.fixture(identity.read_json(p / 'input.json.gz'), gzip.decompress((p / 'output.json.gz').read_bytes()))
    result['contracts'].pop(sizing.CONTRACT)
    for name in [CONTRACT, ORACLE_CONTRACT]:
        c = out['contracts'][NAME][name]; code = c['evm']['deployedBytecode']
        identity.check(not code['linkReferences'] and not code['immutableReferences'], 'account references')
        result['contracts'][name] = {'runtime_code': '0x' + code['object'],
            'runtime_sha256': identity.sha(bytes.fromhex(code['object'])),
            'selectors': c['evm']['methodIdentifiers'], 'storage_layout': c['storageLayout']}
    result.update(schema='nqc-miner-aave-account-execution-fixture-v1',
        compiler_input_sha256=identity.sha(identity.encoded(value)), compiler_output_sha256=identity.sha(raw),
        harness_source_sha256=identity.sha(harness.encode()), extracted_segments=segments,
        previous_sizing_fixture_sha256=identity.sha((identity.MODULE / 'fixtures/aave_sizing_execution.json').read_bytes()),
        health_factor_supplied=False, aggregate_debt_and_collateral_supplied=False,
        aggregate_account_data_calculation_executed=True, emode_selection_executed=True,
        borrower_emode_category='supplied', bonus_derived_from_reserve_configuration=False,
        bonus_derived_from_reserve_or_emode_configuration=True, oracle_calls_executed=True,
        oracle_prices_supplied=True, oracle_kind='synthetic_test_double', oracle_runtime_authenticated=False,
        oracle_state_authenticated=False, account_reserve_scope='two_distinct_assets_with_explicit_list_gaps')
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
    (identity.MODULE / 'fixtures/aave_account_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes': len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'health_factor_supplied': False, 'oracle_kind': result['oracle_kind']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); build(args.compiler, args.output)
