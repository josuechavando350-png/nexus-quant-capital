// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import {EntryPoint} from "../lib/account-abstraction/contracts/core/EntryPoint.sol";
import {IEntryPoint} from "../lib/account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {PackedUserOperation} from "../lib/account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {NqcMorphoRobinhoodL2Lab, NqcMarketParams} from "./NqcMorphoRobinhoodL2Lab.sol";
import {NqcBudgetPaymasterFixture} from "./NqcBudgetPaymasterFixture.sol";
import {NqcEip191AccountFixture} from "../test/Fixtures.sol";
import {NqcHistoricalNetRoute} from "./NqcHistoricalNetRoute.sol";

/// @notice Local fixture provisioning only. Actual protocol contracts come from the witness.
contract NqcHistoricalScenario {
    EntryPoint public immutable ep;
    NqcEip191AccountFixture public immutable account;
    NqcBudgetPaymasterFixture public immutable paymaster;
    NqcHistoricalNetRoute public immutable router;
    NqcMorphoRobinhoodL2Lab public immutable executor;
    NqcMarketParams public market;

    constructor(address entrypoint, address owner) payable {
        ep = EntryPoint(payable(entrypoint));
        account = new NqcEip191AccountFixture(entrypoint, owner);
        paymaster = new NqcBudgetPaymasterFixture(IEntryPoint(entrypoint), address(account), 1e16, msg.value);
        paymaster.deposit{value: msg.value}();
        router = new NqcHistoricalNetRoute();
        market = NqcMarketParams(router.USDG(), router.WSNET(),
            0xCDE9599059f8Ae6D6B9F33A0aF7877827ec75F16,
            0x2BD3d5965B26B51814AC95127B2b80dD6CcC0fa1, 625000000000000000);
        executor = new NqcMorphoRobinhoodL2Lab(
            0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010, address(router), address(account), market);
    }

    function unsignedOp(uint256 deadline, uint256 minProfit, uint256 minimumOut, uint256 callGas)
        external view returns (PackedUserOperation memory op)
    {
        op.sender = address(account);
        op.nonce = ep.getNonce(address(account), 0);
        op.callData = abi.encodeCall(NqcEip191AccountFixture.execute, (address(executor),
            abi.encodeCall(NqcMorphoRobinhoodL2Lab.execute, (market,
                0x689Afbae02a62d10e9a20A6f76B08D94eB7361f0,
                93436250743843184, 194034132, minProfit, minimumOut, deadline, bytes32(uint256(20261016))))));
        op.accountGasLimits = bytes32((uint256(500000) << 128) | callGas);
        op.preVerificationGas = 80000;
        op.gasFees = bytes32((uint256(1000000) << 128) | uint256(2000000000));
        op.paymasterAndData = abi.encodePacked(address(paymaster), uint128(200000), uint128(160000));
        op.signature = new bytes(65);
    }
}
