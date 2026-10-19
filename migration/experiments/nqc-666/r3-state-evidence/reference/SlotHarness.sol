// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;
import {MorphoStorageLib} from "upstream/src/libraries/periphery/MorphoStorageLib.sol";
import {Id} from "upstream/src/interfaces/IMorpho.sol";

/// Pure slot arithmetic only; this is not Morpho deployment or execution.
contract SlotHarness {
    function slots(bytes32 market, address borrower) external pure returns (bytes32[9] memory r) {
        Id id = Id.wrap(market);
        r[0] = MorphoStorageLib.positionBorrowSharesAndCollateralSlot(id, borrower);
        r[1] = MorphoStorageLib.marketTotalSupplyAssetsAndSharesSlot(id);
        r[2] = MorphoStorageLib.marketTotalBorrowAssetsAndSharesSlot(id);
        r[3] = MorphoStorageLib.marketLastUpdateAndFeeSlot(id);
        r[4] = MorphoStorageLib.idToLoanTokenSlot(id);
        r[5] = MorphoStorageLib.idToCollateralTokenSlot(id);
        r[6] = MorphoStorageLib.idToOracleSlot(id);
        r[7] = MorphoStorageLib.idToIrmSlot(id);
        r[8] = MorphoStorageLib.idToLltvSlot(id);
    }
}
