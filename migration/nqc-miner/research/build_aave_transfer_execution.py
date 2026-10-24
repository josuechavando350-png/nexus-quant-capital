#!/usr/bin/env python3
"""Compose original receive-aToken/fee excerpts with actual audited dependencies."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import aave_runtime_identity as identity
import build_aave_rewards as rewards
from build_aave_amount_harness import SOURCE_PATH, SOURCE_SHA

NAME = 'fixtures/AaveTransferExecutionHarness.sol'
CONTRACT = 'AaveTransferExecutionHarness'
SIGNATURE = 'calculate((uint256,uint256,uint256,uint256,uint128,uint128,uint16,uint256,uint256,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint16))'
DIRECTORY = identity.MODULE / 'evidence/aave-transfer-execution-20261023'


def extracted_harness(source):
    original = source['sources'][SOURCE_PATH]['content']
    identity.check(identity.sha(original.encode()) == SOURCE_SHA, 'liquidation source identity')
    def segment(start, end):
        identity.check(original.count(start) == 1, 'ambiguous excerpt start')
        a = original.index(start)
        return original[a:original.index(end, a)]
    structure = segment('  struct LiquidationCallLocalVars {', '\n\n  /**')
    consumption = segment('    bool hasNoCollateralLeft;', '    _burnDebtTokens(')
    transfer = segment('      IAToken(vars.collateralReserveCache.aTokenAddress).transferOnLiquidation(\n        params.borrower,', '    } else {')
    fee = segment('    // Transfer fee to treasury', '    // burn bad debt')
    imports = '\n'.join(f'import {{{symbol}}} from "{identity.PREFIX}{path}";' for symbol,path in [
        ('DataTypes','protocol/libraries/types/DataTypes.sol'),
        ('LiquidationLogic','protocol/libraries/logic/LiquidationLogic.sol'),
        ('UserConfiguration','protocol/libraries/configuration/UserConfiguration.sol'),
        ('TokenMath','protocol/libraries/helpers/TokenMath.sol'),
        ('IAToken','interfaces/IAToken.sol'),
        ('IVariableDebtToken','interfaces/IVariableDebtToken.sol')])
    harness = '''// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED: original excerpts and internal debt function; synthetic Pool entrypoint/state.
''' + imports + '''
contract AaveTransferExecutionHarness {
  using TokenMath for uint256;
  using UserConfiguration for DataTypes.UserConfigurationMap;
  DataTypes.ReserveData private debtReserve;
  DataTypes.UserConfigurationMap private borrowerConfig;
  DataTypes.ReserveData private collateralReserve;
''' + structure + '''
  struct Input {
    uint256 debt; uint256 repayment; uint256 debtIndex; uint256 cached;
    uint128 deficit; uint128 virtualBalance; uint16 debtId; uint256 config; uint256 factor;
    address aToken; address liquidator; uint256 index; uint256 amount; uint256 fee;
    uint256 price; uint256 unit; uint256 totalBase; uint16 collateralId;
  }
  function calculate(Input memory input) external returns (uint256[19] memory result) {
    LiquidationCallLocalVars memory vars;
    DataTypes.ExecuteLiquidationCallParams memory params;
    params.borrower = address(0xCAFE);
    params.liquidator = input.liquidator;
    params.collateralAsset = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    params.debtAsset = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    params.interestRateStrategyAddress = 0x9ec6F08190DeA04A54f8Afc53Db96134e5E3FdFB;
    vars.collateralReserveCache.aTokenAddress = input.aToken;
    vars.collateralReserveCache.nextLiquidityIndex = input.index;
    vars.borrowerScaledCollateralBalance = IAToken(input.aToken).scaledBalanceOf(params.borrower);
    vars.actualCollateralToLiquidate = input.amount;
    vars.liquidationProtocolFeeAmount = input.fee;
    vars.collateralAssetPrice = input.price;
    vars.collateralAssetUnit = input.unit;
    vars.totalCollateralInBaseCurrency = input.totalBase;
    debtReserve.deficit = input.deficit;
    debtReserve.virtualUnderlyingBalance = input.virtualBalance;
    debtReserve.id = input.debtId;
    borrowerConfig.data = input.config;
    collateralReserve.id = input.collateralId;
    vars.debtReserveCache.nextScaledVariableDebt = input.cached;
    vars.debtReserveCache.nextVariableBorrowIndex = input.debtIndex;
    vars.debtReserveCache.nextLiquidityIndex = 1e27;
    vars.debtReserveCache.reserveFactor = input.factor;
    vars.debtReserveCache.variableDebtTokenAddress = 0x72E95b8931767C79bA4EeE721354d6E99a61D004;
''' + consumption + '''
    LiquidationLogic._burnDebtTokens(vars.debtReserveCache, debtReserve, borrowerConfig,
      params.borrower, params.debtAsset, input.debt, input.repayment,
      hasNoCollateralLeft, params.interestRateStrategyAddress);
    // Only the original receiveAToken=true branch is exercised here.
''' + transfer + fee + '''
    IAToken token = IAToken(input.aToken);
    IVariableDebtToken debt = IVariableDebtToken(vars.debtReserveCache.variableDebtTokenAddress);
    result = [vars.debtReserveCache.nextScaledVariableDebt, input.debt - input.repayment,
      uint256(debtReserve.deficit), borrowerConfig.data, uint256(debtReserve.virtualUnderlyingBalance),
      uint256(debtReserve.currentLiquidityRate), uint256(debtReserve.currentVariableBorrowRate),
      debt.scaledBalanceOf(params.borrower), debt.getPreviousIndex(params.borrower), debt.scaledTotalSupply(),
      token.scaledBalanceOf(params.borrower), token.scaledBalanceOf(params.liquidator),
      token.scaledBalanceOf(token.RESERVE_TREASURY_ADDRESS()), token.scaledTotalSupply(),
      token.getPreviousIndex(params.borrower), token.getPreviousIndex(params.liquidator),
      token.getPreviousIndex(token.RESERVE_TREASURY_ADDRESS()), vars.liquidationProtocolFeeAmount,
      hasNoCollateralLeft ? 1 : 0];
  }
}
'''
    return harness, {k: identity.sha(v.encode()) for k,v in [('structure',structure),('consumption_and_flag',consumption),('receive_atoken_transfer',transfer),('fee_transfer',fee)]}


def compilation_input():
    source = identity.read_json(identity.EVIDENCE / 'source.json.gz')
    identity.verify_provenance(source)
    value = identity.compilation_input(source)
    harness, segments = extracted_harness(source)
    value['sources'][NAME] = {'content':harness}
    value['settings']['outputSelection'] = {NAME:{CONTRACT:['evm.deployedBytecode','evm.methodIdentifiers','storageLayout']}}
    return value, harness, segments


def fixture(value, raw):
    expected, harness, segments = compilation_input()
    identity.check(value == expected, 'transfer compiler input identity')
    output = json.loads(raw)
    identity.check(not any(e.get('severity')=='error' for e in output.get('errors',[])),str(output.get('errors',[])))
    c=output['contracts'][NAME][CONTRACT]; code=c['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'], 'unexpected harness references')
    result=copy.deepcopy(rewards.fixture())
    result['schema']='nqc-miner-aave-transfer-execution-fixture-v1'
    result['previous_rewards_fixture_sha256']=identity.sha((identity.MODULE/'fixtures/aave_rewards_execution.json').read_bytes())
    result['contracts'].pop('AaveDebtExecutionHarness')
    result['contracts'][CONTRACT]={'runtime_code':'0x'+code['object'],'runtime_sha256':identity.sha(bytes.fromhex(code['object'])),'selectors':c['evm']['methodIdentifiers'],'storage_layout':c['storageLayout']}
    result.update(compiler_input_sha256=identity.sha(identity.encoded(value)),compiler_output_sha256=identity.sha(raw),compiler_sha256=identity.COMPILER_SHA,harness_source_sha256=identity.sha(harness.encode()),extracted_segments=segments,original_liquidation_source_sha256=SOURCE_SHA,post_liquidator_balance_supplied=False,atoken_transfer_outcomes_supplied=False,underlying_transfer_executed=False,liquidation_amounts_supplied=True,initial_health_validation_executed=False,receive_atoken_only=True)
    return result


def build(compiler, output):
    value,harness,_=compilation_input()
    raw,stderr=identity.compile_source(compiler,value)
    result=fixture(value,raw)
    output.mkdir(parents=True,exist_ok=False)
    for name,data in [('input.json.gz',identity.encoded(value)),('output.json.gz',raw)]: (output/name).write_bytes(gzip.compress(data,mtime=0))
    (output/'compiler.stderr').write_bytes(stderr)
    (identity.MODULE/NAME).write_text(harness)
    (identity.MODULE/'fixtures/aave_transfer_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes':(len(result['contracts'][CONTRACT]['runtime_code'])-2)//2,'sha256':result['contracts'][CONTRACT]['runtime_sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.compiler,a.output)
