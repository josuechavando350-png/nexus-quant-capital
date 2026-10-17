// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// MOCK-ONLY unit regressions. Foundry/solc unavailable in the authoring
// environment; this file is NOT claimed compiled or executed.
import {NqcMorphoSponsoredLiquidation, INqcMorphoBlue, INqcExactInputAdapter}
    from "../contracts/NqcMorphoSponsoredLiquidation.sol";

interface Vm {
    function deal(address who, uint256 amount) external;
    function coinbase(address newCoinbase) external;
}

contract MockToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount; return true;
    }
    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "funds");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
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
        if (data.length != 0) {
            NqcMorphoSponsoredLiquidation(payable(msg.sender)).onMorphoLiquidate(repaid, data);
        }
        require(loan.transferFrom(msg.sender, address(this), repaid), "repayment");
    }
}

contract MockAdapter is INqcExactInputAdapter {
    MockToken collateral;
    MockToken loan;
    constructor(address collateral_, address loan_) {
        collateral = MockToken(collateral_);
        loan = MockToken(loan_);
    }
    function swapExactInput(
        address tokenIn, address tokenOut, uint256 amountIn,
        uint256 minAmountOut, bytes calldata
    ) external returns (uint256 amountOut) {
        require(tokenIn == address(collateral) && tokenOut == address(loan), "route");
        require(collateral.transferFrom(msg.sender, address(this), amountIn));
        amountOut = amountIn; // Artificial 1:1 liquidity, not real DEX.
        require(amountOut >= minAmountOut, "minimum");
        require(loan.transfer(msg.sender, amountOut));
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
        vm.deal(address(this), 50 ether);
        vm.coinbase(address(0xBEEF));
        weth = new MockWeth();
        collateral = new MockToken();
        morpho = new MockMorpho(address(collateral), address(weth));
        adapter = new MockAdapter(address(collateral), address(weth));
        executor = new NqcMorphoSponsoredLiquidation(
            address(this), address(morpho), address(adapter), address(weth)
        );
        weth.deposit{value: 10 ether}();
        require(weth.transfer(address(adapter), 10 ether));
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
    }

    function testWethLoanCallbackStartsWithZeroExecutorBalances() public {
        require(address(executor).balance == 0);
        require(weth.balanceOf(address(executor)) == 0);
        require(collateral.balanceOf(address(executor)) == 0);
        uint256 coinbaseBefore = address(0xBEEF).balance;
        uint256 operatorLoanBefore = weth.balanceOf(address(this));
        uint256 operatorNativeBefore = address(this).balance;
        uint256 profit = executor.execute(_plan(), hex"01", "");
        require(profit == 1.5 ether, "WETH profit");
        require(weth.balanceOf(address(this)) == operatorLoanBefore + 1.5 ether);
        require(address(this).balance == operatorNativeBefore + 0.1 ether);
        require(address(0xBEEF).balance == coinbaseBefore + 0.4 ether);
        require(weth.balanceOf(address(morpho)) == 8 ether);
        require(address(executor).balance == 0);
        require(weth.balanceOf(address(executor)) == 0);
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

    function testRejectPreFundedExecutor() public {
        collateral.mint(address(executor), 1);
        (bool ok,) = address(executor).call(
            abi.encodeWithSelector(executor.execute.selector, _plan(), hex"01", bytes(""))
        );
        require(!ok, "unexpected success");
    }
}
