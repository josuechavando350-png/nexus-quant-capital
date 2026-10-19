# NQC063 — ETHEREUM CROSSED BOOKS / PROVENANCE GATE

**Result: ETHEREUM PORTABILITY IS A TECHNICAL HYPOTHESIS; PROFITABILITY, DEPLOYMENT AND FINANCING ARE UNKNOWN.**

This investigation descends from NQC062 `c15036c29bfe6ca25a71d93555c4d7f704fd59c6`; it does not claim an economic winner. It resolves an address/chain ambiguity and a fatal gap in the historical-evidence method.

## Concrete new source findings

1. The [pinned Morpho address test](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/packages/contracts/test/contracts.test.ts) expects Base's deterministic `CrossedBooksResolver` address `0xc7FB5fB4967944336F866849043fc4d3cD163b81`, derived with Base Midnight `0xAdedD8ab6dE832766Fedf0FaC4992E5C4D3EA18A`. **This is an expectation from source/tests, not proof the contract is deployed or used.** Public BaseScan HTML was inaccessible on the first attempted read. No retry, alternate provider or proxy was used.
2. [Morpho's `CrossedBooksResolver.sol`](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/packages/contracts/solidity/CrossedBooksResolver.sol) binds an immutable Midnight address and has no explicit Base chain-ID restriction. It implements atomic buy/sell offer crossing with callbacks, requires strictly positive gross loan-token delta, sends it to `msg.sender` and emits `Resolve`. No trading principal token inventory is required in the design, **but the gas is still external**.
3. The [official bot configuration](https://github.com/morpho-org/morpho-bots/blob/08d0a415d6d027f7e401fd6a904b09bedb441668/bots/midnight-crossed-books/src/config/config.service.ts) rejects chains other than **Base 8453**, so that bot CANNOT simply run on Ethereum. Separately, [Morpho](https://docs.morpho.org/developers/contracts/addresses/) lists Midnight Ethereum 1 at `0x471686c42792F93528B000beF54bC10E3aa2045f`. Its [API docs](https://docs.morpho.org/developers/api/morpho-midnight/) describe Ethereum book discovery. No Ethereum resolver address, deployed bytecode, offer snapshot, actual crossing or fee receipt was authenticated. Chain portability remains an **untested engineering hypothesis**, not implemented NQC coverage.

## Why past receipts cannot prove available money

The [Midnight whitepaper](https://morpho.org/whitepapers/midnight-whitepaper.pdf) (section 3.4) explicitly states the protocol keeps no canonical queue of resting signed orders, no onchain price-time priority, and no reservation of maker capital. Signed offers may be consumed across markets via shared budgets, depend on callbacks, expire or become ineligible. [Morpho's router documentation](https://docs.morpho.org/developers/midnight/concepts/mempool-router/) assembles live books offchain.

**Implication:** an authentic old `Resolve` receipt can demonstrate one historical settled gross profit, but cannot demonstrate the two signed offers were publicly accessible and simultaneously executable by NQC *before* the successful trade. The correct evidence standard is an independently preserved **predecision signed-order-book snapshot**, tied to a later receipt and full cost ledger. Documentation examples of book data are not authentic prospective observations.

## Titan economics and gas

[Titan's API](https://docs.titanbuilder.xyz/api/eth_sendbundle) documents ETH sponsorship when a signed bundle lacks gas funds, contingent on increasing the builder's balance. For an Ethereum crossed-book resolver, **loan-token profit does not automatically become ETH sponsor reimbursement**. USDC needs an actual supported swap/settlement path, WETH would need proved conversion/unwrapping and ownership; neither is established. Sponsor must cover each signed prefix (and CREATE if needed), and builder/proposer payments, contract deployment, potential revert gas loss, offchain liabilities, personal non-recourse and inclusion must all be resolved. No specific NQC bundle was accepted and no financing is committed.

Base [Coinbase CDP developer terms](https://www.coinbase.com/de/legal/developer-platform/terms-of-service) still allocate potential paymaster charges to the developer; Base paymaster is not an approved free, non-recourse financier for NQC.

## Hard-stop decision

No historical Base `Resolve` receipt, Ethereum chain-1 crossing, NQC P&L, or sponsor acceptance could be verified in this bounded review. A derived target or source comment does not upgrade this status.

**GO** for a narrowly scoped, permitted acquisition of one contemporaneous Ethereum signed-order-book snapshot and authenticated follow-on settlement evidence, if a source is legitimately accessible. **NO-GO** for bot development, new endpoints following denial, trading, signed bundles, deployment, account creation or costs. **UNKNOWN** for expected monthly income and competition.

This experiment adds source/decision records only in `migration/experiments/nqc-063-crossed-books-ethereum-evidence-gate/`. No tests or original isolation suite were executed because nothing executable changed and the complete original checkout is unavailable. The owner remains protected by `commercial_admission=false`, no own principal, no live operation and unchanged Triport budget.

**Next useful action: no more infrastructure until an authentic, permitted predecision order-book artifact and concrete Titan terms exist.**
