// SPDX-License-Identifier: GPL-2.0-or-later
pragma solidity ^0.8.24;

import {MathLib} from "../reference/morpho-blue/src/libraries/MathLib.sol";
import {SharesMathLib} from "../reference/morpho-blue/src/libraries/SharesMathLib.sol";
import {Call} from "../reference/bundler3/src/interfaces/IBundler3.sol";

interface ParityVm {
    function readFile(string calldata path) external view returns (string memory);
    function parseBytes(string calldata value) external pure returns (bytes memory);
}

/// Python fixtures are compared to Solidity ABI and original upstream libraries.
contract ReferenceParityTest {
    using MathLib for uint256;
    using SharesMathLib for uint256;
    ParityVm constant vm=ParityVm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function _read(string memory path) private view returns (bytes memory) {
        return vm.parseBytes(vm.readFile(path));
    }

    function testLiquidationParity65Vectors() public view {
        uint256[12][] memory cases=abi.decode(_read("fixtures/math_parity.hex"),(uint256[12][]));
        require(cases.length==65,"missing vectors");
        for(uint256 i;i<cases.length;i++) {
            uint256[12] memory c=cases[i];
            uint256 lif=uint256(1e18).wDivDown(1e18-uint256(3e17).wMulDown(1e18-c[5]));
            if(lif>1.15e18) lif=1.15e18;
            require(lif==c[9],"incentive mismatch");
            require(c[6].toAssetsUp(c[0],c[1])==c[8],"repay mismatch");
            require(c[6].toAssetsDown(c[0],c[1]).wMulDown(lif).mulDivDown(1e36,c[4])==c[7],"seize mismatch");
            require(c[2].toAssetsUp(c[0],c[1])==c[10],"debt mismatch");
            require(c[3].mulDivDown(c[4],1e36).wMulDown(c[5])==c[11],"health mismatch");
        }
    }

    function testInterestParity65Vectors() public view {
        uint256[5][] memory cases=abi.decode(_read("fixtures/interest_parity.hex"),(uint256[5][]));
        require(cases.length==65,"missing vectors");
        for(uint256 i;i<cases.length;i++) {
            uint256[5] memory c=cases[i];
            uint256 factor=c[0].wTaylorCompounded(c[1]);
            require(factor==c[3],"Taylor mismatch");
            require(c[2].wMulDown(factor)==c[4],"interest mismatch");
        }
    }

    function _calls() private pure returns (Call[] memory calls) {
        calls=new Call[](3);
        bytes memory data=new bytes(33);
        for(uint256 i;i<33;i++) data[i]=0x01;
        calls[0]=Call(address(0x1111111111111111111111111111111111111111),data,7,false,bytes32(uint256(type(uint256).max/255*171)));
        calls[1]=Call(address(0x2222222222222222222222222222222222222222),"",0,false,bytes32(0));
        data=new bytes(31);
        for(uint256 i;i<31;i++) data[i]=bytes1(uint8(i));
        calls[2]=Call(calls[0].to,data,2,false,bytes32(0));
    }

    function testBundler3AbiEncoderParity() public view {
        bytes memory actual=abi.encode(_calls());
        require(keccak256(actual)==keccak256(_read("fixtures/calls_parity.hex")),"Call[] layout differs");
        require(abi.decode(_read("fixtures/callback_hash_parity.hex"),(bytes32))==keccak256(actual),"callback hash differs");
    }

    function testFlashloanCallbackWrappingParity() public view {
        bytes memory actual=abi.encodeWithSignature("morphoFlashLoan(address,uint256,bytes)",
            address(0x2222222222222222222222222222222222222222),1234567,abi.encode(_calls()));
        require(keccak256(actual)==keccak256(_read("fixtures/flashloan_abi_parity.hex")),"flash ABI differs");
    }
}
