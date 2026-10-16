// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

interface IHistoricalToken {
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    function approve(address, uint256) external returns (bool);
}
interface IHistoricalWrapper { function unwrap(uint256) external returns (uint256); }
interface IHistoricalStaking { function unstake(address, uint256) external returns (uint256); }
interface IHistoricalPair {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112, uint112, uint32);
    function swap(uint256, uint256, address, bytes calldata) external;
}

/// @notice Research adapter for the single captured Robinhood wsNET/NET/USDG route.
/// @dev No deployment or commercial approval. Token identities and fee formula are
///      tied to the historical evidence; no claim of universal future compatibility.
contract NqcHistoricalNetRoute {
    address public constant USDG = 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168;
    address public constant WSNET = 0x63C12667638f2Ae6fC6ae09B43D98Ec84a8586eA;
    address public constant SNET = 0xb773ec2C326B7f98a5a83fc098825492F020a4c7;
    address public constant NET = 0xCA9c78Dd337A67F6e0077F65F5E9218719d30eDf;
    address public constant STAKING = 0xB078cc304A0B264C5F3680DC0488954ACcd02E87;
    address public constant POOL = 0x59F95461E68e0c77605299791E1449f175165B54;
    bool private entered;

    function _balance(address token) private view returns (uint256) {
        return IHistoricalToken(token).balanceOf(address(this));
    }
    function _empty() private view {
        require(_balance(WSNET) == 0 && _balance(SNET) == 0 &&
                _balance(NET) == 0 && _balance(USDG) == 0, "ROUTE_INVENTORY");
    }

    function swapExactCollateral(address collateral, address loan, uint256 amount, uint256 minimum)
        external returns (uint256 received)
    {
        require(!entered && collateral == WSNET && loan == USDG && amount > 0, "ROUTE_CONTEXT");
        entered = true;
        _empty();
        require(IHistoricalToken(WSNET).transferFrom(msg.sender, address(this), amount), "PULL_WSNET");
        require(_balance(WSNET) == amount, "WSNET_DELTA");
        uint256 unwrapped = IHistoricalWrapper(WSNET).unwrap(amount);
        require(unwrapped > 0 && _balance(WSNET) == 0 && _balance(SNET) == unwrapped, "UNWRAP_DELTA");
        require(IHistoricalToken(SNET).approve(STAKING, 0), "RESET_SNET");
        require(IHistoricalToken(SNET).approve(STAKING, unwrapped), "APPROVE_SNET");
        uint256 unstaked = IHistoricalStaking(STAKING).unstake(address(this), unwrapped);
        require(unstaked > 0 && _balance(SNET) == 0 && _balance(NET) == unstaked, "UNSTAKE_DELTA");
        require(IHistoricalToken(SNET).approve(STAKING, 0), "CLEAR_SNET");
        IHistoricalPair pair = IHistoricalPair(POOL);
        require(pair.token0() == USDG && pair.token1() == NET, "PAIR_ASSETS");
        (uint112 reserveUsd, uint112 reserveNet,) = pair.getReserves();
        uint256 beforeNet = IHistoricalToken(NET).balanceOf(POOL);
        require(beforeNet == reserveNet && reserveNet > 0 && reserveUsd > 0, "PAIR_STATE");
        require(IHistoricalToken(NET).transfer(POOL, unstaked), "SELL_NET");
        // Credit only tokens actually delivered by this transfer, after NET's tax.
        uint256 actualInput = IHistoricalToken(NET).balanceOf(POOL) - beforeNet;
        require(actualInput > 0 && actualInput <= unstaked && _balance(NET) == 0, "NET_DELTA");
        uint256 weighted = actualInput * 997;
        uint256 quoted = weighted * uint256(reserveUsd) / (uint256(reserveNet) * 1000 + weighted);
        require(quoted >= minimum && quoted > 0, "ROUTE_MINIMUM");
        pair.swap(quoted, 0, address(this), "");
        received = _balance(USDG);
        require(received == quoted, "USDG_DELTA");
        uint256 beforeRecipient = IHistoricalToken(USDG).balanceOf(msg.sender);
        require(IHistoricalToken(USDG).transfer(msg.sender, received), "RETURN_USDG");
        require(IHistoricalToken(USDG).balanceOf(msg.sender) - beforeRecipient == received, "RECIPIENT_DELTA");
        _empty();
        entered = false;
    }
}
