// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity 0.8.24;
import {INqcMorphoBlue} from "./NqcMorphoSponsoredLiquidation.sol";
// Test-only helpers. The AMM and lending implementation are unmodified upstream bytecode.
interface Token { function transferFrom(address,address,uint256) external returns(bool); }
interface Pair {
    function initialize(address,address) external;
    function getReserves() external view returns(uint112,uint112,uint32);
    function swap(uint256,uint256,address,bytes calldata) external;
}
contract LabOracle {
    address public immutable owner = msg.sender;
    uint256 public price = 2e36;
    function setPrice(uint256 p) external { require(msg.sender == owner); price = p; }
}
contract LabFactory {
    address public pair;
    function feeTo() external pure returns(address) { return address(0); }
    function create(bytes memory code,address collateral,address weth) external {
        require(pair == address(0)); address p;
        assembly { p := create(0,add(code,32),mload(code)) }
        require(p != address(0)); pair=p; Pair(p).initialize(collateral,weth);
    }
}
contract LabV2Adapter {
    Pair public immutable pair;
    address public immutable collateral;
    address public immutable weth;
    constructor(address p,address c,address w) { require(p!=address(0));pair=Pair(p);collateral=c;weth=w; }
    function quote(uint256 amount) public view returns(uint256) {
        (uint112 x,uint112 y,)=pair.getReserves();
        return amount*997*uint256(y)/(uint256(x)*1000+amount*997);
    }
    function swapExactInput(address a,address b,uint256 amount,uint256 minimum,bytes calldata)
        external returns(uint256 out) {
        require(a==collateral && b==weth,"route");
        out=quote(amount); require(out>=minimum,"slippage");
        require(Token(collateral).transferFrom(msg.sender,address(pair),amount),"transfer");
        pair.swap(0,out,msg.sender,"");
    }
}
contract RejectNative { receive() external payable { revert("reject native"); } }
contract ForceNative {
    constructor(address payable recipient) payable { selfdestruct(recipient); }
}
interface BalanceToken is Token {
    function balanceOf(address) external view returns(uint256);
    function approve(address,uint256) external returns(bool);
}
/// Deliberately defective repayment control, used only on the newly created local market.
/// The production NQC executor is not altered to bypass its safeguards.
contract UnderpayControl {
    INqcMorphoBlue immutable morpho;
    BalanceToken immutable collateral;
    BalanceToken immutable loan;
    LabV2Adapter immutable adapter;
    constructor(address m,address c,address w,address a) {
        morpho=INqcMorphoBlue(m);collateral=BalanceToken(c);loan=BalanceToken(w);adapter=LabV2Adapter(a);
    }
    function run(INqcMorphoBlue.MarketParams calldata market,address borrower,uint256 shares) external {
        morpho.liquidate(market,borrower,0,shares,hex"01");
    }
    function onMorphoLiquidate(uint256 repaid,bytes calldata) external {
        require(msg.sender==address(morpho));
        uint256 amount=collateral.balanceOf(address(this));
        require(collateral.approve(address(adapter),amount));
        adapter.swapExactInput(address(collateral),address(loan),amount,0,"");
        // Morpho must reject the one-wei deficient allowance after the real swap has happened.
        require(loan.approve(address(morpho),repaid-1));
    }
}
