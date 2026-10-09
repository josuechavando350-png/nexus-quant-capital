# NQC — Architecture V2 and the gas-capital amendment

Accepted task requirements, 2026-10-09. This prospective specification records
the user's architecture and subsequent explicit capital amendment. It is not a
certificate, a new trading permission, or a statement that the layers exist.
Historical artifacts retain their original meaning and exact bytes.

## Governing objective

Discover, understand, finance, execute and optimize economically superior
opportunities with verifiable evidence. Technological sophistication cannot
substitute for a demonstrated economic advantage. A negative finding is valid;
a desired profitability number is not evidence.

The later user instruction authorizes **MXN 2,000 of operator capital for gas**.
It supersedes the earlier zero-own-gas requirement prospectively. The active
model is external principal plus a bounded own-gas contribution, not
`OWN_CAPITAL = 0`. No operator principal, collateral, guarantees or additional
contingent liabilities have been authorized. See `capital-policy.json`.

## Required layers and exits

| Layer | Required work | Exit evidence |
| --- | --- | --- |
| 1. Protocol / Fork Truth | Deterministic bytecode, storage, proxies, implementation/configuration, oracles, arithmetic, historical forks, reorgs and canonical state. | Independent reproduction and parity with explicit protocols, contracts, chains and blocks. No absolute precision outside the certified scope. |
| 2. Real Market Census | Markets, positions, borrowers, liquidations, capital, liquidity, routes, gas, competition, censored opportunities and conflict sets. Market Truth, Capital Truth and Economic Truth are separate mandatory authorities. | Exhaustive declared scope, reconciled sources, reproducible executable/non-executable/insufficient-evidence classifications with reasons, and treatment of every material unknown. |
| 3. Sovereign Market Intelligence Fabric | Temporal market graph; winning and losing transaction archaeology; probabilistic competitor forensics; calibrated intent/hazard inference; causal counterfactuals without future information; multidimensional opportunity identity; Decision-Time Truth Ledger. | Out-of-sample anticipation, calibration and incremental economic value against explicit baselines. Starts during Census. |
| 4. Shadow Execution | Detect, classify, decide, hypothetically finance with verified sources, route, construct, simulate, assess competition/inclusion and reconcile; chronological rejected/failed/missed opportunity ledger. | Reproducible adversarial calibration without hindsight. Distinguish technical possibility, financing, estimated inclusion, supported capture, hypothetical profit and realized profit. Simulation alone cannot establish that Nexus would have won. |
| 5. Apex Execution Hardening | Formal verification, fuzz/property testing, Rust kernel, deterministic replay, fault/reorg tolerance, kill switches and fundamental safety. Incremental latency, differential clients, builder/relay intelligence, public/private inclusion and recovery improvements. | Measured improvement over a reproducible baseline. Fundamental controls precede Canary; multi-region and owned nodes require demonstrated benefit. |
| 6. Canary | Minimum-size real operations with authenticated funds and permissions, concurrency/exposure limits, least privilege, monitoring and automatic shutdown. Own gas is limited by the later MXN 2,000 amendment. | Real executions match Shadow within predefined cost and risk limits. No hidden operator loss obligation. |
| 7. Real P&L Evidence | Reconcile transactions, balances, receipts, tokens and realized conversions; principal/bonuses/flash fees/swaps/slippage/gas/builders/funder payments/failures/inventory/infrastructure and other attributable costs. | Independent financial reconciliation separating realized net profit, paid costs, remaining exposure/liabilities, estimated opportunity costs and hypothetical income. |
| 8. Revenue Reliability Certification | Initial hypothesis: P(monthly net P&L >= USD 15,000) >= 0.90. Advanced hypothesis: P(monthly net P&L >= USD 55,000) >= 0.90. Prefer monthly net Q10. | Separate falsifiable certifications using sufficient real evidence, temporal holdout, regimes, autocorrelation, concentration, tail losses, downtime, failure costs and confidence bounds. Neither target is an assumption. |
| 9. Final Certification — Liquidations | Correctness + coverage + capital + routing + execution + competition + real P&L + reliability + reproducibility. | Technical correctness and demonstrated commercial viability together. Technically valid but commercially uncertified is a valid outcome. |
| 10. Multi-Strategy Expansion | Arbitrage, backruns, auctions, keepers, bad debt, refinancing, atomic compositions and protocol-specific opportunities. | Each strategy independently traverses Truth, Census, Intelligence, Shadow, Execution, Canary, P&L and Reliability. Research can begin early; results and permissions do not transfer. |
| 11. Global Capacity Optimization | Allocate external capital, flash liquidity, gas, compute, routes, nodes, nonces, builders/relays and time under shared conflicts. Minimal allocator begins in Census/Shadow. | Better total realizable risk-adjusted net profit without resource double counting or internal competition. Full optimization follows multiple viable strategies. |
| 12. NQC Apex | Champion/challengers, hypotheses, learning, causal analysis, regime adaptation, drift detection and policy evolution. | Independent validation and measurable sustained improvement before affecting live operations. No autonomous expansion of financial permissions, risk limits or certified contracts. |

Certification dependencies: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9.
Layer 3 starts during 2; Shadow development may use explicitly partial evidence;
critical safety begins before Canary; alternative-strategy research may start
before commercial liquidation certification. Independently validated strategies
precede 10 → 11 → 12.

## Evidence constitution

No layer certifies itself. Every material claim needs an independent authority,
explicit scope, exact commit and tree, block/hash/timestamp/provenance, immutable
hashed evidence, deterministic reproduction, mismatch and failure ledgers,
uncertainty classification, falsification criteria, absence of future information,
and explicit non-claims. A different script from the same author is not by itself
an independent certifying authority.

The Decision-Time Truth Ledger must separate when data existed, when it was
received, what Nexus actually observed at a decision, and what became known
afterward. A block timestamp is not proof that Nexus possessed the information
then. Recovered historical evidence must not be reclassified as contemporaneous
observation.

No positive executable value is allowed without admissible financing, complete
costs, and sufficient execution and capture evidence. The gas amendment does not
waive principal, obligation, route, inclusion or competitive-evidence gates.
Learning cannot exceed certified permissions or limits.

## Economic admission

Before significant strategy scaling, independently demonstrate all seven:

1. An identifiable opportunity using information available before execution.
2. Exact state and transaction reconstruction.
3. Real principal funding and gas compatible with the active capital policy.
4. Full costs and positive net margin under explicit scenarios.
5. Evidence-based competitive and inclusion risk.
6. Out-of-sample repeatability.
7. Phase-appropriate safety and risk controls.

Failure permits continued research, not economically certified capacity.

## Capital amendment boundaries

The MXN 2,000 limit is a cumulative contribution budget shared by all chains and
wallets. It cannot be reset per transaction, per wallet or per month. Funding-lot
costs include acquisition fees. Failed transaction gas counts. No conversion
rate, token amount, wallet, available balance or signed financing agreement has
been established by the user instruction alone.

Concurrent nonces reserve the sum of their possible gas costs. Alternative
transactions sharing a nonce reserve their maximum exposure while all variants
remain pending. Only authenticated final receipts can settle that exposure.
There is no automatic release, refund-based contribution reset or profit
reinvestment. Reorgs and outside-wallet activity require independent recovery.

`gas_budget.py` implements an offline witness-accounting model of these rules.
It does not authenticate witnesses or constrain a live executor. Integration
with the Rust capital engine, wallet admission, authenticated receipts, reorg
handling and independent review remain prerequisites for operational use.
