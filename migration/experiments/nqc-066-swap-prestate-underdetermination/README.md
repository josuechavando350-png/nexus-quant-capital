# NQC066 — Uniswap pool-state non-identifiability and a two-leg economic stop gate

**Result: STOP a claimed profitable zero-capital historical replay until the real market state is obtained.** This research follows NQC065, reusing the same February 2025 external Morpho Blue transaction. It adds a constructive proof that raw swap transfers do not uniquely determine the Uniswap V2 reserves, plus a conservative *joint* stress envelope for the UNI→WETH and WETH→USDC legs. It creates no new market opportunity, no authenticated EVM replay and no NQC revenue.

## Why the transfer ledger cannot prove a counterfactual execution

NQC064 recorded WETH→USDC **266.862310264246861824 WETH in**, **616,687.327559 USDC out**, while the debt was **616,687.327558 USDC**. Only **0.000001 USDC** remained. The source is an Etherscan decoded transaction-page transcription, **not** independently authenticated raw receipt/parent state or contract ownership.

The [pinned Uniswap V2 periphery library](https://github.com/Uniswap/v2-periphery/blob/ed24991304291297c3b4a52818d02f46a17aa9a2/contracts/libraries/UniswapV2Library.sol) defines 997/1000 fee model output and the `getAmountIn` exact-output reverse function. **Under that mathematical model only**, three different synthetic WETH/USDC reserve configurations reproduce the exact reported 616,687.327559 USDC output for 266.862310264246861824 WETH input. The JSON witness values are examples, **not measured Uniswap reserves**. No true historic reserves/pair code/tx0 or V3 tick/liquidity data were obtained.

The synthetic exact-output calculation for precisely **616,687.327558 USDC** saves **less than 0.000000001 WETH** versus the observed WETH input in all three compatible states. Exact-output can improve the repayment design by requesting the needed loan assets, but it is not a demonstrated material extra source of profit. Without authentic reserves and original runtime, no conclusion about the actual exact-output price, profitable execution, gas, or whether Morpho liquidation remained eligible may be drawn.

## Joint margin stress — two legs can move against us

Conditional baseline from NQC064/065: UNI sale yielded **281.407578800167103862 WETH**, buying USDC cost **266.862310264246861824 WETH**, historical builder payment **12.447536358167279703 ETH**, and gas from **a different EOA** cost **0.182306290745378005 ETH**. That yields **1.915425887007584330 ETH equivalent** only under WETH unwrap at 1:1 and consolidated economic ownership, with all other obligations unchanged. The builder payment is backed by a WETH withdrawal and is not subtracted twice.

In integer wei, a hypothetical unfavorable 30 bp fall in UNI→WETH proceeds plus a 20 bp increase in WETH→USDC input leaves **0.537478530078589294 ETH equivalent**, before any incremental gas and sponsorship. A 50 bp / 25 bp combination yields **-0.158767782653868345**, and 60 bp / 10 bp yields **-0.039881896057665156**. Stress losses are conservatively rounded upward to whole wei.

These scenarios are **not predictions of slippage** or proof that these conditions existed. The real C1 callback changes the order of the Morpho oracle check and both swaps; a different block-prefix state, pool liquidity or pricing can invalidate this simplified decomposition. Titan may demand additional fees or may not include the bundle, and its founder non-recourse remains UNKNOWN.

## The hard proof boundary

The pinned [Morpho Blue core](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol) reads the oracle and checks borrower health **before** sending seized collateral to the liquidator, then invokes `onMorphoLiquidate` when nonempty data is provided, and only afterward pulls the exact debt repayment. Therefore rewriting the original sequence to liquidate first may affect the oracle dependency and eligibility; reproducing swaps' final token totals does **not** reconstruct the 2025 state.

The exact canonical packet required is in `EVIDENCE_GATE.json`: **parent block 21,762,896, tx0 transitions, target tx index 1, 2025 fork/runtime, market/oracle/debt state, V2 reserves and V3 liquidity/tick, callback code, gas, and Titan payout/failure terms**. [Geth archive documentation](https://geth.ethereum.org/docs/fundamentals/archive) describes why old historical state is not the same as mere event history: the provider has to maintain relevant past account/storage data, and proof support depends on node configuration. No permitted complete packet was found in this bounded review. No RPC, prior-denied explorer reattempt, provider-circumvention, or live financial transaction occurred.

A separate third-party GitHub retrospective identified the historical executor as a previously active MEV liquidator over *older* blocks. This is context of possible competition only, not independent attribution of the February 2025 transaction or evidence of NQC's capture probability.

## Decision

- **GO, arithmetic only:** an external transaction had positive residual **under explicitly stated assumptions**; sensitive to both swap legs.
- **UNKNOWN:** original pool reserves, altered callback's EVM success, committed Titan sponsorship, owner liability, future capture probability.
- **NO-GO:** live execution, signing, deployment, trade, any P&L attribution to NQC.
- **STOP** on additional historical optimization when data remain missing; do not recycle this old event as a current mine.

No new code or runtime tests were added. Exact BigInt arithmetic was checked in this turn; this does not replace the repository's original isolation tests or a canonical EVM replay. Main and historical branches remain untouched, `commercial_admission=false`, Triport 0/8 known uses, Census/Shadow zero funds.

**Next movement:** identify a lawful, explicitly permitted archive providing the full prestate; if not feasible under current constraints, request separate authorization for a *strictly read-only*, zero-funded, capped prospective Shadow pilot measuring fresh Morpho opportunities and rejected bids. We cannot learn NQC's current competitiveness from a transaction another searcher won in 2025.
