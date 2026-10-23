// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED synthetic excerpt harness. Not the full pool or execution path.
import {LiquidationLogic} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/LiquidationLogic.sol";
import {DataTypes} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol";
import {ReserveConfiguration} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/configuration/ReserveConfiguration.sol";
import {PercentageMath} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/math/PercentageMath.sol";
import {MathUtils} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/math/MathUtils.sol";
import {Errors} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/helpers/Errors.sol";
contract AaveAmountHarness {
  using PercentageMath for uint256;
  using ReserveConfiguration for DataTypes.ReserveConfigurationMap;
  uint256 internal constant DEFAULT_LIQUIDATION_CLOSE_FACTOR = 0.5e4;
  uint256 public constant CLOSE_FACTOR_HF_THRESHOLD = 0.95e18;
  uint256 public constant MIN_BASE_MAX_CLOSE_FACTOR_THRESHOLD = 2000e8;
  uint256 public constant MIN_LEFTOVER_BASE = MIN_BASE_MAX_CLOSE_FACTOR_THRESHOLD / 2;
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
    vars.collateralAssetUnit = 10 ** vars.collateralReserveCache.reserveConfiguration.getDecimals();
    vars.debtAssetUnit = 10 ** vars.debtReserveCache.reserveConfiguration.getDecimals();

    vars.borrowerReserveDebtInBaseCurrency = MathUtils.mulDivCeil(
      vars.borrowerReserveDebt,
      vars.debtAssetPrice,
      vars.debtAssetUnit
    );

    // @note floor rounding
    vars.borrowerReserveCollateralInBaseCurrency =
      (vars.borrowerCollateralBalance * vars.collateralAssetPrice) /
      vars.collateralAssetUnit;

    // by default whole debt in the reserve could be liquidated
    uint256 maxLiquidatableDebt = vars.borrowerReserveDebt;
    // but if debt and collateral is above or equal MIN_BASE_MAX_CLOSE_FACTOR_THRESHOLD
    // and health factor is above CLOSE_FACTOR_HF_THRESHOLD this amount may be adjusted
    if (
      vars.borrowerReserveCollateralInBaseCurrency >= MIN_BASE_MAX_CLOSE_FACTOR_THRESHOLD &&
      vars.borrowerReserveDebtInBaseCurrency >= MIN_BASE_MAX_CLOSE_FACTOR_THRESHOLD &&
      vars.healthFactor > CLOSE_FACTOR_HF_THRESHOLD
    ) {
      uint256 totalDefaultLiquidatableDebtInBaseCurrency = vars.totalDebtInBaseCurrency.percentMul(
        DEFAULT_LIQUIDATION_CLOSE_FACTOR
      );

      // if the debt is more then DEFAULT_LIQUIDATION_CLOSE_FACTOR % of the whole,
      // then we CAN liquidate only up to DEFAULT_LIQUIDATION_CLOSE_FACTOR %
      if (vars.borrowerReserveDebtInBaseCurrency > totalDefaultLiquidatableDebtInBaseCurrency) {
        maxLiquidatableDebt =
          (totalDefaultLiquidatableDebtInBaseCurrency * vars.debtAssetUnit) /
          vars.debtAssetPrice;
      }
    }

    vars.actualDebtToLiquidate = params.debtToCover > maxLiquidatableDebt
      ? maxLiquidatableDebt
      : params.debtToCover;

    (
      vars.actualCollateralToLiquidate,
      vars.actualDebtToLiquidate,
      vars.liquidationProtocolFeeAmount
    ) = _calculateAvailableCollateralToLiquidate(
      vars.collateralReserveCache.reserveConfiguration,
      vars.collateralAssetPrice,
      vars.collateralAssetUnit,
      vars.debtAssetPrice,
      vars.debtAssetUnit,
      vars.actualDebtToLiquidate,
      vars.borrowerCollateralBalance,
      vars.liquidationBonus
    );

    // to prevent accumulation of dust on the protocol, it is enforced that you either
    // 1. liquidate all debt
    // 2. liquidate all collateral
    // 3. leave more than MIN_LEFTOVER_BASE of collateral & debt
    if (
      vars.actualDebtToLiquidate < vars.borrowerReserveDebt &&
      vars.actualCollateralToLiquidate + vars.liquidationProtocolFeeAmount <
      vars.borrowerCollateralBalance
    ) {
      bool isDebtMoreThanLeftoverThreshold = MathUtils.mulDivCeil(
        vars.borrowerReserveDebt - vars.actualDebtToLiquidate,
        vars.debtAssetPrice,
        vars.debtAssetUnit
      ) >= MIN_LEFTOVER_BASE;

      // @note floor rounding
      bool isCollateralMoreThanLeftoverThreshold = ((vars.borrowerCollateralBalance -
        vars.actualCollateralToLiquidate -
        vars.liquidationProtocolFeeAmount) * vars.collateralAssetPrice) /
        vars.collateralAssetUnit >=
        MIN_LEFTOVER_BASE;

      require(
        isDebtMoreThanLeftoverThreshold && isCollateralMoreThanLeftoverThreshold,
        Errors.MustNotLeaveDust()
      );
    }


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
