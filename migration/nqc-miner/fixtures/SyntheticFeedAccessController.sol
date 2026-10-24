// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.27;
// Explicit test double, not the observed Chainlink controller.
contract SyntheticFeedAccessController {
  uint256 private allowed;
  uint256 private blocked;
  address private expectedUser;
  address private expectedProxy;
  function hasAccess(address user, bytes calldata data) external view returns (bool) {
    require(blocked == 0, "synthetic controller blocked");
    return allowed != 0 && user == expectedUser && msg.sender == expectedProxy
      && keccak256(data) == keccak256(hex"50d25bcd");
  }
}
// Only models caller-dependent answers; it is not Chainlink DualAggregator code.
contract SyntheticCallerSensitiveFeed {
  uint256 private expectedProxy;
  int256 private proxyAnswer;
  int256 private directAnswer;
  function latestAnswer() external view returns (int256) {
    return msg.sender == address(uint160(expectedProxy)) ? proxyAnswer : directAnswer;
  }
}
