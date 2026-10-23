// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
import {LiquidationLogic} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/LiquidationLogic.sol';
import {DataTypes} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol';

// Calls the original complete internal function. Token/strategy outcomes are supplied.
contract AaveDebtHarness {
  DataTypes.ReserveData private reserve;
  DataTypes.UserConfigurationMap private borrowerConfig;
  bool private tokenCalled;
  uint256 private burnedScaled;
  uint256 private expectedIndex;
  bool private burnReverts;
  bytes private burnData;
  bool private returnNoMore;
  uint256 private returnScaled;
  bool private rateReverts;
  bytes private rateData;
  uint256 private quoteLiquidity;
  uint256 private quoteVariable;
  bool private captureRates;
  struct Input {
    uint256 debt; uint256 repayment; bool noCollateral;
    uint256 index; uint256 currentScaledDebt;
    bool returnedNoMore; uint256 returnedScaledDebt;
    uint128 deficit; uint128 virtualBalance; uint16 reserveId;
    uint256 userConfiguration; uint256 reserveFactor;
    uint256 liquidityRate; uint256 variableRate;
    bool burnFails; bytes burnFailure; bool rateFails; bytes rateFailure;
  }
  function revertWith(bytes memory data) private pure {
    assembly { revert(add(data, 32), mload(data)) }
  }
  function burn(address from, uint256 scaledAmount, uint256 index) external returns (bool, uint256) {
    require(from == address(0xCAFE) && index == expectedIndex, 'unexpected burn arguments');
    tokenCalled = true;
    burnedScaled = scaledAmount;
    if (burnReverts) revertWith(burnData);
    return (returnNoMore, returnScaled);
  }
  function calculateInterestRates(DataTypes.CalculateInterestRatesParams memory params) external view returns (uint256, uint256) {
    if (rateReverts) revertWith(rateData);
    // A separate probe call exposes every actual strategy input, then rolls back.
    if (captureRates) revertWith(abi.encode(params));
    return (quoteLiquidity, quoteVariable);
  }
  function calculate(Input memory input, bool probeRates) external returns (uint256[10] memory) {
    reserve.deficit = input.deficit;
    reserve.virtualUnderlyingBalance = input.virtualBalance;
    reserve.id = input.reserveId;
    borrowerConfig.data = input.userConfiguration;
    tokenCalled = false; burnedScaled = 0; expectedIndex = input.index;
    burnReverts = input.burnFails; burnData = input.burnFailure;
    returnNoMore = input.returnedNoMore; returnScaled = input.returnedScaledDebt;
    rateReverts = input.rateFails; rateData = input.rateFailure;
    quoteLiquidity = input.liquidityRate; quoteVariable = input.variableRate;
    captureRates = probeRates;
    DataTypes.ReserveCache memory cache;
    cache.nextScaledVariableDebt = input.currentScaledDebt;
    cache.nextVariableBorrowIndex = input.index;
    cache.nextLiquidityIndex = 1e27;
    cache.reserveFactor = input.reserveFactor;
    cache.variableDebtTokenAddress = address(this);
    LiquidationLogic._burnDebtTokens(cache, reserve, borrowerConfig,
      address(0xCAFE), address(0xD00D), input.debt, input.repayment, input.noCollateral, address(this));
    return [tokenCalled ? 1 : 0, burnedScaled, cache.nextScaledVariableDebt,
      input.debt - input.repayment, uint256(reserve.deficit), borrowerConfig.data,
      uint256(reserve.virtualUnderlyingBalance), uint256(reserve.currentLiquidityRate),
      uint256(reserve.currentVariableBorrowRate), (!tokenCalled || returnNoMore) ? 1 : 0];
  }
}
