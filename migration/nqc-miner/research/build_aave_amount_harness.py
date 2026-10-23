#!/usr/bin/env python3
"""Build an extracted synthetic amount kernel; never a full liquidation replay.

The contiguous close-factor/calculation/dust segment and its struct/constants
are copied byte for byte from the pinned source. The internal collateral helper
is invoked from the unchanged original library. No recovered source is edited.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import aave_runtime_identity as identity

NAME = 'fixtures/AaveAmountHarness.sol'
SOURCE_PATH = identity.PREFIX + 'protocol/libraries/logic/LiquidationLogic.sol'
SOURCE_SHA = '385c9761118ac72a443698b7b03749a60b0aa52f7b8d24478a979795afbcf9a0'
SIGNATURE = 'calculate((uint256,uint256,uint256,uint256,uint256,uint256,uint8,uint8,uint16,uint16,uint256))'


def extracted_harness(source):
    original = source['sources'][SOURCE_PATH]['content']
    identity.check(identity.sha(original.encode()) == SOURCE_SHA, 'amount source identity')
    def segment(start, end):
        identity.check(original.count(start) == 1, 'ambiguous segment start')
        begin = original.index(start)
        finish = original.index(end, begin)
        return original[begin:finish]
    structure = segment('  struct LiquidationCallLocalVars {', '\n\n  /**')
    units = segment('    vars.collateralAssetUnit = 10 **', '\n\n    vars.borrowerReserveDebtInBaseCurrency')
    arithmetic = segment('    vars.borrowerReserveDebtInBaseCurrency = MathUtils.mulDivCeil(', '    // Determine whether')
    constants = re.findall(r'^  uint256 (?:internal|public) constant [^;]+;', original, re.M)
    identity.check(len(constants) == 4, 'amount constants')
    prefix = identity.PREFIX
    imports = '\n'.join(f'import {{{symbol}}} from "{prefix}{path}";' for symbol,path in [
        ('LiquidationLogic','protocol/libraries/logic/LiquidationLogic.sol'),
        ('DataTypes','protocol/libraries/types/DataTypes.sol'),
        ('ReserveConfiguration','protocol/libraries/configuration/ReserveConfiguration.sol'),
        ('PercentageMath','protocol/libraries/math/PercentageMath.sol'),
        ('MathUtils','protocol/libraries/math/MathUtils.sol'),
        ('Errors','protocol/libraries/helpers/Errors.sol')])
    harness = '''// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED synthetic excerpt harness. Not the full pool or execution path.
''' + imports + '''
contract AaveAmountHarness {
  using PercentageMath for uint256;
  using ReserveConfiguration for DataTypes.ReserveConfigurationMap;
''' + '\n'.join(constants) + '\n' + structure + '''
  struct Input {
    uint256 collateralBalance; uint256 reserveDebt; uint256 totalDebtBase;
    uint256 healthFactor; uint256 collateralPrice; uint256 debtPrice;
    uint8 collateralDecimals; uint8 debtDecimals;
    uint16 bonus; uint16 fee; uint256 debtToCover;
  }
  function calculate(Input memory input) external pure returns (uint256[6] memory) {
    LiquidationCallLocalVars memory vars;
    DataTypes.ExecuteLiquidationCallParams memory params;
    vars.borrowerCollateralBalance = input.collateralBalance;
    vars.borrowerReserveDebt = input.reserveDebt;
    vars.totalDebtInBaseCurrency = input.totalDebtBase;
    vars.healthFactor = input.healthFactor;
    vars.collateralAssetPrice = input.collateralPrice;
    vars.debtAssetPrice = input.debtPrice;
    vars.liquidationBonus = input.bonus;
    vars.collateralReserveCache.reserveConfiguration.data =
      (uint256(input.collateralDecimals) << 48) | (uint256(input.fee) << 152);
    vars.debtReserveCache.reserveConfiguration.data = uint256(input.debtDecimals) << 48;
    params.debtToCover = input.debtToCover;
''' + units + '\n\n' + arithmetic + '''
    return [maxLiquidatableDebt, vars.actualDebtToLiquidate,
      vars.actualCollateralToLiquidate, vars.liquidationProtocolFeeAmount,
      vars.borrowerReserveDebtInBaseCurrency, vars.borrowerReserveCollateralInBaseCurrency];
  }
  function _calculateAvailableCollateralToLiquidate(
    DataTypes.ReserveConfigurationMap memory config,
    uint256 collateralPrice, uint256 collateralUnit,
    uint256 debtPrice, uint256 debtUnit, uint256 debtToCover,
    uint256 balance, uint256 bonus
  ) internal pure returns (uint256, uint256, uint256) {
    return LiquidationLogic._calculateAvailableCollateralToLiquidate(
      config, collateralPrice, collateralUnit, debtPrice, debtUnit, debtToCover, balance, bonus);
  }
}
'''
    return harness, {'structure': identity.sha(structure.encode()), 'units': identity.sha(units.encode()),
                     'amount_segment': identity.sha(arithmetic.encode()),
                     'constants': [identity.sha(v.encode()) for v in constants]}


def build(compiler, output):
    source = identity.read_json(identity.EVIDENCE / 'source.json.gz')
    identity.verify_provenance(source)
    original = identity.compilation_input(source)
    harness, segments = extracted_harness(source)
    original['sources'][NAME] = {'content': harness}
    original['settings']['outputSelection'] = {NAME: {'AaveAmountHarness': ['evm.deployedBytecode', 'evm.methodIdentifiers']}}
    raw, stderr = identity.compile_source(compiler, original)
    result = json.loads(raw)
    errors = [e for e in result.get('errors', []) if e.get('severity') == 'error']
    identity.check(not errors, str(errors))
    contract = result['contracts'][NAME]['AaveAmountHarness']
    code = contract['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'unexpected deployment references')
    runtime = bytes.fromhex(code['object'])
    fixture = {'schema':'nqc-miner-aave-amount-harness-v1', 'kind':'synthetic_fixture',
        'reference_kind':'byte_exact_extracted_segment_and_imported_internal_helper',
        'compiler_sha256':identity.COMPILER_SHA, 'compiler_version':identity.COMPILER_VERSION,
        'compiler_input_sha256':identity.sha(identity.encoded(original)),
        'compiler_output_sha256':identity.sha(raw), 'harness_source_sha256':identity.sha(harness.encode()),
        'runtime_sha256':identity.sha(runtime), 'runtime_code':'0x'+runtime.hex(),
        'selector':'0x'+contract['evm']['methodIdentifiers'][SIGNATURE],
        'source_path':SOURCE_PATH, 'source_sha256':SOURCE_SHA, 'extracted_segments':segments,
        'original_sources':{p:identity.sha(v['content'].encode()) for p,v in source['sources'].items()},
        'executable_eligibility_verified':False,'activation_allowed':False}
    output.mkdir(parents=True, exist_ok=False)
    (output/'input.json.gz').write_bytes(gzip.compress(identity.encoded(original),mtime=0))
    (output/'output.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    (output/'compiler.stderr').write_bytes(stderr)
    (identity.MODULE/NAME).write_text(harness)
    (identity.MODULE/'fixtures/aave_amount_harness.json').write_bytes(identity.encoded(fixture))
    print(json.dumps({'runtime_bytes':len(runtime),'runtime_sha256':fixture['runtime_sha256']}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    build(args.compiler,args.output)
