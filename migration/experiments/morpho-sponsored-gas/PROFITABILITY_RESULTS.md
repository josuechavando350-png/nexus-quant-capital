# Exact economic boundaries — 2026-10-17 UTC

## Latest case B cost boundary (observed external route)

`case_b_route_audit.cost_frontier` now computes an integer-exact cost frontier.
Keep the observed Fluid output, debt, entire coinbase payment and 745509 gas
units fixed. These are sensitivity assumptions, not NQC gas or sponsor quotes.

| Total effective gas price | Residual ETH-equivalent before unknown obligations |
| ---: | ---: |
| Observed 0.266148625 gwei | 0.001651296044494913 |
| 1 gwei | 0.001104203239770038 |
| 3 gwei | **-0.000386814760229962** |
| 5 gwei | -0.001877832760229962 |
| 10 gwei | -0.005605377760229962 |

The maximum integer gas price leaving a strictly positive residual before other
costs is **2481140052 wei/gas** (2.481140052 gwei); one wei/gas more fails that
strict boundary. At the observed gas price, additional obligations of exactly
1651296044494913 wei consume all remaining residual. A strictly positive result
allows at most 1651296044494912 additional wei under these unchanged assumptions.
Any unaccounted deployment, funding, sponsor remuneration or external liability
reduces that amount. No positive net result is certified while those costs and
ownership consolidation are unknown. The initial 0.006392502690919791 WETH stays
excluded; the 0.368092735714237547 ETH coinbase payment is fully charged, without
attributing it to a particular builder. Output already includes conversion costs.

This refutes profitability at 3 gwei for this fixed route and bid, not for all
Morpho liquidations or all possible bids. Removing the bid would alter inclusion
conditions. Original route gas cannot be substituted for either NQC architecture.
The one-wei boundary, already-exhausted budget and exact-integer checks pass.
Executed output: `evidence/2026-10-17-prospective-recovered/final-case-b-costs.json`.

## Earlier economic checkpoints

`MONTHLY_POTENTIAL.md` and `case_b_route_audit.py` identify
case B's actual Fluid ezETH/ETH conversion. It is not the V2 fixture below.
Its observed sale-minus-debt is 0.369942447954007585 ETH-equivalent; after the
entire coinbase payment and sender gas, the residual upper bound is
0.001651296044494913 before unknown external obligations, excluding old WETH.
That is not certified profit or an NQC executable quote. The new 143-event
30-day census still does not supply authentic net margins or capture rates;
monthly NQC profit remains not estimable. Earlier synthetic results follow.

Baseline `a96be36` was checked against the GitHub branch and reproduced: 141
Python / 48 Solidity / 9 isolation tests. This continuation adds an exact boundary
model, six focused Python tests and two Solidity test functions. The outcome is
147 Python / 50 Solidity / 9 isolation, all passing. Synthetic state remains
synthetic; economically admitted authentic operations remain **zero**.

## Why the 0.5 ETH allocation fails

The unchanged synthetic position repays **8 WETH**, seizing exactly
**9.278589654372535368** collateral. Its oracle and initial pool price are both
**0.9 WETH/collateral**. Morpho's rounded incentive factor is
`1043841336116910229 / 10^18`.

| Component at 1000 collateral / 900 WETH reserves | WETH units (18 decimals) |
| --- | ---: |
| Collateral valued at spot, rounded down | 8.350730688935281831 |
| Price impact evaluated without fee | -0.076770679741992938 |
| Additional effect of the 0.3% fee | -0.024594363622737655 |
| Executable pair output | 8.249365645570551238 |
| Liquidation repayment | -8.000000000000000000 |
| Available for **all** external costs and operator net assets | **0.249365645570551238** |

The fee and impact above already reduce executable output; subtracting them again
would double count. Flash principal is a financing inflow and equal repayment:
it cancels in B's final ledger, but does not eliminate the liquidation debt.

Even as pool depth tends to infinity, fee-adjusted output tends to the exact
rational `10407098121085594982133 / 1250` raw WETH units. Surplus is strictly less
than **0.3256784968684759857064 WETH**. Finite pair capacity tightens the ceiling;
the JSON report computes that bound separately. Thus the previous 0.5 allocation
fails at every allowed depth at this price, even before its additional 0.1 token
profit requirement. This refutes that scenario, not every possible market.

## Necessary and sufficient arithmetic conditions

Let `s` be seized collateral, `x/y` the collateral/loan reserves, `D` repayment,
`C` the complete effective external cost in WETH-equivalent units, and `P` a
required operator residual. WETH unwrap is 1:1 here; other loan assets require an
additional executable conversion. The original pair quote is

`Q = floor(997*s*y / (1000*x + 997*s))`.

For these inputs, `Q >= D+C+P` is necessary and sufficient for the **output
arithmetic**, not transaction admission, protocol eligibility or sponsorship.
For positive integer profit use `P >= 1`. If costs are unknown, the result is
a cost ceiling, not an assumed profitable operation. At 1000/900, at most
`249365645570551237` wei-equivalent may leave the operator for at least one wei
to remain. At 100/90 the full 8-WETH liquidation cannot repay even before costs.

At fixed rational spot `p=a/b`, use the exact reserve lattice `x=b*k, y=a*k`.
For target `T=D+C+P`, define `delta=997*s*a-1000*b*T`. If `delta<=0`, no finite
depth works. Otherwise the exact minimum scale is

`k_min = ceil(997*s*T / delta)`.

The reserves and post-input collateral must fit uint112. This capacity check is
also necessary. Using arbitrary `floor(p*x)` while binary-searching x would be
incorrect: the quote can fall when x increases but the integer y stays unchanged.
`profitability_boundary.py` instead solves the integer inequality directly.

For fixed x, the minimum y is `ceil(T*(1000*x+997*s)/(997*s))`. This quantifies a
required price change without pretending it happened. For example, paying 8.5
WETH at x=1000 would require at least **927.344032096288867256 WETH** in the pool,
instead of the observed synthetic 900. No test reprices that fixture to claim a gain.

## Independent original-code execution at the threshold

The existing plan requires 8 WETH debt + 0.1 native allocation + 0.01 WETH token
residual. Python generates an ABI fixture for the minimum reserves at price 0.9:

| Collateral reserve | WETH reserve | Pair output | A / B |
| ---: | ---: | ---: | --- |
| 347.849299304143955810 | 313.064369373729560229 | 8.109999999999999999 | Both revert |
| 347.849299304143955820 | 313.064369373729560238 | 8.110000000000000000 | Both settle |

The adjacent lattice points differ by 10 collateral base units / 9 WETH wei.
Original Morpho, Bundler3, GeneralAdapter and V2 pair bytecode execute both edges.
Checks cover debt, pair reserves, token/native operator receipts, sponsor/coinbase
payments and zero route balances. The Python parser rejects altered trace output.
An independent exhaustive small-integer enumeration checks the closed-form formula.

The initial new fixture had a trailing newline, rejected by Foundry `parseBytes`.
That failed trace is retained. The generator now produces the same newline-free
format as the existing ABI fixtures; the corrected EVM test really ran.

The **0.1 allocation is not all an external expense**: 0.05 goes to a synthetic
sponsor, 0.04 to coinbase and 0.01 back to the operator. At 1000/900 the operator
therefore receives 0.149365645570551238 WETH plus 0.01 ETH. Those are local gross
receipts after test allocations, not demonstrated after-gas profit. The test
sponsor has no proved advance, builder identity or required remuneration.

## Size, incentive and architecture

The report varies liquidation shares of the same unhealthy position, maintaining
its oracle and the pool price. At 100/90 reserves, repayment sizes 1 and 2 WETH
leave respectively 0.028813190089088135 and 0.034370961525381457 WETH before costs;
sizes 4 and 8 lose value. These smaller mathematical margins are not sponsored
opportunities. Gas and all other costs still need evidence and may consume them.
Counterfactual LLTV comparisons are explicitly separate markets: at LLTV 0.90 or
0.945 this position is healthy, so the model rejects liquidation rather than
reporting a fictitious margin.

At identical 8-WETH Morpho cash and 1000/900 reserves, separate fresh test functions
measure the external execution call after payload construction:

| Route | Local gross call gas | Initial Morpho loan cash required |
| --- | ---: | ---: |
| A: NQC callback | 516339 | 0 |
| B: Bundler flash | 400205 | 8 WETH |

The 116134-gas difference favors B **in this warm synthetic call measurement**.
It excludes intrinsic transaction/calldata charges, storage refunds, creation,
funding transactions and real token/router implementations. It is not a production
gas estimate. A's extra balance/state guards also make the implementations
different; fewer calls or lower gross gas does not establish equal safety.
For the same conversion, repayment and financing terms, the economic comparison
is `net_A-net_B = total_cost_B-total_cost_A`, provided both routes are feasible.
A is technically available when B lacks flash cash, but needs a profitable DEX
sale and gas funding nonetheless. B may avoid executor deployment only if every
required adapter is already deployed and compatible; the local V2 bridge is a
test contract, not evidence of such a production route. Bundler3 remains deprecated.

## Sponsorship accounting and evidence gates

Retain `economic_ledger.py` for separate asset/participant accounting. Let A be
the sponsor advance, U its returned unused part, R the sponsor payment from the
operation, V other **verified** builder receipts, F funding-transaction gas, B
the builder's separate proposer payment and O its other costs. Builder margin is
`R+U+V-A-F-B-O`; a required margin M implies `R >= A+F+B+O+M-U-V`.
The operator must also cover its direct coinbase payment and financing/conversion
obligations. Gas paid from A must not be subtracted from the sponsor twice; a
payment already reimbursing gas must not be counted again as another gas expense.
Unused advanced funds are not trading proceeds. Establish complete initial/final
balances before consolidating any residual assets or outstanding liability.

Titan documents funding when insufficient gas/value balance prevents execution;
Quasar documents gas funding. Both condition sponsorship on increased builder
balance. Neither reviewed endpoint page supplies NQC acceptance, a verified
repayment address or a guaranteed creation-plus-execution financing policy.
`refundPercent` describes a builder-to-user refund, not our repayment to a sponsor.
No bundle was sent and no transaction was signed. Coinbase payment alone remains
insufficient evidence of builder income. No inclusion means no onchain execution
cost for that unexecuted bundle; an included reverted transaction consumes gas,
and separately included funding/deployment transactions do not revert with it.
Actual rejection/partial-inclusion liability terms are still unverified.

## Reproduction

Use the pinned toolchains in REPRODUCE.md. From this directory:

```sh
python profitability_boundary.py --check-fixture
FOUNDRY_PROFILE=core forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 --match-test 'testExactPythonDepthBoundaryBothRoutes|testTraceCallbackAtSameCash|testTraceFlashAtBoundary' -vvvv
python profitability_boundary.py --trace evidence/2026-10-17-profitability/economic-boundary-traces.log.gz
# Final command exits 2: synthetic result, never economic admission.
```

Full traces, failure log, model output, validation commands and hashes are under
`evidence/2026-10-17-profitability/`. Primary documents rechecked 2026-10-17:
https://docs.titanbuilder.xyz/api/eth_sendbundle and
https://docs.quasar.win/api/eth_sendbundle . Original pinned source identities
remain in LIQUIDITY_BOUNDARY_RESULTS.md and the build manifests.
