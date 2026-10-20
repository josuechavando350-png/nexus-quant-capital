// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

// RESEARCH ONLY. Not compiled or executed in the authoring environment.
// Restricted to the historical block; not a mainnet-ready trading contract.
// No fabricated prices, mints, balance overwrites or external loan providers.
interface IERC20Historical {
    function balanceOf(address who) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function approve(address to, uint256 value) external returns (bool);
}
interface IWETHHistorical is IERC20Historical { function withdraw(uint256) external; }
interface IV2Historical {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112, uint112, uint32);
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata data) external;
}
interface IV3Historical {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function fee() external view returns (uint24);
    function swap(address to, bool zeroForOne, int256 amountSpecified,
        uint160 sqrtPriceLimitX96, bytes calldata data) external returns (int256, int256);
}
struct HistoricalMarketParams {
    address loanToken;
    address collateralToken;
    address oracle;
    address irm;
    uint256 lltv;
}
interface IMorphoHistorical {
    function idToMarketParams(bytes32 id) external view returns (HistoricalMarketParams memory);
    function liquidate(HistoricalMarketParams memory params, address borrower,
        uint256 seizedAssets, uint256 repaidShares, bytes calldata data)
        external returns (uint256, uint256);
}

contract HistoricalFlashExecutor {
    address internal constant USDC = address(bytes20(hex"a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"));
    address internal constant UNI = address(bytes20(hex"1f9840a85d5af5bf1d1762f925bdaddc4201f984"));
    address internal constant WETH = address(bytes20(hex"c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"));
    address internal constant V2 = address(bytes20(hex"b4e16d0168e52d35cacd2c6185b44281ec28c9dc"));
    address internal constant V3 = address(bytes20(hex"1d42064fc4beb5f8aaf85f4617ae8b3b5b8bd801"));
    address internal constant MORPHO = address(bytes20(hex"bbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"));
    address internal constant BORROWER = address(bytes20(hex"8dca753a1f0918061ea27e69645a189d3ee1d53c"));
    address internal constant ORACLE = address(bytes20(hex"630a3b4a095220f4b36082dec1deae903346e372"));
    address internal constant IRM = address(bytes20(hex"870ac11d48b15db9a138cf899d20f13f79ba00bc"));
    bytes32 internal constant MARKET = hex"718af3af39b183758849486340b69466e3e89b84b7884188323416621ee91cb7";
    uint256 public constant USDC_OUT = 616687327559;
    uint256 public constant UNI_SEIZED = 94718231775052038007708;
    uint256 public constant TARGET_BLOCK = 21762897;
    uint256 public constant TARGET_TIMESTAMP = 1738548455;
    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE = 4295128740;

    address public immutable operator;
    address public immutable beneficiary;
    address public immutable sponsor;
    uint256 public phase;
    uint256 public v2Repayment;
    uint256 public actualDebtPaid;
    uint256 public actualUniSeized;
    uint256 public actualWethSale;

    event HistoricalExecution(
        uint256 debtPaid, uint256 collateralSeized, uint256 wethSale,
        uint256 v2Repayment, uint256 inclusionReward, uint256 sponsorPayment,
        uint256 beneficiaryWeth, uint256 beneficiaryUsdc
    );

    constructor(address operator_, address beneficiary_, address sponsor_) {
        _historicalOnly();
        require(operator_ != address(0) && beneficiary_ != address(0) && sponsor_ != address(0), "ZERO_ADDRESS");
        operator = operator_;
        beneficiary = beneficiary_;
        sponsor = sponsor_;
        require(IV2Historical(V2).token0() == USDC && IV2Historical(V2).token1() == WETH, "V2_TOKENS");
        require(IV3Historical(V3).token0() == UNI && IV3Historical(V3).token1() == WETH, "V3_TOKENS");
        require(IV3Historical(V3).fee() == 3000, "V3_FEE");
    }

    function _historicalOnly() private view {
        require(block.chainid == 1 && block.number == TARGET_BLOCK && block.timestamp == TARGET_TIMESTAMP,
            "HISTORICAL_RESEARCH_ONLY");
    }

    function execute(uint256 inclusionReward, uint256 sponsorPayment, uint256 minBeneficiaryWeth)
        external returns (uint256 beneficiaryWeth, uint256 beneficiaryUsdc)
    {
        _historicalOnly();
        require(msg.sender == operator && phase == 0, "OPERATOR_OR_PHASE");
        // Principal zero must be checked, not manufactured with deal()/mint().
        require(address(this).balance == 0, "INITIAL_ETH");
        require(IERC20Historical(USDC).balanceOf(address(this)) == 0, "INITIAL_USDC");
        require(IERC20Historical(UNI).balanceOf(address(this)) == 0, "INITIAL_UNI");
        require(IERC20Historical(WETH).balanceOf(address(this)) == 0, "INITIAL_WETH");
        (uint112 r0, uint112 r1,) = IV2Historical(V2).getReserves();
        require(uint256(r0) > USDC_OUT && r1 > 0, "V2_LIQUIDITY");
        v2Repayment = uint256(r1) * USDC_OUT * 1000 / ((uint256(r0) - USDC_OUT) * 997) + 1;
        phase = 1;
        IV2Historical(V2).swap(USDC_OUT, 0, address(this), abi.encode(MARKET));
        require(phase == 4, "V2_CALLBACK_INCOMPLETE");
        uint256 balance = IERC20Historical(WETH).balanceOf(address(this));
        uint256 externalPayments = inclusionReward + sponsorPayment;
        require(balance >= externalPayments + minBeneficiaryWeth, "ECONOMIC_FLOOR");
        beneficiaryWeth = balance - externalPayments;
        beneficiaryUsdc = IERC20Historical(USDC).balanceOf(address(this));
        phase = 5;
        if (externalPayments != 0) IWETHHistorical(WETH).withdraw(externalPayments);
        if (inclusionReward != 0) {
            (bool ok,) = block.coinbase.call{value: inclusionReward}("");
            require(ok, "INCLUSION_PAYMENT_FAILED");
        }
        if (sponsorPayment != 0) {
            (bool ok,) = sponsor.call{value: sponsorPayment}("");
            require(ok, "SPONSOR_PAYMENT_FAILED");
        }
        if (beneficiaryWeth != 0) _transfer(WETH, beneficiary, beneficiaryWeth);
        if (beneficiaryUsdc != 0) _transfer(USDC, beneficiary, beneficiaryUsdc);
        require(IERC20Historical(UNI).balanceOf(address(this)) == 0, "UNSOLD_UNI");
        emit HistoricalExecution(actualDebtPaid, actualUniSeized, actualWethSale,
            v2Repayment, inclusionReward, sponsorPayment, beneficiaryWeth, beneficiaryUsdc);
    }

    function uniswapV2Call(address sender, uint256 amount0, uint256 amount1, bytes calldata data) external {
        require(msg.sender == V2 && sender == address(this) && phase == 1, "V2_AUTH");
        require(amount0 == USDC_OUT && amount1 == 0 && keccak256(data) == keccak256(abi.encode(MARKET)), "V2_ARGS");
        HistoricalMarketParams memory p = IMorphoHistorical(MORPHO).idToMarketParams(MARKET);
        require(keccak256(abi.encode(p)) == MARKET, "MARKET_ID");
        require(p.loanToken == USDC && p.collateralToken == UNI && p.oracle == ORACLE
            && p.irm == IRM && p.lltv == 625000000000000000, "MARKET_PARAMS");
        _approve(USDC, MORPHO, USDC_OUT);
        (actualUniSeized, actualDebtPaid) = IMorphoHistorical(MORPHO).liquidate(p, BORROWER, UNI_SEIZED, 0, "");
        require(actualUniSeized == UNI_SEIZED && actualDebtPaid <= USDC_OUT, "MORPHO_AMOUNTS");
        phase = 2;
        (int256 d0, int256 d1) = IV3Historical(V3).swap(address(this), true,
            int256(UNI_SEIZED), MIN_SQRT_RATIO_PLUS_ONE, abi.encode(MARKET));
        require(phase == 3 && d0 == int256(UNI_SEIZED) && d1 < 0, "V3_INCOMPLETE");
        actualWethSale = uint256(-d1);
        require(IERC20Historical(WETH).balanceOf(address(this)) == actualWethSale, "WETH_RECONCILIATION");
        _transfer(WETH, V2, v2Repayment);
        phase = 4;
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data) external {
        require(msg.sender == V3 && phase == 2, "V3_AUTH");
        require(amount0Delta == int256(UNI_SEIZED) && amount1Delta < 0
            && keccak256(data) == keccak256(abi.encode(MARKET)), "V3_ARGS");
        phase = 3;
        _transfer(UNI, V3, uint256(amount0Delta));
    }

    function _transfer(address token, address to, uint256 amount) private {
        (bool ok, bytes memory result) = token.call(abi.encodeWithSelector(IERC20Historical.transfer.selector, to, amount));
        require(ok && (result.length == 0 || abi.decode(result, (bool))), "TRANSFER_FAILED");
    }
    function _approve(address token, address to, uint256 amount) private {
        (bool ok, bytes memory result) = token.call(abi.encodeWithSelector(IERC20Historical.approve.selector, to, amount));
        require(ok && (result.length == 0 || abi.decode(result, (bool))), "APPROVE_FAILED");
    }
    receive() external payable { require(msg.sender == WETH, "WETH_ONLY"); }
}
