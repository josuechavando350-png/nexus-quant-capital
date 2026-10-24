# Actual aToken liquidation-transfer composition

The closed-state experiment now executes the original collateral-consumption and
fee excerpts, original internal debt function, actual debt token/rate strategy,
actual aToken, both retained token-proxy families and actual rewards proxy/controller.
The tested branch is `receiveAToken=true`. The Pool entrypoint and all storage remain synthetic; liquidation amounts are
explicitly supplied and initial health/eligibility validation is not executed.
It is not `Pool.liquidationCall` or a historical transaction replay.

## Source and compiler binding

`research/build_aave_transfer_execution.py` validates the retained original Pool
source and copies four byte-exact segments from its `LiquidationLogic.sol`: the
local-variable structure, collateral consumption/flag handling, liquidator aToken
transfer, and capped treasury fee transfer. It calls the unchanged imported
`LiquidationLogic._burnDebtTokens`. Original source files and compiler settings
are unchanged; only the synthetic wrapper is added and output selection narrowed.
The wrapper is generated as `fixtures/AaveTransferExecutionHarness.sol`.

The checksum-pinned solc 0.8.27 compiler produces a 5,928-byte synthetic harness.
Two executions reproduce identical output bytes. The inherited real dependency
runtimes, substitutions, metadata and storage layouts are regenerated through the
previous source/compiler/historical-code audits. There are no new network reads,
historical events or claims of new historical code coverage in this block.

## Actual sequence

The original consumption excerpt computes the sum of separately ceil-rounded
scaled transfers, caps it to the borrower balance, computes consumed base value,
and clears the collateral flag when required. Clearing calls the original
`UserConfiguration` helper, whose disabled event is unconditional even when the
flag was already clear. The original debt function then burns debt, updates its
flag/deficit and recalculates rates. The aToken transfer updates borrower/liquidator
scaled balances and previous indices, then calls the real rewards controller for
each distinct user with pre-transfer balances. The treasury fee reads the resulting
borrower balance and caps its scaled amount accordingly. Its callbacks reuse the
already-updated reward distribution index and timestamp within the same transaction.

Default example: collateral index 1.5 RAY; borrower/liquidator/treasury scaled
balances 100/20/7; scaled supply 1000; requested transfers 40 and 10. The scaled
transfers are 27 and 7, leaving balances 66/47/14 and unchanged supply 1000. The
original ten debt outputs are followed by nine collateral outputs. All 19 outputs,
17 ordered events and 17 changed storage slots match independent expectations.
The example requests six-decimal synthetic rewards even though proxy addresses
come from real historical samples; these are not historical reward parameters.

At index 1.5 RAY, liquidator amount 148 consumes 99 of 100 scaled units. A fee of 2
would consume two more, so the original fee logic caps it to the remaining one
scaled unit and recomputes the fee amount as 1. Both balances are computed by the
actual aToken. Full collateral exhaustion also triggers debt deficit accounting.
When the liquidator consumes all 100 units and a fee was requested, the actual
fee path still calls transferOnLiquidation with zero amount/zero scaled amount.

## Verification

Eight new Rust tests include 320 seeded composition cases with independent integer
models for scaled rounding, interest events, rewards, flags and fee capping. Each
case also runs the preceding real debt/rewards composition and its independently
checked debt/token/rate reference. The 320 cases are not 320 additional test counts.
The suite covers all four distinct retained aToken proxies across both families,
zero fee/transfer, recipient=treasury, no rewards, multiple rewards, zero-value
collateral dust, already-clear flags, reserve IDs 127/128, maximum uint120 balance
and uint128 index, and non-Pool rejection. A standalone self-transfer case probes
token behavior only; normal liquidation validation rejects borrower=liquidator.

Late recipient/treasury overflow, a future previous index, and treasury reward
accrual overflow must revert all debt, reserve, aToken and controller storage
changes and all logs. Missing proxy target/slot, balance, supply or nested reward
witnesses must stop execution; absent state never becomes an assumed zero.
Eight Python tests bind source/settings/excerpts/layouts, regenerate the complete
fixture, reject mutations, replay the CLI example, and verify fee cap/late rollback.

Initial harness extraction and test-model failures are retained and explained in
`evidence/aave-transfer-execution-20261023/execution-notes.json`. The originals are
not edited to make the comparison pass. An interrupted targeted run is retained
without being counted as a completed result. Final full verification is separate.

## Remaining limits

Underlying asset transfer/burn branch, debt payment via transferFrom, complete
validation/health/eMode, multireserve bad debt, actual Pool/proxy dispatch and
historical transaction state/fork remain open. Additional reserve cache/state
updates before liquidation are not composed here. Reward claims, transfer
strategies and deployed admin contracts are not executed. The closed sandbox uses
Cancun with synthetic state; all addresses/code hashes alone cannot authenticate
state roots. Gas measures only the harness. No Foundry or hermetic-production
certification, economic claim, deployment, signing, broadcasting or spending is
implied. Observer and earlier evidence remain intact. Progress stays 43/100.
