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
interface UnderlyingView { function balanceOf(address) external view returns (uint256); }
contract AavePaymentExecutionHarness {
  using GPv2SafeERC20 for IERC20;
  using TokenMath for uint256;
  using UserConfiguration for DataTypes.UserConfigurationMap;
  DataTypes.ReserveData private debtReserve;
  DataTypes.UserConfigurationMap private borrowerConfig;
  DataTypes.ReserveData private collateralReserve;

  struct Input {
    uint256 debt; uint256 repayment; uint256 debtIndex; uint256 cached;
    uint128 deficit; uint128 virtualBalance; uint16 debtId; uint256 config; uint256 factor;
    address aToken; address liquidator; uint256 index; uint256 amount; uint256 fee;
    uint256 price; uint256 unit; uint256 totalBase; uint16 collateralId;
    uint128 collateralVirtual; uint256 collateralScaledDebt; uint256 collateralBorrowIndex;
    uint256 collateralFactor; uint128 collateralDeficit;
  }
  function calculate(Input memory input) external returns (uint256[27] memory result) {
    LiquidationLogic.LiquidationCallLocalVars memory vars;
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
    vars.actualDebtToLiquidate = input.repayment;
    vars.debtReserveCache.aTokenAddress = 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c;
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
    vars.collateralReserveCache.nextScaledVariableDebt = input.collateralScaledDebt;
    vars.collateralReserveCache.nextVariableBorrowIndex = input.collateralBorrowIndex;
    vars.collateralReserveCache.reserveFactor = input.collateralFactor;
    vars.debtReserveCache.nextScaledVariableDebt = input.cached;
    vars.debtReserveCache.nextVariableBorrowIndex = input.debtIndex;
    vars.debtReserveCache.nextLiquidityIndex = 1e27;
    vars.debtReserveCache.reserveFactor = input.factor;
    vars.debtReserveCache.variableDebtTokenAddress = 0x72E95b8931767C79bA4EeE721354d6E99a61D004;
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
      params.borrower, params.debtAsset, input.debt, input.repayment,
      hasNoCollateralLeft, params.interestRateStrategyAddress);
    // Original full collateral helper: rate update, aToken burn and actual WETH transfer.
    LiquidationLogic._burnCollateralATokens(collateralReserve, params, vars);
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


    // Synthetic composition omits initial validation and the multi-reserve _burnBadDebt branch.
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
    result = [vars.debtReserveCache.nextScaledVariableDebt, input.debt - input.repayment,
      uint256(debtReserve.deficit), borrowerConfig.data, uint256(debtReserve.virtualUnderlyingBalance),
      uint256(debtReserve.currentLiquidityRate), uint256(debtReserve.currentVariableBorrowRate),
      debt.scaledBalanceOf(params.borrower), debt.getPreviousIndex(params.borrower), debt.scaledTotalSupply(),
      token.scaledBalanceOf(params.borrower), token.scaledBalanceOf(params.liquidator),
      token.scaledBalanceOf(token.RESERVE_TREASURY_ADDRESS()), token.scaledTotalSupply(),
      token.getPreviousIndex(params.borrower), token.getPreviousIndex(params.liquidator),
      token.getPreviousIndex(token.RESERVE_TREASURY_ADDRESS()), vars.liquidationProtocolFeeAmount,
      hasNoCollateralLeft ? 1 : 0, uint256(collateralReserve.virtualUnderlyingBalance),
      uint256(collateralReserve.currentLiquidityRate), uint256(collateralReserve.currentVariableBorrowRate),
      UnderlyingView(params.collateralAsset).balanceOf(input.aToken),
      UnderlyingView(params.collateralAsset).balanceOf(params.liquidator),
      IERC20(params.debtAsset).balanceOf(params.liquidator),
      IERC20(params.debtAsset).balanceOf(vars.debtReserveCache.aTokenAddress),
      IERC20(params.debtAsset).allowance(params.liquidator, address(this))];
  }
}
