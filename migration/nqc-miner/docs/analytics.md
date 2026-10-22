# Analytics boundary and model specification

This module implements deterministic, local analytical functions for Miner components
7, 8, 10, 11 and a preparatory research allocator for component 13. Its tests use
explicitly synthetic inputs. Passing them does not establish market profitability,
data completeness, calibrated competition thresholds, Shadow success, or authority
to spend.

All money in observations is denominated in **USD millionths**, not native token
units or MXN centavos. Converting token amounts to this numeraire requires separate,
time-correct price evidence. Research allocation uses indivisible abstract compute
units. It never translates those units into money or authorizes a wallet.

## Source separation and canonicality

`EvidenceClass` distinguishes `fixture`, `historical`, `shadow`, and `realized`.
Analyses reject mixed classes. Data collectors must verify origin, canonicality,
finality, prices, and completeness before supplying inputs; a caller-provided label
does not prove any of those properties.

Canonical liquidation events are deduplicated by chain, transaction hash and log
index. The canonical block hash, timestamp and transaction location must agree.
Log positions are unique across the whole block, including across contracts:
distinct transactions at the same chain, block height and log index fail analysis.
Accepted observations are ordered by chain, block height and log index.
Conflicting versions fail analysis. Orphaned observations are counted as excluded.
Unfinalized observations cannot support a complete saturation or coverage result.

Events, addresses and hashes use canonical lowercase hexadecimal representations.
Input and output structures reject unknown JSON fields. Outputs still require
binding to the ingestion journal and build identity before any lifecycle gate uses
them; deserializing a report is not verification.

## Saturation

`saturation(&SaturationInput, &SaturationCalibration)` reports:

- The exact mine, chain, block interval, evidence class and calibration identifier.
- Distinct liquidators among deduplicated, canonical, finalized observations.
- Median elapsed blocks from first proven eligibility to liquidation.
- Arithmetic mean of the observed direct-builder-payment / gross-bonus ratios.
- Sample counts for each metric and counts of excluded observations.

A missing eligibility block gives a missing delay. A missing tip or missing/zero
bonus gives a missing tip ratio. Neither is filled with zero. Direct builder
payments exclude gas, including priority fees already included in gas costs.

The state is `incomplete_scan` if completeness is unproven or any canonical input
is unfinalized, `insufficient_data` if sample requirements are unmet, and
`uncalibrated` if the caller has not established a calibration. Only a complete,
sufficient, calibrated input can yield `virgin`, `disputed`, or `dead`. The code
does not invent Census thresholds. The thresholds in tests are synthetic.

## Coverage and blind spots

`coverage(&ScanManifest, events, watches)` considers only the explicitly declared
chain / contract / event-topic / inclusive block ranges. Overlapping ranges fail.
Any supplied event outside those ranges fails rather than being silently dropped.
The final block hash of each range is checked against events at that height.

Every range must be complete and finalized, and every included canonical event
must be finalized, before a ratio is reported. A complete scan with zero events
has `fraction: null`, because its ratio has a zero denominator. It does not mean
100% coverage. An incomplete scan also has `fraction: null`.

Watch intervals are prospective. Registration must occur before the first watched
block; a watch cannot be backdated to improve a historical metric. A liquidation
counts as watched only if its mine, chain, contract, topic and block match a watch
active at that time. Multiple matching watches still count one event. Reasons for
misses distinguish unregistered scope, later discovery, and an inactive interval.

The denominator is the finalized liquidation events supplied for this complete
scan scope. Its completeness must be independently established by ingestion. This
function cannot discover omitted events, unknown contracts, unsupported protocols,
or chains outside the manifest, and makes no global-market coverage claim.

## Conditional monthly valuation

`value_month(history, config)` performs a **circular moving-block bootstrap of
observed daily economics**, with a seeded ChaCha8 random number generator.

For each simulated day:

```
daily_net = available_bonus * assumed_capture_share * (1 - assumed_builder_share)
            - successful_attempt_gas - failed_attempt_gas
            - other_execution_cost - daily_operating_cost
```

All quantities in a sampled day remain together. The model selects a uniform
historical start index and copies consecutive days for the configured block length,
wrapping at the history boundary. It repeats until the horizon is filled, then
repeats for every scenario. This preserves correlations inside each sampled block,
with an artificial circular boundary explicitly acknowledged.

The provided daily gas and execution costs must correspond to the modeled strategy
at the assumed participation. Gas from failed attempts is charged even when
capture share is zero. Builder share means direct payments outside the gas amounts;
otherwise the same expense would be counted twice. Financing and route/slippage
costs belong in `other_execution_cost_microusd` and must not be omitted merely
because this statistical core cannot measure them.

History must contain unique, consecutive UTC days. Missing days are rejected and
never filled as zero. A day with no economic activity may be included as an
explicit, independently evidenced zero observation. Samples are finite and bounded;
nonfinite assumptions and excessively large integer inputs are rejected.

The result contains every scenario, mean, interpolated 5th/50th/95th percentiles,
the mean of the lowest ceil(5%) scenarios, and the fraction strictly above zero.
The lower-tail mean is a finite empirical statistic, not a confidence guarantee.

Priority converts effort into the same monetary unit before division:

```
effort_cost = adapter_hours * explicit_hourly_rate + setup_compute_cost
priority_score = expected_operating_net_over_horizon / effort_cost
```

Zero or nonfinite denominators and nonfinite scores fail. Adapter setup cost is
reported as the denominator, not also silently subtracted from every month's
operating net. A caller wanting first-month total net must account for that
one-time cost explicitly.

This implementation is not yet a price-path / position-state / EVM simulation.
It does not estimate the capture share from competition, model unseen price
regimes, infer liquidity or legal execution opportunities, or validate the input
economics. Those are upstream requirements for the complete phase-B valuator.
Outputs are always marked `output_is_simulation: true`, even when based on realized
historical observations. Results are reproducible with identical inputs, seed,
locked dependencies, toolchain and target; cross-architecture floating-point bit
identity has not been established.

## Bayesian rival monitoring

`RivalMonitor` maintains a Beta-Bernoulli mixture over possible run lengths.
The observed Bernoulli variable is a separately calibrated indicator of elevated
competition. Each input retains its mine, chain, canonical block hash, finality,
class, sample ID and set of liquidator addresses.

For observation `x` and constant per-observation hazard `h`, the unnormalized
new-regime weight is `h * P(x | prior)`. Each existing regime receives weight
`(1-h) * previous_weight * P(x | regime)`. The observation updates the Beta
parameters in both cases. The normalized new-regime weight is reported as the
changepoint probability. This uses a change-before-observation model and does not
mistake the constant hazard itself for the posterior change probability.

The number of retained hypotheses is bounded. Lowest-weight hypotheses are pruned,
the retained weights are normalized again, and discarded probability mass is
reported. An alarm needs both elevated competition and configured minimum samples
and posterior probability. Priors, hazard, sample cadence and alarm threshold
require real-world calibration before a production claim.

An address not seen after initialization separately requests reevaluation; it is
an observed new address, not proof of a new person or organization. The monitor
does not change a bid or execute anything. Identical latest samples are idempotent;
out-of-order data, reused IDs and hashes, class mixing and unfinalized samples fail.

A reorg resets all model state; the caller must rebuild from the canonical journal.
The local core caps history at 100,000 observations and addresses and requires
archival or reconstruction at that bound. It is not itself a durable streaming
service or a Temporal workflow.

## Thompson research allocation

`ThompsonBandit` maintains one Beta prior per mine. Only externally verified,
canonical, finalized **realized** net outcomes can be recorded. Positive net adds
one success; zero/negative net adds one failure. This Bernoulli model estimates
the probability of positive net, not the magnitude of profit. Different profits
with the same sign have the same update; a value-sensitive production allocator
requires a separately validated reward model.

Outcomes are deduplicated by settlement event and outcome ID. Conflicts fail.
Posteriors are derived from retained outcomes, so retracting an orphaned block
removes exactly its contribution. Synthetic, historical simulation and Shadow
profits cannot train these posteriors. A verification-reference string only binds
an external proof; this estimator cannot verify receipts or settlement by itself.

For each cycle, the allocator draws one Beta sample per eligible, individually
affordable request, orders requests by the sampled probability, and admits whole
requests while budget remains. Ties use mine ID. Each mine receives at most one
research quantum per cycle; requests are not split. This is a bounded heuristic
for research scheduling, not a claim of optimal constrained capital allocation.

`ResearchBudget::default()` is zero. Every plan reports exact integer allocated
and remaining units and `authorizes_spending: false`. A separate reservation system
is required to prevent concurrent callers from allocating the same real resource.
The core retains at most one million outcome facts and can be rebuilt from the
isolated journal. It has no wallet, signing key, network client, or outbound action.

## Verification

Run the actual Rust tests with locked dependencies:

```
cargo test --locked --offline --test analytics_tests
```

The suite checks independent constant-cashflow expectations, failure gas, data
class separation, conflicting canonical evidence, no-lookahead coverage, unknown
metrics, stale/orphaned observations, Bayesian response to a synthetic regime
change, reorg rollback and idempotency. Property tests check allocation conservation,
deduplication invariance and the fact that additional failed gas cannot improve a
same-seed valuation. No test fabricates evidence of an operational phase exit.
