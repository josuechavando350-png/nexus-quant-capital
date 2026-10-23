// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED excerpt harness: post-transfer balance and token calls are synthetic.
import {DataTypes} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol";
import {ReserveConfiguration} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/configuration/ReserveConfiguration.sol";
import {TokenMath} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/helpers/TokenMath.sol";
import {IAToken} from "lib/aave-v3-origin-private/src/contracts/interfaces/IAToken.sol";
contract AaveCollateralHarness {
  using TokenMath for uint256;
  using ReserveConfiguration for DataTypes.ReserveConfigurationMap;
  uint256 private suppliedPostBalance;
  uint256 private capturedAmount;
  uint256 private capturedScaled;
  bool private capturedCall;
  struct LiquidationCallLocalVars {
    uint256 borrowerCollateralBalance;
    uint256 borrowerReserveDebt;
    uint256 actualDebtToLiquidate;
    uint256 actualCollateralToLiquidate;
    uint256 liquidationBonus;
    uint256 healthFactor;
    uint256 liquidationProtocolFeeAmount;
    uint256 totalCollateralInBaseCurrency;
    uint256 totalDebtInBaseCurrency;
    uint256 borrowerReserveDebtInBaseCurrency;
    uint256 borrowerReserveCollateralInBaseCurrency;
    uint256 borrowerScaledCollateralBalance;
    uint256 collateralAssetPrice;
    uint256 debtAssetPrice;
    uint256 collateralAssetUnit;
    uint256 debtAssetUnit;
    DataTypes.ReserveCache debtReserveCache;
    DataTypes.ReserveCache collateralReserveCache;
  }
  struct Input {
    uint256 index; uint256 scaledBalance; uint256 liquidatorAmount;
    uint256 feeAmount; uint256 price; uint8 decimals;
    uint256 totalCollateralBase; uint256 postLiquidatorScaledBalance;
  }
  function scaledBalanceOf(address) external view returns (uint256) { return suppliedPostBalance; }
  function RESERVE_TREASURY_ADDRESS() external pure returns (address) { return address(0xBEEF); }
  function transferOnLiquidation(address, address, uint256 amount, uint256 scaledAmount, uint256) external {
    capturedCall = true; capturedAmount = amount; capturedScaled = scaledAmount;
  }
  function calculate(Input memory input) external returns (uint256[8] memory) {
    LiquidationCallLocalVars memory vars;
    DataTypes.ExecuteLiquidationCallParams memory params;
    vars.collateralReserveCache.nextLiquidityIndex = input.index;
    vars.collateralReserveCache.reserveConfiguration.data = uint256(input.decimals) << 48;
    vars.collateralReserveCache.aTokenAddress = address(this);
    vars.borrowerScaledCollateralBalance = input.scaledBalance;
    vars.actualCollateralToLiquidate = input.liquidatorAmount;
    vars.liquidationProtocolFeeAmount = input.feeAmount;
    vars.collateralAssetPrice = input.price;
    vars.totalCollateralInBaseCurrency = input.totalCollateralBase;
    suppliedPostBalance = input.postLiquidatorScaledBalance;
    capturedCall = false; capturedAmount = 0; capturedScaled = 0;
    vars.collateralAssetUnit = 10 ** vars.collateralReserveCache.reserveConfiguration.getDecimals();

    bool hasNoCollateralLeft;
      uint256 scaledCollateralConsumed = vars.actualCollateralToLiquidate.getATokenBurnScaledAmount(
          vars.collateralReserveCache.nextLiquidityIndex
        ) +
        vars.liquidationProtocolFeeAmount.getATokenTransferScaledAmount(
          vars.collateralReserveCache.nextLiquidityIndex
        );

      // Cap to the actual scaled balance (the fee transfer is capped on-chain too, see L430)
      if (scaledCollateralConsumed > vars.borrowerScaledCollateralBalance) {
        scaledCollateralConsumed = vars.borrowerScaledCollateralBalance;
      }

      bool reserveFullyConsumed = scaledCollateralConsumed == vars.borrowerScaledCollateralBalance;

      // Compute consumed$ from the capped scaled consumption.
      // When reserveFullyConsumed, this equals the reserve's full base value.
      // When not, a few-wei leftover that rounds to $0 makes consumed$ == totalCollateral$ too.
      uint256 consumedInBaseCurrency = (scaledCollateralConsumed.getATokenBalance(
          vars.collateralReserveCache.nextLiquidityIndex
        ) * vars.collateralAssetPrice) / vars.collateralAssetUnit;

      hasNoCollateralLeft = consumedInBaseCurrency == vars.totalCollateralInBaseCurrency;

    // Transfer fee to treasury if it is non-zero
    if (vars.liquidationProtocolFeeAmount != 0) {
      // getATokenTransferScaledAmount has been used because under the hood, transferOnLiquidation is calling AToken.transfer
      uint256 scaledDownLiquidationProtocolFee = vars
        .liquidationProtocolFeeAmount
        .getATokenTransferScaledAmount(vars.collateralReserveCache.nextLiquidityIndex);
      uint256 scaledDownBorrowerBalance = IAToken(vars.collateralReserveCache.aTokenAddress)
        .scaledBalanceOf(params.borrower);
      // To avoid trying to send more aTokens than available on balance, due to 1 wei imprecision
      if (scaledDownLiquidationProtocolFee > scaledDownBorrowerBalance) {
        scaledDownLiquidationProtocolFee = scaledDownBorrowerBalance;
        vars.liquidationProtocolFeeAmount = scaledDownBorrowerBalance.getATokenBalance(
          vars.collateralReserveCache.nextLiquidityIndex
        );
      }
      IAToken(vars.collateralReserveCache.aTokenAddress).transferOnLiquidation({
        from: params.borrower,
        to: IAToken(vars.collateralReserveCache.aTokenAddress).RESERVE_TREASURY_ADDRESS(),
        amount: vars.liquidationProtocolFeeAmount,
        scaledAmount: scaledDownLiquidationProtocolFee,
        index: vars.collateralReserveCache.nextLiquidityIndex
      });
    }


    return [scaledCollateralConsumed, consumedInBaseCurrency,
      reserveFullyConsumed ? 1 : 0, hasNoCollateralLeft ? 1 : 0,
      (reserveFullyConsumed || hasNoCollateralLeft) ? 1 : 0,
      capturedCall ? 1 : 0, capturedAmount, capturedScaled];
  }
}
