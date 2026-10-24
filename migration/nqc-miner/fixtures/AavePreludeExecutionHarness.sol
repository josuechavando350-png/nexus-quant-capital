// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
// GENERATED: original excerpts and internal debt function; synthetic Pool entrypoint/state.
import {DataTypes} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol";
import {LiquidationLogic} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/LiquidationLogic.sol";
import {UserConfiguration} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/configuration/UserConfiguration.sol";
import {TokenMath} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/helpers/TokenMath.sol";
import {IAToken} from "lib/aave-v3-origin-private/src/contracts/interfaces/IAToken.sol";
import {IVariableDebtToken} from "lib/aave-v3-origin-private/src/contracts/interfaces/IVariableDebtToken.sol";
import {IERC20} from "lib/aave-helpers/lib/aave-address-book/lib/aave-v3-origin/lib/solidity-utils/lib/openzeppelin-contracts-upgradeable/lib/openzeppelin-contracts/contracts/token/ERC20/IERC20.sol";
import {GPv2SafeERC20} from "lib/aave-v3-origin-private/src/contracts/dependencies/gnosis/contracts/GPv2SafeERC20.sol";
import {IPool} from "lib/aave-v3-origin-private/src/contracts/interfaces/IPool.sol";
import {ReserveLogic} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/ReserveLogic.sol";
import {ValidationLogic} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/ValidationLogic.sol";
contract AavePreludeExecutionHarness {
  using ReserveLogic for DataTypes.ReserveData;
  using GPv2SafeERC20 for IERC20;
  using TokenMath for uint256;
  using UserConfiguration for DataTypes.UserConfigurationMap;
  DataTypes.ReserveData private debtReserve;
  DataTypes.UserConfigurationMap private borrowerConfig;
  DataTypes.ReserveData private collateralReserve;

  struct Start {
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
  function calculate(Input memory input) external returns (uint256[37] memory result) {
    LiquidationLogic.LiquidationCallLocalVars memory vars;
    DataTypes.ExecuteLiquidationCallParams memory params;
    params.borrower = address(0xCAFE);
    params.liquidator = input.liquidator;
    params.receiveAToken = input.receiveAToken;
    params.collateralAsset = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    params.debtAsset = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    params.interestRateStrategyAddress = 0x9ec6F08190DeA04A54f8Afc53Db96134e5E3FdFB;
    vars.actualCollateralToLiquidate = input.amount;
    vars.actualDebtToLiquidate = input.repayment;
    vars.liquidationProtocolFeeAmount = input.fee;
    vars.collateralAssetPrice = input.price;
    vars.collateralAssetUnit = input.unit;
    vars.totalCollateralInBaseCurrency = input.totalBase;
    debtReserve.deficit = input.deficit;
    debtReserve.virtualUnderlyingBalance = input.virtualBalance;
    debtReserve.id = input.debtId;
    borrowerConfig.data = input.config;
    collateralReserve.id = input.collateralId;
    collateralReserve.deficit = input.collateralDeficit;
    collateralReserve.virtualUnderlyingBalance = input.collateralVirtual;
    _initialize(debtReserve, input.debtStart,
      0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c, 0x72E95b8931767C79bA4EeE721354d6E99a61D004);
    _initialize(collateralReserve, input.collateralStart,
      input.aToken, 0xeA51d7853EEFb32b6ee06b1C12E6dcCA88Be0fFE);
    vars.debtReserveCache = debtReserve.cache();
    debtReserve.updateState(vars.debtReserveCache);
    // caching of the collateral happens after debtReserveCache is updated
    // this ensures a non stale cache is used
    vars.collateralReserveCache = collateralReserve.cache();
    collateralReserve.updateState(vars.collateralReserveCache);

    // Aggregate GenericLogic health calculation remains omitted; health is explicitly supplied.
    vars.healthFactor = input.health;
    vars.borrowerScaledCollateralBalance = IAToken(vars.collateralReserveCache.aTokenAddress)
      .scaledBalanceOf(params.borrower);
    vars.borrowerCollateralBalance = vars.borrowerScaledCollateralBalance.getATokenBalance(
      vars.collateralReserveCache.nextLiquidityIndex
    );
    vars.borrowerReserveDebt = IVariableDebtToken(vars.debtReserveCache.variableDebtTokenAddress)
      .scaledBalanceOf(params.borrower)
      .getVTokenBalance(vars.debtReserveCache.nextVariableBorrowIndex);

    ValidationLogic.validateLiquidationCall(
      borrowerConfig,
      collateralReserve,
      debtReserve,
      DataTypes.ValidateLiquidationCallParams({
        debtReserveCache: vars.debtReserveCache,
        totalDebt: vars.borrowerReserveDebt,
        healthFactor: vars.healthFactor,
        borrower: params.borrower,
        liquidator: params.liquidator
      })
    );

    bool hasNoCollateralLeft;
    {
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

      // Clear the collateral flag when:
      // - the reserve's scaled balance will be zero post-transfer, or
      // - all user collateral is consumed (deficit will be created)
      if (reserveFullyConsumed || hasNoCollateralLeft) {
        borrowerConfig.setUsingAsCollateral(
          collateralReserve.id,
          params.collateralAsset,
          params.borrower,
          false
        );
      }
    }

    LiquidationLogic._burnDebtTokens(vars.debtReserveCache, debtReserve, borrowerConfig,
      params.borrower, params.debtAsset, vars.borrowerReserveDebt, vars.actualDebtToLiquidate,
      hasNoCollateralLeft, params.interestRateStrategyAddress);
    if (params.receiveAToken) {
      IAToken(vars.collateralReserveCache.aTokenAddress).transferOnLiquidation(
        params.borrower,
        params.liquidator,
        vars.actualCollateralToLiquidate,
        vars.actualCollateralToLiquidate.getATokenTransferScaledAmount(
          vars.collateralReserveCache.nextLiquidityIndex
        ),
        vars.collateralReserveCache.nextLiquidityIndex
      );
    } else {
      // @note Manually updating the cache in case the debt and collateral are the same asset.
      // This ensures the rates are updated correctly, considering the burning of debt
      // in the `_burnDebtTokens` function.
      if (params.collateralAsset == params.debtAsset) {
        vars.collateralReserveCache.nextScaledVariableDebt = vars
          .debtReserveCache
          .nextScaledVariableDebt;
      }

      _burnCollateralATokens(collateralReserve, params, vars);
    }

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


    // Aggregate health/amount calculation and multi-reserve _burnBadDebt remain omitted.
    // Transfers the debt asset being repaid to the aToken, where the liquidity is kept
    IERC20(params.debtAsset).safeTransferFrom(
      params.liquidator,
      vars.debtReserveCache.aTokenAddress,
      vars.actualDebtToLiquidate
    );

    emit IPool.LiquidationCall(
      params.collateralAsset,
      params.debtAsset,
      params.borrower,
      vars.actualDebtToLiquidate,
      vars.actualCollateralToLiquidate,
      params.liquidator,
      params.receiveAToken
    );

    IAToken token = IAToken(input.aToken);
    IVariableDebtToken debt = IVariableDebtToken(vars.debtReserveCache.variableDebtTokenAddress);
    result = [vars.debtReserveCache.nextScaledVariableDebt, vars.borrowerReserveDebt - vars.actualDebtToLiquidate,
      uint256(debtReserve.deficit), borrowerConfig.data, uint256(debtReserve.virtualUnderlyingBalance),
      uint256(debtReserve.currentLiquidityRate), uint256(debtReserve.currentVariableBorrowRate),
      debt.scaledBalanceOf(params.borrower), debt.getPreviousIndex(params.borrower), debt.scaledTotalSupply(),
      token.scaledBalanceOf(params.borrower), token.scaledBalanceOf(params.liquidator),
      token.scaledBalanceOf(token.RESERVE_TREASURY_ADDRESS()), token.scaledTotalSupply(),
      token.getPreviousIndex(params.borrower), token.getPreviousIndex(params.liquidator),
      token.getPreviousIndex(token.RESERVE_TREASURY_ADDRESS()), vars.liquidationProtocolFeeAmount,
      hasNoCollateralLeft ? 1 : 0, uint256(collateralReserve.virtualUnderlyingBalance),
      uint256(collateralReserve.currentLiquidityRate), uint256(collateralReserve.currentVariableBorrowRate),
      IERC20(params.debtAsset).balanceOf(params.liquidator),
      IERC20(params.debtAsset).balanceOf(vars.debtReserveCache.aTokenAddress),
      IERC20(params.debtAsset).allowance(params.liquidator, address(this)),
      uint256(debtReserve.liquidityIndex), uint256(debtReserve.variableBorrowIndex),
      uint256(debtReserve.accruedToTreasury), uint256(debtReserve.lastUpdateTimestamp),
      uint256(collateralReserve.liquidityIndex), uint256(collateralReserve.variableBorrowIndex),
      uint256(collateralReserve.accruedToTreasury), uint256(collateralReserve.lastUpdateTimestamp),
      vars.borrowerReserveDebt, vars.borrowerCollateralBalance,
      vars.debtReserveCache.currScaledVariableDebt, vars.collateralReserveCache.currScaledVariableDebt];
  }

  function _burnCollateralATokens(
    DataTypes.ReserveData storage reserve,
    DataTypes.ExecuteLiquidationCallParams memory params,
    LiquidationLogic.LiquidationCallLocalVars memory vars
  ) internal {
    LiquidationLogic._burnCollateralATokens(reserve, params, vars);
  }

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
}
