// SPDX-License-Identifier: MIT
pragma solidity 0.8.23;
import "../NqcStateReadLens.sol";

interface Vm { function etch(address, bytes calldata) external; }
contract MockMorpho {
    function idToMarketParams(bytes32) external pure virtual returns (MarketParams memory) {
        return MarketParams(address(uint160(0x005fc5360d0400a0fd4f2af552add042d716f1d168)),
            address(uint160(0x0063c12667638f2ae6fc6ae09b43d98ec84a8586ea)),
            address(uint160(0x00cde9599059f8ae6d6b9f33a0af7877827ec75f16)),
            address(uint160(0x002bd3d5965b26b51814ac95127b2b80dd6ccc0fa1)), 625000000000000000);
    }
    function market(bytes32) external pure returns (Market memory) { return Market(1, 2, 3, 4, 5, 6); }
    function position(bytes32, address user) external pure returns (uint256, uint128, uint128) {
        return (uint160(user), uint128(uint160(user)) + 1, uint128(uint160(user)) + 2);
    }
}
contract WrongMarket is MockMorpho {
    function idToMarketParams(bytes32) external pure override returns (MarketParams memory) { return MarketParams(address(0), address(0), address(0), address(0), 0); }
}
contract MockOracle { function price() external pure returns (uint256) { return 700; } }
contract MockIrm {
    function borrowRateView(MarketParams memory p, Market memory m) external pure returns (uint256) {
        require(p.lltv == 625000000000000000 && m.totalBorrowAssets == 3 && m.fee == 6, "EXACT_INPUTS"); return 800;
    }
}
contract RevertingView { fallback() external { revert("FIXTURE_REVERT"); } }
contract WritingOracle {
    uint256 public counter;
    function price() external returns (uint256) { ++counter; return 700; }
}
contract LensTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant MORPHO = address(uint160(0x009d53d5e3bd5e8d4cbfa6db1ca238aea02e651010));
    address constant ORACLE = address(uint160(0x00cde9599059f8ae6d6b9f33a0af7877827ec75f16));
    address constant IRM = address(uint160(0x002bd3d5965b26b51814ac95127b2b80dd6ccc0fa1));
    function setUp() public {
        vm.etch(MORPHO, type(MockMorpho).runtimeCode); vm.etch(ORACLE, type(MockOracle).runtimeCode); vm.etch(IRM, type(MockIrm).runtimeCode);
    }
    function createLens(address[] memory users) internal returns (address result) {
        bytes memory code = abi.encodePacked(type(NqcStateReadLens).creationCode, abi.encode(users));
        assembly { result := create(0, add(code, 32), mload(code)) }
    }
    function read(address[] memory users) internal returns (uint256[] memory) {
        address result = createLens(users); require(result != address(0), "CREATE_FAILED");
        return abi.decode(result.code, (uint256[]));
    }
    function testExactStateAndPositionOrdering() public {
        address[] memory a = new address[](2); a[0] = address(10); a[1] = address(20);
        uint256[] memory v = read(a); require(v.length == 14, "LENGTH");
        for (uint256 i; i < 6; ++i) require(v[i] == i+1, "MARKET");
        require(v[6] == 700 && v[7] == 800, "ORACLE_RATE");
        require(v[8] == 10 && v[9] == 11 && v[10] == 12 && v[11] == 20 && v[12] == 21 && v[13] == 22, "POSITIONS");
    }
    function testEmptyCohort() public { require(read(new address[](0)).length == 8, "EMPTY"); }
    function testMaximumCohort() public {
        address[] memory a = new address[](64); for (uint256 i; i<64; ++i) a[i] = address(uint160(i+1));
        uint256[] memory v = read(a); require(v.length == 200 && v[199] == 66, "MAXIMUM");
    }
    function testExcessCohortReverts() public { require(createLens(new address[](65)) == address(0), "LIMIT"); }
    function testZeroAccountReverts() public { require(createLens(new address[](1)) == address(0), "ZERO"); }
    function testDuplicateAccountReverts() public {
        address[] memory a = new address[](2); a[0] = address(1); a[1] = address(1); require(createLens(a) == address(0), "DUPLICATE");
    }
    function testUnsortedAccountReverts() public {
        address[] memory a = new address[](2); a[0] = address(2); a[1] = address(1); require(createLens(a) == address(0), "SORT");
    }
    function testMarketIdentityReverts() public { vm.etch(MORPHO, type(WrongMarket).runtimeCode); require(createLens(new address[](0)) == address(0), "IDENTITY"); }
    function testOracleFailurePropagates() public { vm.etch(ORACLE, type(RevertingView).runtimeCode); require(createLens(new address[](0)) == address(0), "ORACLE"); }
    function testIrmFailurePropagates() public { vm.etch(IRM, type(RevertingView).runtimeCode); require(createLens(new address[](0)) == address(0), "IRM"); }
    function testViewUsesStaticCall() public {
        vm.etch(ORACLE, type(WritingOracle).runtimeCode); require(createLens(new address[](0)) == address(0), "MUST_BE_STATIC");
        require(WritingOracle(ORACLE).counter() == 0, "NO_WRITE");
    }
}
