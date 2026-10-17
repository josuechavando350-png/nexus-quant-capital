// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {NqcMorphoSponsoredLiquidation, INqcMorphoBlue} from "../contracts/NqcMorphoSponsoredLiquidation.sol";
import {MockToken, MockWeth, MockAdapter, MockExternalDexSeeder} from "../tests-solidity/NqcMorphoSponsoredLiquidationMock.t.sol";

interface CoreVm {
    function getCode(string calldata artifactPath) external returns (bytes memory);
    function deal(address account, uint256 amount) external;
    function coinbase(address account) external;
    function prank(address account) external;
    function expectRevert(bytes calldata reason) external;
}

interface OriginalMorpho {
    function enableIrm(address irm) external;
    function enableLltv(uint256 lltv) external;
    function createMarket(INqcMorphoBlue.MarketParams calldata params) external;
    function supply(INqcMorphoBlue.MarketParams calldata params, uint256 assets, uint256 shares, address onBehalf, bytes calldata data) external returns (uint256, uint256);
    function supplyCollateral(INqcMorphoBlue.MarketParams calldata params, uint256 assets, address onBehalf, bytes calldata data) external;
    function borrow(INqcMorphoBlue.MarketParams calldata params, uint256 assets, uint256 shares, address onBehalf, address receiver) external returns (uint256, uint256);
    function position(bytes32 id, address who) external view returns (uint256, uint128, uint128);
}

contract LocalOracle {
    uint256 public price = 2e36;
    function setPrice(uint256 value) external { price = value; }
}

/// Source-authentic Morpho bytecode, entirely synthetic state/DEX. NOT a fork.
abstract contract NqcOriginalMorphoFixture {
    CoreVm constant vm = CoreVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    MockWeth weth;
    MockToken collateral;
    OriginalMorpho morpho;
    MockAdapter adapter;
    LocalOracle oracle;
    NqcMorphoSponsoredLiquidation executor;
    INqcMorphoBlue.MarketParams market;
    address constant BORROWER = address(0xCAFE);
    address constant LENDER = address(0xDADA);
    uint256 shares;
    receive() external payable {}

    function setUp() public virtual {
        vm.deal(address(this), 0);
        vm.coinbase(address(0xBEEF));
        bytes memory creation = abi.encodePacked(vm.getCode("out-upstream/Morpho.json"), abi.encode(address(this)));
        address deployed;
        assembly { deployed := create(0, add(creation, 32), mload(creation)) }
        require(deployed != address(0), "original Morpho creation failed");
        morpho = OriginalMorpho(deployed);
        weth = new MockWeth();
        collateral = new MockToken();
        oracle = new LocalOracle();
        market = INqcMorphoBlue.MarketParams(address(weth), address(collateral), address(oracle), address(0), 86e16);
        morpho.enableIrm(address(0));
        morpho.enableLltv(market.lltv);
        morpho.createMarket(market);
        adapter = new MockAdapter(address(collateral), address(weth));
        executor = new NqcMorphoSponsoredLiquidation(address(this), deployed, address(adapter), address(weth));
        MockExternalDexSeeder seeder = new MockExternalDexSeeder();
        vm.deal(address(seeder), 120 ether);
        seeder.seed(weth, LENDER, 100 ether);
        seeder.seed(weth, address(adapter), 20 ether);
        vm.prank(LENDER);
        weth.approve(deployed, 100 ether);
        vm.prank(LENDER);
        morpho.supply(market, 100 ether, 0, LENDER, "");
        collateral.mint(BORROWER, 10 ether);
        vm.prank(BORROWER);
        collateral.approve(deployed, 10 ether);
        vm.prank(BORROWER);
        morpho.supplyCollateral(market, 10 ether, BORROWER, "");
        vm.prank(BORROWER);
        (, shares) = morpho.borrow(market, 8 ether, 0, BORROWER, BORROWER);
        require(address(this).balance == 0 && weth.balanceOf(address(this)) == 0, "operator seeded");
    }

    function _plan() internal view returns (NqcMorphoSponsoredLiquidation.Plan memory p) {
        p.market = market;
        p.borrower = BORROWER;
        p.repaidShares = shares;
        p.validThroughBlock = block.number;
        p.minLoanOut = 1;
        p.loanForWeth = 0.5 ether;
        p.minWethOut = 0.5 ether;
        p.minOperatorProfitLoan = 0.1 ether;
        p.coinbaseTipWei = 0.4 ether;
        p.sponsorRefundRecipient = address(0xF00D);
        p.sponsorRefundWei = 0.05 ether;
    }

    function _exhaustLoanCash() internal {
        address otherBorrower = address(0xB00B);
        uint256 available = weth.balanceOf(address(morpho));
        collateral.mint(otherBorrower, 200 ether);
        vm.prank(otherBorrower);
        collateral.approve(address(morpho), 200 ether);
        vm.prank(otherBorrower);
        morpho.supplyCollateral(market, 200 ether, otherBorrower, "");
        vm.prank(otherBorrower);
        morpho.borrow(market, available, 0, otherBorrower, otherBorrower);
        require(weth.balanceOf(address(morpho)) == 0, "cash not exhausted");
    }
}

contract NqcOriginalMorphoTest is NqcOriginalMorphoFixture {
    function testCallbackLiquidationWorksWithoutMorphoLoanCash() public {
        _exhaustLoanCash();
        oracle.setPrice(9e35);
        uint256 profit = executor.execute(_plan(), hex"01", "");
        require(profit > 0, "synthetic conversion did not settle");
        require(weth.balanceOf(address(morpho)) == 8 ether, "liquidation debt not received");
        (, uint128 remainingShares,) = morpho.position(keccak256(abi.encode(market)), BORROWER);
        require(remainingShares == 0, "debt not closed");
    }

    function testOriginalMorphoCallbackRepaymentAndBalanceConservation() public {
        oracle.setPrice(9e35);
        uint256 debtBefore = weth.balanceOf(address(morpho));
        uint256 seizedBefore = collateral.balanceOf(address(adapter));
        uint256 profit = executor.execute(_plan(), hex"01", "");
        require(weth.balanceOf(address(morpho)) - debtBefore == 8 ether, "real core debt mismatch");
        (, uint128 remainingShares,) = morpho.position(keccak256(abi.encode(market)), BORROWER);
        require(remainingShares == 0, "original debt not closed");
        uint256 seized = collateral.balanceOf(address(adapter)) - seizedBefore;
        require(profit == seized - 8 ether - 0.5 ether, "value not conserved");
        require(weth.balanceOf(address(this)) == profit, "receipt mismatch");
        require(address(this).balance == 0.05 ether, "native residual mismatch");
        require(weth.allowance(address(executor), address(morpho)) == 0, "loan approval leaked");
        require(collateral.allowance(address(executor), address(adapter)) == 0, "adapter approval leaked");
    }

    function testOriginalMorphoRejectsHealthyPosition() public {
        vm.expectRevert(abi.encodeWithSignature("Error(string)", "position is healthy"));
        executor.execute(_plan(), hex"01", "");
    }

    function testOriginalMorphoChangedOracleInvalidatesPriorPlan() public {
        oracle.setPrice(9e35);
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        oracle.setPrice(2e36);
        vm.expectRevert(abi.encodeWithSignature("Error(string)", "position is healthy"));
        executor.execute(p, hex"01", "");
    }
}
