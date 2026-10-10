"""Pinned research overlays; immutable historical inputs are never edited."""
from pathlib import Path
from rpc_witness import sha
from run_fork import TEST_PATH, PATCHED_TEST_SHA

VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
FEE_RECIPIENT = "0x6Adb3baB5730852eB53987EA89D8e8f16393C200"
OBSERVED_PAYMENT_WEI = 95915734379292898
SCENARIO_SHAS = {
    "aave": "0aca5fe9ff8f05c1fad52691bdc0312a147498e34a257526b4c8282ffcae11bb",
    "balancer": "f8c665b28f6090660d65d95e601adc1b8baa0e96b597f3c0738fabc471e4d321",
    "balancer_bid": "bd4a3fa53c42b32fd3fc080701942757b5e31bb1f00247ae6e91464575f33553",
}
FEE_INTERFACE = '''
interface IBalancerFeeModuleScenario {
    function getFlashLoanFeePercentage() external view returns (uint256);
}
interface IBalancerVaultFeeScenario {
    function getProtocolFeesCollector() external view returns (address);
}
'''
BALANCER_FEE = '''    function _fee(uint256 principal) internal view returns (uint256) {
        address collector = IBalancerVaultFeeScenario(BALANCER).getProtocolFeesCollector();
        uint256 rate = IBalancerFeeModuleScenario(collector).getFlashLoanFeePercentage();
        require(rate <= 1 ether, "INVALID_FLASH_FEE_RATE");
        uint256 product = principal * rate;
        return product == 0 ? 0 : (product - 1) / 1 ether + 1;
    }
'''
AAVE_FEE = '''    function _fee(uint256 principal) internal view returns (uint256) {
        uint256 premiumBps = uint256(IAavePoolRmc016(POOL).FLASHLOAN_PREMIUM_TOTAL());
        require(premiumBps == 5, "HISTORICAL_FEE_BPS_CHANGED");
        return (principal * premiumBps + 5000) / 10000;
    }
'''


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError("scenario preimage pattern differs")
    return text.replace(before, after)


def scenario_bytes(raw, variant):
    if sha(raw) != PATCHED_TEST_SHA or variant not in {"aave", "balancer", "balancer_bid"}:
        raise ValueError("scenario preimage or variant differs")
    text = raw.decode()
    text = replace_once(text, "contract NqcRmc016RankOneSelfFinancingForkTest {",
                        "contract NqcFundingComparisonForkTest {")
    text = replace_once(text, "/// @notice Exact source-derived historical WETH/WETH liquidation attempt from",
                        "/// @notice NEW RESEARCH FUNDING SCENARIO derived from the historical test;\n/// not original evidence. WETH/WETH liquidation attempt from")
    text = replace_once(text, "        uint256 gasBefore = gasleft();", '''        bytes memory encoded = abi.encodeWithSelector(flashExecutor.execute.selector, actualPlan, payload);
        uint256 zeroBytes;
        for (uint256 i; i < encoded.length; ++i) {
            if (encoded[i] == 0) ++zeroBytes;
        }
        uint256 gasBefore = gasleft();''')
    text = replace_once(text, '        emit log_named_uint("NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS", measuredExecutionGas);', '''        emit log_named_uint("NQC_RANK1_FORK_CALLDATA_BYTES", encoded.length);
        emit log_named_uint("NQC_RANK1_FORK_CALLDATA_ZERO_BYTES", zeroBytes);
        emit log_named_uint("NQC_RANK1_FORK_CALLDATA_NONZERO_BYTES", encoded.length - zeroBytes);
        emit log_named_uint("NQC_RANK1_FORK_INTRINSIC_GAS_4_16", 21000 + zeroBytes * 4 + (encoded.length - zeroBytes) * 16);
        emit log_named_uint("NQC_RANK1_FORK_EXECUTE_CALL_GAS_UNITS", measuredExecutionGas);''')
    if variant.startswith("balancer"):
        text = replace_once(text, "interface VmRmc016 {", FEE_INTERFACE + "\ninterface VmRmc016 {")
        text = replace_once(text, "    uint256 internal constant PREVIOUS_BLOCK", "    address internal constant BALANCER = " + VAULT + ";\n    uint256 internal constant PREVIOUS_BLOCK")
        text = replace_once(text, AAVE_FEE, BALANCER_FEE)
        text = replace_once(text, "            sourceKind:1,\n            lender:POOL,", "            sourceKind:2,\n            lender:BALANCER,")
        text = replace_once(text, 'keccak256("T36_CANONICAL_REAL_AAVE_CALLBACK")', 'keccak256("T36_BALANCER_V2_CALLBACK_SCENARIO")')
        text = replace_once(text, "        uint256 flashFee = _fee(REPAY_PRINCIPAL);", '''        uint256 flashFee = _fee(REPAY_PRINCIPAL);
        uint256 vaultLiquidity = IERC20FlashMinimal(WETH).balanceOf(BALANCER);
        require(vaultLiquidity >= REPAY_PRINCIPAL, "INSUFFICIENT_REAL_VAULT_LIQUIDITY");
        emit log_named_uint("NQC_RANK1_FORK_VAULT_LIQUIDITY_WEI", vaultLiquidity);
        address collector = IBalancerVaultFeeScenario(BALANCER).getProtocolFeesCollector();
        emit log_named_uint("NQC_RANK1_FORK_VAULT_FEE_WAD", IBalancerFeeModuleScenario(collector).getFlashLoanFeePercentage());''')
    if variant == "balancer_bid":
        text = replace_once(text, "interface VmRmc016 {", '''interface IWethSettlementScenario {
    function withdraw(uint256 amount) external;
}

interface VmRmc016 {''')
        constants = ("    address internal constant HISTORICAL_FEE_RECIPIENT = " + FEE_RECIPIENT + ";\n"
                     "    uint256 internal constant HISTORICAL_PAYMENT = " + str(OBSERVED_PAYMENT_WEI) + ";\n")
        text = replace_once(text, "    address public immutable weth;", constants + "    address public immutable weth;")
        text = replace_once(text, "    function setExecutor(address executor_) external {", '''    receive() external payable {
        require(msg.sender == weth, "ONLY_WETH_NATIVE_RECEIPT");
    }

    function setExecutor(address executor_) external {''')
        text = replace_once(text, "        returnedAssetUnits = IERC20FlashMinimal(weth).balanceOf(address(this));", '''        uint256 nativeBefore = address(this).balance;
        IWethSettlementScenario(weth).withdraw(HISTORICAL_PAYMENT);
        require(address(this).balance == nativeBefore + HISTORICAL_PAYMENT, "UNWRAP_DELTA_MISMATCH");
        (bool paid,) = payable(HISTORICAL_FEE_RECIPIENT).call{value: HISTORICAL_PAYMENT}("");
        require(paid && address(this).balance == nativeBefore, "HISTORICAL_PAYMENT_NOT_SETTLED");
        returnedAssetUnits = IERC20FlashMinimal(weth).balanceOf(address(this));''')
        text = replace_once(text, "    uint256 internal constant PREVIOUS_BLOCK", constants + "    uint256 internal constant PREVIOUS_BLOCK")
        text = replace_once(text, "        uint256 operatorWethBefore =", '''        require(HISTORICAL_FEE_RECIPIENT.code.length == 0, "RECIPIENT_BEHAVIOR_NOT_EOA");
        uint256 recipientBefore = HISTORICAL_FEE_RECIPIENT.balance;
        uint256 strategyNativeBefore = address(strategy).balance;
        uint256 operatorWethBefore =''')
        text = replace_once(text, '        emit log_named_uint("NQC_RANK1_FORK_CALLDATA_BYTES", encoded.length);', '''        require(HISTORICAL_FEE_RECIPIENT.balance == recipientBefore + HISTORICAL_PAYMENT,
                "NATIVE_RECIPIENT_DELTA_MISMATCH");
        require(address(strategy).balance == strategyNativeBefore, "STRATEGY_NATIVE_BALANCE_DRIFT");
        emit log_named_uint("NQC_RANK1_FORK_NATIVE_BASELINE_WEI", strategyNativeBefore);
        emit log_named_uint("NQC_RANK1_FORK_SETTLED_NATIVE_PAYMENT_WEI", HISTORICAL_PAYMENT);
        emit log_named_uint("NQC_RANK1_FORK_CALLDATA_BYTES", encoded.length);''')
        text = replace_once(text, "        uint256 debtorHfBefore = _hf();", '''        uint256 debtorHfBefore = _hf();
        uint256 recipientBefore = HISTORICAL_FEE_RECIPIENT.balance;
        uint256 strategyNativeBefore = address(strategy).balance;
        uint256 lenderBefore = IERC20FlashMinimal(WETH).balanceOf(BALANCER);''')
        text = replace_once(text, '        require(!ok, "UNSUPPORTED_PROFIT_WAS_ACCEPTED");', '''        require(!ok, "UNSUPPORTED_PROFIT_WAS_ACCEPTED");
        require(HISTORICAL_FEE_RECIPIENT.balance == recipientBefore, "REVERT_DID_NOT_ROLL_BACK_NATIVE_PAYMENT");
        require(IERC20FlashMinimal(WETH).balanceOf(BALANCER) == lenderBefore, "REVERT_DID_NOT_ROLL_BACK_LENDER_BALANCE");
        require(address(strategy).balance == strategyNativeBefore, "FAILED_OPERATION_NATIVE_DRIFT");''')
    return text.encode()


def apply_scenario(source, variant, expected_sha):
    path = Path(source) / TEST_PATH
    raw = path.read_bytes()
    result = scenario_bytes(raw, variant)
    if sha(result) != expected_sha:
        raise ValueError("scenario postimage differs from published pin")
    path.write_bytes(result)
    return {"variant": variant, "path": TEST_PATH, "before_sha256": sha(raw),
            "after_sha256": sha(result), "scope": "FRESH_RESEARCH_COPY_NOT_ORIGINAL_TEST",
            "executor_modified": False, "original_non_fee_assertions_retained": True,
            "provider_fee_rule_changed": variant.startswith("balancer"),
            "research_strategy_adds_atomic_native_payment": variant == "balancer_bid"}
