# NQC059 — FIRST ECONOMIC PROOF: competitive-surplus boundary

**Decision: INSUFFICIENT_CANONICAL_EVIDENCE.** New public practitioner account and official SVR documentation expose an additional economic bottleneck for Aave liquidations: competition may absorb almost all post-execution value. This is **not** an authenticated profitable capture, a verified zero-profit chain trace, a Titan funding commitment, or a reason to declare all of Aave unprofitable.

## Reported historical example

[Burnbytes in Aave Governance, 1 Sep 2026](https://governance.aave.com/t/aave-v3-v4-liquidation-bot/25565/5) reports an Ethereum mainnet Aave V3 liquidation at block **25832630** (WETH collateral, USDT debt), with the following approximate figures:

| Component | Reported |
|---|---:|
| Debt covered | ~$11,809 |
| Gross liquidation bonus | ~$614.56 |
| Withdrawn after exit sale | ~0.2162 WETH (~$531.90) |
| Paid to block.coinbase | 0.215488 WETH (~$530.10) |
| Paid to a different address | 0.000732 WETH (~$1.80) |
| Kept by executor | 0 WETH, according to reporter |

The two outgoing transfers sum to **0.216220 WETH**; the reported available **0.2162** has four decimal places, so do not assume an exact +0.000020 WETH deficit or surplus. All payout values are *source transcriptions*, not authenticated receipt/storage evidence. No transaction hash or full trace was supplied by that post. Do **not** attribute block.coinbase automatically to the builder; owner identities are unknown. No ETH gas from WETH without a proven conversion.

## Falsifiable bounded calculation

The new `economics.py` uses Decimal precision and reports conditional display bounds with no hidden additional inflows or outflows:

- Rounded to nearest 4 decimals: available in **[0.21615, 0.21625) WETH**; conditional solvent residual after stated outflows in **[0, 0.000030) WETH**.
- Truncated to 4 decimals: available in **[0.2162, 0.2163) WETH**; conditional solvent residual in **[0, 0.000080) WETH**.

Neither implies a positive residue or initial ETH gas. The poster claims zero retention; this is compatible with both bounds. Keeping the *same* winning bid schedule offers no **demonstrated** additional sponsor margin. Reducing a winning bid changes the inclusion outcome; do not assume acceptance.

## Financing meets execution: two distinct bundle protocols

- [Chainlink SVR Ethereum onboarding](https://docs.chain.link/data-feeds/svr-feeds/searcher-onboarding-ethereum) describes auctioned oracle-update **backruns** using `mev_sendBundle`, requiring a *signed* liquidation transaction and competitive payment.
- [Chainlink SVR overview](https://docs.chain.link/data-feeds/svr-feeds) says Titan participates as a parallel SVR order-flow auction provider alongside Flashbots.
- [Titan's sponsored bundle documentation](https://docs.titanbuilder.xyz/api/eth_sendbundle) describes automatic ETH advances for insufficient-balance `eth_sendBundle` sequences contingent on builder net benefit.

**Open compatibility question:** No reviewed documentation proves Titan will automatically fund a zero-ETH EOA through the *specific* SVR auction route (`mev_sendBundle`/Titan OFA), handle initial CREATE, bear partial failure risk, or establish personal non-recourse. A method existing in one API is not proof of that method existing in another.

[LlamaRisk's August 2026 public study](https://governance.aave.com/t/arfc-liquidation-protocol-fee-increase-for-wbtc-weth-and-wsteth-on-aave-v3-ethereum-core/25470) reports **14,006 measured Aave V3 liquidation events** (~$1.05B seized) with sale impact, gas, builder bids and SVR proceeds. It is aggregate research, not a shared verified NQC settlement ledger. Proposed future liquidation fee parameters must not be applied to past transactions as facts.

## Unchanged target and acquisition boundary

NQC058's target **0x0ec3a4ce06ab809e82cb454a6e41b149d3bd8c5e72d0606a17fd039a2240753d**, block **24393012**, still has no complete canonical receipt, executable sale and participant ledger. Its public Etherscan page returned **inaccessible** on first read during NQC059; it was **not** retried, mirrored, proxied or queried through a second provider/RPC. The earlier Morpho and Aave conditioned rejections remain unchanged.

**Next evidence needed:** One legally accessible, independently verifiable whole historical settlement packet (header/tx/receipt/trace, exact conversion, fees, address ownership), then condition-specific sponsor/auction participation proof and prospective Shadow competition measurement. Without that, claims of `RENTABLE_Y_VIABLE`, net NQC profit and monthly revenue remain **UNKNOWN**, not recovered or verified.

## Reproduction / constraints

`python migration/experiments/nqc-059-first-economic-proof/run_checks.py`: 10 new isolated Decimal tests reported **PASS** locally, Python 3.13.5; no network calls. `RESULTS.json` is a deterministic computed output, **not** realized P&L. Historic full checkout not available in the working container: **original isolation verifier, NQC055–058 suites and EVM replay NOT RUN**. No claim of full source-history isolation recertification.

All files in this commit live under `migration/experiments/nqc-059-first-economic-proof/`. No old file or protected main changed. No trading, RPC, wallet, credential, broadcasting, deployment, subscription or new third-party contact. Triport 0/8 known lifetime usage, safe intake still blocked; `commercial_admission=false`, `canary_enabled=false`.

**Decision:** GO for bounded documentary acquisition, **UNKNOWN** for profitability and no-recourse financing, **NO-GO** for real-money execution.
