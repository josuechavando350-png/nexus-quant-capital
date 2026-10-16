// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import {EntryPoint} from "../lib/account-abstraction/contracts/core/EntryPoint.sol";
import {IEntryPoint} from "../lib/account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {PackedUserOperation} from "../lib/account-abstraction/contracts/interfaces/PackedUserOperation.sol";
import {MessageHashUtils} from "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import {NqcMorphoRobinhoodL2Lab, NqcMarketParams} from "../src/NqcMorphoRobinhoodL2Lab.sol";
import {NqcBudgetPaymasterFixture} from "../src/NqcBudgetPaymasterFixture.sol";
import {NqcEip191AccountFixture, NqcFullMorphoLocal, NqcLocalERC20,
    NqcLocalOracle, NqcLocalDex, NqcLocalBorrower} from "./Fixtures.sol";

interface VmNqc {
    struct Log { bytes32[] topics; bytes data; address emitter; }
    function deal(address, uint256) external;
    function fee(uint256) external;
    function txGasPrice(uint256) external;
    function chainId(uint256) external;
    function roll(uint256) external;
    function etch(address, bytes calldata) external;
    function store(address, bytes32, bytes32) external;
    function mockCall(address, bytes calldata, bytes calldata) external;
    function mockCallRevert(address, bytes calldata, bytes calldata) external;
    function clearMockedCalls() external;
    function readFile(string calldata) external view returns (string memory);
    function parseJsonBytes(string calldata, string calldata) external pure returns (bytes memory);
    function sign(uint256, bytes32) external returns (uint8, bytes32, bytes32);
    function addr(uint256) external returns (address);
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

/// @dev Setup separated from measured handleOps. Also reusable by localhost receipt runner.
contract NqcLocalScenario {
    EntryPoint public immutable ep;
    NqcEip191AccountFixture public account;
    NqcBudgetPaymasterFixture public paymaster;
    NqcFullMorphoLocal public morpho;
    NqcLocalERC20 public loan;
    NqcLocalERC20 public collateral;
    NqcLocalBorrower public borrower;
    NqcMorphoRobinhoodL2Lab public executor;
    NqcMarketParams public market;

    constructor(address entrypoint, bytes memory morphoCreation, address owner, uint256 rate)
        payable
    {
        ep = EntryPoint(payable(entrypoint));
        account = new NqcEip191AccountFixture(entrypoint, owner);
        paymaster = new NqcBudgetPaymasterFixture(IEntryPoint(entrypoint), address(account), 1e16, msg.value);
        paymaster.deposit{value:msg.value}();
        bytes memory init = abi.encodePacked(morphoCreation, abi.encode(address(this)));
        address deployed;
        assembly ("memory-safe") { deployed := create(0, add(init,32), mload(init)) }
        require(deployed.code.length > 800, "MORPHO_DEPLOY");
        morpho = NqcFullMorphoLocal(deployed);
        loan = new NqcLocalERC20();
        collateral = new NqcLocalERC20();
        NqcLocalOracle oracle = new NqcLocalOracle(13e35);
        morpho.enableIrm(address(0));
        morpho.enableLltv(625e15);
        market = NqcMarketParams(address(loan),address(collateral),address(oracle),address(0),625e15);
        morpho.createMarket(market);
        loan.mint(address(this),100_000e6);
        loan.approve(address(morpho),100_000e6);
        morpho.supply(market,100_000e6,0,address(this),"");
        borrower = new NqcLocalBorrower();
        collateral.mint(address(borrower),1_000e6);
        borrower.open(morpho,market,collateral,1_000e6,700e6);
        NqcLocalDex dex = new NqcLocalDex(loan,collateral,rate);
        loan.mint(address(dex),100_000e6);
        executor = new NqcMorphoRobinhoodL2Lab(address(morpho),address(dex),address(account),market);
        oracle.setPrice(1e36);
    }

    function rejectPostOp() external { paymaster.setRejectPostOp(true); }

    function unsignedOp(uint256 deadline, bytes32 id, uint256 callGas, uint256 postGas)
        external view returns (PackedUserOperation memory op)
    {
        op.sender = address(account);
        op.nonce = ep.getNonce(address(account),0);
        op.callData = abi.encodeCall(NqcEip191AccountFixture.execute, (address(executor),
            abi.encodeCall(NqcMorphoRobinhoodL2Lab.execute,
                (market,address(borrower),500e6,600e6,50e6,490e6,deadline,id))));
        op.accountGasLimits = bytes32((uint256(500_000)<<128)|callGas);
        op.preVerificationGas = 120_000;
        op.gasFees = bytes32((uint256(1 gwei)<<128)|uint256(3 gwei));
        op.paymasterAndData = abi.encodePacked(address(paymaster),bytes16(uint128(220_000)),bytes16(uint128(postGas)));
    }
}

contract NqcRobinhoodCycleTest {
    VmNqc constant vm = VmNqc(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant EP = 0x0000000071727De22E5E9d8BAf0edAc6f37da032;
    address payable constant BUNDLER = payable(address(0xBEEF));
    uint256 constant L2 = 90_000_000;
    uint256 constant KEY = 0x1234; // Public test fixture, never a funded real account.
    bytes32 constant ID = bytes32(uint256(201));
    EntryPoint ep;
    NqcLocalScenario scene;

    event GasMeasurement(string scenario, uint256 handleOpsCallGas, uint256 sponsorDebitWei,
        uint256 billedGas, uint256 postOpArgumentWei, uint256 reservedWei,
        uint256 loanSurplusRaw, bool success);

    function setUp() public {
        vm.chainId(4663);
        vm.roll(26_000_000); // Parent and L2 intentionally diverge.
        vm.fee(1 gwei);
        vm.txGasPrice(2 gwei);
        vm.deal(address(this),1 ether);
        vm.etch(EP,vm.parseJsonBytes(vm.readFile("runtime.json"),".runtime"));
        vm.store(EP,bytes32(0),bytes32(uint256(1))); // ReentrancyGuard constructor state.
        ep = EntryPoint(payable(EP));
        _clock(L2);
        scene = _scene(11e17,1e17);
    }
    function _scene(uint256 rate,uint256 deposit) internal returns(NqcLocalScenario) {
        bytes memory creation = vm.parseJsonBytes(vm.readFile("../morpho-native-lab/out/Morpho.sol/Morpho.json"),".bytecode.object");
        return new NqcLocalScenario{value:deposit}(EP,creation,vm.addr(KEY),rate);
    }
    function _clock(uint256 n) internal { vm.mockCall(address(100),hex"a3b1b31d",abi.encode(n)); }
    function _sign(PackedUserOperation memory op) internal returns(PackedUserOperation memory) {
        (uint8 v,bytes32 r,bytes32 s) = vm.sign(KEY,MessageHashUtils.toEthSignedMessageHash(ep.getUserOpHash(op)));
        op.signature = abi.encodePacked(r,s,v); return op;
    }
    function _op(uint256 deadline,uint256 callGas) internal returns(PackedUserOperation memory) {
        return _sign(scene.unsignedOp(deadline,ID,callGas,160_000));
    }
    function _run(PackedUserOperation memory op,string memory label,bool expectedSuccess)
        internal returns(uint256 debit)
    {
        NqcBudgetPaymasterFixture sponsor = scene.paymaster();
        uint256 beforeDeposit = ep.balanceOf(address(sponsor));
        uint256 beforeBudget = sponsor.budgetRemaining();
        uint256 beforeBeneficiary = BUNDLER.balance;
        bytes32 marketId = scene.executor().immutableMarketId();
        (,uint128 debtBefore,uint128 collBefore) = scene.morpho().position(marketId,address(scene.borrower()));
        PackedUserOperation[] memory ops = new PackedUserOperation[](1); ops[0]=op;
        vm.recordLogs();
        uint256 start = gasleft(); ep.handleOps(ops,BUNDLER); uint256 callGas = start-gasleft();
        VmNqc.Log[] memory logs = vm.getRecordedLogs();
        bool found; uint256 billed; uint256 cost;
        for(uint256 i; i<logs.length; i++) {
            if(logs[i].emitter==EP && logs[i].topics[0]==keccak256("UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)")) {
                (uint256 nonce,bool success,uint256 amount,uint256 usedGas) = abi.decode(logs[i].data,(uint256,bool,uint256,uint256));
                require(nonce==op.nonce && success==expectedSuccess,"EVENT_RESULT");
                require(logs[i].topics[1]==ep.getUserOpHash(op),"EVENT_HASH");
                cost=amount; billed=usedGas; found=true;
            }
        }
        require(found,"NO_USEROP_EVENT");
        debit=beforeDeposit-ep.balanceOf(address(sponsor));
        require(debit>0 && debit==cost && debit==BUNDLER.balance-beforeBeneficiary,"GAS_RECONCILIATION");
        require(cost==billed*2 gwei,"EFFECTIVE_PRICE");
        uint256 reserve=beforeBudget-sponsor.budgetRemaining();
        require(reserve>=debit,"RESERVE_UNDERCOUNTS_COST");
        require(ep.getNonce(address(scene.account()),0)==op.nonce+1,"NONCE");
        require(address(scene.account()).balance==0 && ep.balanceOf(address(scene.account()))==0,"ACCOUNT_PAID_GAS");
        (,uint128 debtAfter,uint128 collAfter) = scene.morpho().position(marketId,address(scene.borrower()));
        uint256 surplus=scene.loan().balanceOf(address(scene.account()));
        if(expectedSuccess) {
            require(debtAfter<debtBefore && collAfter<collBefore && surplus>=50e6,"LIQUIDATION_RESULT");
            require(scene.executor().used(ID),"EXECUTION_ID");
            require(sponsor.postOpCount()==1 && sponsor.postOpCostArgument()<debit,"POSTOP_IS_NOT_FINAL_COST");
        } else {
            require(debtAfter==debtBefore && collAfter==collBefore && surplus==0,"ROLLBACK");
            require(!scene.executor().used(ID),"FAILED_ID_ROLLBACK");
        }
        require(scene.loan().balanceOf(address(scene.executor()))==0 && scene.collateral().balanceOf(address(scene.executor()))==0,"STRANDED_ASSETS");
        require(scene.loan().allowance(address(scene.executor()),address(scene.morpho()))==0,"LEFTOVER_APPROVAL");
        emit GasMeasurement(label,callGas,debit,billed,sponsor.postOpCostArgument(),reserve,surplus,expectedSuccess);
    }
    function _rejected(PackedUserOperation memory op) internal {
        PackedUserOperation[] memory ops = new PackedUserOperation[](1);ops[0]=op;
        uint256 deposit=ep.balanceOf(address(scene.paymaster()));
        uint256 budget=scene.paymaster().budgetRemaining();
        (bool ok,) = EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,BUNDLER)));
        require(!ok,"EXPECTED_VALIDATION_REJECTION");
        require(ep.balanceOf(address(scene.paymaster()))==deposit && scene.paymaster().budgetRemaining()==budget,"REJECTED_POLICY_MUTATED");
        require(ep.getNonce(address(scene.account()),0)==0,"REJECTED_NONCE");
    }

    function testCanonicalRuntimeSuccessAtL2Boundary() public { _run(_op(L2,1_800_000),"success-original-limits",true); }
    function testSuccessWithReducedCallGas() public { _run(_op(L2,600_000),"success-reduced-limits",true); }
    function testExpiredL2DespiteUnchangedParentBlock() public { _clock(L2+1); _run(_op(L2,600_000),"expired-l2",false); }
    function testL1HeightCannotServeAsL2Expiry() public { _run(_op(block.number,600_000),"parent-height-rejected",false); }
    function testWrongChainFailsClosed() public { vm.chainId(1); _run(_op(L2,600_000),"wrong-chain",false); }
    function testMissingArbSysFailsClosed() public { vm.clearMockedCalls(); _run(_op(L2,600_000),"missing-arbsys",false); }
    function testMalformedArbSysFailsClosed() public { vm.mockCall(address(100),hex"a3b1b31d",hex"01"); _run(_op(L2,600_000),"malformed-arbsys",false); }
    function testRevertingArbSysFailsClosed() public { vm.mockCallRevert(address(100),hex"a3b1b31d",hex"01"); _run(_op(L2,600_000),"reverting-arbsys",false); }
    function testZeroArbSysFailsClosed() public { _clock(0); _run(_op(L2,600_000),"zero-arbsys",false); }
    function testExcessiveWindowFailsClosed() public { _run(_op(L2+17,600_000),"excessive-window",false); }
    function testWindowLimitAccepted() public { _run(_op(L2+16,600_000),"window-boundary",true); }
    function testSwapFailureStillChargesSponsor() public { scene=_scene(8e17,1e17); _run(_op(L2,600_000),"swap-revert",false); }
    function testCallOutOfGasStillChargesSponsor() public { _run(_op(L2,30_000),"call-out-of-gas",false); }
    function testPostOpFailureRollsBackLiquidationButKeepsReserve() public { scene.rejectPostOp(); _run(_op(L2,600_000),"postop-revert",false); require(scene.paymaster().postOpCount()==0,"POSTOP_WRITES_NOT_REVERTED"); }
    function testDeadlineTamperingInvalidatesSignature() public { PackedUserOperation memory a=_op(L2,600_000); PackedUserOperation memory b=scene.unsignedOp(L2+1,ID,600_000,160_000); a.callData=b.callData; _rejected(a); }
    function testUnfundedSponsorRejected() public { scene=_scene(11e17,0); _rejected(_op(L2,600_000)); }
    function testCumulativeBudgetStopsRepeatedSpend() public {
        scene=_scene(11e17,6e15);
        _clock(L2+1); _run(_op(L2,600_000),"budget-first-expired",false);
        PackedUserOperation memory op=_op(L2,600_000);
        PackedUserOperation[] memory ops=new PackedUserOperation[](1);ops[0]=op;
        (bool ok,)=EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,BUNDLER)));
        require(!ok && ep.getNonce(address(scene.account()),0)==1,"BUDGET_EXCEEDED");
    }
    function testNonceReplayRejected() public {
        PackedUserOperation memory op=_op(L2,600_000);_run(op,"before-replay",true);
        PackedUserOperation[] memory ops=new PackedUserOperation[](1);ops[0]=op;
        uint256 before=ep.balanceOf(address(scene.paymaster()));
        (bool ok,)=EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,BUNDLER)));
        require(!ok && ep.balanceOf(address(scene.paymaster()))==before,"REPLAY");
    }
    function testTwoOpsCannotOverreserveTheSameBudget() public {
        scene=_scene(11e17,6e15);
        PackedUserOperation[] memory ops=new PackedUserOperation[](2);
        ops[0]=_op(L2,600_000);
        ops[1]=scene.unsignedOp(L2,bytes32(uint256(202)),600_000,160_000);
        ops[1].nonce=1;
        ops[1]=_sign(ops[1]);
        uint256 deposit=ep.balanceOf(address(scene.paymaster()));
        (bool ok,)=EP.call(abi.encodeCall(EntryPoint.handleOps,(ops,BUNDLER)));
        require(!ok,"BUNDLE_BUDGET_OVERRUN");
        require(ep.balanceOf(address(scene.paymaster()))==deposit,"REJECTED_BUNDLE_DEBITED_SPONSOR");
        require(scene.paymaster().budgetRemaining()==6e15,"REJECTED_BUNDLE_RESERVATION");
        require(ep.getNonce(address(scene.account()),0)==0,"REJECTED_BUNDLE_NONCE");
        require(scene.loan().balanceOf(address(scene.account()))==0,"REJECTED_BUNDLE_EXECUTED");
    }
}
