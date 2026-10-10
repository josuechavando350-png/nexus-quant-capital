# Wider search, bounded Census and small net opportunities

Decision recorded 2026-10-10 UTC (2026-10-09 Mexico City), from PR #3 head
`a1292b8a46e225934b1e1c5f375418718739a68b`. The user requested several
strategies, wider markets and many smaller opportunities. This is a research
priority decision, not an 80% success estimate or a new execution permission.
No B2B sales strategy is proposed.

## What the retained population actually covers

`execution_replay/compare_strategy_families.py` replays the full retained
127-winner/139-event population and pins receipts, economic source, loan
observations and inventory readbacks. Its disjoint transaction families are:

| Family | Transactions | Liquidation events | Transactions with selected funding observations |
| --- | ---: | ---: | ---: |
| Single liquidation, same debt/collateral asset | 9 | 9 | 7 |
| Single liquidation, different assets | 107 | 107 | 52 |
| Multiple liquidations, including different assets | 11 | 23 | 6 |

There are 53 distinct collateral/debt pairs, with overlap between families.
The nine same-asset transactions span three assets; they are **not** the nine
historical WETH cost-reference cases. Sixty-five transactions have at least one
selected funding observation; 62 lack these selected observations. Absence here
does not prove own principal or rule out another funding route. Counts include
overlapping funding protocols and must not be added as independent captures.

Two legacy economic rows omit flash indices that the later full receipts and
22-event funding file contain: transaction `0xfcd28a32be33d1c047b04c5005285c31e5d8dcc92132c4353eebbc9c7426f369`
at log 185 and `0xfd76e2f691f2b18e4116d41d7842c7717b77674d3092827d58daad3dc6a9c427`
at log 916. The new ledger exposes both comparisons and rejects any other
disagreement. Immutable prior evidence stays unchanged and is not recertified.
All 127 remain insufficient evidence for NQC economic admission.

These are executed winners selected after the fact, not the whole opportunity
population or a survey of all protocols. A difficult Ethereum case cannot
establish that smaller opportunities across other markets are unviable.

## Research order and falsification

| Priority | Candidate family | Why investigate | Gate that can reject it |
| --- | --- | --- | --- |
| 1 | Small Aave V3 liquidations on Base and Arbitrum | Reuse the liquidation model; test whether complete network cost permits smaller net edges | Exact deployment/state, liquidatable opportunities including misses, flash access, realizable unwind and complete fee/capture evidence |
| 2 | Morpho Blue liquidation markets, starting with a verified deployment on Base | Alternative market structure and financing/callback composition | Pin market ID, tokens, oracle, LLTV, liquidity, deployed code and atomic repayment; documentation is not a capital quote |
| 3 | Same-chain liquidations with a collateral swap/backrun | The existing 107 cross-asset single winners justify examining monetization routes | Executable depth, adverse selection, swap fees, slippage, ordering and competing bids erase the margin |
| 4 | Compound III discounted collateral purchases | Different inventory-sale mechanism may create a separate opportunity family | Discounted inventory actually available, reserves/pauses permit purchase and an atomic funded sale repays in full |
| 5 | Standalone same-chain atomic arbitrage | Potential reuse of funding and route tools | No independently observed spread after all costs, or no competitive capture evidence |

The order is an engineering judgment based on reuse and compatibility, **not** a
measured ranking of expected profits. Existing Balancer-funded WETH work stays a
controlled baseline while the search widens. No cross-chain flash repayment,
bridge-funded inventory, own collateral or assumed free infrastructure is used.
Gas-wallet provisioning on each chain is an unresolved prerequisite; the MXN
2,000 cumulative gas-only limit does not authorize bridging or new spending.

For each market, first freeze its chain ID, exact addresses/market IDs, historical
block/hash window and acquisition limits. Then retain complete events, position
states, rejected/failed/missed opportunities, exact costs and same-time funding
and unwind quotes. A documentation shortlist is not historical coverage. Use a
single coordinated rate-limited acquisition queue: the existing Ethereum worker
keeps its lock and is neither duplicated nor accelerated. No new large sweep was
launched in this revision.

Maintain a chronological discovery ledger and freeze each decision rule before
an untouched later evaluation window. The current historical cases cannot become
a holdout after repeated inspection. Compare candidate size bands within each
asset using native units; aggregate value only with supported contemporaneous
conversion routes. Measure inclusion, failures, downtime, correlated competition
and concentration, not just successful trade counts.

Daily portfolio net is the sum of **actually captured** net outcomes less
attributable failures and shared costs counted once. A hundred small apparent
edges are not a hundred independent or attainable profits. Choose a portfolio
only after resolving shared liquidity, borrower/transaction conflicts, nonce,
gas-wallet and compute constraints. Neither small principal nor low quoted gas
alone establishes a profitable operation.

The declared Ethereum 25880316–26095351, 67-asset Census keeps every existing
closeout gate. Expansion candidates receive separate scopes and dispositions;
they neither inherit certification nor move its milestones. No profitable
strategy is admitted yet. The user's desired 80% has no fabricated estimator.

## Official discovery sources checked 2026-10-10 UTC

- [Aave deployments](https://aave.com/help/aave-101/accessing-aave) lists Base
  and Arbitrum V3 deployments. This establishes places to investigate, not local
  opportunity volume or protocol state at a historical block.
- [Aave flash loans](https://aave.com/docs/aave-v3/guides/flash-loans) documents
  atomic repayment and fees. Read deployed fee parameters; do not assume a fee
  waiver or use debt-opening collateral/delegation outside the capital policy.
- [Morpho contract reference](https://docs.morpho.org/developers/contracts/blue/)
  describes its flash-loan callback, zero documented flash fee and balance-bound
  liquidity. [Addresses](https://docs.morpho.org/developers/contracts/addresses/)
  is a discovery registry, not a proof of historical deployed code or access.
- [Morpho liquidation](https://docs.morpho.org/developers/borrow/concepts/liquidation/)
  describes LLTV-based eligibility and its liquidation incentive. Incentives are
  not net profit; token behavior, oracle and unwind remain market-specific.
- [Compound III liquidation](https://docs.compound.finance/liquidation/)
  separates absorption from buying discounted collateral. Liquidator points or
  possible future governance compensation are not admitted cash income.
- [Base network fees](https://docs.base.org/specifications/transactions/network-fees)
  includes execution and L1 publication components. The cheapest displayed L2
  fee is not a complete transaction quote.
- [Arbitrum fees](https://docs.arbitrum.io/how-arbitrum-works/deep-dives/gas-and-fees)
  includes parent-chain posting and child-chain execution components. Costs and
  inclusion behavior need their own measurement; Ethereum figures do not transfer.

These web pages inform prospectively selected hypotheses only. They are not
substitutes for exact historical captures, code/state proofs or independent
Market/Capital/Economic authority acceptance.
