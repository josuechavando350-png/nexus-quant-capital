// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity ^0.8.24;

import {NqcOriginalMorphoFixture} from "./NqcOriginalMorpho.t.sol";
import {NqcMorphoSponsoredLiquidation, INqcMorphoBlue, INqcExactInputAdapter} from "../contracts/NqcMorphoSponsoredLiquidation.sol";
import {MockToken, MockExternalDexSeeder} from "../tests-solidity/NqcMorphoSponsoredLiquidationMock.t.sol";
import {LocalWrapperMetadata} from "./NqcBundlerOriginal.t.sol";
import {Call, IBundler3} from "../reference/bundler3/src/interfaces/IBundler3.sol";

interface BoundaryVm {
    function snapshotState() external returns (uint256);
    function revertToState(uint256) external returns (bool);
    function readFile(string calldata path) external view returns (string memory);
    function parseBytes(string calldata text) external pure returns (bytes memory);
}
interface V2Pair {
    function initialize(address, address) external;
    function mint(address) external returns (uint256);
    function getReserves() external view returns (uint112, uint112, uint32);
    function swap(uint256, uint256, address, bytes calldata) external;
}
interface BoundaryGeneral {
    function morphoFlashLoan(address, uint256, bytes calldata) external;
    function erc20Transfer(address, address, uint256) external;
    function unwrapNative(uint256, address) external;
}

/// Test-only bridge to original pair bytecode. Not a production adapter.
contract LocalV2Bridge is INqcExactInputAdapter {
    V2Pair public immutable pair;
    MockToken public immutable collateral;
    MockToken public immutable loan;
    constructor(V2Pair p, MockToken c, MockToken w) { pair=p;collateral=c;loan=w; }
    function quote(uint256 amount) public view returns(uint256) {
        (uint112 x,uint112 y,)=pair.getReserves();
        return amount*997*uint256(y)/(uint256(x)*1000+amount*997);
    }
    function swapExactInput(address a,address b,uint256 amount,uint256 minimum,bytes calldata)
        external returns(uint256 out) {
        require(a==address(collateral)&&b==address(loan),"test route");
        out=quote(amount);require(out>=minimum,"output below bound");
        require(collateral.transferFrom(msg.sender,address(pair),amount),"input transfer");
        pair.swap(0,out,msg.sender,"");
    }
}

/// Original Morpho, Bundler, GeneralAdapter and Uniswap V2; synthetic state.
contract NqcLiquidityBoundaryTest is NqcOriginalMorphoFixture {
    BoundaryVm constant stateVm=BoundaryVm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant OTHER_BORROWER=address(0xB00B);
    address constant LP=address(0x1A);
    address constant SPONSOR=address(0xF00D); // Synthetic payment sink, no operator identity claim.
    V2Pair pair;
    LocalV2Bridge bridge;
    IBundler3 bundler;
    BoundaryGeneral general;
    event Scenario(bool flashRoute,uint256 morphoCash,uint256 collateralReserve,uint256 dexOut,bool success,uint256 operatorWeth);
    // Call-frame gas under this fixture's warm state, not transaction charged gas.
    event LocalCallGas(bool flashRoute,uint256 grossCallGas,bool success);
    event ExactBoundary(bool flashRoute,uint256 collateralReserve,uint256 loanReserve,uint256 dexOut,bool success);

    function _create(string memory path,bytes memory args) private returns(address result) {
        bytes memory data=abi.encodePacked(vm.getCode(path),args);
        assembly { result:=create(0,add(data,32),mload(data)) }
        require(result!=address(0),"local reference create");
    }
    function feeTo() external pure returns(address) { return address(0); }

    function setUp() public override {
        super.setUp();
        pair=V2Pair(_create("out-upstream/UniswapV2Pair.json",""));
        pair.initialize(address(collateral),address(weth));
        bridge=new LocalV2Bridge(pair,collateral,weth);
        executor=new NqcMorphoSponsoredLiquidation(address(this),address(morpho),address(bridge),address(weth));
        bundler=IBundler3(_create("out-upstream/Bundler3.json",""));
        address metadata=address(new LocalWrapperMetadata(address(weth)));
        general=BoundaryGeneral(_create("out-upstream/EthereumGeneralAdapter1.json",
            abi.encode(address(bundler),address(morpho),address(weth),metadata,address(collateral),metadata)));
        oracle.setPrice(9e35);
    }
    function _configure(uint256 cash,uint256 reserve) private {
        require(cash<=92 ether,"cash bounds");
        if(cash<92 ether) {
            collateral.mint(OTHER_BORROWER,200 ether);
            vm.prank(OTHER_BORROWER);collateral.approve(address(morpho),200 ether);
            vm.prank(OTHER_BORROWER);morpho.supplyCollateral(market,200 ether,OTHER_BORROWER,"");
            vm.prank(OTHER_BORROWER);morpho.borrow(market,92 ether-cash,0,OTHER_BORROWER,OTHER_BORROWER);
        }
        // Explicitly funded external LP, fully backed WETH, no operator funding.
        MockExternalDexSeeder seeder=new MockExternalDexSeeder();
        uint256 reserveLoan=reserve*9/10;
        vm.deal(address(seeder),reserveLoan);
        seeder.seed(weth,address(pair),reserveLoan);
        collateral.mint(address(pair),reserve);
        pair.mint(LP);
        require(weth.balanceOf(address(morpho))==cash,"cash mismatch");
        require(weth.balanceOf(address(this))==0&&address(this).balance==0,"operator subsidy");
        require(weth.balanceOf(address(executor))==0&&weth.balanceOf(address(bundler))==0,"route subsidy");
        require(weth.balanceOf(address(general))==0&&weth.balanceOf(address(bridge))==0,"adapter subsidy");
    }
    function _seized() private pure returns(uint256) {
        uint256 lif=uint256(1e36)/(1e18-3e17*(1e18-86e16)/1e18);
        return (8 ether*lif/1e18)*1e36/9e35;
    }
    function _boundedPlan() private view returns(NqcMorphoSponsoredLiquidation.Plan memory p) {
        p=_plan();p.minLoanOut=8.11 ether;p.loanForWeth=0.1 ether;p.minWethOut=0.1 ether;
        p.minOperatorProfitLoan=0.01 ether;p.coinbaseTipWei=0.04 ether;
    }
    function _route(uint256 out) private view returns(Call[] memory outer) {
        Call[] memory n=new Call[](12);
        n[0]=Call(address(general),abi.encodeCall(general.erc20Transfer,(address(weth),address(bundler),8 ether)),0,false,0);
        n[1]=Call(address(weth),abi.encodeWithSignature("approve(address,uint256)",address(morpho),8 ether),0,false,0);
        n[2]=Call(address(morpho),abi.encodeCall(INqcMorphoBlue.liquidate,(market,BORROWER,0,shares,bytes(""))),0,false,0);
        n[3]=Call(address(weth),abi.encodeWithSignature("approve(address,uint256)",address(morpho),0),0,false,0);
        n[4]=Call(address(collateral),abi.encodeWithSignature("approve(address,uint256)",address(bridge),_seized()),0,false,0);
        n[5]=Call(address(bridge),abi.encodeCall(bridge.swapExactInput,(address(collateral),address(weth),_seized(),8.11 ether,bytes(""))),0,false,0);
        n[6]=Call(address(collateral),abi.encodeWithSignature("approve(address,uint256)",address(bridge),0),0,false,0);
        n[7]=Call(address(weth),abi.encodeWithSignature("transfer(address,uint256)",address(general),8.1 ether),0,false,0);
        n[8]=Call(address(general),abi.encodeCall(general.unwrapNative,(0.05 ether,SPONSOR)),0,false,0);
        n[9]=Call(address(general),abi.encodeCall(general.unwrapNative,(0.04 ether,block.coinbase)),0,false,0);
        n[10]=Call(address(general),abi.encodeCall(general.unwrapNative,(0.01 ether,address(this))),0,false,0);
        uint256 residual=out>=8.1 ether ? out-8.1 ether : 0;
        n[11]=Call(address(weth),abi.encodeWithSignature("transfer(address,uint256)",address(this),residual),0,false,0);
        bytes memory data=abi.encode(n);outer=new Call[](1);
        outer[0]=Call(address(general),abi.encodeCall(general.morphoFlashLoan,(address(weth),8 ether,data)),0,false,keccak256(data));
    }
    function _execute(bool flash,uint256 quoted) private returns(bool ok) {
        bytes memory payload=flash ? abi.encodeCall(bundler.multicall,(_route(quoted)))
            : abi.encodeCall(executor.execute,(_boundedPlan(),hex"01",bytes("")));
        address target=flash ? address(bundler) : address(executor);
        uint256 beforeGas=gasleft();
        (ok,)=target.call(payload);
        uint256 spent=beforeGas-gasleft();
        emit LocalCallGas(flash,spent,ok);
    }
    function _scenario(bool flash,uint256 cash,uint256 reserve) private {
        _configure(cash,reserve);
        uint256 out=bridge.quote(_seized());
        uint256 backingBefore=address(weth).balance;
        bool expected=out>=8.11 ether&&(!flash||cash>=8 ether);
        bool ok=_execute(flash,out);
        require(ok==expected,"unexpected admission result");
        (,uint128 debt,)=morpho.position(keccak256(abi.encode(market)),BORROWER);
        if(ok) {
            require(debt==0&&weth.balanceOf(address(morpho))==cash+8 ether,"repayment");
            require(weth.balanceOf(address(pair))==reserve*9/10-out,"pool paid incorrect output");
            require(collateral.balanceOf(address(pair))==reserve+_seized(),"pool input");
            require(weth.balanceOf(address(this))==out-8.1 ether,"operator residual");
            require(address(this).balance==0.01 ether&&SPONSOR.balance==0.05 ether&&block.coinbase.balance==0.04 ether,"native allocation");
            require(address(weth).balance==backingBefore-0.1 ether,"unbacked unwrap");
        } else {
            require(debt==shares&&weth.balanceOf(address(morpho))==cash,"debt/cash changed on revert");
            require(weth.balanceOf(address(pair))==reserve*9/10&&collateral.balanceOf(address(pair))==reserve,"pool changed on revert");
            require(weth.balanceOf(address(this))==0&&address(this).balance==0,"operator paid on revert");
            require(SPONSOR.balance==0&&block.coinbase.balance==0&&address(weth).balance==backingBefore,"native changed on revert");
        }
        require(weth.balanceOf(address(adapter))==20 ether,"old fixed-price mock subsidized run");
        require(weth.balanceOf(address(executor))==0&&weth.balanceOf(address(bundler))==0&&weth.balanceOf(address(general))==0,"route balance not settled");
        require(weth.balanceOf(address(bridge))==0&&collateral.balanceOf(address(bridge))==0,"bridge retained funds");
        require(collateral.allowance(address(bundler),address(bridge))==0&&collateral.allowance(address(executor),address(bridge))==0,"swap approval left");
        emit Scenario(flash,cash,reserve,out,ok,weth.balanceOf(address(this)));
    }
    function testMorphoCashBoundarySweep() public {
        uint256[5] memory cash=[uint256(0),uint256(1),8 ether-1,8 ether,92 ether];
        for(uint256 i;i<cash.length;i++) for(uint256 route;route<2;route++) {
            uint256 snap=stateVm.snapshotState();_scenario(route==1,cash[i],1000 ether);
            require(stateVm.revertToState(snap),"state restore");
        }
    }
    function testPoolDepthSweep() public {
        uint256[4] memory reserves=[uint256(20 ether),100 ether,1000 ether,10000 ether];
        for(uint256 i;i<reserves.length;i++) for(uint256 route;route<2;route++) {
            uint256 snap=stateVm.snapshotState();_scenario(route==1,8 ether,reserves[i]);
            require(stateVm.revertToState(snap),"state restore");
        }
    }
    function testTraceCallbackZeroCash() public { _scenario(false,0,1000 ether); }
    function testTraceFlashBelowBoundary() public { _scenario(true,8 ether-1,1000 ether); }
    function testTraceFlashAtBoundary() public { _scenario(true,8 ether,1000 ether); }
    function testTraceCallbackAtSameCash() public { _scenario(false,8 ether,1000 ether); }
    function testExactPythonDepthBoundaryBothRoutes() public {
        (uint256 seized,uint256 x,uint256 y,uint256 belowOut,uint256 atOut)=abi.decode(
            stateVm.parseBytes(stateVm.readFile("fixtures/profitability_boundary.hex")),
            (uint256,uint256,uint256,uint256,uint256));
        require(seized==_seized()&&x*9==y*10,"fixture identity/price");
        require(belowOut==8.11 ether-1&&atOut==8.11 ether,"one wei output boundary");
        for(uint256 route;route<2;route++) for(uint256 edge;edge<2;edge++) {
            uint256 snap=stateVm.snapshotState();
            uint256 reserve=edge==0 ? x-10 : x;
            _configure(8 ether,reserve);
            uint256 out=bridge.quote(_seized());
            require(out==(edge==0 ? belowOut : atOut),"independent quote mismatch");
            bool ok=_execute(route==1,out);
            require(ok==(edge==1),"boundary execution mismatch");
            (,uint128 debt,)=morpho.position(keccak256(abi.encode(market)),BORROWER);
            require(weth.balanceOf(address(this))==(ok ? 0.01 ether : 0),"token conservation");
            require(address(this).balance==(ok ? 0.01 ether : 0),"native conservation");
            require(SPONSOR.balance==(ok ? 0.05 ether : 0),"sponsor conservation");
            require(block.coinbase.balance==(ok ? 0.04 ether : 0),"coinbase conservation");
            require(weth.balanceOf(address(morpho))==(ok ? 16 ether : 8 ether),"debt receipt");
            require(debt==(ok ? 0 : shares),"debt shares");
            require(weth.balanceOf(address(pair))==reserve*9/10-(ok ? out : 0),"DEX output");
            require(collateral.balanceOf(address(pair))==reserve+(ok ? seized : 0),"DEX input");
            require(weth.balanceOf(address(executor))==0&&weth.balanceOf(address(bundler))==0
                &&weth.balanceOf(address(general))==0,"route balance");
            emit ExactBoundary(route==1,reserve,reserve*9/10,out,ok);
            require(stateVm.revertToState(snap),"state restore");
        }
    }
    function testOriginalHalfEthBudgetIsNotCoveredAtOracleAlignedPrice() public {
        _configure(8 ether,10000 ether);
        require(bridge.quote(_seized())<8.5 ether,"expected economic shortfall");
        (bool ok,)=address(executor).call(abi.encodeCall(executor.execute,(_plan(),hex"01",bytes(""))));
        require(!ok,"fixed price mock profit wrongly generalized");
        require(weth.balanceOf(address(morpho))==8 ether&&address(this).balance==0,"not rolled back");
    }
    function testEarlierSwapInvalidatesBothRoutesAndDoesNotSpendDonations() public {
        _configure(8 ether,1000 ether);
        uint256 oldOut=bridge.quote(_seized());
        address trader=address(0x777);
        collateral.mint(trader,100 ether);
        vm.prank(trader);collateral.approve(address(bridge),100 ether);
        vm.prank(trader);bridge.swapExactInput(address(collateral),address(weth),100 ether,0,"");
        require(bridge.quote(_seized())<8 ether,"competition did not exhaust margin");
        MockExternalDexSeeder donor=new MockExternalDexSeeder();vm.deal(address(donor),3 ether);
        donor.seed(weth,address(executor),1 ether);donor.seed(weth,address(bundler),1 ether);donor.seed(weth,address(general),1 ether);
        require(!_execute(false,oldOut)&&!_execute(true,oldOut),"stale plan accepted");
        require(weth.balanceOf(address(executor))==1 ether&&weth.balanceOf(address(bundler))==1 ether&&weth.balanceOf(address(general))==1 ether,"donation spent");
    }
}
