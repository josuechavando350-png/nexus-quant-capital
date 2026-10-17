// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// RESEARCH PROTOTYPE ONLY. Not compiled or audited in this working environment.
// No deployed code, no live authority, no signed/broadcast transactions.

interface INqcErc20 {
    function balanceOf(address account) external view returns (uint256);
}

interface INqcMorphoBlue {
    struct MarketParams {
        address loanToken;
        address collateralToken;
        address oracle;
        address irm;
        uint256 lltv;
    }

    function liquidate(
        MarketParams memory marketParams,
        address borrower,
        uint256 seizedAssets,
        uint256 repaidShares,
        bytes calldata data
    ) external returns (uint256 seizedAssetsFinal, uint256 repaidAssetsFinal);
}

interface INqcExactInputAdapter {
    function swapExactInput(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minAmountOut,
        bytes calldata routeData
    ) external returns (uint256 amountOut);
}

interface INqcWeth {
    function withdraw(uint256 amount) external;
}

/// @dev Morpho callback receives collateral before Morpho pulls the debt token.
///      block.coinbase ETH transfers are NOT by themselves proof of builder income.
///      The adapter must be independently audited / allowlisted before any live use.
contract NqcMorphoSponsoredLiquidation {
    error Unauthorized();
    error InvalidPlan();
    error StateContaminated();
    error AlreadyActive();
    error InvalidCallback();
    error SwapFailed();
    error ProfitTooLow();
    error NativeTipNotFunded();
    error TokenCallFailed(address token);
    error NativeTransferFailed();

    struct Plan {
        INqcMorphoBlue.MarketParams market;
        address borrower;
        uint256 repaidShares;
        uint256 validThroughBlock;
        uint256 minLoanOut;
        uint256 loanForWeth;
        uint256 minWethOut;
        uint256 minOperatorProfitLoan;
        uint256 coinbaseTipWei;
        // Sponsor must be a distinct, independently authenticated recipient.
        address sponsorRefundRecipient;
        uint256 sponsorRefundWei;
    }

    address public immutable operator;
    INqcMorphoBlue public immutable morpho;
    INqcExactInputAdapter public immutable swapAdapter;
    address public immutable weth;

    bool private active;
    bool private callbackSeen;
    bytes32 private expectedCallbackHash;
    address private activeLoanToken;
    address private activeCollateralToken;
    uint256 private reservedLoanForWeth;
    uint256 private minProfit;
    uint256 private activeMinLoanOut;

    event ExperimentalLiquidation(
        address indexed borrower,
        uint256 seizedCollateral,
        uint256 repaidLoan,
        uint256 operatorLoanProfit,
        uint256 coinbaseTipWei,
        address sponsorRefundRecipient,
        uint256 sponsorRefundWei
    );

    constructor(address operator_, address morpho_, address adapter_, address weth_) {
        if (operator_ == address(0) || morpho_ == address(0) ||
            adapter_ == address(0) || weth_ == address(0)) revert InvalidPlan();
        operator = operator_;
        morpho = INqcMorphoBlue(morpho_);
        swapAdapter = INqcExactInputAdapter(adapter_);
        weth = weth_;
    }

    receive() external payable {
        if (msg.sender != weth) revert Unauthorized();
    }

    function execute(Plan calldata plan, bytes calldata collateralRoute, bytes calldata wethRoute)
        external returns (uint256 operatorLoanProfit)
    {
        if (msg.sender != operator) revert Unauthorized();
        if (active) revert AlreadyActive();
        if (block.number > plan.validThroughBlock || plan.repaidShares == 0 ||
            plan.borrower == address(0) || plan.minLoanOut == 0 ||
            plan.minOperatorProfitLoan == 0 || plan.coinbaseTipWei == 0 ||
            plan.sponsorRefundWei == 0) revert InvalidPlan();

        address loan = plan.market.loanToken;
        address collateral = plan.market.collateralToken;
        if (loan == address(0) || collateral == address(0) ||
            loan == collateral || plan.loanForWeth == 0 || plan.minWethOut == 0) revert InvalidPlan();

        // WETH debt markets (including historical EZETH/WETH) unwrap only the
        // reserved share of WETH rather than swapping WETH into itself.
        if (loan == weth && plan.minWethOut != plan.loanForWeth) revert InvalidPlan();
        // The sponsor and block proposer are two different recipients. A
        // coinbase payment alone does not repay gas advanced by a builder.
        if (plan.sponsorRefundRecipient == address(0) ||
            plan.sponsorRefundRecipient == operator ||
            plan.sponsorRefundRecipient == address(this) ||
            plan.sponsorRefundRecipient == block.coinbase ||
            plan.minWethOut < plan.sponsorRefundWei + plan.coinbaseTipWei) revert InvalidPlan();
        if (_balance(loan) != 0 || _balance(collateral) != 0 ||
            _balance(weth) != 0 || address(this).balance != 0) revert StateContaminated();

        active = true;
        callbackSeen = false;
        activeLoanToken = loan;
        activeCollateralToken = collateral;
        reservedLoanForWeth = plan.loanForWeth;
        minProfit = plan.minOperatorProfitLoan;
        activeMinLoanOut = plan.minLoanOut;
        expectedCallbackHash = keccak256(collateralRoute);

        (uint256 seized, uint256 repaid) = morpho.liquidate(
            plan.market, plan.borrower, 0, plan.repaidShares, collateralRoute
        );
        if (!callbackSeen || _balance(collateral) != 0) revert InvalidCallback();
        // Morpho transferred debt tokens back using transferFrom before returning.
        _forceApprove(loan, address(morpho), 0);
        if (_balance(loan) < plan.loanForWeth + plan.minOperatorProfitLoan) revert ProfitTooLow();

        if (loan == weth) {
            INqcWeth(weth).withdraw(plan.loanForWeth);
        } else {
            _swap(loan, weth, plan.loanForWeth, plan.minWethOut, wethRoute);
            uint256 availableWeth = _balance(weth);
            if (availableWeth < plan.minWethOut) revert NativeTipNotFunded();
            INqcWeth(weth).withdraw(availableWeth);
        }
        uint256 totalNativePayments = plan.sponsorRefundWei + plan.coinbaseTipWei;
        if (address(this).balance < totalNativePayments) revert NativeTipNotFunded();
        // Candidate direct reimbursement, not proof of builder acceptance.
        // Ownership of this address and builder balance must be proven offchain.
        (bool refundOk,) = payable(plan.sponsorRefundRecipient).call{value: plan.sponsorRefundWei}("");
        if (!refundOk) revert NativeTransferFailed();
        (bool tipOk,) = payable(block.coinbase).call{value: plan.coinbaseTipWei}("");
        if (!tipOk) revert NativeTransferFailed();

        operatorLoanProfit = _balance(loan);
        if (operatorLoanProfit < plan.minOperatorProfitLoan) revert ProfitTooLow();
        _safeTransfer(loan, operator, operatorLoanProfit);
        uint256 residualNative = address(this).balance;
        if (residualNative != 0) {
            (bool profitOk,) = payable(operator).call{value: residualNative}("");
            if (!profitOk) revert NativeTransferFailed();
        }
        if (_balance(loan) != 0 || _balance(collateral) != 0 ||
            _balance(weth) != 0) revert StateContaminated();

        active = false;
        callbackSeen = false;
        expectedCallbackHash = bytes32(0);
        activeLoanToken = address(0);
        activeCollateralToken = address(0);
        reservedLoanForWeth = 0;
        minProfit = 0;
        activeMinLoanOut = 0;
        emit ExperimentalLiquidation(
            plan.borrower, seized, repaid, operatorLoanProfit, plan.coinbaseTipWei,
            plan.sponsorRefundRecipient, plan.sponsorRefundWei
        );
    }

    function onMorphoLiquidate(uint256 repaidAssets, bytes calldata collateralRoute) external {
        if (msg.sender != address(morpho) || !active || callbackSeen ||
            repaidAssets == 0 || keccak256(collateralRoute) != expectedCallbackHash) revert InvalidCallback();
        callbackSeen = true;
        uint256 seizedBalance = _balance(activeCollateralToken);
        if (seizedBalance == 0) revert InvalidCallback();
        uint256 required = repaidAssets + reservedLoanForWeth + minProfit;
        if (activeMinLoanOut > required) required = activeMinLoanOut;
        _swap(activeCollateralToken, activeLoanToken, seizedBalance, required, collateralRoute);
        _forceApprove(activeLoanToken, address(morpho), repaidAssets);
    }

    function _swap(
        address tokenIn, address tokenOut, uint256 amountIn,
        uint256 minAmountOut, bytes memory route
    ) private {
        uint256 inputBefore = _balance(tokenIn);
        uint256 outputBefore = _balance(tokenOut);
        if (amountIn == 0 || inputBefore < amountIn || minAmountOut == 0) revert SwapFailed();
        _forceApprove(tokenIn, address(swapAdapter), amountIn);
        swapAdapter.swapExactInput(tokenIn, tokenOut, amountIn, minAmountOut, route);
        _forceApprove(tokenIn, address(swapAdapter), 0);
        uint256 inputAfter = _balance(tokenIn);
        uint256 outputAfter = _balance(tokenOut);
        if (inputBefore - inputAfter != amountIn ||
            outputAfter < outputBefore ||
            outputAfter - outputBefore < minAmountOut) revert SwapFailed();
    }

    function _balance(address token) private view returns (uint256) {
        return INqcErc20(token).balanceOf(address(this));
    }

    function _forceApprove(address token, address spender, uint256 amount) private {
        _tokenCall(token, abi.encodeWithSignature("approve(address,uint256)", spender, 0));
        if (amount != 0) _tokenCall(token, abi.encodeWithSignature("approve(address,uint256)", spender, amount));
    }

    function _safeTransfer(address token, address recipient, uint256 amount) private {
        _tokenCall(token, abi.encodeWithSignature("transfer(address,uint256)", recipient, amount));
    }

    function _tokenCall(address token, bytes memory data) private {
        (bool success, bytes memory returned) = token.call(data);
        if (!success ||
            (returned.length != 0 && (returned.length != 32 ||
                !abi.decode(returned, (bool))))) revert TokenCallFailed(token);
    }
}
