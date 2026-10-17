// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity 0.8.24;
/// Constructor-only metadata for unused Ethereum-specific branches of the ORIGINAL adapter.
/// Not a replacement for Morpho, Bundler3, GeneralAdapter, WETH or the AMM.
/// Does not implement staking/wrapping; those routes are NOT validated by this experiment.
contract ConstructorMetadataFixture {
    address public immutable token;
    constructor(address t) { token = t; }
    function stETH() external view returns (address) { return token; }
    function underlying() external view returns (address) { return token; }
}
