// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

/// @notice Research-only expiry for Robinhood mainnet (4663).
/// @dev Arbitrum block.number is a parent-chain height. No parent-height fallback.
abstract contract NqcRobinhoodL2Expiry {
    error WrongChain();
    error L2ClockUnavailable();
    error ExpiredL2Block(uint256 current, uint256 deadline);
    error ExcessiveL2Window();

    // Research policy: short inclusion window, NOT a guarantee of state freshness.
    uint256 public constant MAX_L2_WINDOW = 16;

    function _checkL2Expiry(uint256 deadline) internal view {
        if (block.chainid != 4663) revert WrongChain();
        (bool ok, bytes memory result) = address(100).staticcall(
            abi.encodeWithSelector(bytes4(0xa3b1b31d)) // ArbSys.arbBlockNumber()
        );
        if (!ok || result.length != 32) revert L2ClockUnavailable();
        uint256 current = abi.decode(result, (uint256));
        if (current == 0) revert L2ClockUnavailable();
        if (current > deadline) revert ExpiredL2Block(current, deadline);
        if (deadline - current > MAX_L2_WINDOW) revert ExcessiveL2Window();
    }
}
