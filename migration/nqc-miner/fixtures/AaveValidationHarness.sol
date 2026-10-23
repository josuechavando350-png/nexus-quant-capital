// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.27;
import {ValidationLogic} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/ValidationLogic.sol";
import {DataTypes} from "lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol";

// Synthetic test adapter only. It invokes the unchanged, runtime-matched
// validation function; it does not duplicate that function's predicates.
contract AaveValidationHarness {
  DataTypes.UserConfigurationMap private user;
  DataTypes.ReserveData private collateral;
  DataTypes.ReserveData private debt;

  struct Input {
    address borrower;
    address liquidator;
    uint256 collateralConfiguration;
    uint256 debtConfiguration;
    uint40 collateralGrace;
    uint40 debtGrace;
    uint16 collateralId;
    uint256 userConfiguration;
    uint256 health;
    uint256 selectedDebt;
  }

  function check(Input calldata input) external {
    user.data = input.userConfiguration;
    collateral.configuration.data = input.collateralConfiguration;
    collateral.liquidationGracePeriodUntil = input.collateralGrace;
    collateral.id = input.collateralId;
    debt.liquidationGracePeriodUntil = input.debtGrace;
    DataTypes.ReserveCache memory cache;
    cache.reserveConfiguration.data = input.debtConfiguration;
    ValidationLogic.validateLiquidationCall(user, collateral, debt,
      DataTypes.ValidateLiquidationCallParams({
        debtReserveCache: cache,
        totalDebt: input.selectedDebt,
        healthFactor: input.health,
        borrower: input.borrower,
        liquidator: input.liquidator
      }));
  }
}
