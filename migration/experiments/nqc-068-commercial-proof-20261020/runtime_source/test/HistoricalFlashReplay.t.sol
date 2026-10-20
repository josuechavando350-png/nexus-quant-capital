// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;
import "../src/HistoricalFlashExecutor.sol";

// No forge-std dependency. Interfaces only. This file is NOT yet compiled/run.
interface VmHistorical {
    function envString(string calldata) external returns (string memory);
    function envOr(string calldata, bool) external returns (bool);
    function createSelectFork(string calldata, bytes32) external returns (uint256);
    function transact(bytes32) external;
    function prank(address) external;
    function expectRevert(bytes calldata) external;
}
interface IOracleHistorical { function price() external view returns (uint256); }

contract HistoricalFlashReplayTest {
    VmHistorical private constant vm = VmHistorical(address(uint160(uint256(keccak256("hevm cheat code")))));
    bytes32 private constant TX = hex"2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb";
    address private constant USDC = address(bytes20(hex"a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"));
    address private constant UNI = address(bytes20(hex"1f9840a85d5af5bf1d1762f925bdaddc4201f984"));
    address private constant WETH = address(bytes20(hex"c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"));
    address private constant V2 = address(bytes20(hex"b4e16d0168e52d35cacd2c6185b44281ec28c9dc"));
    address private constant OLD_EXECUTOR = address(bytes20(hex"8ce45e650ab17b6ca0dd6071f7c2b5c69b5b42b2"));
    address private constant ORACLE = address(bytes20(hex"630a3b4a095220f4b36082dec1deae903346e372"));
    address private constant PAYEE = address(bytes20(hex"95222290dd7278aa3ddd389cc1e1d165cc4bafe5"));
    address private constant OPERATOR = address(0xA110);
    address private constant BENEFICIARY = address(0xA111);
    address private constant SPONSOR_SCENARIO_ONLY = address(0xA112);
    uint256 private constant INCLUSION_REFERENCE = 12447536358167279703;
    uint256 private constant ACTUAL_SALE = 281407578800167103862;
    uint256 private constant MIN_V2_PAY = 266862310264222944156;
    event ScopeGas(string scope, uint256 gasUnits);
    event MeasuredTokenSurplus(uint256 wethBeforeGasAndUnverifiedCosts, uint256 usdcDust);

    function setUp() public {
        require(vm.envOr("NQC_ARCHIVE_READ_APPROVED", false), "ARCHIVE_READ_NOT_APPROVED");
        // This overload replays the earlier txs in the target block, then stops BEFORE TX.
        // A fork at block 21762896 or at the end of 21762897 is NOT an equivalent fixture.
        vm.createSelectFork(vm.envString("NQC_ARCHIVE_RPC_URL"), TX);
        require(block.chainid == 1 && block.number == 21762897, "CHAIN_BLOCK");
        require(block.timestamp == 1738548455 && block.basefee == 302819782345, "BLOCK_ENVIRONMENT");
        require(block.coinbase == PAYEE, "COINBASE");
        require(blockhash(21762896) == hex"c3b1f4fe26e6743df8727eceec10c536b33db580b3346fa87e731d888ca5f4d3", "PARENT_HASH");
        (uint112 r0, uint112 r1,) = IV2Historical(V2).getReserves();
        require(r0 == 38669555298186 && r1 == 16417414753955494219446, "PRESTATE_RESERVES");
        require(IERC20Historical(USDC).balanceOf(OLD_EXECUTOR) == 2085631109623, "OLD_USDC_PRESTATE");
        require(IERC20Historical(WETH).balanceOf(OLD_EXECUTOR) == 337933651560660046099, "OLD_WETH_PRESTATE");
        require(IOracleHistorical(ORACLE).price() == uint256(0x061178cc4362f51dedd856), "ORACLE_PRESTATE");
    }

    function test_01_original_transaction_token_parity() public {
        uint256 ethBefore = PAYEE.balance;
        uint256 uniBefore = IERC20Historical(UNI).balanceOf(OLD_EXECUTOR);
        vm.transact(TX);
        require(IERC20Historical(WETH).balanceOf(OLD_EXECUTOR) == 340031383738413008434, "BASELINE_WETH");
        require(IERC20Historical(USDC).balanceOf(OLD_EXECUTOR) == 2085631109624, "BASELINE_USDC");
        require(IERC20Historical(UNI).balanceOf(OLD_EXECUTOR) == uniBefore, "BASELINE_UNI");
        require(PAYEE.balance - ethBefore == INCLUSION_REFERENCE, "BASELINE_INCLUSION");
        // Gas from vm.transact or gasleft() is not accepted as a new transaction receipt.
    }

    function _newExecutor() private returns (HistoricalFlashExecutor e) {
        uint256 gasBefore = gasleft();
        vm.prank(OPERATOR);
        e = new HistoricalFlashExecutor(OPERATOR, BENEFICIARY, SPONSOR_SCENARIO_ONLY);
        emit ScopeGas("internal_CREATE_scope_only_not_billed_deployment_tx", gasBefore - gasleft());
    }

    function test_02_zero_principal_real_protocol_sequence() public {
        HistoricalFlashExecutor e = _newExecutor();
        require(IERC20Historical(USDC).balanceOf(address(e)) == 0, "START_USDC");
        require(IERC20Historical(WETH).balanceOf(address(e)) == 0, "START_WETH");
        require(IERC20Historical(UNI).balanceOf(address(e)) == 0 && address(e).balance == 0, "START_OTHER");
        uint256 beforeWeth = IERC20Historical(WETH).balanceOf(BENEFICIARY);
        uint256 beforeUsdc = IERC20Historical(USDC).balanceOf(BENEFICIARY);
        uint256 beforePayee = PAYEE.balance;
        uint256 gasBefore = gasleft();
        vm.prank(OPERATOR);
        // ZERO sponsorPayment intentionally isolates the token route, not financed net profit.
        (uint256 residual, uint256 dust) = e.execute(INCLUSION_REFERENCE, 0, 1);
        emit ScopeGas("external_call_scope_only_not_full_transaction_receipt", gasBefore - gasleft());
        require(e.actualDebtPaid() == 616687327558 && e.actualUniSeized() == 94718231775052038007708, "MORPHO_PARITY");
        require(e.actualWethSale() == ACTUAL_SALE && e.v2Repayment() == MIN_V2_PAY, "SWAP_PARITY");
        require(residual == ACTUAL_SALE - MIN_V2_PAY - INCLUSION_REFERENCE && dust == 1, "RESIDUAL_PARITY");
        require(IERC20Historical(WETH).balanceOf(BENEFICIARY) - beforeWeth == residual, "BENEFICIARY_WETH");
        require(IERC20Historical(USDC).balanceOf(BENEFICIARY) - beforeUsdc == dust, "BENEFICIARY_USDC");
        require(PAYEE.balance - beforePayee == INCLUSION_REFERENCE, "INCLUSION_PAYMENT");
        require(IERC20Historical(WETH).balanceOf(address(e)) == 0 && address(e).balance == 0, "NO_RESIDUE");
        emit MeasuredTokenSurplus(residual, dust);
        // No statement about sponsor acceptance, authentic owner, capture probability or monthly P&L.
    }

    function test_03_economic_floor_reverts_all_protocol_changes() public {
        HistoricalFlashExecutor e = _newExecutor();
        (uint112 r0Before, uint112 r1Before,) = IV2Historical(V2).getReserves();
        uint256 payeeBefore = PAYEE.balance;
        vm.expectRevert(abi.encodeWithSignature("Error(string)", "ECONOMIC_FLOOR"));
        vm.prank(OPERATOR);
        e.execute(INCLUSION_REFERENCE, 0, ACTUAL_SALE);
        (uint112 r0After, uint112 r1After,) = IV2Historical(V2).getReserves();
        require(r0Before == r0After && r1Before == r1After, "ROLLBACK_RESERVES");
        require(PAYEE.balance == payeeBefore && e.phase() == 0, "ROLLBACK_PAYMENTS");
        // A reverted included transaction can still consume gas. Rollback != loss-free sponsorship.
    }

    function test_04_untrusted_callbacks_fail() public {
        HistoricalFlashExecutor e = _newExecutor();
        vm.expectRevert(abi.encodeWithSignature("Error(string)", "V2_AUTH"));
        e.uniswapV2Call(address(e), 616687327559, 0, "");
        vm.expectRevert(abi.encodeWithSignature("Error(string)", "V3_AUTH"));
        e.uniswapV3SwapCallback(1, -1, "");
    }
}
