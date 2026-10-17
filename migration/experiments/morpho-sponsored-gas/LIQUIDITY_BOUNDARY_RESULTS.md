# Liquidity boundary experiment — 2026-10-17 UTC

## What was actually reproduced

Baseline at `fd9c1ff`: 136 Python, 41 Solidity and 9 isolation tests re-executed
successfully. Added seven targeted Solidity tests, five Python regressions, and
an original Uniswap V2 pair build. Latest totals: 141 Python / 48 Solidity / 9
isolation. No historical fork or sponsored transaction was executed.

Original protocol sources are unchanged. Morpho, Bundler3 and GeneralAdapter
identities remain as recorded. Uniswap V2 pair source is pinned to
`6a9e7c97860676e0992f22a49665760444c1cdf5`, built with solc 0.5.16, Istanbul and
999999 optimizer runs. `compile_uniswap_reference.py` checks compiler and Git
blob identities. Eleven original source files are recorded in the build manifest.

The test-only bridge sends the exact collateral to the original pair. The pair
checks balances, its 0.3% swap fee and constant-product invariant. Oracle, tokens,
LP reserves and borrowers remain synthetic. This is not the historical EZETH route.

## Exact asset order and why cash requirements differ

A, direct callback:

1. Original Morpho checks the position and calculates debt/seizure.
2. Morpho transfers collateral to NQC, then invokes `onMorphoLiquidate`.
3. NQC sells only that collateral through the pair; the pair pays WETH from reserves.
4. Morpho collects 8 WETH from NQC after the callback returns.
5. NQC unwraps the budget and pays recipients, then transfers the token residual.

B, flash route:

1. Original Morpho must transfer 8 WETH to GeneralAdapter **before** its flash callback.
2. The authenticated callback reenters Bundler. Adapter transfers 8 WETH to Bundler.
3. Bundler liquidates with empty callback data, receives collateral and pays the
   liquidation debt to Morpho before that liquidation call returns.
4. Bundler sells collateral through the same pair and returns 8.1 WETH to adapter.
5. Adapter unwraps/distributes 0.1 WETH; Morpho collects the remaining 8 WETH as
   flash repayment when the callback returns. Bundler sends the token residual.

Thus B needs 8 WETH **before** liquidation, although repayment replenishes that
cash later. A uses Morpho's collateral-before-payment ordering and never borrows
those 8 WETH from Morpho. This is a real property of the pinned original protocol,
not the former mock's transfer order. It is not unique to NQC and does not prove
an advantage over every other existing-contract route. Case B's external winner
also used a nonempty liquidation callback.

## Measured boundaries (synthetic amounts, 18 decimals)

Debt is 8 WETH. The oracle and initial pool price are both 0.9 WETH/collateral.
Seizure is exactly `9278589654372535368` collateral units. The pool output must
cover 8 WETH debt, a 0.1 WETH native budget, and at least 0.01 WETH token residual.

At pool reserves of 1000 collateral / 900 WETH:

| Initial Morpho debt-token cash | A: callback | B: flash |
| --- | --- | --- |
| 0 | Settles | Reverts |
| 1 wei | Settles | Reverts |
| 8 WETH minus 1 wei | Settles | Reverts |
| 8 WETH | Settles | Settles |
| 92 WETH | Settles | Settles |

At Morpho cash of 8 WETH:

| Initial pool collateral / WETH | Executable WETH output | Both routes |
| --- | --- | --- |
| 20 / 18 | 5.692624900872323549 | Revert: output cannot repay debt |
| 100 / 90 | 7.620705762452758073 | Revert: output cannot repay debt |
| 1000 / 900 | 8.249365645570551238 | Settle under synthetic budget |
| 10000 / 9000 | 8.317983734833098023 | Settle under synthetic budget |

For the 1000/900 pool, WETH residual is exactly 0.149365645570551238 after
8 WETH debt and 0.1 WETH conversion. That 0.1 unwrap pays synthetic sponsor
0.05 ETH, coinbase 0.04 ETH and operator 0.01 ETH. Neither recipient identity nor
sponsor funding/gas acceptance is established by these test payments.

**Refuted assumption:** the old 1:1 fixed-price mock overvalued collateral relative
to the 0.9 oracle/pool price. With 10000/9000 reserves, the former 0.5 ETH budget
cannot be paid; the actual contract reverts. Even infinite depth at this price
cannot generate 8.5 WETH from this seizure before fees. Positive output under a
smaller invented budget is not an economically admitted historical operation.

A prior synthetic trader's 100-collateral sale reduces output below repayment.
Both stale routes then revert. One donated WETH in each of executor, Bundler and
GeneralAdapter is preserved; it cannot rescue the insufficient-output route.
This is one order-dependence stress case, not a measured competition probability.

## Subsidies and conservation checks

Owner starts at 0 ETH / 0 WETH. New executor, Bundler, GeneralAdapter and bridge
start without loan tokens. An explicitly separate synthetic lender funds Morpho;
an external synthetic LP funds the pair with backed WETH. Collateral is minted
for test setup, so its market availability is not historical evidence.
The old fixed-price mock's 20 WETH stays untouched throughout these runs.

Success checks exact Morpho debt receipt, pool asset changes, operator receipt,
native allocations, WETH backing reduction, route balances and temporary approval
cleanup. Failure checks debt, pool reserves, Morpho cash, operator and native
balances unchanged. Upstream GeneralAdapter's persistent Morpho allowance remains
a separate design property. No function's reported gas is a mainnet gas estimate:
EOA admission, creation costs and funding transactions are not charged by this harness.

## Reproduction and evidence

See REPRODUCE.md for compiler/bootstrap commands. From this directory:

```sh
FOUNDRY_PROFILE=core forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 --match-path 'tests-core/NqcLiquidityBoundary.t.sol' -vvvv
/tmp/nqc-python/bin/python liquidity_boundary_model.py
# Model exits 2: local synthetic evidence, not economic admission.
```

`evidence/2026-10-17-continuation/liquidity-boundary-traces.log.gz` preserves the
complete unabridged EVM call traces (gzip only). Raw trace SHA-256:
`2e2f39d7070394d8d818f9f28ee07f0fd605626c83281dec0fdf575563214cdd`.
`liquidity_boundary_model.py` checks 21 emitted results (16 distinct configurations,
including three repeated detailed trace cases) against independent integer math.
It decomposes loss from spot into price impact without fee and additional fee
effect without charging either twice. Tampering with an EVM amount is rejected.

`historical_trace_audit.py` now also reconciles the three direct token transfers
against normalized receipt movements and checks WETH wrap/unwrap against native
flows. `historical-ledger.json` keeps initial/final ETH and collateral unknown
where not observed. DEX fees and price impact cannot yet be separated historically.
Coinbase flow is recorded without inventing builder/proposer ownership. Historical
raw inputs remain unchanged.

## Historical data and sponsorship: remaining evidence

Additional legitimate public reads: 1RPC `eth_chainId` returned HTTP 405 and dRPC
HTTP 403. Earlier PublicNode/Llama reads failed similarly. Etherscan case B page
was inaccessible through web retrieval; case A returned 403. No credentials,
quota circumvention, paid endpoints, signing or bundle submission was attempted.
dRPC documentation explicitly reserves debug/trace methods for its paid tier;
no paid-only method was requested. New provider probes are saved in JSON.

A: parent state and 226 preceding transactions remain unavailable. B: parent state
and its one preceding transaction remain unavailable. Neither case has an
independently verified pretransaction witness, real DEX-state replay or NQC gas
measurement. Running a local client without these inputs cannot reconstruct the
missing state merely from receipts; no fabricated state was substituted.

Titan documents a funding transfer prepended to a candidate bundle when the
builder can recoup costs. That is conditional support, not evidence of NQC
acceptance or explicit guaranteed deployment sponsorship. Quasar distinguishes
simulation, selection, relay submission and landing; passing simulation does
not establish any later stage. Its optional authentication/reputation can affect
selection, and invalid authentication can cause rejection. We did not sign or
query a fabricated bundle hash.

No builder-controlled repayment address or historical sponsor ledger has been
verified. Contract payments to the synthetic address `0xF00D` are only test outputs.
A separate top-up/creation transaction does not revert with a later execution.
The existing exact `economic_ledger.py` model is retained; there are no verified
new sponsorship cost inputs to promote it beyond theoretical accounting.

**Economically admitted authentic operations: 0.** The nine-condition matrix is
saved as `economic-admission.json`. This is insufficient evidence, not a proof
that every zero-owner-capital strategy is impossible. Next decisive input is an
authenticated pretransaction state for case B; after replay, funding identity,
complete cost accounting and temporal capture evidence would still be required.

Primary references checked 2026-10-17:

- https://github.com/Uniswap/v2-core/tree/6a9e7c97860676e0992f22a49665760444c1cdf5
- https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/Morpho.sol
- https://drpc.org/docs/ethereum-api/debugandtrace
- https://docs.1rpc.io/guide/how-to-use-1rpc
- https://docs.titanbuilder.xyz/api/eth_sendbundle
- https://titanbuilder.substack.com/p/titan-tech-teatime-1
- https://docs.quasar.win/api/eth_sendbundle
- https://docs.quasar.win/bundle-tracing
- https://docs.quasar.win/authentication
