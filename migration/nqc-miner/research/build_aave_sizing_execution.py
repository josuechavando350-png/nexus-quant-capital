#!/usr/bin/env python3
"""Connect original amount/dust arithmetic to updated reserves and both payment paths.

No eMode, oracle authentication or aggregate account calculation is claimed.
All recovered sources remain unchanged; only this synthetic wrapper is generated.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import build_aave_prelude_execution as prelude
import build_aave_amount_harness as amount

identity = prelude.identity
DIRECTORY = identity.MODULE / 'evidence/aave-sizing-execution-20261023'
NAME = 'fixtures/AaveSizingExecutionHarness.sol'
CONTRACT = 'AaveSizingExecutionHarness'
SIGNATURE = 'calculate((uint256,uint128,uint128,uint16,uint256,address,address,uint256,uint256,uint256,uint256,uint16,uint128,uint128,bool,' + prelude.START + ',' + prelude.START + ',uint256))'


def harness_input():
    value, harness, segments = prelude.harness_input()
    original = value['sources'][amount.SOURCE_PATH]['content']
    identity.check(identity.sha(original.encode()) == amount.SOURCE_SHA, 'sizing original identity')
    def replace(old, new):
        nonlocal harness
        identity.check(harness.count(old) == 1, 'unique sizing edit: ' + old[:70])
        harness = harness.replace(old, new)
    replace(prelude.CONTRACT, CONTRACT)
    replace('uint256 repayment;', 'uint256 debtToCover;')
    replace('address aToken; address liquidator; uint256 amount; uint256 fee;\n    uint256 price; uint256 unit; uint256 totalBase;',
        'address aToken; address liquidator; uint256 price; uint256 debtPrice;\n    uint256 totalBase; uint256 totalDebtBase;')
    for line in ['vars.actualCollateralToLiquidate = input.amount;',
                 'vars.actualDebtToLiquidate = input.repayment;',
                 'vars.liquidationProtocolFeeAmount = input.fee;',
                 'vars.collateralAssetUnit = input.unit;']:
        replace('    ' + line + '\n', '')
    replace('    vars.collateralAssetPrice = input.price;', '''    params.debtToCover = input.debtToCover;
    vars.totalDebtInBaseCurrency = input.totalDebtBase;
    vars.debtAssetPrice = input.debtPrice;
    vars.collateralAssetPrice = input.price;''')
    imports = '\n'.join('import {' + n + '} from "' + identity.PREFIX + p + '";' for n, p in [
        ('PercentageMath', 'protocol/libraries/math/PercentageMath.sol'),
        ('MathUtils', 'protocol/libraries/math/MathUtils.sol'),
        ('ReserveConfiguration', 'protocol/libraries/configuration/ReserveConfiguration.sol'),
        ('Errors', 'protocol/libraries/helpers/Errors.sol')])
    replace('contract ' + CONTRACT + ' {', imports + '\ncontract ' + CONTRACT + ' {\n  using PercentageMath for uint256;\n  using ReserveConfiguration for DataTypes.ReserveConfigurationMap;')
    constants = re.findall(r'^  uint256 (?:internal|public) constant [^;]+;', original, re.M)
    identity.check(len(constants) == 4, 'sizing constants')
    replace('  struct Start {', '\n'.join(constants) + '\n  struct Start {')
    begin = original.index('    vars.collateralAssetUnit = 10 **')
    arithmetic = original[begin:original.index('    // Determine whether', begin)]
    bonus = '      vars.liquidationBonus = vars\n        .collateralReserveCache\n        .reserveConfiguration\n        .getLiquidationBonus();'
    identity.check(original.count(bonus) == 1, 'reserve bonus selection')
    replace('    bool hasNoCollateralLeft;', '''    // This wrapper models borrowerEModeCategory == 0 only. Prices and totals are supplied.
''' + bonus + '\n' + arithmetic + '''    uint256 computedFee = vars.liquidationProtocolFeeAmount;
    bool hasNoCollateralLeft;''')
    replace('// Aggregate health/amount calculation and multi-reserve _burnBadDebt remain omitted.',
        '// Aggregate health/eMode/oracle lookup and multi-reserve _burnBadDebt remain omitted.')
    replace('uint256[37]', 'uint256[43]')
    replace('vars.collateralReserveCache.currScaledVariableDebt];', '''vars.collateralReserveCache.currScaledVariableDebt,
      maxLiquidatableDebt, vars.actualDebtToLiquidate, vars.actualCollateralToLiquidate,
      computedFee, vars.borrowerReserveDebtInBaseCurrency, vars.borrowerReserveCollateralInBaseCurrency];''')
    old_harness, _ = amount.extracted_harness({'sources': value['sources']})
    helper = old_harness[old_harness.index('  function _calculateAvailableCollateralToLiquidate('):-2]
    harness = harness[:-2] + helper + '}\n'
    segments['unchanged_units_amounts_and_dust'] = identity.sha(arithmetic.encode())
    segments['unchanged_default_reserve_bonus'] = identity.sha(bonus.encode())
    segments['amount_constants'] = [identity.sha(c.encode()) for c in constants]
    value['sources'].pop(prelude.NAME)
    value['sources'][NAME] = {'content': harness}
    value['settings']['outputSelection'] = {NAME: {CONTRACT: ['evm.deployedBytecode', 'evm.methodIdentifiers', 'storageLayout']}}
    return value, harness, segments


def fixture(value, raw):
    expected, harness, segments = harness_input()
    identity.check(value == expected, 'sizing input identity')
    out = json.loads(raw)
    identity.check(not any(e.get('severity') == 'error' for e in out.get('errors', [])), 'sizing compiler errors')
    c = out['contracts'][NAME][CONTRACT]; code = c['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'sizing references')
    p = prelude.DIRECTORY / 'compiler'
    result = prelude.fixture(identity.read_json(p / 'input.json.gz'), gzip.decompress((p / 'output.json.gz').read_bytes()))
    result['contracts'].pop(prelude.CONTRACT)
    result['contracts'][CONTRACT] = {'runtime_code': '0x' + code['object'],
        'runtime_sha256': identity.sha(bytes.fromhex(code['object'])),
        'selectors': c['evm']['methodIdentifiers'], 'storage_layout': c['storageLayout']}
    result.update(schema='nqc-miner-aave-sizing-execution-fixture-v1',
        compiler_input_sha256=identity.sha(identity.encoded(value)), compiler_output_sha256=identity.sha(raw),
        harness_source_sha256=identity.sha(harness.encode()), extracted_segments=segments,
        previous_prelude_fixture_sha256=identity.sha((identity.MODULE / 'fixtures/aave_prelude_execution.json').read_bytes()),
        liquidation_amounts_supplied=False, liquidation_amount_calculation_executed=True,
        close_factor_and_dust_executed=True, bonus_derived_from_reserve_configuration=True,
        borrower_emode_category=0, emode_selection_executed=False, oracle_prices_supplied=True,
        aggregate_debt_and_collateral_supplied=True)
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
    (identity.MODULE / 'fixtures/aave_sizing_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes': len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'liquidation_amounts_supplied': False, 'historical_state_authenticated': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); build(args.compiler, args.output)
