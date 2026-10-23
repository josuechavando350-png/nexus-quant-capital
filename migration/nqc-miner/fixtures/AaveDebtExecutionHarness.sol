// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.27;
import {LiquidationLogic} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/logic/LiquidationLogic.sol';
import {DataTypes} from 'lib/aave-v3-origin-private/src/contracts/protocol/libraries/types/DataTypes.sol';

interface DebtView {
  function scaledBalanceOf(address user) external view returns (uint256);
  function scaledTotalSupply() external view returns (uint256);
  function getPreviousIndex(address user) external view returns (uint256);
  function burn(address user, uint256 amount, uint256 index) external returns (bool, uint256);
}

// Artificial Pool entry point calling the unchanged complete internal function.
// Token and rate responses are produced by the actual runtime-matched contracts.
contract AaveDebtExecutionHarness {
  DataTypes.ReserveData private reserve;
  DataTypes.UserConfigurationMap private borrowerConfig;
  address constant TOKEN = 0x72E95b8931767C79bA4EeE721354d6E99a61D004;
  address constant STRATEGY = 0x9ec6F08190DeA04A54f8Afc53Db96134e5E3FdFB;
  address constant ASSET = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
  struct Input {
    uint256 debt; uint256 repayment; bool noCollateral;
    uint256 index; uint256 currentScaledDebt;
    uint128 deficit; uint128 virtualBalance; uint16 reserveId;
    uint256 userConfiguration; uint256 reserveFactor;
  }
  function calculate(Input memory input) external returns (uint256[10] memory) {
    reserve.deficit = input.deficit;
    reserve.virtualUnderlyingBalance = input.virtualBalance;
    reserve.id = input.reserveId;
    borrowerConfig.data = input.userConfiguration;
    DataTypes.ReserveCache memory cache;
    cache.nextScaledVariableDebt = input.currentScaledDebt;
    cache.nextVariableBorrowIndex = input.index;
    cache.nextLiquidityIndex = 1e27;
    cache.reserveFactor = input.reserveFactor;
    cache.variableDebtTokenAddress = TOKEN;
    LiquidationLogic._burnDebtTokens(cache, reserve, borrowerConfig,
      address(0xCAFE), ASSET, input.debt, input.repayment, input.noCollateral, STRATEGY);
    return [cache.nextScaledVariableDebt, input.debt - input.repayment,
      uint256(reserve.deficit), borrowerConfig.data, uint256(reserve.virtualUnderlyingBalance),
      uint256(reserve.currentLiquidityRate), uint256(reserve.currentVariableBorrowRate),
      DebtView(TOKEN).scaledBalanceOf(address(0xCAFE)), DebtView(TOKEN).getPreviousIndex(address(0xCAFE)),
      DebtView(TOKEN).scaledTotalSupply()];
  }
}

// Explicit synthetic forwarding proxy. It does NOT certify deployed proxy code.
contract SyntheticDebtProxy {
  fallback() external payable {
    address target = 0xb27C52c7f84819e3157993489741cB60786aE330;
    assembly {
      calldatacopy(0, 0, calldatasize())
      let success := delegatecall(gas(), target, 0, calldatasize(), 0, 0)
      returndatacopy(0, 0, returndatasize())
      switch success case 0 { revert(0, returndatasize()) } default { return(0, returndatasize()) }
    }
  }
}

// Synthetic callback behavior; real rewards controller is still outside coverage.
contract RewardsProbe {
  uint256 public mode;
  uint256 public calls;
  error RewardsRejected();
  event Callback(address indexed token, address indexed user, uint256 totalBefore,
    uint256 balanceBefore, uint256 totalAfter, uint256 balanceAfter, uint256 indexAfter);
  function handleAction(address user, uint256 totalBefore, uint256 balanceBefore) external {
    require(msg.sender == 0x72E95b8931767C79bA4EeE721354d6E99a61D004 && user == address(0xCAFE), 'unexpected callback');
    calls++;
    DebtView token = DebtView(msg.sender);
    emit Callback(msg.sender, user, totalBefore, balanceBefore,
      token.scaledTotalSupply(), token.scaledBalanceOf(user), token.getPreviousIndex(user));
    if (mode == 1) revert RewardsRejected();
    if (mode == 2) assembly { revert(0, 0) }
    // An attempted burn by the controller must fail the real token's onlyPool.
    if (mode == 3) token.burn(user, 1, token.getPreviousIndex(user));
  }
}
