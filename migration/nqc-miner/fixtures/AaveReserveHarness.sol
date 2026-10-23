// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
import {ReserveLogic} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/ReserveLogic.sol';
import {DataTypes} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol';
import {TokenMath} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/helpers/TokenMath.sol';

// Synthetic storage and supplied debt-token total; no chain authentication.
contract AaveReserveHarness {
  using ReserveLogic for DataTypes.ReserveData;
  using TokenMath for uint256;
  DataTypes.ReserveData private reserve;
  uint256 private suppliedScaledTotalDebt;
  struct Input {
    uint128 liquidityIndex; uint128 variableBorrowIndex;
    uint128 liquidityRate; uint128 variableBorrowRate;
    uint128 accruedToTreasury; uint40 lastUpdate; uint16 reserveFactor;
    uint256 scaledTotalDebt; uint256 userScaledCollateral; uint256 userScaledDebt;
  }
  function scaledTotalSupply() external view returns (uint256) {
    return suppliedScaledTotalDebt;
  }
  function project(Input memory input, bool updateTwice) external returns (uint256[9] memory) {
    reserve.liquidityIndex = input.liquidityIndex;
    reserve.variableBorrowIndex = input.variableBorrowIndex;
    reserve.currentLiquidityRate = input.liquidityRate;
    reserve.currentVariableBorrowRate = input.variableBorrowRate;
    reserve.accruedToTreasury = input.accruedToTreasury;
    reserve.lastUpdateTimestamp = input.lastUpdate;
    reserve.configuration.data = uint256(input.reserveFactor) << 64;
    reserve.variableDebtTokenAddress = address(this);
    suppliedScaledTotalDebt = input.scaledTotalDebt;
    // Invoke the original functions, including the external scaledTotalSupply read.
    DataTypes.ReserveCache memory cache = reserve.cache();
    reserve.updateState(cache);
    if (updateTwice) {
      // Re-cache as the liquidation path does when debt and collateral coincide.
      cache = reserve.cache();
      reserve.updateState(cache);
    }
    return [uint256(reserve.liquidityIndex), uint256(reserve.variableBorrowIndex),
      uint256(reserve.accruedToTreasury), uint256(reserve.lastUpdateTimestamp),
      input.userScaledCollateral.getATokenBalance(cache.nextLiquidityIndex),
      input.userScaledDebt.getVTokenBalance(cache.nextVariableBorrowIndex),
      cache.nextLiquidityIndex, cache.nextVariableBorrowIndex,
      uint256(cache.reserveLastUpdateTimestamp)];
  }
}
