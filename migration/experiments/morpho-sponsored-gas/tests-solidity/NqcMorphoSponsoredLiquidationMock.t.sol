// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// MOCK-ONLY unit regressions. Executed results are in RESEARCH_STATUS.md.
import {NqcMorphoSponsoredLiquidation, INqcMorphoBlue, INqcExactInputAdapter}
    from "../contracts/NqcMorphoSponsoredLiquidation.sol";

interface Vm {
    function deal(address who, uint256 amount) external;
    function coinbase(address newCoinbase) external;
    function prank(address sender) external;
    function expectRevert(bytes4 selector) external;
    function expectRevert(bytes calldata reason) external;
    function roll(uint256 height) external;
}

contract MockToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    bool public rejectApproval;
    address public shortRecipient;
    function setRejectApproval(bool value) external { rejectApproval = value; }
    function setShortRecipient(address value) external { shortRecipient = value; }

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function approve(address spender, uint256 amount) external returns (bool) {
        if (rejectApproval) return false;
        allowance[msg.sender][spender] = amount; return true;
    }
    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "funds");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += to == shortRecipient ? amount - 1 : amount;
        return true;
    }
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "allowance");
        allowance[from][msg.sender] -= amount;
        require(balanceOf[from] >= amount, "funds");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract MockWeth is MockToken {
    function deposit() external payable { balanceOf[msg.sender] += msg.value; }
    function withdraw(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "WETH funds");
        balanceOf[msg.sender] -= amount;
        (bool ok,) = payable(msg.sender).call{value: amount}("");
        require(ok, "ETH transfer");
    }
}

contract MockMorpho is INqcMorphoBlue {
    uint256 public mode;
    function setMode(uint256 mode_) external { mode = mode_; }
    MockToken collateral;
    MockToken loan;
    constructor(address collateral_, address loan_) {
        collateral = MockToken(collateral_);
        loan = MockToken(loan_);
    }
    function liquidate(
        MarketParams memory, address, uint256 seizedAssets, uint256 repaidShares, bytes calldata data
    ) external returns (uint256 seized, uint256 repaid) {
        require(seizedAssets == 0 && repaidShares != 0, "invalid");
        seized = 10 ether;
        repaid = repaidShares; // Simplified mock, NOT genuine Morpho math.
        require(collateral.transfer(msg.sender, seized), "collateral");
        if (data.length != 0 && mode != 1) {
            bytes memory route = mode == 2 ? bytes(hex"aabb") : bytes(data);
            NqcMorphoSponsoredLiquidation(payable(msg.sender)).onMorphoLiquidate(repaid, route);
            if (mode == 3) NqcMorphoSponsoredLiquidation(payable(msg.sender)).onMorphoLiquidate(repaid, data);
        }
        require(loan.transferFrom(msg.sender, address(this), mode == 4 ? repaid - 1 : repaid), "repayment");
        if (mode == 5) seized += 1;
    }
}

contract MockAdapter is INqcExactInputAdapter {
    MockToken collateral;
    MockToken loan;
    uint256 public outputReduction;
    bool public ignoreMinimum;
    bool public partialInput;
    function configure(uint256 reduction, bool ignore, bool partialSpend) external {
        outputReduction = reduction; ignoreMinimum = ignore; partialInput = partialSpend;
    }
    constructor(address collateral_, address loan_) {
        collateral = MockToken(collateral_);
        loan = MockToken(loan_);
    }
    function swapExactInput(
        address tokenIn, address tokenOut, uint256 amountIn,
        uint256 minAmountOut, bytes calldata
    ) external returns (uint256 amountOut) {
        require(tokenIn == address(collateral) && tokenOut == address(loan), "route");
        require(collateral.transferFrom(msg.sender, address(this), partialInput ? amountIn - 1 : amountIn));
        amountOut = amountIn - outputReduction; // Artificial test liquidity, not real DEX.
        if (!ignoreMinimum) require(amountOut >= minAmountOut, "minimum");
        require(loan.transfer(msg.sender, amountOut));
        return amountIn; // Deliberately do not trust this reported amount.
    }
}

// Explicitly separate the mock DEX's test liquidity from the zero-funded NQC operator.
// This seeder is an artificial unit-test venue, NOT a proven real market route.
contract MockExternalDexSeeder {
    receive() external payable {}
    function seed(MockWeth weth_, address adapter_, uint256 amount_) external {
        weth_.deposit{value: amount_}();
        require(weth_.transfer(adapter_, amount_), "external venue seed");
    }
}

contract NqcMorphoSponsoredLiquidationMockTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    MockWeth weth;
    MockToken collateral;
    MockMorpho morpho;
    MockAdapter adapter;
    NqcMorphoSponsoredLiquidation executor;

    receive() external payable {}

    function setUp() public {
        vm.deal(address(this), 0); // Test operator has no native capital.
        vm.coinbase(address(0xBEEF));
        weth = new MockWeth();
        collateral = new MockToken();
        morpho = new MockMorpho(address(collateral), address(weth));
        adapter = new MockAdapter(address(collateral), address(weth));
        executor = new NqcMorphoSponsoredLiquidation(
            address(this), address(morpho), address(adapter), address(weth)
        );
        MockExternalDexSeeder liquidity = new MockExternalDexSeeder();
        vm.deal(address(liquidity), 10 ether); // External test-venue capital, not NQC.
        liquidity.seed(weth, address(adapter), 10 ether);
        require(address(this).balance == 0, "operator started with ETH");
        require(weth.balanceOf(address(this)) == 0, "operator started with WETH");
        collateral.mint(address(morpho), 10 ether);
    }

    function _plan() private view returns (NqcMorphoSponsoredLiquidation.Plan memory p) {
        p.market = INqcMorphoBlue.MarketParams({
            loanToken: address(weth), collateralToken: address(collateral),
            oracle: address(0x1111), irm: address(0x2222), lltv: 860000000000000000
        });
        p.borrower = address(0xCAFE);
        p.repaidShares = 8 ether;
        p.validThroughBlock = block.number + 1;
        p.minLoanOut = 10 ether;
        p.loanForWeth = 0.5 ether;
        p.minWethOut = 0.5 ether;
        p.minOperatorProfitLoan = 1 ether;
        p.coinbaseTipWei = 0.4 ether;
        p.sponsorRefundRecipient = address(0xF00D);
        p.sponsorRefundWei = 0.05 ether;
    }

    function testWethLoanCallbackStartsWithZeroExecutorBalances() public {
        require(address(this).balance == 0, "operator ETH");
        require(weth.balanceOf(address(this)) == 0, "operator WETH");
        require(address(executor).balance == 0);
        require(weth.balanceOf(address(executor)) == 0);
        require(collateral.balanceOf(address(executor)) == 0);
        uint256 coinbaseBefore = address(0xBEEF).balance;
        uint256 sponsorBefore = address(0xF00D).balance;
        uint256 operatorLoanBefore = weth.balanceOf(address(this));
        uint256 operatorNativeBefore = address(this).balance;
        uint256 profit = executor.execute(_plan(), hex"01", "");
        require(profit == 1.5 ether, "WETH profit");
        require(weth.balanceOf(address(this)) == operatorLoanBefore + 1.5 ether);
        require(address(this).balance == operatorNativeBefore + 0.05 ether);
        require(address(0xF00D).balance == sponsorBefore + 0.05 ether, "refund paid");
        require(address(0xBEEF).balance == coinbaseBefore + 0.4 ether);
        require(weth.balanceOf(address(morpho)) == 8 ether);
        require(address(executor).balance == 0);
        require(weth.balanceOf(address(executor)) == 0);
    }

    function testDexLiquidityComesFromSeparateExternalSeeder() public view {
        require(address(this).balance == 0, "operator native must be zero");
        require(weth.balanceOf(address(this)) == 0, "operator tokens must be zero");
        require(weth.balanceOf(address(adapter)) == 10 ether, "mock venue liquidity");
    }

    function testRejectInsufficientNativeSponsorReserve() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.sponsorRefundWei = 0.2 ether; // 0.2 + 0.4 exceeds 0.5 WETH reserved.
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "insufficient sponsor repayment accepted");
    }

    function testRejectSelfSponsorOrCoinbaseAsBuilder() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.sponsorRefundRecipient = address(this);
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "operator falsely treated as sponsor");
        p.sponsorRefundRecipient = address(0xBEEF);
        (ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "coinbase falsely treated as sponsor");
    }

    function testRejectUnrealisticMinLoanOut() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.minLoanOut = 11 ether;
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "unexpected success");
        require(weth.balanceOf(address(morpho)) == 0);
    }

    function testUnsolicitedTokensAndForcedEthArePreserved() public {
        // External dust is NOT capital available to NQC.
        collateral.mint(address(executor), 1 ether);
        weth.mint(address(executor), 3 ether);
        vm.deal(address(executor), 0.2 ether);
        require(address(this).balance == 0 && weth.balanceOf(address(this)) == 0, "operator funded");
        uint256 profit = executor.execute(_plan(), hex"01", "");
        require(profit == 1.5 ether, "donation counted as profit");
        require(collateral.balanceOf(address(executor)) == 1 ether, "collateral dust spent");
        require(weth.balanceOf(address(executor)) == 3 ether, "WETH dust spent");
        require(address(executor).balance == 0.2 ether, "forced ETH spent");
        require(address(this).balance == 0.05 ether, "fresh ETH payout missing");
    }

    function testDonationsCannotFakeMinimumSwapOutput() public {
        collateral.mint(address(executor), 1 ether);
        weth.mint(address(executor), 3 ether);
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.minLoanOut = 11 ether;
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "donated WETH masked insufficient swap output");
        require(weth.balanceOf(address(executor)) == 3 ether, "WETH donation corrupted");
    }

    function testForcedEthCannotSubsidizeBuilderRefund() public {
        vm.deal(address(executor), 4 ether);
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.sponsorRefundWei = 0.2 ether;
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "forced ETH paid the builder");
        require(address(executor).balance == 4 ether, "native dust corrupted");
    }

    function testDonationsCannotSubsidizeMissingProfit() public {
        weth.mint(address(executor), 3 ether);
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.minOperatorProfitLoan = 2 ether; // fresh tokens yield only 1.5 profit
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, p, hex"01", bytes(""))
        );
        require(!ok, "donated loan token subsidized artificial profit");
        require(weth.balanceOf(address(executor)) == 3 ether, "donated loan token changed");
    }

    function testRejectShortRepayment() public {
        morpho.setMode(4);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.execute(_plan(), hex"01", "");
    }

    function testRejectInconsistentSeizedReturn() public {
        morpho.setMode(5);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.execute(_plan(), hex"01", "");
    }

    function testRejectShortOperatorReceipt() public {
        weth.setShortRecipient(address(this));
        vm.expectRevert(NqcMorphoSponsoredLiquidation.ProfitTooLow.selector);
        executor.execute(_plan(), hex"01", "");
    }

    function testUnauthorizedExecution() public {
        vm.prank(address(0xBAD));
        vm.expectRevert(NqcMorphoSponsoredLiquidation.Unauthorized.selector);
        executor.execute(_plan(), hex"01", "");
    }

    function testCallbacksOutsideExecutionRejected() public {
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.onMorphoLiquidate(8 ether, hex"01");
        vm.prank(address(morpho));
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.onMorphoLiquidate(8 ether, hex"01");
    }

    function testCallbackPayloadMismatchRollsBack() public {
        morpho.setMode(2);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.execute(_plan(), hex"01", "");
        _assertRolledBack();
    }

    function testDuplicateCallbackRollsBack() public {
        morpho.setMode(3);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidCallback.selector);
        executor.execute(_plan(), hex"01", "");
        _assertRolledBack();
    }

    function testMissingCallbackRollsBack() public {
        morpho.setMode(1);
        (bool ok,) = address(executor).call(abi.encodeCall(executor.execute, (_plan(), hex"01", bytes(""))));
        require(!ok, "missing callback accepted");
        _assertRolledBack();
    }

    function testAdapterCannotLieAboutOutput() public {
        adapter.configure(1, true, false);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.SwapFailed.selector);
        executor.execute(_plan(), hex"01", "");
        _assertRolledBack();
    }

    function testAdapterMustConsumeExactInput() public {
        adapter.configure(0, true, true);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.SwapFailed.selector);
        executor.execute(_plan(), hex"01", "");
        _assertRolledBack();
    }

    function testFalseApprovalRejected() public {
        collateral.setRejectApproval(true);
        vm.expectRevert(abi.encodeWithSelector(NqcMorphoSponsoredLiquidation.TokenCallFailed.selector, address(collateral)));
        executor.execute(_plan(), hex"01", "");
        _assertRolledBack();
    }

    function testExpiredPlan() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        vm.roll(p.validThroughBlock + 1);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidPlan.selector);
        executor.execute(p, hex"01", "");
    }

    function testEmptyCallbackRouteRejectedBeforeMorpho() public {
        vm.expectRevert(NqcMorphoSponsoredLiquidation.InvalidPlan.selector);
        executor.execute(_plan(), "", "");
        _assertRolledBack();
    }

    function testAllowancesClearedAndSecondExecutionWorks() public {
        executor.execute(_plan(), hex"01", "");
        require(weth.allowance(address(executor), address(morpho)) == 0, "Morpho approval");
        require(collateral.allowance(address(executor), address(adapter)) == 0, "adapter approval");
        collateral.mint(address(morpho), 10 ether);
        MockExternalDexSeeder seeder = new MockExternalDexSeeder();
        vm.deal(address(seeder), 10 ether);
        seeder.seed(weth, address(adapter), 10 ether);
        require(executor.execute(_plan(), hex"01", "") == 1.5 ether, "state not reset");
    }

    function testFuzzPriorBalancesPreserved(uint96 loanDust, uint96 collateralDust, uint96 ethDust) public {
        weth.mint(address(executor), loanDust);
        collateral.mint(address(executor), collateralDust);
        vm.deal(address(executor), ethDust);
        require(executor.execute(_plan(), hex"01", "") == 1.5 ether, "dust changed profit");
        require(weth.balanceOf(address(executor)) == loanDust, "loan dust spent");
        require(collateral.balanceOf(address(executor)) == collateralDust, "collateral dust spent");
        require(address(executor).balance == ethDust, "ETH dust spent");
    }

    function _assertRolledBack() private view {
        require(collateral.balanceOf(address(morpho)) == 10 ether, "seizure not reverted");
        require(weth.balanceOf(address(morpho)) == 0, "debt not reverted");
        require(weth.balanceOf(address(adapter)) == 10 ether, "swap not reverted");
        require(weth.balanceOf(address(this)) == 0 && address(this).balance == 0, "operator paid on revert");
        require(weth.allowance(address(executor), address(morpho)) == 0, "leaked approval");
        require(collateral.allowance(address(executor), address(adapter)) == 0, "leaked adapter approval");
    }
}

// Artificial two-hop venue to exercise a non-WETH debt token.
contract MockTwoHopAdapter is INqcExactInputAdapter {
    uint256 public secondOutput = 0.5 ether;
    address immutable weth;
    constructor(address weth_) { weth = weth_; }
    function setSecondOutput(uint256 amount) external { secondOutput = amount; }
    function swapExactInput(address tokenIn, address tokenOut, uint256 amountIn, uint256, bytes calldata)
        external returns (uint256)
    {
        require(MockToken(tokenIn).transferFrom(msg.sender, address(this), amountIn));
        uint256 output = tokenOut == weth ? secondOutput : amountIn;
        require(MockToken(tokenOut).transfer(msg.sender, output));
        return type(uint256).max; // Executor must use actual balances, not this return.
    }
}

contract RejectNative {
    receive() external payable { revert("reject native"); }
}

contract NqcNonWethMockTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    MockToken loan;
    MockToken collateral;
    MockWeth weth;
    MockMorpho morpho;
    MockTwoHopAdapter adapter;
    NqcMorphoSponsoredLiquidation executor;
    receive() external payable {}

    function setUp() public {
        vm.deal(address(this), 0);
        vm.coinbase(address(0xBEEF));
        loan = new MockToken();
        collateral = new MockToken();
        weth = new MockWeth();
        morpho = new MockMorpho(address(collateral), address(loan));
        adapter = new MockTwoHopAdapter(address(weth));
        executor = new NqcMorphoSponsoredLiquidation(address(this), address(morpho), address(adapter), address(weth));
        collateral.mint(address(morpho), 10 ether);
        loan.mint(address(adapter), 10 ether);
        MockExternalDexSeeder seeder = new MockExternalDexSeeder();
        vm.deal(address(seeder), 1 ether);
        seeder.seed(weth, address(adapter), 1 ether);
    }

    function _plan() private view returns (NqcMorphoSponsoredLiquidation.Plan memory p) {
        p.market = INqcMorphoBlue.MarketParams(address(loan), address(collateral), address(1), address(2), 86e16);
        p.borrower = address(3);
        p.repaidShares = 8 ether;
        p.validThroughBlock = block.number;
        p.minLoanOut = 10 ether;
        p.loanForWeth = 0.5 ether;
        p.minWethOut = 0.5 ether;
        p.minOperatorProfitLoan = 1 ether;
        p.coinbaseTipWei = 0.4 ether;
        p.sponsorRefundRecipient = address(0xF00D);
        p.sponsorRefundWei = 0.05 ether;
    }

    function testTwoHopBalancesAndApprovals() public {
        loan.mint(address(executor), 7);
        collateral.mint(address(executor), 11);
        weth.mint(address(executor), 13);
        vm.deal(address(executor), 17);
        require(executor.execute(_plan(), hex"01", hex"02") == 1.5 ether);
        require(loan.balanceOf(address(morpho)) == 8 ether);
        require(loan.balanceOf(address(this)) == 1.5 ether);
        require(address(this).balance == 0.05 ether);
        require(loan.balanceOf(address(executor)) == 7);
        require(collateral.balanceOf(address(executor)) == 11);
        require(weth.balanceOf(address(executor)) == 13);
        require(address(executor).balance == 17);
        require(loan.allowance(address(executor), address(morpho)) == 0);
        require(loan.allowance(address(executor), address(adapter)) == 0);
        require(collateral.allowance(address(executor), address(adapter)) == 0);
    }

    function testShortSecondSwapCannotUseDonatedWeth() public {
        weth.mint(address(executor), 5 ether);
        adapter.setSecondOutput(0.49 ether);
        vm.expectRevert(NqcMorphoSponsoredLiquidation.SwapFailed.selector);
        executor.execute(_plan(), hex"01", hex"02");
        require(weth.balanceOf(address(executor)) == 5 ether);
        require(collateral.balanceOf(address(morpho)) == 10 ether);
        require(loan.balanceOf(address(morpho)) == 0);
    }

    function testRejectingSponsorRollsBackEntireOperation() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        p.sponsorRefundRecipient = address(new RejectNative());
        vm.expectRevert(NqcMorphoSponsoredLiquidation.NativeTransferFailed.selector);
        executor.execute(p, hex"01", hex"02");
        require(collateral.balanceOf(address(morpho)) == 10 ether);
        require(loan.balanceOf(address(morpho)) == 0);
        require(weth.balanceOf(address(adapter)) == 1 ether);
        require(address(this).balance == 0);
    }

    function testRejectingCoinbaseRollsBackSponsorPayment() public {
        NqcMorphoSponsoredLiquidation.Plan memory p = _plan();
        vm.coinbase(address(new RejectNative()));
        uint256 beforeSponsor = p.sponsorRefundRecipient.balance;
        vm.expectRevert(NqcMorphoSponsoredLiquidation.NativeTransferFailed.selector);
        executor.execute(p, hex"01", hex"02");
        require(p.sponsorRefundRecipient.balance == beforeSponsor);
        require(collateral.balanceOf(address(morpho)) == 10 ether);
    }
}
