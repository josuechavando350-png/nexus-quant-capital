# NQC062 — Crossed Books / Zero Inventory / Funding Truth

**Decision (2026-10-19): NEW_MECHANISM_DOCUMENTED; REAL_PROFIT_NOT_DEMONSTRATED; FINANCING_NOT_SECURED; NO-GO live.**

This study follows NQC061 (`c4e96acc3e9775f822df2cc70ea017b5b119ea44`) and does not modify the prior experiments. The owner has no permission for any trading, signing, deployment, new authenticated provider requests, account creation, or expenses. There are no production transactions or revenues attributable to NQC.

## What actually changed

A **different strategic family** was identified in Morpho's own pinned public code: **Crossed Books Resolution** for fixed-maturity Midnight markets on **Base 8453**. The permissionless `CrossedBooksResolver` pairs valid sell-credit offers and buy-credit offers in the **same market**, recursively settles them through Midnight callbacks, requires an actual positive loan-token balance change, and transfers the positive difference to `msg.sender` in one atomic transaction. This **does not require the resolver to hold the debt/principal token inventory before the call**. This is materially distinct from a liquidation, but it does not itself fund **native-ETH gas**.

Primary evidence (Morpho upstream `08d0a415d6d027f7e401fd6a904b09bedb441668`):
- `packages/contracts/solidity/CrossedBooksResolver.sol`: public `resolve` verifies same market, offer sides, positive unit quantities, balanced units; revert if gross token profit is zero or below `minimumProfit`, then ERC-20 transfer of profit to caller; emits `Resolve(caller, marketHash, sellOfferCount, buyOfferCount, units, profit)`.
- `bots/midnight-crossed-books/README.md`: no inventory, one transaction, `READONLY` design, Base-only chain 8453 and requirement for RPC and signed requests in write mode.
- `bots/midnight-crossed-books/src/config/config.service.ts`: rejects chains other than 8453, defaults `MIN_PROFIT_ASSETS=1` **raw token unit**, **not** net of gas or sponsor.
- `bots/midnight-crossed-books/src/infrastructure/resolver/resolver.service.ts`: simulates exact call, checks contract-level minimum profit; it does **not** establish a complete financial P&L.
- `bots/midnight-crossed-books/src/application/crossed-books-bot.service.ts`: logs `match.computed` after simulation; `match.submitted` is not proof of canonical inclusion.

**Important qualification:** Although the published software is operational code, its existence is not evidence of at least one currently executable profitable crossed book, a live deployed resolver at a particular address, a canonical receipt, or actual net revenue. We did not obtain a transaction hash, effective gas, market order book, payer identities, or business economics. Do not label tests or default `minimumProfit` as a money-making result.

## Comparing with the previous Ethereum Midnight liquidation hypothesis

NQC061's most specific route was an Ethereum mainnet (1) `loan-as-collateral` post-maturity liquidation. Official Morpho repo contains a helper that seeds a *real* loan-as-collateral position, but the script is explicitly **Base-only** (`CHAIN_ID=8453`, Base USDC, 2 funded EOAs). It demonstrates implementation intent on Base, **not** an Ethereum market, an already published profitable outcome, or a counterexample to NQC061's `realized_profit=null`.

The official Ethereum liquidation bot (`bots/midnight-liquidation/src/config.ts`) supports chain 1 and uses a default **2 gwei priority tip** and **3 million gas-limit ceiling**; these are source-code operator defaults, **not** an actual gas receipt, sponsor price, or profit forecast. The bot can idle with zero listed markets. Its presence does not prove observed competition wins on Ethereum, although it shows the strategy is known and can be implemented. `liquidatorGate` evaluates the Executor contract in its standard path, not the external EOA.

## Can Coinbase CDP finance the Base cross-book operation?

**Mechanism documented, financing liability not resolved.** Coinbase CDP's official `Managed Mode` docs describe automatic sponsorship of **Base** user operations via a paymaster and smart account, letting that account operate without holding ETH. In a suitably configured ERC-4337 call, a smart account could be `msg.sender` of the permissionless resolver and receive the loan-token profit; this is an **unverified integration hypothesis**, not an accepted execution.

Coinbase's product page advertises **up to $15,000 of gas credits**, **not a guaranteed grant to NQC**. More decisively, its [Developer Platform Terms, Paymaster & Bundler, clauses 1.1 and 5](https://www.coinbase.com/de/legal/developer-platform/terms-of-service) explain that:
- credits are intended to offset *initial* sponsored end-user transactions;
- the developer is responsible for **amounts owed** and may be billed by invoice or payment card;
- promotional trials/credits are conditional, and costs can recur after a trial;
- the paymaster offering is framed around sponsoring **end users of an app**, not an explicit permanent non-recourse funding line for the developer's own MEV searcher.

**Conclusion:** under the owner's condition of no own principal, no founder liability, and no deposits or subscriptions before specific permission, CDP is **NOT_ADMITTED** as an NQC financer. Promotional credits cannot be farmed or treated as sustainable sponsor capital. Eligibility for a proprietary cross-book searcher and explicit non-recourse are **UNKNOWN**. Neither accounts nor service applications were created, nor was Coinbase contacted.

## Why gross positive is not net viable

The resolver's `profit` is only the **ERC-20 loan-token delta** of the specific smart-contract call. The NQC-required result is *net realized profit attributable to NQC* after actual Base ETH gas, paymaster markup/billing, failed attempts, inclusion payments, deployed-contract amortization, infrastructure, and possible legal obligations. There is **no justified cross-asset conversion** or settlement ledger in the accessible data. `MIN_PROFIT_ASSETS=1` is **one base unit of the loan token**, e.g. one millionth of USDC when the loan token has six decimals, **not** a USD minimum or a business viability requirement.

Unlike a liquidation, a successful `Resolve` event carries *gross* token profit directly: a canonical transaction receipt + correct asset decimals + a validated call/trace + chain fee + ownership can turn this into a far smaller evidence-acquisition package. That is a **promising information advantage**: it is **not evidence that a profitable resolution has occurred or can be repeated**.

## Exact evidence needed before any new implementation

See `EVIDENCE_GATE.json` for the smallest admissible packet: an allowed, complete Base 8453 crossed-books transaction with on-chain `Resolve` event and exact tokens/fees/addresses; pre-execution matching book evidence; gas and paymaster/legal/no-recourse conditions; then an offline net calculation and prospective Shadow frequency/competition. A source that only lists executable-looking orders is insufficient. RPC and Morpho's previously unreadable market API are **not retried or replaced by a proxy/provider** to evade access restrictions. A new authenticated provider acquisition must be explicitly authorized.

If this packet does not exist from approved sources, **STOP**. Do not build yet another generic bot, invent a viable route, or mistake an untested source artifact for profit.

## Status and safety

- Real economically positive NQC transactions demonstrated: **0**.
- Authentic historical profitable Base Crossed Books resolution acquired: **0**.
- Ethereum Midnight loan-as-collateral opportunities authenticated: **0**.
- Confirmed Titan sponsorship for Base: **0**; Titan Ethereum mechanism does not generalize to Base.
- Confirmed CDP grant/no-recourse: **0**, development billing risks documented.
- `commercial_admission=false`; `canary_enabled=false`; no live/signatures/bundles/deployments/fees/RPC.
- Triport 4663: 0/8 known lifetime uses, untouched. Owner's future Canary gas policy unchanged: MXN 2,000 total, <=500 recarga, stop-and-review after MXN 1,000 without captured gain; no wallet funds for Census/Shadow.
- `main` and historical studies unchanged. **No Python/Solidity/Rust code changed**, therefore no new runtime tests. The repository-wide isolation suite cannot run in this environment (the full checkout fails to resolve GitHub DNS). JSON/schemas and SHA-256 manifest checked locally; no claim of full historical isolation certification.

**Decision:** GO for conditional documentary evidence discovery; **UNKNOWN** for opportunity frequency and NQC profit; **NO-GO** for commercial execution, provider registration, credits, financing obligations, or signed operations.
