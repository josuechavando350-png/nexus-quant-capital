// Appended only to a fresh, pinned native-realization research source.
// One retrospective case, no independent sample or production authorization.
contract NqcStrategyBoundaryForkTest is NqcNativeRealizationForkTest {
    function _rejectAndCheck(NqcFlashFundingExecutor.FlashExecutionPlan memory p,
                             bytes memory payload, bytes memory expectedReason) internal {
        uint256 operatorWeth = IERC20FlashMinimal(WETH).balanceOf(address(this));
        uint256 operatorNative = address(this).balance;
        uint256 recipientNative = HISTORICAL_FEE_RECIPIENT.balance;
        uint256 strategyNative = address(strategy).balance;
        // Aave delivers underlying from its aToken, not the Pool coordinator.
        // This holder is bound by the retained Aave transferUnderlyingTo trace.
        address fundingHolder = p.legs[0].sourceKind == 1
            ? 0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8 : p.legs[0].lender;
        uint256 lenderWeth = IERC20FlashMinimal(WETH).balanceOf(fundingHolder);
        uint256 hf = _hf();
        (bool ok, bytes memory reason) = address(this).call(
            abi.encodeWithSelector(this.settleToNative.selector, p, payload));
        require(!ok, "UNSUPPORTED_STRATEGY_ACCEPTED");
        require(keccak256(reason) == keccak256(expectedReason), "UNEXPECTED_REJECTION_REASON");
        require(IERC20FlashMinimal(WETH).balanceOf(address(this)) == operatorWeth, "OPERATOR_WETH_DRIFT");
        require(address(this).balance == operatorNative, "OPERATOR_NATIVE_DRIFT");
        require(HISTORICAL_FEE_RECIPIENT.balance == recipientNative, "RECIPIENT_DRIFT");
        require(address(strategy).balance == strategyNative, "STRATEGY_NATIVE_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(fundingHolder) == lenderWeth, "LENDER_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(address(strategy)) == 0, "STRATEGY_WETH_DRIFT");
        require(IERC20FlashMinimal(WETH).balanceOf(address(flashExecutor)) == 0, "EXECUTOR_WETH_DRIFT");
        require(_hf() == hf, "BORROWER_DRIFT");
        require(!flashExecutor.consumedExecutionIdentity(p.executionIdentityHash), "IDENTITY_CONSUMED");
    }

    function testAaveWithSameBidCannotRepayAndRollsBack() public {
        _advanceClockOnly();
        bytes memory payload = hex"163705";
        uint256 premiumBps = uint256(IAavePoolRmc016(POOL).FLASHLOAN_PREMIUM_TOTAL());
        require(premiumBps == 5, "HISTORICAL_FEE_DRIFT");
        uint256 fee = (REPAY_PRINCIPAL * premiumBps + 5000) / 10000;
        NqcFlashFundingExecutor.FlashExecutionPlan memory p = _plan(payload, fee, 1);
        p.legs[0].sourceKind = 1;
        p.legs[0].lender = POOL;
        p.legs[0].callbackSemanticsHash = keccak256("T36_CANONICAL_REAL_AAVE_CALLBACK");
        _rejectAndCheck(p, payload, abi.encodeWithSelector(
            NqcFlashFundingExecutor.InsufficientForRepaymentAndProfit.selector,
            REPAY_PRINCIPAL + fee + 1, REPAY_PRINCIPAL + 240390311727552));
        emit log_named_uint("NQC_TRIAL_AAVE_FEE_WEI", fee);
        emit log_named_uint("NQC_TRIAL_AAVE_SHORTFALL_BEFORE_GAS_WEI", fee - 240390311727552);
    }

    function testBalancerBeforeEligibilityRollsBack() public {
        require(_hf() == PREVIOUS_HF_WAD && _hf() >= 1 ether, "PREVIOUS_ELIGIBILITY_DRIFT");
        bytes memory payload = hex"163706";
        NqcFlashFundingExecutor.FlashExecutionPlan memory p = _plan(payload, _fee(REPAY_PRINCIPAL), 1);
        // Exact historical Aave error is checked; an arbitrary revert is not success.
        _rejectAndCheck(p, payload, abi.encodeWithSignature("HealthFactorNotBelowThreshold()"));
        emit log_named_uint("NQC_TRIAL_REJECTED_PREVIOUS_HF_WAD", _hf());
    }
}
