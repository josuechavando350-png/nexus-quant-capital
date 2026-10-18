// SPDX-License-Identifier: MIT
pragma solidity 0.8.19;
import {MathLib} from "./MathLib.sol";
import {SharesMathLib} from "./SharesMathLib.sol";

/// LOCAL PURE FORMULA HARNESS: not Morpho runtime, not a fork or a deployed contract certificate.
contract FormulaHarness {
    function evaluate(uint256 op, uint256[6] memory a) external pure returns (uint256, uint256, uint256) {
        if (op == 0) {
            return (a[3] == 0 ? MathLib.mulDivDown(a[0],a[1],a[2]) : MathLib.mulDivUp(a[0],a[1],a[2]),0,0);
        }
        if (op == 1) {
            return (a[3] == 0 ? SharesMathLib.toAssetsDown(a[0],a[1],a[2]) : SharesMathLib.toAssetsUp(a[0],a[1],a[2]),0,0);
        }
        if (op == 2) return (MathLib.wTaylorCompounded(a[0],a[1]),0,0);
        require(op == 3);
        uint256 debt = SharesMathLib.toAssetsUp(a[2],a[0],a[1]);
        uint256 cap = MathLib.wMulDown(MathLib.mulDivDown(a[3],a[4],1e36),a[5]);
        return (debt,cap,debt > cap ? 1 : 0);
    }
}
