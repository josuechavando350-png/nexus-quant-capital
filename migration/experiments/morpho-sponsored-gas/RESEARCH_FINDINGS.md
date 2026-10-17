# Findings — 2026-10-17 UTC (2026-10-16 Mexico City)

## Decision supported by present evidence

Neither architecture has demonstrated economically viable execution with $0 of
owner capital on Ethereum. Both can settle a synthetic local liquidation without
spending initial operator assets. These tests do not charge an external sender
for transaction admission, establish historical liquidity, or prove sponsorship.

| Requirement | A: NQC executor | B: existing Bundler3 + adapter |
| --- | --- | --- |
| Liquidation financing | Morpho sends collateral, calls NQC, then collects debt. The callback sells newly seized collateral. | Morpho flash loan supplies debt tokens; Bundler liquidates with empty callback data, then sells collateral and returns the flash principal. |
| New NQC contract | Executor required; a compatible production swap adapter is still missing. Its deployment must also be financed if needed. | No new NQC executor for the call graph tested. The test swap adapter is a mock, not an existing production route. |
| Morpho token cash | Does not need Morpho to lend debt tokens before the sale. Collateral and external DEX liquidity remain necessary. | Requires the flash amount to be available in Morpho's **actual aggregate token balance**, not just a market accounting field. |
| Native gas before execution | External funding needed for deployment(s) and execution if operator starts at zero. | External funding still needed for execution. |
| Local evidence | Four tests against original Morpho bytecode; exact balance, callback and payment guards in NQC. | Four tests against original Bundler3, EthereumGeneralAdapter1 and Morpho bytecode; callback hash and repayment verified. |
| Remaining integration | Authenticated DEX adapter, initial deployment funding, historical runtime identity, historical replay. | Historical runtime/immutables, real DEX calldata, native sponsorship settlement and equivalent balance protections. |
| Maintenance | NQC must maintain and review its own contracts. | Bundler3 is deprecated; new Bundles are not a drop-in arbitrary-call replacement. |

**New discriminating test:** exhaust Morpho's debt-token cash through a separate,
healthy synthetic borrower. A still liquidates through its callback and pays the
8 WETH debt. B's 8 WETH flash route reverts and leaves the target debt unchanged.
This demonstrates a liquidity dependency, not a historical opportunity or an
exhaustive proof about every possible existing-contract architecture.

A is the present local reference for balance invariants. B remains a conditional
way to avoid new deployment, with additional liquidity and maintenance constraints.
There is no evidence-based overall cost or safety winner yet. Test-function gas
includes harness work and synthetic paths; do not quote it as mainnet execution
or deployment cost.

## Source and deployment checks

- Original Morpho source: commit `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`.
  `liquidate` transfers collateral before callback and pulls repayment afterward;
  `flashLoan` transfers principal before callback and pulls exactly that principal
  afterward. This pinned flash implementation has no extra flash fee.
- Original Bundler3 source: commit `b4014349e3527f44ceaab697b26e29f2b11457f3`.
  `Call` encodes `(address,bytes,uint256,bool,bytes32)`. Reentry is bound to both
  the callee and callback calldata hash. GeneralAdapter1 authenticates Morpho.
  It has a flash callback, not an `onMorphoLiquidate` callback.
- Explorer source for `Bundler3.sol` and `GeneralAdapter1.sol` matches these pinned
  files byte for byte. Metadata for EthereumGeneralAdapter1 reports **partial**
  verification, solc 0.8.28, Cancun, via-IR and 999999 optimizer runs.
  Source agreement is not proof of exact deployed runtime at the historical block.
- Bundler's exact temporary approvals are cleared in the test. The original
  adapter retains its own maximum approval to Morpho by design. Clearing an
  allowance owned by Bundler does not clear the adapter's allowance.
- No standing operator approval to public Bundler is granted. Local routes use
  exact amounts and zero initial Bundler/adapter funds; they do not sweep existing
  public balances. Original adapters must not become long-term asset stores.
- The B test proves flash/callback/liquidation/swap/repayment sequencing only. It
  does not yet reproduce native sponsor repayment or NQC's full baseline guards.

Pinned sources:

- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/Bundler3.sol
- https://github.com/morpho-org/bundler3/blob/b4014349e3527f44ceaab697b26e29f2b11457f3/src/adapters/GeneralAdapter1.sol
- https://docs.morpho.org/developers/contracts/bundles/

## Sponsorship accounting and the zero-capital boundary

Ethereum's EIP-1559 transaction validity checks the sender's ability to cover
`value + gasLimit * maxFeePerGas` before executing its code. A flash loan or
liquidation callback inside that transaction cannot supply this earlier balance.
For the ordinary EOA flows studied, neither architecture removes this requirement.
An independently funded party must advance gas if owner funds are zero.

Titan documents automatic funding after `LackOfFundForGasLimit`, covering gas and
transaction value, conditional on increasing builder balance. Quasar documents
gas funding under the same error and a positive builder balance condition. These
statements do not establish NQC acceptance, a reimbursement address, deployment
support, top-up amounts or a guaranteed inclusion policy. No bundle was submitted.

`refundPercent` is a refund **to the user** from builder reward; it is not our
payment to repay the sponsor. Titan's documentation example contains a unit
inconsistency: 150000 gas times 100 Gwei is 15000000 Gwei, not 15000 Gwei. NQC uses
integer arithmetic, not that example's amounts.

Let `A` be actual ETH advanced, `U` unused advance returned, `R` independently
verified payment to sponsor, `Gt` actual funding-transaction cost, `V` other
verified builder receipts, `P` proposer payment and `C` other builder costs:

`builder_net = R + U + V - A - Gt - P - C`.

A direct `block.coinbase` payment is recorded against the header fee recipient.
It enters `V` only with independent beneficiary/ownership/accounting evidence;
it is never automatically counted as both builder income and proposer payment.
The base fee is burned. Priority fees and later proposer settlement are separate.

For owner zero funding, `A` must cover transaction admission. For all modeled
transactions the gate conservatively sums gas caps and values; actual gas spent
uses gas used and effective gas price, separately for creation and execution.
Unused advance is a liability, not trading profit. If gas was paid from `A`, do
not subtract that same gas again from sponsor net after already subtracting `A`.
Deployment costs are not measured for a production route here.

For asset-specific liquidation settlement:

`loan_residual = executable_sale + flash_received - liquidation_repaid
                 - flash_returned - finance_fee - other_costs - converted_to_ETH`.

`native_residual = executable_ETH_out - sponsor_payment - coinbase_payment`.

DEX outputs must already include fees and price impact. Do not subtract them a
second time. Flash principal appears once as inflow and once as repayment;
liquidation repayment remains a separate outflow. Tokens and ETH cannot be summed
without an executable conversion. `economic_ledger.py` implements this exact model.

For failure sensitivity it uses explicit rational probabilities:
`expected_sponsor_margin = p_success * success_margin - p_included_failure * loss`.
No empirical failure or capture probability has been established. A non-included
bundle has no onchain execution fee, but an included reverting transaction burns
gas. A separate funding/deployment transaction is not rolled back by a later
transaction's revert. Builder bundle policy is not a consensus atomic boundary.

Primary references checked 2026-10-17 UTC:

- https://eips.ethereum.org/EIPS/eip-1559
- https://docs.titanbuilder.xyz/api/eth_sendbundle
- https://docs.quasar.win/api/eth_sendbundle

## Historical case B: arithmetic reconciled, no canonical replay

Transaction `0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b`.
Block `26190955`, hash
`0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8`.
Parent `26190954`, hash
`0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc`.
Index **1** means one prior transaction must be replayed. Parent state alone is
not the immediate pretransaction state.

The saved single-indexer trace has 158 nodes, complete child counts and no reported
failed calls. The receipt's outer calldata is truncated; the separate raw trace
contains full calldata. Request identities and receipt prefixes are checked, but
these consistency checks do not authenticate a consensus state root.

| Field | Observed / exactly derived units |
| --- | --- |
| Market | `0xa0534c78620867b7c8706e3b6df9e69a2bc67c783281b7a77e034ed75cee012e` |
| Debt / collateral | WETH / EZETH |
| Borrow rate, WAD per second | `3559581937` |
| Accrual interval, seconds | `913008` |
| Interest, WETH units | `84501962012302301` |
| Loan assets repaid, WETH units | `26039738525656992415` |
| Collateral seized, EZETH units | `24343983926960874121` |
| Preexisting executor WETH | `6392502690919791` = 0.006392502690919791 WETH |
| New ETH wrapped, wei | `26409680973611000000` |
| ETH unwrapped and paid entirely to coinbase | `368092735714237547` = 0.368092735714237547 ETH |
| Inferred final executor WETH | `8242214930689829` |
| Incremental executor WETH | `1849712239770038` |
| Executor native ETH change from traced transfers | `0` |
| Sender gas | `745509 * 266148625 = 198416195275125` wei |
| Incremental WETH less sender gas, arithmetic only | `1651296044494913` wei-equivalent |

Interest and liquidation calculations exactly match the original call returns.
Full market/position/oracle fields and native transfer edges are in
`evidence/2026-10-17/historical-trace-audit.json`.

**Negative findings:** the 0.368 ETH is not retained executor profit. Preexisting
WETH means this is not a zero-funded executor demonstration. It does not prove
that the initial WETH was economically necessary, either; that needs a controlled
counterfactual replay. The small residual less gas is not certified consolidated
P&L: actor ownership, all external balances and financing are not established.
It is never NQC profit. Coinbase ownership and sponsorship remain unknown.

Oracle/rate values read inside the external winner validate historical arithmetic;
they are not treated as pre-winner NQC quotes or proof of prior observability.

## Case A and replay blockers

Case A is at block `25402186`, transaction index **226**. Its exact gas is
`182780 * 1771490340 = 323793004345200` wei. Empty callback data means it did not
exercise our callback architecture. Market configuration/receipt are saved;
pretransaction position, oracle, DEX liquidity and financing remain unreplayed.

The original archive probe obtained no state. On this continuation, even read-only
`eth_chainId` failed from this environment: PublicNode HTTP 403, Llama HTTP 405.
See `archive-connectivity.json`. These failures do not establish whether the
providers actually retain the needed archive or trace data. The free Blockscout
session quota was exhausted; no paid key or subscription was requested.

No Reth/Geth archive or independently authenticated state witness is available.
The explorer block response does not include the complete transaction list or a
state root. No authentic fork was run. Fabricating storage from the observed
winner would not close this gap.

Next input collection is specified in `fixtures/case_b_replay_requests.json`:
chain identity, full canonical block and parent header, receipt, prestate tracer
and call trace. Geth's `debug_traceTransaction` replays preceding block transactions.
A prestate trace contains only accessed accounts/slots; it is neither a state-root
proof nor necessarily enough for an alternative NQC route with different accesses.

Replay acceptance must include:

1. Independently verify block/header/transaction identities and historical fork
   rules; obtain parent state and replay the prefix, or verify an equivalent
   witness against that boundary. Do not substitute latest or block-end state.
2. Reproduce the original transaction's status, outputs, logs, gas and relevant
   state changes before evaluating a replacement at the **same** pretransaction
   boundary. Restore state for each alternative; do not use the winner's poststate.
3. Execute actual DEX pools/router code with real reserves, allowances, balances,
   oracles and IRM storage. Source-authentic bytecode plus artificial state is
   insufficient. Capture complete token/native ledgers, including donated dust.
4. Start NQC-controlled addresses at zero owned funds; model external financing
   explicitly. Keep source-identical replay separate from this counterfactual.
5. Reconcile sponsor advances/refunds, gas, coinbase and proposer payments, failed
   paths, operator receipts and outstanding liabilities. Inclusion/competition
   and actual operator sponsorship remain separate evidence requirements.

References:

- https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-debug
- https://geth.ethereum.org/docs/developers/evm-tracing/built-in-tracers
- https://ethereum.publicnode.com/
- https://llamarpc.com/es/eth

## Evidence classification

- **Theoretical:** exact Python economics, sensitivity and supplied-input math.
- **Locally reproduced:** compiled contracts, original-source integration,
  Python/Solidity parity and synthetic adversarial execution.
- **Historical observation:** external receipts/trace reconciliation from one
  indexer, with no independent state proof or fork reproduction.
- **Realized NQC result:** none certified. No capture rate or income forecast.
