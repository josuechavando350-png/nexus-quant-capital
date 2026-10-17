# Economic evidence and monthly capacity — 2026-10-17 UTC

**No authentic NQC operation is economically admitted. Monthly NQC income is
not yet estimable.** We now have a bounded historical census and a more precise
accounting of the external case B. Neither supplies the missing financing,
pretransaction replay or competitive capture evidence.

Baseline commits `31cb31e58e223c2b1769bf38be1f2a59afe598b3` and
`1e21bbc40ac87f89f89a0eb9d277124103db589c` were checked through GitHub; the
authorized branch initially pointed to the latter. Reproduced baseline:
150 Python / 50 Solidity / 9 isolation. Current Python suite: **159 passed**,
including nine checks of the new evidence analysis. Solidity is unchanged and
its 50 tests were executed again this session. No network transaction was signed
or submitted; research spending remains zero.

## 1. Case B: actual Fluid route, not a Uniswap V2 replay

`case_b_route_audit.py` connects three independent types of evidence: the prior
indexer call trace, the saved public RPC receipt, and the official Fluid source
and deployment record at commit `9496626f71a761fc296dc3b2efbfd54c504e18f0`.
That source commit is dated 2026-09-16. The extraction is recorded, with original
Git blob/SHA-256 identities and selected ABI, in `fixtures/fluid_case_b_reference.json`.
It does **not** establish historical deployed runtime identity.

The observed pool is `0xdd72157a021804141817d46d9852a97addfb9f59`, Fluid ezETH/ETH,
with liquidity layer `0x52aa899454998be5b000ad077a46bbe360f4e497`.
The call selector `0x2668dfaa` is **swapIn**, not `swapInWithCallback`.
An initial decoder assumption used the latter and correctly failed; the actual
failure is retained in `route-selector-failure.log`. Morpho's callback is still
present; it must not be confused with Fluid's optional external swap callback.

The swap call, return, `Swap` event, two signed `LogOperate` events and existing
token/native ledger agree:

| Item | Exact amount | Evidence boundary |
| --- | ---: | --- |
| ezETH seized and sent to Liquidity | 24.343983926960874121 | Trace token calls + receipt transfers |
| ezETH credited as pool supply by `operate` | 24.340940928969000000 | Call + event; not the full token transfer |
| ETH withdrawn from Liquidity to executor | 26.409680973611000000 | Call + event + trace native transfer |
| WETH debt repaid | 26.039738525656992415 | Morpho return/model + transfer event |
| Sale minus debt, before remaining costs | **0.369942447954007585 ETH equivalent** | Observed route only |
| ETH sent entirely to `block.coinbase` | **0.368092735714237547** | Trace, not builder attribution |
| Incremental executor WETH after coinbase | 0.001849712239770038 | Exact balance reconciliation |
| Sender gas: 745509 × 266148625 wei | 0.000198416195275125 ETH | Receipt/indexer agreement |
| Incremental residual after known costs | **0.001651296044494913 ETH equivalent** | Upper bound before unknown external obligations |
| Pre-existing executor WETH, excluded from income | **0.006392502690919791** | Trace balance read |
| Final executor WETH, inferred | 0.008242214930689829 | Includes the pre-existing balance |

Executor native change is zero; all seized collateral is converted. Initial/final
native and collateral balances remain unknown; zero *change* is not zero initial
balance. Sender/executor ownership consolidation and outside financing are not
proved. The residual is not a certified realized profit, nor an NQC quotation.
Keeping the same observed route and coinbase payment, additional obligations of
1651296044494913 wei would consume the entire arithmetic residual; any greater
cost makes it negative. The less restrictive 369942447954007585-wei margin before
coinbase/gas is not all available to NQC: removing the original bid changes the
inclusion conditions, and sponsorship would need its own evidenced payment.

Both Liquidity operations have zero borrow amount: this observed swap uses supply
and withdrawal accounting. The 0.003042997991874121-ezETH difference between
transfer and supply credit is **not the total DEX fee**. Reference source separates
swap fee, revenue cut, precision adjustment and imaginary-reserve calculations.
Do not deduct this difference again from the already-net sale output. Total fee
and price impact cannot yet be separated from authenticated historical parameters.

At the oracle price observed inside the winning transaction, seized collateral
has mathematical value 26.476602466351797043617625222410141508 WETH. Its difference
from the executed sale is 0.066921492740797043617625222410141508 WETH. This is an
oracle-to-execution difference, not an independently identified fee or a prior
NQC executable quote. Python preserves both as exact fractions.

Four `readFromStorage` calls are now identified by their deployment-record slots:
token0/token1 exchange-price configurations and pool supply positions. Their
values were observed **inside the winner before Fluid's operate calls**. They are
not a complete, authenticated state before transaction index 1. Event packed
totals are explicitly post-operation values. No post-event value is used to
manufacture a pre-event opportunity.

Missing for replay: parent account/storage proofs and runtime bytes; the effects
of prefix transaction `0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`;
Morpho/oracle/IRM state; Fluid pool configuration, actual and imaginary reserves,
balance/withdrawal/borrow/utilization limits and time-dependent state. Fluid's
official integration guide requires more than two reserves. Original V2 tests
remain useful synthetic boundary tests, not a replacement for these inputs.

## 2. Fixed historical windows and coverage

The selection was saved before querying results (`selection.json`). All Ethereum
Morpho `Liquidation` API records were requested without asset, size, liquidator,
bad-debt or profitability filters. UTC half-open windows:

| Window | Start inclusive | End exclusive | Events | Transactions | Markets | Liquidator addresses |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 30 days | 2026-09-17 00:00 | 2026-10-17 00:00 | **143** | **141** | 60 | 49 |
| 7 days | 2026-10-10 00:00 | 2026-10-17 00:00 | **29** | **28** | 22 | 16 |

Forward pages contain 100, 43 and 0 records; reverse pages contain 100 and 43.
Both normalized sets match exactly. The initial reverse query reports total 143;
its cursor-filtered next page reports 43, not a second population total. A
separate seven-day query returns exactly the 29-row subset. Identity is
`(chain, txHash, logIndex)`. Duplicate events, a missing terminal page, altered
amounts, conflicting metadata and lossy floating-point integers fail validation.

This is **exhausted API pagination**, not proof of complete Ethereum coverage.
The same provider backing both directions is not independent corroboration.
The public API has no SLA. The `eth_getLogs` positive control for B returned
HTTP 200 with `[]`, while its already-saved receipt contains the matching Morpho
event. The validator records `KNOWN_POSITIVE_OMISSION_OR_CONFLICT` and refuses
to certify population completeness. No broad scan was built on that source.

Before retrieving more receipts, a diagnostic selection was frozen: first event
per debt-token address, all WETH-debt transactions, and both transactions with
multiple liquidation events. It contains 23 unique transactions. B's existing
receipt is reused; all **22 new requests returned `result: null`**. This is missing
evidence, not failed execution or zero gas. The sole receipt cross-check matches
B's raw liquidation amounts and transaction gas. This diagnostic sample is not
a representative profit sample. All envelopes and the bounded read-only collector
are retained; there were no retries, credentials or batch-RPC submissions.

Additional archive alternatives were checked in public documentation: BlockPI
distinguishes its public endpoint from key-based archive access; Tenderly's node
setup uses a project API key. No account/private key was supplied and no new
subscription or endpoint was activated. Earlier pruned/403/405 results remain
documented; blocked methods/providers were not retried or bypassed.

## 3. What the frequency sample does and does not say

Thirty-day observed event frequency is exactly 143/30 per day; seven-day frequency
is 29/7. The windows overlap. Four days in the longer window have no API records;
one day (September 26) contains 36. Fifteen of the 29 seven-day events fall on
October 15. Constant daily flow is not established.

Of 143 events, 94 have USDC debt, 9 USDT, 9 RLUSD, 7 msETH and 7 WETH; ten
other debt-token addresses account for the remaining 17. Amounts are aggregated
by token address and decimals, never by ticker or assumed USD parity. For example,
USDC repaid totals 1959916.002871 tokens and WETH 27.458932397784792302 tokens.
Those are repaid principal, **not revenue**. Historical USD conversion is null.
The JSON report retains every debt-token aggregate and daily count.

**43 events report bad debt**, including 3 in the seven-day subset. Applying a
liquidation-incentive percentage mechanically to principal would be misleading.
Borrower state, exact seizure/repayment mode and any loss socialization require
replay. The current shares-based Python quote is not a full bad-debt transition
model. These events are retained in the sample, not silently excluded.

The largest liquidator-address counts are 35 and 15 events. They reveal observed
concentration only: addresses need not identify different firms; unsuccessful
bids, private bundles, latency and builder relationships are unobserved. Two
transactions each contain two liquidations. Shared gas and conflicting state
mean 143 events cannot be counted as 143 independent wins.

Technically compatible and plausibly winnable NQC counts remain **unknown**.
Authentic economically admitted NQC operations remain **zero**. Seven WETH-debt
events simplify gas-asset conversion; they do not establish seven eligible
opportunities. The other 136 need a separate conversion under the current NQC
implementation. No funded, real DEX route has been validated for either group.

## 4. Architecture, deployment and sponsorship

| Requirement | A: own callback executor | B: experimental Bundler3 flash route |
| --- | --- | --- |
| Morpho debt-token cash | Not required for collateral-first callback repayment | At least the flash principal at transfer time |
| External conversion liquidity | Required | Required |
| Equal-state local gross call gas | 516339 | 400205 |
| Initial deployment | Executor plus any required adapter | Avoided only if all compatible adapters already exist |
| Authentic Fluid route / total transaction gas | Unverified | Unverified |
| Owner-zero-ETH funding / positive net result | Unverified | Unverified |

The 116134-gas difference is a warm synthetic call measurement, excluding
intrinsic/calldata gas, refunds, initialization, funding and deployment. At
10 gwei it corresponds arithmetically to 0.00116134 ETH, **not** a measured
historical cost advantage. Market supply minus borrowing is not the Morpho
contract's aggregate token balance; a single-market calculation cannot prove
flash cash availability. More eligible states for A do not imply positive margin.

First-operation economics must charge any actual deployment and initialization
cost, plus its financing. Later amortization cannot supply upfront ETH. B's
synthetic V2 bridge was locally deployed too; it is not a production deployment
available for free. Bundler3 remains deprecated; current Bundles are specialized
entrypoints and do not provide a general replacement for arbitrary DEX composition.

Titan documents automatic ETH funding for insufficient gas/value funds, and
Quasar for insufficient gas funds, conditional on builder balance increase.
Neither reviewed page establishes NQC acceptance, a repayment beneficiary,
funding limits, creation-plus-execution support, or our failure-liability terms.
`refundPercent` is a refund to the user, not the user's sponsor repayment.
Coinbase income is not automatically builder income. No bundle was submitted.

The existing exact ledger keeps sponsor advance A, returned unused funds U,
operation payment R, other verified builder receipts V, funding gas F, separate
proposer payment P and other costs O distinct: builder margin = R+U+V-A-F-P-O.
Gas paid from A is not charged a second time. Missing terms stay unknown.
An unexecuted bundle has no onchain gas execution; an included reverted
transaction burns gas, and separate funding/deployment transactions do not
automatically revert with it. These liabilities require evidence before admission.

## 5. Monthly categories and target requirements

| Category | Current result |
| --- | --- |
| A — NQC realized income | 0 certified gains; no real NQC operations |
| B — authentic historical NQC replay | 0 completed positive replays |
| C — conditioned potential | Sensitivity only; no inferred win probabilities |
| D — defensible monthly expectation | **Not estimable** |

For a genuinely measured average net contribution m per captured transaction,
after all variable costs, and fixed monthly cost F, the target T requires at least
`ceil((T+F)/m)` captured transactions. Initial deployment/funding adds to first-month
F and still requires upfront financing. Failure costs must already be included
or added separately. Heterogeneous margins require summing the individual net
contributions; an average cannot be inferred from repayment principal.

The table is exact sensitivity with F=0, an optimistic **requirement bound**, not
measured production cost. These margins are explicit hypotheses, not observations:

| Target net USD/month | $10 net/win | $50 net/win | $100 net/win | $500 net/win |
| ---: | ---: | ---: | ---: | ---: |
| $1,000 | 100 | 20 | 10 | 2 |
| $5,000 | 500 | 100 | 50 | 10 |
| $10,000 | 1000 | 200 | 100 | 20 |
| $50,000 | 5000 | 1000 | 500 | 100 |

At $100 net per transaction, $50k would require 500 captures, exceeding the 141
transactions in this particular API sample even under hypothetical full coverage,
compatibility and capture. At $500 it requires 100 captures, still unproved.
This comparison is confined to the observed window; it is not a bound on all
possible future opportunities or alternative transaction partitioning.

To turn any target into a defensible estimate requires: independently checked
event coverage over multiple predetermined windows, authentic per-candidate
net margins (including negative outcomes), real route compatibility, documented
gas funding and deployment costs, and time-stamped evidence of attempts, latency,
competing state and inclusion outcomes. Required capture fraction is K/N for K
needed wins and N genuinely eligible opportunities; N and win probability are
currently unknown. Public successful liquidations alone cannot determine either.

## Reproduce and next decisive experiment

Use the pinned environment in REPRODUCE.md, from this directory:

```sh
python -m unittest discover -v -s tests -p 'test_*.py'
python case_b_route_audit.py > /tmp/nqc-case-b-route.json
python monthly_census.py > /tmp/nqc-monthly-census.json
# Both analysis commands intentionally exit 2: economics remains pending.
sha256sum -c evidence/2026-10-17-monthly/SHA256SUMS
```

The saved `validation-run.json` contains actual absolute tool paths, commands,
return codes and source hashes. Baseline Forge logs record 33 + 17 actual passes.
Nine isolation tests pass; 106 workflows remain disabled. Original Git object
verification, Rust tests, remote CI and authentic EVM replay remain unrun.

The next decisive input is a freely available, authorized witness sufficient to
replay B's parent state, prefix and original Fluid route. Validate receipt/state
parity before substituting NQC. Restore identical state for each architecture,
preserve pre-existing balances, measure total execution/creation/funding costs,
and reconcile an evidenced sponsor payment. Test reduced liquidity, changed order
and larger costs. Until then, build no monthly income forecast from this census.

Primary documents reviewed 2026-10-17:

- https://docs.morpho.org/developers/api/get-started/
- https://docs.morpho.org/developers/contracts/bundles/
- https://docs.fluid.instadapp.io/integrate/dex-swaps.html
- https://docs.fluid.instadapp.io/contracts/contract-addresses.html
- https://docs.titanbuilder.xyz/api/eth_sendbundle
- https://docs.quasar.win/api/eth_sendbundle
- https://docs.flashbots.net/flashbots-protect/ratelimiting
- https://docs.blockpi.io/basic-tutorials/best-practices
- https://docs.blockpi.io/pricing/pricing-and-rate-limit
- https://tenderly.co/blog/web3-tech-stack/
