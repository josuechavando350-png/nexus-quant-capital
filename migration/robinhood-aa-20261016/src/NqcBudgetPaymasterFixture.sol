// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import {BasePaymaster} from "../lib/account-abstraction/contracts/core/BasePaymaster.sol";
import {IEntryPoint} from "../lib/account-abstraction/contracts/interfaces/IEntryPoint.sol";
import {PackedUserOperation} from "../lib/account-abstraction/contracts/interfaces/PackedUserOperation.sol";

/// @notice LOCAL fixture. Conservative reservation, not a commercial sponsorship offer.
/// @dev Every admitted op consumes its FULL prefund from the lifetime budget.
///      No postOp refund: its cost argument excludes postOp and the final penalty.
///      Owner must externally reconcile before any new epoch/deployment. No credit.
///      This does not prove ERC-7562/bundler admission, stake policy or underwriting.
contract NqcBudgetPaymasterFixture is BasePaymaster {
    address public immutable permittedSender;
    uint256 public immutable perOpCap;
    uint256 public budgetRemaining;
    uint256 public postOpCostArgument;
    uint256 public postOpCount;
    PostOpMode public lastMode;
    bool public rejectPostOp;

    constructor(IEntryPoint ep, address sender, uint256 cap, uint256 budget)
        BasePaymaster(ep)
    {
        permittedSender = sender;
        perOpCap = cap;
        budgetRemaining = budget;
    }

    function setRejectPostOp(bool value) external onlyOwner { rejectPostOp = value; }

    function _validatePaymasterUserOp(PackedUserOperation calldata op, bytes32 hash, uint256 maxCost)
        internal override returns (bytes memory context, uint256 validationData)
    {
        require(op.sender == permittedSender, "SENDER_POLICY");
        require(maxCost <= perOpCap && maxCost <= budgetRemaining, "BUDGET_POLICY");
        budgetRemaining -= maxCost;
        return (abi.encode(hash, maxCost), 0);
    }

    function _postOp(PostOpMode mode, bytes calldata, uint256 cost, uint256)
        internal override
    {
        require(!rejectPostOp, "TEST_POSTOP_FAILURE");
        postOpCount++;
        postOpCostArgument = cost;
        lastMode = mode;
    }
}
