// SPDX-License-Identifier: GPL-2.0-or-later
pragma solidity ^0.8.24;

import {NqcOriginalMorphoFixture} from "./NqcOriginalMorpho.t.sol";
import {INqcMorphoBlue} from "../contracts/NqcMorphoSponsoredLiquidation.sol";
import {Call, IBundler3} from "../reference/bundler3/src/interfaces/IBundler3.sol";
import {MathLib} from "../reference/morpho-blue/src/libraries/MathLib.sol";

interface LocalGeneralAdapter {
    function morphoFlashLoan(address token, uint256 assets, bytes calldata data) external;
    function erc20Transfer(address token, address receiver, uint256 amount) external;
}

contract LocalWrapperMetadata {
    address immutable token;
    constructor(address token_) { token=token_; }
    function stETH() external view returns(address) { return token; }
    function underlying() external view returns(address) { return token; }
}

/// Original dispatch/adapter/core bytecode; synthetic assets, oracle and swap.
/// This is not a mainnet fork, deployment-cost proof or sponsored transaction.
contract NqcBundlerOriginalTest is NqcOriginalMorphoFixture {
    using MathLib for uint256;
    IBundler3 bundler;
    LocalGeneralAdapter general;

    function _create(string memory path, bytes memory args) private returns(address result) {
        bytes memory data=abi.encodePacked(vm.getCode(path),args);
        assembly { result := create(0,add(data,32),mload(data)) }
        require(result!=address(0),"reference creation failed");
    }

    function setUp() public override {
        super.setUp();
        bundler=IBundler3(_create("out-upstream/Bundler3.json",""));
        address metadata=address(new LocalWrapperMetadata(address(weth)));
        general=LocalGeneralAdapter(_create("out-upstream/EthereumGeneralAdapter1.json",
            abi.encode(address(bundler),address(morpho),address(weth),metadata,address(collateral),metadata)));
        oracle.setPrice(9e35);
    }

    function _route() private view returns(Call[] memory outer, uint256 seized) {
        uint256 lif=uint256(1e18).wDivDown(1e18-uint256(3e17).wMulDown(1e18-market.lltv));
        seized=uint256(8 ether).wMulDown(lif).mulDivDown(1e36,9e35);
        Call[] memory nested=new Call[](9);
        nested[0]=Call(address(general),abi.encodeCall(general.erc20Transfer,(address(weth),address(bundler),8 ether)),0,false,bytes32(0));
        nested[1]=Call(address(weth),abi.encodeWithSignature("approve(address,uint256)",address(morpho),8 ether),0,false,bytes32(0));
        nested[2]=Call(address(morpho),abi.encodeCall(INqcMorphoBlue.liquidate,(market,BORROWER,0,shares,bytes(""))),0,false,bytes32(0));
        nested[3]=Call(address(weth),abi.encodeWithSignature("approve(address,uint256)",address(morpho),0),0,false,bytes32(0));
        nested[4]=Call(address(collateral),abi.encodeWithSignature("approve(address,uint256)",address(adapter),seized),0,false,bytes32(0));
        nested[5]=Call(address(adapter),abi.encodeWithSignature("swapExactInput(address,address,uint256,uint256,bytes)",
            address(collateral),address(weth),seized,8.5 ether,hex"01"),0,false,bytes32(0));
        nested[6]=Call(address(collateral),abi.encodeWithSignature("approve(address,uint256)",address(adapter),0),0,false,bytes32(0));
        nested[7]=Call(address(weth),abi.encodeWithSignature("transfer(address,uint256)",address(general),8 ether),0,false,bytes32(0));
        nested[8]=Call(address(weth),abi.encodeWithSignature("transfer(address,uint256)",address(this),seized-8 ether),0,false,bytes32(0));
        outer=new Call[](1);
        bytes memory callback=abi.encode(nested);
        outer[0]=Call(address(general),abi.encodeCall(general.morphoFlashLoan,(address(weth),8 ether,callback)),0,false,keccak256(callback));
    }

    function testBundlerOriginalFlashLiquidationReentryRepays() public {
        (Call[] memory route,uint256 seized)=_route();
        uint256 beforeLoan=weth.balanceOf(address(morpho));
        bundler.multicall(route);
        require(weth.balanceOf(address(morpho))==beforeLoan+8 ether,"liquidation/flash not settled");
        require(weth.balanceOf(address(this))==seized-8 ether,"operator receipt");
        require(weth.balanceOf(address(bundler))==0 && weth.balanceOf(address(general))==0,"retained flash funds");
        require(collateral.balanceOf(address(bundler))==0,"retained collateral");
        require(weth.allowance(address(bundler),address(morpho))==0,"bundler approval left");
        require(collateral.allowance(address(bundler),address(adapter))==0,"DEX approval left");
        require(weth.allowance(address(general),address(morpho))>0,"upstream persistent approval absent");
        require(bundler.initiator()==address(0) && bundler.reenterHash()==bytes32(0),"transient locks not cleared");
    }

    function testBundlerWrongCallbackHashRollsBack() public {
        (Call[] memory route,)=_route();route[0].callbackHash=keccak256("wrong");
        uint256 beforeLoan=weth.balanceOf(address(morpho));
        (bool ok,)=address(bundler).call(abi.encodeCall(bundler.multicall,(route)));
        require(!ok,"unexpected callback accepted");
        require(weth.balanceOf(address(morpho))==beforeLoan,"flash not rolled back");
        require(weth.balanceOf(address(general))==0,"loan leaked");
    }

    function testBundlerInsufficientSwapRollsBack() public {
        (Call[] memory route,)=_route();adapter.configure(2 ether,false,false);
        uint256 beforeLoan=weth.balanceOf(address(morpho));
        (bool ok,)=address(bundler).call(abi.encodeCall(bundler.multicall,(route)));
        require(!ok,"insufficient conversion accepted");
        require(weth.balanceOf(address(morpho))==beforeLoan,"Morpho changed after failure");
        require(weth.balanceOf(address(this))==0,"operator paid after failure");
        require(weth.allowance(address(bundler),address(morpho))==0,"approval leaked");
    }

    function testBundlerFlashRouteNeedsMorphoLoanCash() public {
        _exhaustLoanCash();
        (Call[] memory route,) = _route();
        (bool ok,) = address(bundler).call(abi.encodeCall(bundler.multicall, (route)));
        require(!ok, "flash loan created missing liquidity");
        require(weth.balanceOf(address(morpho)) == 0, "Morpho cash changed");
        (, uint128 remainingShares,) = morpho.position(keccak256(abi.encode(market)), BORROWER);
        require(remainingShares == shares, "failed flash changed borrower debt");
        require(weth.balanceOf(address(this)) == 0, "operator received funds on failure");
    }
}
