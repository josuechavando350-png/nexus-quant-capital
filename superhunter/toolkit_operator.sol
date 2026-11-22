// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "../src/NqcFlashFundingExecutor.sol";
import "./PropertiesAsserts.sol";
contract OperatorProperty is PropertiesAsserts {
    NqcFlashFundingExecutor internal immutable executor;
    constructor() { executor = new NqcFlashFundingExecutor(address(this), address(1)); }
    function property_configuredOperator() public view returns (bool) {
        return executor.operator() == address(this) && address(executor.strategyExecutor()) == address(1);
    }
    function testConfiguredOperator() public { assertWithMsg(property_configuredOperator(), "constructor roles"); }
}
