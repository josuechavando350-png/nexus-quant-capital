// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "./morpho_liquidation_probe.sol";

interface HistoricalVm {
    struct Log { bytes32[] topics; bytes data; address emitter; }
    function createSelectFork(string calldata, bytes32) external returns (uint256);
    function load(address, bytes32) external view returns (bytes32);
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
    function transact(bytes32) external;
}

/// @notice Compile-only H25 scaffold, deliberately abstract and never executed.
/// @dev Implementing the missing pins requires a separate evidence review.
/// No deal, mint, etch, warp, roll, storage writes or public broadcast.
abstract contract OmegaMorphoHistoricalHarness {
    HistoricalVm constant vm = HistoricalVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
    address constant POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;
    address constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address constant BORROWER = 0x7A0575018B57cB64434Fcd794f4F0C624fD0Fbd3;
    bytes32 constant TARGET = 0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba;
    bytes32 constant PARENT = 0x42cf44b75185587327a1aa8fc859cc5f49a639e7256547511430d6068b6f09ab;
    bytes32 constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    bytes32 constant MORPHO_CODE = 0xfa259fa317198f88f5fa3c119f06c066295dbcd47d715e0a30e1bcf94c02ef8c;
    bytes32 constant POOL_CODE = 0x96107dc4006b4c7fecd1827cfb275ffeef31e6194cd50466f85f8eb24ccf2679;
    // Single-provider WETH observation only; future admission needs second-provider parity.
    bytes32 constant WETH_CODE = 0xd0a06b12ac47863b5c7be4185c2deaad1c61557033f56c7d4ea74429cbb25e23;
    bytes32 constant RECEIPT_LOGS = 0xb9168897e4a396ded65303ee084918c09e2e525e00567ded2a58d1d149557196;
    bytes32 constant LIQUIDATION = 0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286;
    uint256 constant PRINCIPAL = 10684013854557827871;
    uint256 constant COLLATERAL = 10780169979248848321;

    // No concrete implementation is supplied in H25. There is no runnable fork test.
    function _reviewedInputs() internal pure virtual returns (address implementation, bytes32 codeHash);

    event HistoricalExperiment(uint256 surplusWei, uint256 innerExecutionGas);

    function _openExactPrestate(string memory rpc) internal {
        (address implementation, bytes32 codeHash) = _reviewedInputs();
        require(implementation != address(0) && codeHash != bytes32(0), "missing reviewed pins");
        // Transaction-hash forks replay preceding transactions, unlike block+warp.
        vm.createSelectFork(rpc, TARGET);
        require(block.chainid == 1 && block.number == 25938048 && block.timestamp == 1788935615
                && blockhash(block.number-1) == PARENT, "wrong prestate anchor");
        require(MORPHO.codehash == MORPHO_CODE && POOL.codehash == POOL_CODE
                && WETH.codehash == WETH_CODE, "runtime mismatch");
        require(vm.load(POOL, IMPLEMENTATION_SLOT) == bytes32(uint256(uint160(implementation)))
                && implementation.codehash == codeHash, "implementation mismatch");
    }

    function _plan(uint256 minimum, bytes32 id) internal pure returns (OmegaMorphoLiquidationProbe.Plan memory) {
        return OmegaMorphoLiquidationProbe.Plan(1,25938048,1788935615,PARENT,BORROWER,PRINCIPAL,minimum,id);
    }

    function _snapshot(OmegaMorphoLiquidationProbe probe) internal view returns (bytes32) {
        OmegaToken token = OmegaToken(WETH);
        return keccak256(abi.encode(token.balanceOf(MORPHO), token.balanceOf(POOL),
            token.balanceOf(address(probe)), token.balanceOf(address(this)),
            token.allowance(address(probe), MORPHO), token.allowance(address(probe), POOL),
            probe.phase(), probe.activePlanHash(), probe.callbackCount(), probe.consumed(bytes32(uint256(25)))));
    }

    function _runLiquidation(string memory rpc) internal {
        _openExactPrestate(rpc);
        OmegaMorphoLiquidationProbe probe = new OmegaMorphoLiquidationProbe(
            address(this), MORPHO, POOL, WETH, MORPHO_CODE, POOL_CODE, WETH_CODE);
        OmegaToken token = OmegaToken(WETH);
        require(token.balanceOf(address(probe)) == 0 && address(probe).balance == 0, "prefunded probe");
        bytes32 beforeRejected = _snapshot(probe);
        (bool ok, bytes memory reason) = address(probe).call(abi.encodeCall(probe.execute,
            (_plan(type(uint128).max, bytes32(uint256(25))))));
        require(!ok && reason.length == 4 && bytes4(reason) == OmegaMorphoLiquidationProbe.InsufficientSurplus.selector,
                "wrong negative result");
        require(_snapshot(probe) == beforeRejected, "negative state drift");
        uint256 lenderBefore = token.balanceOf(MORPHO);
        uint256 operatorBefore = token.balanceOf(address(this));
        vm.recordLogs();
        uint256 gasBefore = gasleft();
        uint256 surplus = probe.execute(_plan(1, bytes32(uint256(25))));
        uint256 innerGas = gasBefore-gasleft();
        HistoricalVm.Log[] memory logs = vm.getRecordedLogs();
        uint256 legs;
        for (uint256 i; i < logs.length; i++) {
            HistoricalVm.Log memory item = logs[i];
            if (item.emitter != POOL || item.topics.length == 0 || item.topics[0] != LIQUIDATION) continue;
            legs++;
            require(item.topics.length == 4 && item.topics[1] == bytes32(uint256(uint160(WETH)))
                && item.topics[2] == bytes32(uint256(uint160(WETH)))
                && item.topics[3] == bytes32(uint256(uint160(BORROWER))), "wrong liquidation parties");
            (uint256 debt, uint256 collateral, address liquidator, bool aToken) =
                abi.decode(item.data, (uint256,uint256,address,bool));
            require(debt == PRINCIPAL && collateral == COLLATERAL && liquidator == address(probe) && !aToken,
                "wrong liquidation amounts");
        }
        require(legs == 1 && surplus == COLLATERAL-PRINCIPAL, "wrong liquidation delta");
        require(token.balanceOf(MORPHO) == lenderBefore && token.balanceOf(address(this))-operatorBefore == surplus,
                "settlement mismatch");
        require(token.balanceOf(address(probe)) == 0 && token.allowance(address(probe), MORPHO) == 0
                && token.allowance(address(probe), POOL) == 0 && probe.callbackCount() == 1
                && probe.phase() == 0 && probe.activePlanHash() == bytes32(0)
                && probe.consumed(bytes32(uint256(25))), "uncleared state");
        // Diagnostic after a negative probe: warmed accesses, no deployment/intrinsic gas or Titan economics.
        emit HistoricalExperiment(surplus, innerGas);
    }

    function _replayOriginalReceipt(string memory rpc) internal {
        _openExactPrestate(rpc);
        vm.recordLogs();
        vm.transact(TARGET); // Local fork replay only, never a public transaction.
        HistoricalVm.Log[] memory logs = vm.getRecordedLogs();
        bytes32 rolling;
        for (uint256 i; i < logs.length; i++) {
            rolling = keccak256(abi.encodePacked(rolling, logs[i].emitter,
                keccak256(abi.encodePacked(logs[i].topics)), keccak256(logs[i].data)));
        }
        require(logs.length == 17 && rolling == RECEIPT_LOGS, "original receipt log mismatch");
    }
}
