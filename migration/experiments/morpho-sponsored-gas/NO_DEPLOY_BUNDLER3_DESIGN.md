# NQC — Hypothesis: already-deployed Bundler3 instead of our own executor

**2026-10-16 | READ ONLY / NOT PROVEN / ZERO LIVE AUTHORITY**

## Why this matters

The experimental NqcMorphoSponsoredLiquidation.sol route assumes a fresh contract deployment.
If NQC's EOA has zero ETH, that makes it necessary to prove that Titan/Quasar sponsor
DEPLOY + EXECUTE (and possibly a swap adapter deployment).

An alternative is to use **existing, immutable, official Morpho Bundler3 contracts**
and GeneralAdapter1 on Ethereum mainnet. This could avoid **our own executor deployment**.
It does NOT eliminate gas sponsorship, MEV competition, price impact or proof of profits.

Official deployed Ethereum addresses, per https://docs.morpho.org/developers/contracts/addresses/:

- Morpho Blue: 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb
- Bundler3: 0x6566194141eefa99Af43Bb5Aa71460Ca2Dc90245
- EthereumGeneralAdapter1: 0x4A6c312ec70E8747a587EE860a0353cd42Be0aE0
- ParaswapAdapter: 0x03b5259Bd204BfD4A616E5B79b0B786d90c6C38f

**Caution:** Morpho officially deprecated Bundler3 in favor of product-specific Bundles.
The old contracts remain listed and deployed for existing integrators, but **using them
for a brand-new liquidation path requires separate technical and security review**.
New Bundles do not currently provide all the general swap / callback composition
capabilities of Bundler3; do not substitute one for the other.

## Source-proven architectural properties

Checked against github.com/morpho-org/bundler3, pinned revision
b4014349e3527f44ceaab697b26e29f2b11457f3:

1. Bundler3.multicall(Call[]) accepts arbitrary calls. Each Call contains
   (address to, bytes data, uint256 value, bool skipRevert, bytes32 callbackHash).
2. GeneralAdapter1 (via EthereumGeneralAdapter1) implements
   morphoFlashLoan(address token, uint256 assets, bytes data) and
   onMorphoFlashLoan; the latter authenticates the Morpho caller and reenters
   Bundler3 with a hash-committed nested Call[].
3. GeneralAdapter1/CoreAdapter implements transfers from adapter-held balances,
   and WETH unwrap to a recipient. Its adapter is not a replacement for Morpho
   liquidation and **does NOT implement onMorphoLiquidate**.
4. Morpho Blue itself permits liquidate with **empty data**; then no
   onMorphoLiquidate callback is required. It sends the collateral to msg.sender,
   and pulls loan assets from msg.sender before liquidate returns.
5. The bundler should never be granted **persistent user allowances**.
   Directly leaving token balances/approvals in an arbitrary-call Bundler3
   contract can expose the funds to anyone. Any experimental route must
   be atomic, revoke exact temporary Morpho approvals, and sweep balances.

Source references:
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/Bundler3.sol
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/adapters/GeneralAdapter1.sol
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/adapters/CoreAdapter.sol
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/interfaces/IBundler3.sol
- https://docs.morpho.org/developers/contracts/bundles/

## Candidate WETH-debt liquidation flow (NOT an executed bundle)

A potential single Bundler3.multicall transaction with no fresh contract
deployment could, IF exact calldata is feasible, proceed as follows:

1. An external builder funds enough ETH for the EOA's gas, if the bundle is
   accepted under that builder's sponsorship policy.
2. Bundler3 calls EthereumGeneralAdapter1.morphoFlashLoan(WETH, debtAmount,
   nestedCalls). Morpho lends WETH to the adapter.
3. On Morpho's flash callback, the adapter reenters Bundler3 using the committed
   Call[] hash. The adapter transfers the flash-borrowed WETH to Bundler3.
4. Bundler3 grants Morpho a temporary **exact** allowance for the loan token.
   Bundler3 calls Morpho.liquidate(marketParams, borrower, seizedAssets=0,
   repaidShares, data=empty bytes). **Bundler3** is msg.sender and receives
   collateral, and Morpho pulls the loan-token debt from Bundler3.
5. Bundler3 resets its exact Morpho token allowance to zero. An independently
   authenticated on-chain DEX route must sell **the seized collateral** into
   enough WETH for flash repayment, native sponsor refund and operator profit.
6. Bundler3 returns at least the borrowed WETH to GeneralAdapter1 before
   onMorphoFlashLoan exits, because Morpho then pulls WETH from the adapter.
7. Separate proceeds (when available) are converted into ETH; repay the
   builder-owned sponsor address **independently of** any block.coinbase tip.
   Finally sweep all residual balances to the NQC EOA. Revert the entire bundle
   if costs, output minima, exact approvals or flash repayment fail.

This is a CALL GRAPH to falsify, NOT calldata ready to sign. In particular,
the swap route, exact ordering of adapter transfers, safe handling of tokens
inside Bundler3, reenter callback hash, beneficiary payout and proposer payment
must each be replayed against the **real bytecode**.

## First decisive tests

- [ ] Check eth_getCode, exact deployed code identity and adapter immutables at
  one canonical prestate block, not latest only.
- [ ] Verify actual WETH capacity for Morpho flashLoan at that prestate.
- [ ] Encode nested Call[] and callbackHash from the pinned Bundler3 ABI. Every
  call must have skipRevert=false, no unchecked approvals, and any empty-data
  liquidate must be called with Bundler3 as msg.sender.
- [ ] Reproduce Morpho interest accrual, current oracle and liquidation math,
  not the after-winner state.
- [ ] Simulate a REAL DEX route at that prestate, including price impact and
  order dependence. Uniswap/Paraswap calls require validated venues and calldata.
- [ ] Prove zero initial ETH and asset balances at NQC-owned addresses and no
  unaccounted capital subsidy in adapters/bundler.
- [ ] Measure actual ETH delivered to a builder-controlled sponsorship address,
  sponsor's gas top-up, all gas fees, all token transfers and residual P&L.
- [ ] Ensure **one** external sponsored transaction could be included before
  another liquidator, with realistic ordering and relay timing.
- [ ] Check whether Titan and/or Quasar actually accepts the ONE-transaction
  no-deployment bundle and how it measures its incremental profit.

**NO CLAIM**: Current code has NOT proved any of the above. In particular, the
published October liquidation was a **different operator**, not NQC, and
no valid builder sponsorship settlement has been observed for us.

## Decision

Keep both alternatives distinct:

A. OWN_EXECUTOR: new NQC Solidity contract and sponsored DEPLOY+EXECUTE;
requires Solidity compilation and a builder-sponsored deployment proof.

B. DEPLOYED_BUNDLER3: no new contract if the existing Morpho and adapter calls
can provide an exact atomic route; requires current deployed-code verification,
callback/callgraph replay and a gas sponsor for the one transaction.

Neither pathway can be admitted until a real historical fork + DEX + sponsor
proof is independently reproduced. No production transactions authorized.


## Executed local update — 2026-10-17 UTC

The proposed call graph now has four executed original-source integration tests
in `tests-core/NqcBundlerOriginal.t.sol`. It settles a synthetic flash/liquidation/
swap/repayment route, rejects a wrong callback hash and insufficient output, and
rejects a flash route when Morpho has no debt-token cash. The callback executor
can still settle that last synthetic condition, as independently tested against
original Morpho. See `RESEARCH_FINDINGS.md` for the comparison and exact scope.

Nested ABI, callback hash and liquidation/interest arithmetic have independent
Solidity parity. Historical runtime identity, real DEX liquidity, zero-capital gas
funding, native sponsor settlement and inclusion are still unproved. The adapter
retains its own Morpho approval by upstream design; it is distinct from the
Bundler-owned exact approvals that tests clear. No public dust is used or swept.
Explorer source equality and partial verification do not certify historical
runtime bytecode. Deprecation remains a material maintenance constraint.

These results advance local feasibility only; they do not check off historical
or sponsorship acceptance gates above. No signed/broadcast bundle exists.
