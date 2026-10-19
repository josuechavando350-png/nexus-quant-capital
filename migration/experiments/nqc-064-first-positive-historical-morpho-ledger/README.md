# NQC064 — FIRST DOCUMENTED POSITIVE MORPHO TRANSACTION-LOCAL RESIDUAL

**Result:** a real 2025 Ethereum Morpho Blue liquidation executed by an *external* MEV bot has a **positive transaction-local WETH residual after the observed builder transfer and gas**, conditional on consolidating the bot and gas-paying EOA's economics. **It does not demonstrate revenue for NQC, no-capital feasibility, Titan admission, or a repeatable opportunity.**

## Source and identity

- [Etherscan transaction detail](https://etherscan.io/tx/0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb), Ethereum mainnet block **21,762,897**, tx index 1, status reported `Success`, **2025-02-03 02:07:35 UTC**.
- Execution contract `0x8Ce45e650aB17B6CA0dD6071f7c2B5c69B5b42b2`; gas-paying EOA `0x0ef3794cb89864337e15a9F077020C285EF0989b`; ETH payout to a contract tagged `beaverbuild` by Etherscan.
- This is an explorer-decoded web page containing token Transfer logs, WETH Withdrawal log, internal ETH movement, and gas data. **Not** independently verified Merkle receipt/parent prestate or ownership of the addresses. No new RPC, raw receipts or actual provider sponsorship acceptance.

## Exact transaction-local cash ledger

| Leg | Quantity | Asset | Account / meaning |
|---|---:|---|---|
| Initial outgoing swap | -266.862310264246861824 | WETH | executor -> Uniswap V2 |
| Swap proceeds | +616687.327559 | USDC | Uniswap V2 -> executor |
| Debt repayment | -616687.327558 | USDC | executor -> Morpho Blue |
| Seized collateral | +94718.231775052038007708 | UNI | Morpho -> executor |
| Collateral sold | -94718.231775052038007708 | UNI | executor -> Uniswap V3 |
| Exit swap | +281.407578800167103862 | WETH | Uniswap V3 -> executor |
| WETH unwrap | -12.447536358167279703 | WETH | WETH Withdrawal, ETH sent to executor |
| Builder-labeled transfer | -12.447536358167279703 | ETH | executor -> beaverbuild |
| Gas charged | -0.182306290745378005 | ETH | EOA distinct from executor |

WETH buy/sell difference **+14.545268535920242038 WETH**. The **withdrawal is not additional income**; it exchanges 12.447536... WETH for ETH and sends that ETH to beaverbuild. Accordingly the executor token-flow residual is **+2.097732177752962335 WETH**, and the separate sender gas flow is **−0.182306290745378005 ETH**. These sum to **+1.915425887007584330 ETH-equivalent** only on the explicit WETH:ETH 1:1 redemption assumption and conditional consolidation of sender and executor economics. USDC has **+0.000001** dust; kept separate. Do not double count swap fees, gas burn/priority fee or the payout.

## What stops this from being an NQC profit proof?

1. The transaction was executed in February 2025 **by another searcher**. It is already settled and no longer capturable. NQC's realized revenue = **unknown/none demonstrated**.
2. The first observed WETH swap **spends 266.862310264246861824 WETH with no same-transaction prior WETH incoming transfer**. The observed method depends on a pre-existing WETH balance or financing arranged outside this transaction, not an demonstrated capital-free route. No source proves the tokens came from a flash loan, nor that Titan funded them.
3. If NQC attempted a **counterfactual WETH flash loan** to replace this initial inventory, the maximum *additional* financing premium (including all incremental flash execution, sponsorship, tips and failure amortization) would be **71.775811 bps** of 266.86231 WETH at the same historical quotes and builder bid. At exactly that expense, the observed surplus is exhausted. A **purely hypothetical 5 bp flash fee** would leave **1.781994731875460900 ETH-equivalent** *before* incremental gas, sponsor fees, competition changes and any additional constraints. Neither a 5 bp loan, liquidity, identical quotes nor Titan support has been obtained.
4. Actual gas is already charged to a different sender than the executing contract. Its economic owner, any offchain payouts, flash charges and personal recourse are not established. No founder debt is assumed absent; no real financier accepted this bundle.
5. Etherscan decoded data are **not** a canonical independent prestate/receipt proof; the case proves only a reproducible, source-grounded historical ledger within this evidence scope.

## Code and validation

`python -m unittest -v test_audit.py` from the experiment directory: **17 new local tests pass** with Python 3.13.5 and no network. `audit.py` uses exact integer token units and rejects invalid assets, non-exact gas reconciliation, double-counting, unsupported profit attribution and corrupted input. `RESULTS.json` is regenerated from `case.json`, and the positive WETH/ETH value is explicitly conditional.

**Unrun:** full original PFT/Census isolation verifier; NQC055-NQC063 unchanged regression suites (the complete repo checkout was not accessible to local Python); authenticated historical state/replay; any live ERC-20 or funding transaction. No new RPC calls, Triport 0/8 lifetime-known used; no wallets, secrets, deploy, sign, bundle, fee, account or provider contact. `main` and all prior experiments remain intact.

## Decision

- `GO`: economic evidence for one **historical external** successful Morpho liquidation with residual positive after reported bid/gas, under the stated source/consolidation assumptions.
- `UNKNOWN`: whether this strategy could be executed with zero initial principal, a committed ETH-gas sponsor and competitive profitability *now*.
- `NO-GO`: NQC commercial admission or any signed/live operation without separate permission, capital route and liability proof.

**Next falsifiable step:** find a *new* accessible onchain case with genuine atomic flash funding plus collateral sale/repay and profit residue; verify receipt and all participants, then obtain Titan's conditions for the **specific** package and a prospective Shadow win-rate distribution. Do not repeat denied Morpho/Blockscout access, reuse old liquidations as current inventory, or add generic bot layers without new income evidence.
