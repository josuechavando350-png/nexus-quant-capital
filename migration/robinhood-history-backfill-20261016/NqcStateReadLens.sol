// SPDX-License-Identifier: MIT
pragma solidity 0.8.23;

struct MarketParams {
    address loanToken; address collateralToken; address oracle; address irm; uint256 lltv;
}
struct Market {
    uint128 totalSupplyAssets; uint128 totalSupplyShares;
    uint128 totalBorrowAssets; uint128 totalBorrowShares;
    uint128 lastUpdate; uint128 fee;
}
interface IReadMorpho {
    function market(bytes32 id) external view returns (Market memory);
    function position(bytes32 id, address user) external view returns (uint256, uint128, uint128);
    function idToMarketParams(bytes32 id) external view returns (MarketParams memory);
}
interface IReadOracle { function price() external view returns (uint256); }
interface IReadIrm {
    function borrowRateView(MarketParams memory params, Market memory state) external view returns (uint256);
}

/// @notice Constructor-only eth_call reader. Its output is ABI data, not an application runtime.
/// All external protocol interactions are STATICCALL through view interfaces.
contract NqcStateReadLens {
    constructor(address[] memory accounts) {
        require(accounts.length <= 64, "ACCOUNT_LIMIT");
        IReadMorpho morpho = IReadMorpho(address(uint160(0x009d53d5e3bd5e8d4cbfa6db1ca238aea02e651010)));
        bytes32 id = 0xaa586d26a6fe62d9c0f0948fede6e2130500ac7a655587447e2d4a37e6330589;
        MarketParams memory params = morpho.idToMarketParams(id);
        require(params.loanToken == address(uint160(0x005fc5360d0400a0fd4f2af552add042d716f1d168)) &&
                params.collateralToken == address(uint160(0x0063c12667638f2ae6fc6ae09b43d98ec84a8586ea)) &&
                params.oracle == address(uint160(0x00cde9599059f8ae6d6b9f33a0af7877827ec75f16)) &&
                params.irm == address(uint160(0x002bd3d5965b26b51814ac95127b2b80dd6ccc0fa1)) &&
                params.lltv == 625000000000000000, "MARKET_IDENTITY");
        Market memory m = morpho.market(id);
        uint256[] memory values = new uint256[](8 + 3 * accounts.length);
        values[0] = m.totalSupplyAssets; values[1] = m.totalSupplyShares;
        values[2] = m.totalBorrowAssets; values[3] = m.totalBorrowShares;
        values[4] = m.lastUpdate; values[5] = m.fee;
        values[6] = IReadOracle(params.oracle).price();
        values[7] = IReadIrm(params.irm).borrowRateView(params, m);
        for (uint256 i; i < accounts.length; ++i) {
            require(accounts[i] != address(0) && (i == 0 || accounts[i] > accounts[i-1]), "ACCOUNT_ORDER");
            (values[8 + 3*i], values[9 + 3*i], values[10 + 3*i]) = morpho.position(id, accounts[i]);
        }
        bytes memory result = abi.encode(values);
        assembly { return(add(result, 32), mload(result)) }
    }
}
