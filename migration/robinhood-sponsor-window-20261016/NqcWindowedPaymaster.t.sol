// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import {EntryPoint} from "../lib/account-abstraction/contracts/core/EntryPoint.sol";
import {IEntryPoint} from "../lib/account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {PackedUserOperation} from "../lib/account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {NqcWindowedPaymasterFixture} from "../src/NqcWindowedPaymasterFixture.sol";
import {NqcEip191AccountFixture} from "./Fixtures.sol";

interface VmWindow {
    function chainId(uint256) external;
    function deal(address,uint256) external;
    function etch(address,bytes calldata) external;
    function store(address,bytes32,bytes32) external;
    function readFile(string calldata) external view returns(string memory);
    function parseJsonBytes(string calldata,string calldata) external pure returns(bytes memory);
    function addr(uint256) external returns(address);
    function sign(uint256,bytes32) external returns(uint8,bytes32,bytes32);
    function prank(address) external;
    function warp(uint256) external;
    function fee(uint256) external;
    function txGasPrice(uint256) external;
}

contract WindowSink {
    uint256 public calls;
    function ping() external { calls++; }
}

contract NqcWindowedPaymasterTest {
    VmWindow constant vm = VmWindow(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant EP = 0x0000000071727De22E5E9d8BAf0edAc6f37da032;
    address constant PM = address(0x9876);
    uint256 constant KEY = 0x1234; // Public laboratory key only.
    uint256 constant CAP = 0.002 ether;
    uint256 constant DEPOSIT = 0.01 ether;
    EntryPoint ep;
    NqcEip191AccountFixture account;
    NqcWindowedPaymasterFixture paymaster;
    WindowSink sink;
    PackedUserOperation storedOp;

    function setUp() public {
        vm.chainId(4663); vm.warp(1000); vm.fee(1 gwei); vm.txGasPrice(2 gwei);
        vm.deal(address(this),1 ether);
        vm.etch(EP,vm.parseJsonBytes(vm.readFile("runtime.json"),".runtime"));
        vm.store(EP,bytes32(uint256(2)),bytes32(uint256(1)));
        ep=EntryPoint(payable(EP));
        account=new NqcEip191AccountFixture(EP,vm.addr(KEY));
        sink=new WindowSink();
        PackedUserOperation memory op;
        op.sender=address(account);
        op.callData=abi.encodeCall(NqcEip191AccountFixture.execute,(address(sink),abi.encodeCall(WindowSink.ping,())));
        op.accountGasLimits=bytes32((uint256(150000)<<128)|uint256(100000));
        op.preVerificationGas=80000;
        op.gasFees=bytes32((uint256(1 gwei)<<128)|uint256(3 gwei));
        op.paymasterAndData=abi.encodePacked(PM,uint128(100000),uint128(0));
        NqcWindowedPaymasterFixture implementation = new NqcWindowedPaymasterFixture(
            IEntryPoint(EP),address(account),ep.getUserOpHash(op),CAP,CAP,1000,1002);
        // Fixed-address fixture initialization only. Not a deployment method.
        vm.etch(PM,address(implementation).code);
        vm.store(PM,bytes32(0),bytes32(uint256(uint160(address(this)))));
        vm.store(PM,bytes32(uint256(1)),bytes32(CAP));
        paymaster=NqcWindowedPaymasterFixture(PM);
        ep.depositTo{value:DEPOSIT}(PM);
        storedOp=_sign(op);
    }

    function _sign(PackedUserOperation memory op) internal returns(PackedUserOperation memory) {
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(KEY,MessageHashUtils.toEthSignedMessageHash(ep.getUserOpHash(op)));
        op.signature=abi.encodePacked(r,s,v); return op;
    }
    function _run(PackedUserOperation memory op) internal returns(bool ok, bytes memory reason) {
        PackedUserOperation[] memory ops=new PackedUserOperation[](1); ops[0]=op;
        return EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,payable(address(0xBEEF)))));
    }
    function _outside(uint256 time) internal {
        vm.warp(time);
        (bool ok,bytes memory reason)=_run(storedOp);
        require(!ok && keccak256(reason)==keccak256(abi.encodeWithSignature(
            "FailedOp(uint256,string)",0,"AA32 paymaster expired or not due")),"WRONG_REJECTION");
        require(sink.calls()==0 && ep.balanceOf(PM)==DEPOSIT && paymaster.budgetRemaining()==CAP,"REVERT_ROLLBACK");
        require(ep.getNonce(address(account),0)==0,"NONCE_ROLLBACK");
    }
    function _inside(uint256 time) internal {
        vm.warp(time); (bool ok,)=_run(storedOp);
        require(ok && sink.calls()==1 && ep.balanceOf(PM)<DEPOSIT,"VALID_EXECUTION");
        require(paymaster.budgetRemaining()==CAP-430000*3 gwei,"FULL_PREFUND_RESERVATION");
    }
    function testRejectsBeforeValidAfter() public { _outside(999); }
    function testAcceptsExactlyValidAfter() public { _inside(1000); }
    function testAcceptsInsideWindow() public { _inside(1001); }
    function testAcceptsExactlyValidUntil() public { _inside(1002); }
    function testRejectsAfterValidUntil() public { _outside(1003); }
    function testReturnsWindowAndEmptyContextWithoutReadingClock() public {
        vm.warp(999); PackedUserOperation memory op=storedOp;
        bytes32 hash=ep.getUserOpHash(op);
        vm.prank(EP);
        (bytes memory context,uint256 data)=paymaster.validatePaymasterUserOp(op,hash,1);
        require(context.length==0 && data==((uint256(1002)<<160)|(uint256(1000)<<208)),"VALIDATION_DATA");
    }
    function testNoPostOpCalledForEmptyContext() public { _inside(1001); }
    function testCalldataMutationDeniedDespiteValidAccountSignature() public {
        PackedUserOperation memory op=storedOp;
        op.callData=abi.encodeCall(NqcEip191AccountFixture.execute,(address(0xCAFE),hex""));
        (bool ok,)=_run(_sign(op)); require(!ok && sink.calls()==0 && ep.balanceOf(PM)==DEPOSIT,"CALLDATA_NOT_BOUND");
    }
    function testFeeMutationDeniedDespiteValidAccountSignature() public {
        PackedUserOperation memory op=storedOp; op.gasFees=bytes32((uint256(1 gwei)<<128)|uint256(4 gwei));
        (bool ok,)=_run(_sign(op)); require(!ok && paymaster.budgetRemaining()==CAP,"FEES_NOT_BOUND");
    }
    function testNonceReplayDenied() public {
        _inside(1001); (bool ok,)=_run(storedOp); require(!ok && sink.calls()==1,"REPLAY");
    }
    function testDifferentChainDenied() public {
        vm.chainId(4664); PackedUserOperation memory op=storedOp;
        (bool ok,)=_run(_sign(op)); require(!ok && sink.calls()==0,"CHAIN_NOT_BOUND");
    }
    function testDirectCallerDenied() public {
        PackedUserOperation memory op=storedOp;
        (bool ok,)=PM.call(abi.encodeWithSignature("validatePaymasterUserOp((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes),bytes32,uint256)",op,ep.getUserOpHash(op),1));
        require(!ok && paymaster.budgetRemaining()==CAP,"UNTRUSTED_CALLER");
    }
    function testZeroUnlimitedAndExcessiveWindowsDenied() public {
        try new NqcWindowedPaymasterFixture(IEntryPoint(EP),address(account),bytes32(uint256(1)),CAP,CAP,0,1) { revert("ZERO_WINDOW"); } catch {}
        try new NqcWindowedPaymasterFixture(IEntryPoint(EP),address(account),bytes32(uint256(1)),CAP,CAP,1000,0) { revert("UNLIMITED_WINDOW"); } catch {}
        try new NqcWindowedPaymasterFixture(IEntryPoint(EP),address(account),bytes32(uint256(1)),CAP,CAP,1000,1061) { revert("LONG_WINDOW"); } catch {}
    }
    function testThirtyOneSecondWindowCanBeConfigured() public {
        NqcWindowedPaymasterFixture fixture=new NqcWindowedPaymasterFixture(
            IEntryPoint(EP),address(account),bytes32(uint256(1)),CAP,CAP,1000,1031);
        require(fixture.validAfter()==1000 && fixture.validUntil()==1031,"WINDOW_CONFIG");
    }
    function testRejectsZeroOrOverCapPrefund() public {
        PackedUserOperation memory op=storedOp;
        bytes32 hash=ep.getUserOpHash(op);
        bytes memory data=abi.encodeWithSignature("validatePaymasterUserOp((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes),bytes32,uint256)",op,hash,0);
        vm.prank(EP); (bool zeroOk,)=PM.call(data);
        data=abi.encodeWithSignature("validatePaymasterUserOp((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes),bytes32,uint256)",op,hash,CAP+1);
        vm.prank(EP); (bool excessOk,)=PM.call(data);
        require(!zeroOk && !excessOk && paymaster.budgetRemaining()==CAP,"PREFUND_CAP");
    }
    function testDoesNotRecycleReservedBudget() public {
        PackedUserOperation memory op=storedOp;
        bytes32 hash=ep.getUserOpHash(op);
        vm.prank(EP); paymaster.validatePaymasterUserOp(op,hash,CAP);
        bytes memory data=abi.encodeWithSignature("validatePaymasterUserOp((address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes),bytes32,uint256)",op,hash,1);
        vm.prank(EP); (bool ok,)=PM.call(data);
        require(!ok && paymaster.budgetRemaining()==0,"BUDGET_REUSED");
    }
}
