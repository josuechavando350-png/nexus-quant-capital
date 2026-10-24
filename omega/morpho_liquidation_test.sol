// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
import {OmegaMorphoLiquidationProbe,OmegaToken} from "../src/morpho_liquidation_probe.sol";

interface ProbeVm {
    function roll(uint256) external;
    function warp(uint256) external;
    function setBlockhash(uint256,bytes32) external;
    function deal(address,uint256) external;
    function etch(address,bytes calldata) external;
}
contract ProbeTokenFixture {
    mapping(address=>uint256) public balanceOf;
    mapping(address=>mapping(address=>uint256)) public allowance;
    uint256 public totalSupply;
    address public failedRecipient;
    bool public failApprove;
    function mint(address a,uint256 n) external {balanceOf[a]+=n;totalSupply+=n;}
    function configure(address recipient,bool approveFailure) external {failedRecipient=recipient;failApprove=approveFailure;}
    function approve(address a,uint256 n) external returns(bool) {if(failApprove)return false;allowance[msg.sender][a]=n;return true;}
    function transfer(address a,uint256 n) external returns(bool) {if(a==failedRecipient)return false;balanceOf[msg.sender]-=n;balanceOf[a]+=n;return true;}
    function transferFrom(address a,address b,uint256 n) external returns(bool) {allowance[a][msg.sender]-=n;balanceOf[a]-=n;balanceOf[b]+=n;return true;}
}
contract ProbePoolFixture {
    ProbeTokenFixture public immutable token;
    uint256 public bonus=1 ether;
    uint256 public calls;
    bool public reject;
    bool public attemptNestedCallback;
    constructor(ProbeTokenFixture t) {token=t;}
    function configure(uint256 n,bool fail,bool nested) external {bonus=n;reject=fail;attemptNestedCallback=nested;}
    function liquidationCall(address collateral,address debt,address borrower,uint256 amount,bool aToken) external {
        require(!reject,"POOL_REJECT");
        require(collateral==address(token)&&debt==address(token)&&borrower!=address(0)&&!aToken,"POOL_ARGUMENTS");
        calls++;
        if(attemptNestedCallback){
            (bool ok,)=msg.sender.call(abi.encodeWithSignature("onMorphoFlashLoan(uint256,bytes)",amount,bytes("forged")));
            require(!ok,"NESTED_CALLBACK_ACCEPTED");
        }
        require(token.transferFrom(msg.sender,address(this),amount),"POOL_PULL");
        token.mint(msg.sender,amount+bonus); // Offline fixture only; never a historical fork.
    }
}
contract ProbeLenderFixture {
    ProbeTokenFixture public immutable token;
    uint256 public mode;
    constructor(ProbeTokenFixture t){token=t;}
    function configure(uint256 n) external {mode=n;}
    function flashLoan(address asset,uint256 amount,bytes calldata data) external {
        require(asset==address(token),"ASSET");
        require(token.transfer(msg.sender,mode==7?amount-1:amount),"LENDER_TRANSFER");
        if(mode==1)return;
        bytes memory payload=mode==3?bytes("changed"):data;
        OmegaMorphoLiquidationProbe(msg.sender).onMorphoFlashLoan(mode==2?amount+1:amount,payload);
        if(mode==4)OmegaMorphoLiquidationProbe(msg.sender).onMorphoFlashLoan(amount,data);
        if(mode!=5)require(token.transferFrom(msg.sender,address(this),amount),"REPAYMENT");
    }
    function lateCallback(address probe,uint256 amount,bytes calldata data) external {
        OmegaMorphoLiquidationProbe(probe).onMorphoFlashLoan(amount,data);
    }
}
contract ProbeOtherCaller {
    function run(OmegaMorphoLiquidationProbe probe,OmegaMorphoLiquidationProbe.Plan calldata p) external {
        probe.execute(p);
    }
}

/// @dev Entirely offline mocks. Mint/deal/etch here are adversarial fixtures,
/// not evidence of historical liquidity, sponsorship or unsubsidized profit.
contract OmegaMorphoLiquidationUnitTest {
    ProbeVm constant vm=ProbeVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    bytes32 constant PARENT=keccak256("OFFLINE_PARENT");
    ProbeTokenFixture token;
    ProbeLenderFixture lender;
    ProbePoolFixture pool;
    OmegaMorphoLiquidationProbe probe;
    function setUp() public {
        vm.roll(101);vm.warp(1000);vm.setBlockhash(100,PARENT);
        token=new ProbeTokenFixture();lender=new ProbeLenderFixture(token);pool=new ProbePoolFixture(token);
        token.mint(address(lender),1_000_000 ether);
        probe=new OmegaMorphoLiquidationProbe(address(this),address(lender),address(pool),address(token),
            address(lender).codehash,address(pool).codehash,address(token).codehash);
    }
    function plan() internal view returns(OmegaMorphoLiquidationProbe.Plan memory p) {
        p=OmegaMorphoLiquidationProbe.Plan(block.chainid,101,1000,PARENT,address(0xb0),10 ether,1,keccak256("ID"));
    }
    function state(bytes32 id) internal view returns(bytes32) {
        return keccak256(abi.encode(token.balanceOf(address(lender)),token.balanceOf(address(pool)),
            token.balanceOf(address(probe)),token.balanceOf(address(this)),token.totalSupply(),
            token.allowance(address(probe),address(lender)),token.allowance(address(probe),address(pool)),
            probe.phase(),probe.activePlanHash(),probe.callbackCount(),probe.consumed(id),pool.calls()));
    }
    function reject(OmegaMorphoLiquidationProbe.Plan memory p,bytes4 expected) internal {
        bytes32 beforeState=state(p.executionId);
        (bool ok,bytes memory data)=address(probe).call(abi.encodeCall(probe.execute,(p)));
        require(!ok&&data.length>=4&&bytes4(data)==expected,"WRONG_REJECTION");
        require(state(p.executionId)==beforeState,"REJECTION_NOT_ATOMIC");
    }
    function testSettlementPreservesLenderAndSweepsOnlyFreshSurplus() public {
        uint256 lenderBefore=token.balanceOf(address(lender));
        require(probe.execute(plan())==1 ether,"SURPLUS");
        require(token.balanceOf(address(lender))==lenderBefore,"LENDER");
        require(token.balanceOf(address(this))==1 ether&&token.balanceOf(address(probe))==0,"SWEEP");
        require(token.allowance(address(probe),address(pool))==0&&token.allowance(address(probe),address(lender))==0,"APPROVALS");
        require(probe.phase()==0&&probe.activePlanHash()==0&&probe.callbackCount()==1,"IDLE");
    }
    function testMinimumSurplusFailureRollsBackAllBalancesAndIdentity() public {
        OmegaMorphoLiquidationProbe.Plan memory p=plan();p.minimumSurplus=1 ether+1;
        reject(p,OmegaMorphoLiquidationProbe.InsufficientSurplus.selector);
    }
    function testZeroBonusCannotBePresentedAsSurplus() public {pool.configure(0,false,false);reject(plan(),OmegaMorphoLiquidationProbe.InsufficientSurplus.selector);}
    function testPrefundedTokensCannotSubsidizeExecution() public {token.mint(address(probe),1);reject(plan(),OmegaMorphoLiquidationProbe.Prefunded.selector);}
    function testPrefundedNativeBalanceIsRejected() public {vm.deal(address(probe),1);reject(plan(),OmegaMorphoLiquidationProbe.Prefunded.selector);}
    function testInsufficientLenderLiquidity() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.principal=1_000_001 ether;reject(p,OmegaMorphoLiquidationProbe.Liquidity.selector);}
    function testWrongChain() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.chainId++;reject(p,OmegaMorphoLiquidationProbe.AnchorMismatch.selector);}
    function testWrongBlock() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.blockNumber++;reject(p,OmegaMorphoLiquidationProbe.AnchorMismatch.selector);}
    function testWrongTimestamp() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.timestamp++;reject(p,OmegaMorphoLiquidationProbe.AnchorMismatch.selector);}
    function testWrongParent() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.parentHash=keccak256("OTHER");reject(p,OmegaMorphoLiquidationProbe.AnchorMismatch.selector);}
    function testZeroParent() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.parentHash=0;reject(p,OmegaMorphoLiquidationProbe.AnchorMismatch.selector);}
    function testZeroBorrower() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.borrower=address(0);reject(p,OmegaMorphoLiquidationProbe.InvalidPlan.selector);}
    function testZeroPrincipal() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.principal=0;reject(p,OmegaMorphoLiquidationProbe.InvalidPlan.selector);}
    function testZeroMinimum() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.minimumSurplus=0;reject(p,OmegaMorphoLiquidationProbe.InvalidPlan.selector);}
    function testZeroIdentity() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();p.executionId=0;reject(p,OmegaMorphoLiquidationProbe.InvalidPlan.selector);}
    function testConsumedIdentityCannotReplay() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();probe.execute(p);reject(p,OmegaMorphoLiquidationProbe.Consumed.selector);}
    function testSecondDistinctPlanStartsWithCleanState() public {OmegaMorphoLiquidationProbe.Plan memory p=plan();probe.execute(p);p.executionId=keccak256("SECOND");require(probe.execute(p)==1 ether&&token.balanceOf(address(this))==2 ether,"SECOND_PLAN");}
    function testMissingCallback() public {lender.configure(1);reject(plan(),OmegaMorphoLiquidationProbe.CallbackMissing.selector);}
    function testWrongCallbackAmount() public {lender.configure(2);reject(plan(),OmegaMorphoLiquidationProbe.CallbackPlan.selector);}
    function testChangedCallbackData() public {lender.configure(3);reject(plan(),OmegaMorphoLiquidationProbe.CallbackPlan.selector);}
    function testDuplicateCallbackRevertsEntireOperation() public {lender.configure(4);reject(plan(),OmegaMorphoLiquidationProbe.CallbackAuth.selector);}
    function testLenderCannotSkipPullRepayment() public {lender.configure(5);reject(plan(),OmegaMorphoLiquidationProbe.RepaymentMismatch.selector);}
    function testShortPrincipalCannotUseExternalFunds() public {lender.configure(7);reject(plan(),OmegaMorphoLiquidationProbe.FreshPrincipal.selector);}
    function testPoolRejectionPropagatesAndRollsBack() public {pool.configure(1 ether,true,false);reject(plan(),bytes4(keccak256("Error(string)")));}
    function testApproveFalseRollsBack() public {token.configure(address(0),true);reject(plan(),OmegaMorphoLiquidationProbe.TokenCall.selector);}
    function testSweepFailureRollsBackLiquidationRepaymentAndIdentity() public {token.configure(address(this),false);reject(plan(),OmegaMorphoLiquidationProbe.TokenCall.selector);}
    function testPoolCannotInjectNestedCallback() public {pool.configure(1 ether,false,true);require(probe.execute(plan())==1 ether,"SURPLUS");}
    function testUnauthorizedOperator() public {
        ProbeOtherCaller other=new ProbeOtherCaller();bytes32 beforeState=state(plan().executionId);
        (bool ok,bytes memory reason)=address(other).call(abi.encodeCall(other.run,(probe,plan())));
        require(!ok&&bytes4(reason)==OmegaMorphoLiquidationProbe.Unauthorized.selector&&state(plan().executionId)==beforeState,"UNAUTHORIZED");
    }
    function testDirectForgedCallback() public {
        (bool ok,bytes memory reason)=address(probe).call(abi.encodeCall(probe.onMorphoFlashLoan,(10 ether,abi.encode(plan()))));
        require(!ok&&bytes4(reason)==OmegaMorphoLiquidationProbe.CallbackAuth.selector,"FORGED_CALLBACK");
    }
    function testLateAuthorizedSenderCallback() public {
        probe.execute(plan());bytes32 beforeState=state(plan().executionId);
        (bool ok,bytes memory reason)=address(lender).call(abi.encodeCall(lender.lateCallback,(address(probe),10 ether,abi.encode(plan()))));
        require(!ok&&bytes4(reason)==OmegaMorphoLiquidationProbe.CallbackAuth.selector&&state(plan().executionId)==beforeState,"LATE_CALLBACK");
    }
    function testRuntimeLenderCodeChange() public {vm.etch(address(lender),hex"00");reject(plan(),OmegaMorphoLiquidationProbe.CodeIdentity.selector);}
    function testRuntimePoolCodeChange() public {
        vm.etch(address(pool),hex"00");
        (bool ok,bytes memory reason)=address(probe).call(abi.encodeCall(probe.execute,(plan())));
        require(!ok&&bytes4(reason)==OmegaMorphoLiquidationProbe.CodeIdentity.selector,"POOL_CODE");
        require(probe.phase()==0&&!probe.consumed(plan().executionId)&&token.balanceOf(address(probe))==0,"POOL_CODE_STATE");
    }
    function testRuntimeAssetCodeChange() public {
        vm.etch(address(token),hex"00");
        (bool ok,bytes memory reason)=address(probe).call(abi.encodeCall(probe.execute,(plan())));
        require(!ok&&bytes4(reason)==OmegaMorphoLiquidationProbe.CodeIdentity.selector,"ASSET_CODE");
    }
    function testConstructorRejectsUnpinnedCode() public {
        try new OmegaMorphoLiquidationProbe(address(this),address(lender),address(pool),address(token),bytes32(0),address(pool).codehash,address(token).codehash) {revert("BAD_CODE_ACCEPTED");}
        catch(bytes memory reason){require(bytes4(reason)==OmegaMorphoLiquidationProbe.CodeIdentity.selector,"BAD_CODE_REASON");}
    }
    function testConstructorRejectsSameLenderAndPool() public {
        try new OmegaMorphoLiquidationProbe(address(this),address(lender),address(lender),address(token),address(lender).codehash,address(lender).codehash,address(token).codehash) {revert("SAME_DEPENDENCY_ACCEPTED");}
        catch(bytes memory reason){require(bytes4(reason)==OmegaMorphoLiquidationProbe.InvalidDependencies.selector,"DEPENDENCY_REASON");}
    }
    function testFuzzFreshSettlement(uint96 rawPrincipal,uint80 rawBonus) public {
        OmegaMorphoLiquidationProbe.Plan memory p=plan();p.principal=uint256(rawPrincipal)%100_000 ether+1;
        uint256 bonus=uint256(rawBonus)%1000 ether+1;pool.configure(bonus,false,false);
        uint256 beforeBalance=token.balanceOf(address(lender));
        require(probe.execute(p)==bonus&&token.balanceOf(address(this))==bonus,"FUZZ_SURPLUS");
        require(token.balanceOf(address(probe))==0&&token.balanceOf(address(lender))==beforeBalance,"FUZZ_REPAYMENT");
    }
}
