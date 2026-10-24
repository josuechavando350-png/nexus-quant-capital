# Original collateral burn with observed WETH runtime

The closed-state experiment now calls the unchanged
`LiquidationLogic._burnCollateralATokens` helper in the same transaction as the
preceding debt burn, rate updates, rewards accrual and capped treasury fee. It
executes actual aWETH/aToken, debt token, strategy and rewards runtimes, together
with the complete 3,124-byte WETH runtime observed at the retained historical
blocks. The tested branch receives underlying WETH. Debt and collateral are
distinct assets (USDC and WETH); same-asset cache handling is not covered here.

## WETH identity and explicit source gap

`research/capture_aave_underlying.py` performs 66 read-only requests across Blast
and dRPC for blocks 26248075, 26248113 and 26248378. Both providers agree on the
complete WETH runtime and aWETH's `_underlyingAsset` word at slot 61. Code and slot
reads use canonical block-hash pins; chain, finality and repeated block/event
headers are checked. The retained capture replays exactly, including request IDs,
provider order and full reply agreement. It adds no liquidation events or balances.
These observations are provider agreement, not authenticated state-root proofs.

Original Sourcify WETH sources, including CRLF and the license text, are retained
unchanged. Checksum-pinned solc 0.4.19 reproduces the same executable prefix of
3,081 bytes. **Full compiled runtime equality is false:** 32 bytes of the `bzzr0`
metadata hash differ, at offsets 3090–3121. The 43-byte footer shape and length are
checked exactly. Source/metadata reconstruction remains incomplete. The compiler
output is not patched. Execution uses the complete observed runtime, with its
original deployed footer, and the mismatch is retained explicitly in the fixture
and `runtime-audit.json`. This distinction must not be silently converted into a
full source/runtime certification in subsequent work.

The old compiler does not emit storageLayout. Balance mapping slot 3 and allowance
mapping slot 4 follow the original AST declaration order/types and lack of base
contracts, plus actual getter/transfer execution. The fixture labels this inference;
it does not fabricate compiler storageLayout. The aToken underlying slot 61 comes
from its independently audited modern compiler layout and the new public reads.

## Composition and expected effects

The new synthetic Pool wrapper preserves the original collateral-consumption/flag
and capped-fee excerpts. It uses the library's original local-variable struct and
calls both original internal debt and collateral-burn helpers. No original contract
source is modified. The added wrapper is 6,663 bytes, built with pinned solc 0.8.27.
Three executions of each compiler profile reproduce identical output bytes.

The collateral helper updates rates and virtual liquidity before aToken burn.
The real aToken reduces scaled supply, updates the borrower's index, invokes the
real rewards controller, and calls WETH.transfer through GPv2SafeERC20. Its actual
transfer mutates the supplied WETH ledger and emits Transfer. The later treasury
fee reads the resulting aToken balance and uses the reduced supply in its callbacks.

Default example: index 1.5 RAY, collateral transfer 40 and fee 10. AToken scaled
balances borrower/liquidator/treasury move from 100/20/7 to 66/20/14. Supply decreases
from 1000 to 973, while WETH vault/liquidator balances move from 1000/13 to 960/53.
The collateral virtual balance decreases from 1000 to 960. All 24 returned words,
14 ordered events and 21 changed storage slots match independent expectations.
Gas 439195 is solely the synthetic harness measurement.

## Tests and failure behavior

Eight new Rust tests include 240 seeded cases, each also executing the two prior
independently checked debt/token/rate and debt/rewards references. Cases cover
interest larger/smaller than the burn, zero fee, full collateral exhaustion,
fee capping to a positive amount or zero, recipient=treasury, no/multiple rewards,
zero reserve debt, zero remaining virtual liquidity and varied rates/factors.

Insufficient WETH, invalid collateral liquidity/factor, zero aToken burn, and late
treasury balance/reward overflow must revert all earlier contract writes and logs.
The late failure cases include the already executed WETH transfer. Missing WETH
account/balance, aToken underlying slot or collateral rate witnesses fail closed.
An artificial uint256-max recipient state checks the legacy WETH wrapping addition;
it is not a naturally backed WETH ledger or an exploitable historical opportunity.

Twelve new Python tests bind sources/compiler settings, AST order, executable and
metadata boundaries, provider replies, fixture regeneration and exact CLI replay.
Rehashed capture mutations must still fail semantic checks. Actual WETH getters,
insufficient transfer, missing witnesses and late rollback are executed via CLI.

## Remaining limits

All execution balances, indices, reward distributions, rate parameters and aggregate
collateral values remain synthetic. Initial reserve updates, health/eMode and amount
calculation are not composed here. Actual debt repayment, multi-reserve bad debt,
same-asset liquidation, full deployed Pool/proxy execution and authenticated
transaction prestate under the correct fork remain open. Reward claims, transfer
strategies and deployed administrator behavior are outside this test. WETH metadata
source parity remains open even though complete observed runtime is executed.
The sandbox uses Cancun. No full liquidation, economic/Foundry/hermetic-production
certification or operational phase exit is claimed. Observer is unchanged; no
signing, broadcasts, deployments or spending. Progress remains 43/100.
