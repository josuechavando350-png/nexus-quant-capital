// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import {EntryPoint} from "../lib/account-abstraction/contracts/core/EntryPoint.sol";
import {IEntryPoint} from "../lib/account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {IStakeManager} from "../lib/account-abstraction/contracts/interfaces/IStakeManager.sol";
import {PackedUserOperation} from "../lib/account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {NqcBudgetPaymasterFixture} from "../src/NqcBudgetPaymasterFixture.sol";
import {NqcEip191AccountFixture} from "./Fixtures.sol";

interface VmAdmission {
    function chainId(uint256) external;
    function deal(address,uint256) external;
    function etch(address,bytes calldata) external;
    function store(address,bytes32,bytes32) external;
    function load(address,bytes32) external view returns(bytes32);
    function readFile(string calldata) external view returns(string memory);
    function parseJsonBytes(string calldata,string calldata) external pure returns(bytes memory);
    function addr(uint256) external returns(address);
    function sign(uint256,bytes32) external returns(uint8,bytes32,bytes32);
    function prank(address) external;
    function record() external;
    function accesses(address) external returns(bytes32[] memory,bytes32[] memory);
    function warp(uint256) external;
    function fee(uint256) external;
    function txGasPrice(uint256) external;
}

contract AdmissionSink {
    uint256 public calls;
    function ping() external { calls++; }
}

/// @notice Narrow LOCAL stake/storage checks. NOT a bundler or ERC-7562 certification.
contract NqcAdmissionTest {
    VmAdmission constant vm = VmAdmission(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant EP = 0x0000000071727De22E5E9d8BAf0edAc6f37da032;
    uint256 constant KEY = 0x1234; // Public fake key, only local simulation.
    uint256 constant DEPOSIT = 1e17;
    uint256 constant LOCAL_MIN_STAKE = 2e16; // TEST POLICY, not Robinhood's bundler requirement.
    uint32 constant DELAY = 86400;
    EntryPoint ep;
    NqcBudgetPaymasterFixture paymaster;
    NqcEip191AccountFixture account;
    AdmissionSink sink;

    event ValidationStorage(bytes32[] reads,bytes32[] writes,uint256 contextBytes);
    event CapitalSeparation(uint256 deposit,uint256 stake,uint256 lifetimeBudget,bool locked);

    function setUp() public {
        vm.chainId(4663);
        vm.warp(1000);
        vm.fee(1 gwei);
        vm.txGasPrice(2 gwei);
        vm.deal(address(this),2 ether);
        vm.etch(EP,vm.parseJsonBytes(vm.readFile("runtime.json"),".runtime"));
        vm.store(EP,bytes32(uint256(2)),bytes32(uint256(1)));
        ep=EntryPoint(payable(EP));
        account=new NqcEip191AccountFixture(EP,vm.addr(KEY));
        paymaster=new NqcBudgetPaymasterFixture(IEntryPoint(EP),address(account),1e16,DEPOSIT);
        paymaster.deposit{value:DEPOSIT}();
        sink=new AdmissionSink();
    }

    function _op() internal returns(PackedUserOperation memory op) {
        op.sender=address(account);
        op.nonce=ep.getNonce(address(account),0);
        op.callData=abi.encodeCall(NqcEip191AccountFixture.execute,
            (address(sink),abi.encodeCall(AdmissionSink.ping,())));
        op.accountGasLimits=bytes32((uint256(500_000)<<128)|uint256(100_000));
        op.preVerificationGas=120_000;
        op.gasFees=bytes32((uint256(1 gwei)<<128)|uint256(3 gwei));
        op.paymasterAndData=abi.encodePacked(address(paymaster),bytes16(uint128(220_000)),bytes16(uint128(160_000)));
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(KEY,MessageHashUtils.toEthSignedMessageHash(ep.getUserOpHash(op)));
        op.signature=abi.encodePacked(r,s,v);
    }

    function _stakeReady() internal view returns(bool) {
        IStakeManager.DepositInfo memory d=ep.getDepositInfo(address(paymaster));
        return d.staked && d.withdrawTime==0 && d.stake>=LOCAL_MIN_STAKE && d.unstakeDelaySec>=DELAY;
    }

    function _run() internal {
        PackedUserOperation[] memory ops=new PackedUserOperation[](1);
        ops[0]=_op();
        ep.handleOps(ops,payable(address(0xBEEF)));
        require(sink.calls()==1 && paymaster.postOpCount()==1,"LOCAL_EXECUTION_FAILED");
    }

    function testDepositDoesNotSatisfyStakeRequirement() public view {
        IStakeManager.DepositInfo memory d=ep.getDepositInfo(address(paymaster));
        require(d.deposit==DEPOSIT && d.stake==0 && !d.staked && !_stakeReady(),"CAPITAL_CONFLATED");
    }

    function testUnstakedValidationWritesOwnBudgetAndReturnsContext() public {
        PackedUserOperation memory op=_op();
        bytes32 hash=ep.getUserOpHash(op);
        vm.record();
        vm.prank(EP);
        (bytes memory context,uint256 validationData)=paymaster.validatePaymasterUserOp(op,hash,3e15);
        (bytes32[] memory reads,bytes32[] memory writes)=vm.accesses(address(paymaster));
        // Ownable occupies slot 0; budgetRemaining is the non-associated slot 1.
        require(reads.length>0,"NO_VALIDATION_READ");
        for(uint256 i;i<reads.length;i++) require(reads[i]==bytes32(uint256(1)),"VALIDATION_READ_CHANGED");
        require(writes.length==1 && writes[0]==bytes32(uint256(1)),"VALIDATION_WRITE_CHANGED");
        require(context.length==64 && validationData==0 && !_stakeReady(),"CONTEXT_STAKE_MISMATCH");
        require(paymaster.budgetRemaining()==DEPOSIT-3e15,"RESERVATION");
        emit ValidationStorage(reads,writes,context.length);
    }

    function testEntryPointConstructorStateUsesCompilerSlotTwo() public view {
        require(vm.load(EP,bytes32(uint256(2)))==bytes32(uint256(1)),"REENTRANCY_STATE");
        require(vm.load(EP,bytes32(0))==bytes32(0),"MAPPING_ROOT_WRITTEN");
    }

    function testHandleOpsSuccessDoesNotProveMempoolAdmission() public {
        require(!_stakeReady(),"UNEXPECTED_STAKE");
        _run();
        require(!_stakeReady(),"HANDLEOPS_CREATED_STAKE");
    }

    function testStakeIsSeparateFromDepositAndBudget() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY);
        IStakeManager.DepositInfo memory d=ep.getDepositInfo(address(paymaster));
        require(_stakeReady() && d.deposit==DEPOSIT && paymaster.budgetRemaining()==DEPOSIT,"STAKE_SEPARATION");
        emit CapitalSeparation(d.deposit,d.stake,paymaster.budgetRemaining(),d.staked);
        _run();
        require(ep.getDepositInfo(address(paymaster)).stake==LOCAL_MIN_STAKE,"GAS_CONSUMED_STAKE");
        require(ep.balanceOf(address(paymaster))<DEPOSIT,"GAS_NOT_PAID_FROM_DEPOSIT");
    }

    function testInsufficientStakeFailsLocalPolicy() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE-1}(DELAY);
        require(!_stakeReady(),"SHORT_STAKE_ALLOWED");
    }

    function testInsufficientDelayFailsLocalPolicy() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY-1);
        require(!_stakeReady(),"SHORT_DELAY_ALLOWED");
    }

    function testUnlockedStakeFailsEvenWhileValueRemains() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY);
        paymaster.unlockStake();
        IStakeManager.DepositInfo memory d=ep.getDepositInfo(address(paymaster));
        require(!_stakeReady() && d.stake==LOCAL_MIN_STAKE && d.withdrawTime==1000+DELAY,"UNLOCK_POLICY");
    }

    function testStakeCannotReplaceGasDeposit() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY);
        paymaster.withdrawTo(payable(address(0xCAFE)),DEPOSIT);
        require(_stakeReady() && ep.balanceOf(address(paymaster))==0,"PRECONDITION");
        PackedUserOperation[] memory ops=new PackedUserOperation[](1);
        ops[0]=_op();
        (bool ok,)=EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,payable(address(0xBEEF)))));
        require(!ok && sink.calls()==0 && ep.getDepositInfo(address(paymaster)).stake==LOCAL_MIN_STAKE,"STAKE_SPENT_AS_DEPOSIT");
    }

    function testOnlyOwnerCanManageStake() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY);
        vm.prank(address(0xBAD));
        (bool ok,)=address(paymaster).call(abi.encodeWithSignature("unlockStake()"));
        require(!ok && _stakeReady(),"UNAUTHORIZED_STAKE_MANAGEMENT");
    }

    function testWithdrawalDelayAndCapitalRemainSeparate() public {
        paymaster.addStake{value:LOCAL_MIN_STAKE}(DELAY);
        paymaster.unlockStake();
        (bool early,)=address(paymaster).call(abi.encodeWithSignature("withdrawStake(address)",address(0xCAFE)));
        require(!early,"EARLY_WITHDRAWAL");
        vm.warp(1000+DELAY);
        paymaster.withdrawStake(payable(address(0xCAFE)));
        require(address(0xCAFE).balance==LOCAL_MIN_STAKE && ep.balanceOf(address(paymaster))==DEPOSIT,"WITHDRAWAL_RECONCILIATION");
        require(!_stakeReady() && paymaster.budgetRemaining()==DEPOSIT,"WITHDRAWAL_POLICY");
    }
}
