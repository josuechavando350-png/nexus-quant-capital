# NQC067 — Zero-funded Shadow, Morpho Blue Ethereum (bounded pilot)

**Result: SOURCE DOCUMENTED + READ-ONLY OBSERVER TESTED OFFLINE; NO LIVE SHADOW DATA ACQUIRED.**

This experiment responds to the owner's request to start genuine economic observation instead of continuously optimizing a 2025 historic liquidation. It descends from NQC066 `236d6c3e26008f5a586cfb412afe24d11e48d2f5`, leaves `main` untouched, and adds only files under `migration/experiments/nqc-067-shadow-blue-public-indexer/`.

## Verified public data route

Morpho's official [API Get Started](https://docs.morpho.org/developers/api/get-started/) documents no-key public access, current/historical positions and markets, a public GraphQL endpoint, and standard 750 requests/minute rate limit (429 Retry-After 600; longer severe limit). It provides **no SLA**. The [Morpho Blue API](https://docs.morpho.org/developers/api/morpho/) documents public REST and GraphQL and defaults GraphQL to Ethereum. The [borrow developer Get Data tutorial](https://docs.morpho.org/developers/borrow/tutorials/get-data/) provides exact schema fragments for `marketPositions` and `marketTransactions` (type `Liquidation`). The live/indexer API is not an Ethereum consensus node and does not authenticate oracle/runtime/storage/reorgs.

A one-time public REST `GET /v1/blue/markets?chain_id=1&listed=true&limit=5` from this environment **failed at DNS resolution**; **no Morpho HTTP status or market payload was received**. The web reader also could not open a public Morpho REST request. No retries after denial or unauthorized provider switching were attempted. **An actual Shadow snapshot has not started; no profit or new liquidatable borrower can be claimed.** See `CONNECTIVITY.json`.

## What was implemented

`shadow.py` is a finite, manually-invoked Python-standard-library sampler. It performs no network activity by default. It uses one tightly bounded official public GraphQL POST per explicitly authorized `--fetch-public-once` invocation, and no alternate providers, authentication headers or retry loops. Hard caps: 1–3 explicit market IDs, 25 positions, 20 liquidation events, 512 KB HTTP response and local hourly cooldown. A 403/429/network failure creates `MANUAL_REVIEW_REQUIRED`, prohibiting subsequent runs without manual review. This is a *single-host safety mechanism*, not a globally atomic multi-host request ledger or network service.

The source response is saved byte-for-byte alongside a normalized append-only snapshot carrying UTC observation time, SHA-256, exact market/tx identities, raw token units, and an optional **indexer-derived approximate health factor** from USD estimates and LLTV. It is **not verified health, not executable price, not an ETH-equivalent net profit**.

The first successful snapshot, once an accessible runtime is available, establishes a baseline only. Later snapshots can identify newly seen indexer events/borrowers, but this is **not proof** those events were novel to the chain, tradable before confirmation or capturable by NQC. Indexed positions are not comprehensive (top 25 by borrow shares across all watchlisted markets); capped pages may miss other events. `coverage_complete=false`, `net_NQC_profit=null`, `commercial_admission=false` unconditionally.

`WATCHLIST.json` identifies one *documentation example* Ethereum Morpho Blue market; its continued deployment, activity and available borrowers have NOT been verified. No invented profitable market.

## Reproduction in a permitted network-enabled automated workspace (not required from the Android owner)

Offline code validation (network-free):

```
python migration/experiments/nqc-067-shadow-blue-public-indexer/run_checks.py
```

Print exact query without network:

```
python migration/experiments/nqc-067-shadow-blue-public-indexer/shadow.py --market-id 0x698fe98247a40c5771537b5786b2f3f9d78eb487b4ce4d75533cd0e94d88a115 --print-query
```

**Not executed** and only after data-source and environment access are approved and verified, a finite read could use:

```
python migration/experiments/nqc-067-shadow-blue-public-indexer/shadow.py --market-id 0x698fe98247a40c5771537b5786b2f3f9d78eb487b4ce4d75533cd0e94d88a115 --fetch-public-once --explicit-read-approval --out /path/to/append-only-shadow-evidence
```

This example is documentation for a delegated agent, not a command the owner must run. No persistent process, cloud service, GitHub Actions, cron, trade sender or background monitoring was created. No API key is requested.

## Actual economic proof gate

A **fresh profitable NQC opportunity is NOT demonstrated** by a high-value liquidation, near-threshold position, `marketTransactions` event, Etherscan receipt, historical backtest or positive local P&L fixture. Economic admission would require **all** of the following, after lawful access:

- At least two authorized timestamped **predecision** observations of a defined universe plus independent onchain state / oracle checks to verify liquidation eligibility.
- Executable token-sale route/quotes at that decision time, actual repay obligations, gas, native-token swap/settlement costs and competitor bids, with units and asset contracts pinned.
- Specific Titan-sponsored ETH advance/CREATE coverage and repayment to an identified owner, loss distribution and no personal recourse; never assume a bundle hash equals sponsorship.
- Shadow statistics measured outside the sample used for calibration: eligible frequency, censored/failed opportunities, estimated competitive wins, overhead and attributable net realized profit after actual Canary approval.

The already settled February 2025 Morpho trade from NQC064 cannot be recaptured. No Canary, keys, wallets or funds were activated. Existing MXN 2,000 future Canary gas cap, MXN 500 replenishment cap and stop after MXN 1,000 without captured profit remain unchanged; zero connected-wallet funds in Census/Shadow. Triport known requests 0/8, untouched.

## Validation and decision

`run_checks.py`: **28 local Python tests PASS**, validating query whitelists, data identity, Decimal parsing, immutable saved responses, first-versus-second snapshots, absent profit, and fail-closed 403/429 without retry. Python 3.13; no external packages or network. Source was not fetched live; all tests use deliberately **synthetic** test input.

Not run: original PFT/Census isolation verifier, NQC055–066 full regressions and historical EVM replay; full original Git checkout not available in the local runtime. The published commit's tree/file scope and protected `main` can be separately checked through GitHub.

**Research: GO for bounded Shadow once the documented public endpoint is genuinely reachable under permitted conditions. Commercial/live execution: NO-GO. Profitability: UNKNOWN.**

**Next decision:** get a real baseline **in a legitimately network-enabled authorized environment** and a follow-up snapshot using the same watchlist, then evaluate whether any positions with indexer-estimated low health have the independently authenticated economic evidence needed to merit more work. Until then, stop claiming surveillance/expected P&L.
