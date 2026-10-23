# Combined debt execution with the audited token and strategy

This offline fixture executes the unchanged original
`LiquidationLogic._burnDebtTokens`, the exact runtime-matched
`VariableDebtTokenInstance.burn` and the exact rate-strategy runtime together in
one REVM transaction. Token burn outcomes and rate quotes are no longer supplied
returns in this experiment. The existing standalone bookkeeping CLI remains an
explicit supplied-outcome model and retains its previous flags.

The synthetic Pool entrypoint runs at the address embedded in the real token's
`POOL` immutable. A small **synthetic** forwarding proxy delegates to the actual
implementation at its observed address. Storage and event address belong to the
proxy, while its implementation retains the exact compiler/runtime-verified
bytes. This forwarding proxy is not the deployed Aave proxy implementation.

The token's nonzero rewards-controller immutable points to an explicit probe.
The probe records pre-burn arguments, reenters read-only token getters to observe
updated balances/index, and either returns, rejects, returns an empty revert, or
attempts a forbidden burn. This checks call context, ordering and propagation;
it does not verify the real rewards controller's behavior or reentrancy safety.
The Pool entrypoint is also synthetic and bypasses the rest of liquidation.

## Executed scope

| Component | Executed code | State / behavior |
| --- | --- | --- |
| Pool debt bookkeeping | Unchanged original internal function and ReserveLogic | Synthetic entrypoint, cache and reserve/user state |
| Token proxy | Synthetic Solidity forwarding proxy | Explicit synthetic storage |
| Variable debt token | Exact audited 7198-byte runtime | Packed user state and total supply supplied explicitly |
| Interest-rate strategy | Exact audited 4038-byte runtime | Packed reserve rate parameters supplied explicitly |
| Rewards controller | Synthetic probe | Controlled return/revert and callback observation |

The actual token calculates scaled supply and the no-more-debt return, updates
its packed 120-bit balance/8-bit delegation/128-bit index and emits original
Transfer plus Mint/Burn events. The old cached supply is deliberately different
in the basic case, demonstrating replacement with the token's actual return.
The real strategy loads packed basis-point parameters and computes both rates
with its original rounding and utilization branches. Strategy storage is never
inferred from missing data.

Eight Rust tests include 600 deterministic seeded successes plus directed cases
for partial/full burns, interest-heavy burns emitting Mint, exhausted collateral,
zero-debt skip, zero remaining supply, the utilization kink on both sides and at
its exact value, maximum packed balance, arbitrary preserved delegation bits,
zero scaled burn, stale index, insufficient supply/balance, index casts, invalid
reserve index, virtual-balance overflow and invalid reserve factor.

Each success compares ten return words, the complete ordered event list and
**all changed contract storage slots** with independent token/rate arithmetic and
the existing bookkeeping model. Failures compare exact revert bytes and require
zero logs and zero contract-storage changes across Pool, token and rewards,
including errors occurring after a successful callback. The real token's Pool
caller guard is exercised directly and through the probe's forbidden burn.
Seven missing account/slot witnesses must stop the closed sandbox rather than
silently assuming empty code or zero storage.

There are 632 Rust sandbox attempts: 611 successes, 14 completed reverts and seven
missing-witness rejections. These counts are executions within eight tests, not
632 additional tests or historical liquidations. Four Python tests bind original
sources, compiler artifacts/layouts, actual dependency code and flags, reproduce
the retained example through the real CLI, and check missing/tampered witnesses.

## Reproduce

From `migration/nqc-miner`:

```bash
cargo test --test aave_debt_execution_tests --locked --offline -- --nocapture
nqc-miner simulate --input evidence/aave-debt-execution-20261023/synthetic/input.json
NQC_MINER_TEST_BINARY=/absolute/path/to/nqc-miner \
  python3 -m unittest discover -s research -p test_aave_debt_execution.py -v
```

The retained `synthetic/output.json` contains the complete result. Its gas use
belongs only to this artificial harness and must not be used as a historical or
production liquidation cost estimate. To regenerate the wrappers with the pinned
solc 0.8.27 binary, use `research/build_aave_debt_execution.py --compiler ...
--output <new-directory>`. Original pool sources and separately compiled token/
strategy settings are unchanged. Dependency byte equivalence is rechecked before
assembling the fixture; no source substitution of the token or strategy occurs.

## Remaining boundary

All states are explicitly `synthetic_fixture`. The EVM fork is the supported
Cancun sandbox profile, not certification of the actual historical fork. Proxy
semantics, actual rewards code/state, historical balances/rate parameters and
transaction prestate still require verification. aToken and underlying-asset
transfers, aggregate health/eMode and multi-reserve bad debt are outside this
experiment. No full liquidation, Foundry fuzzing, authenticated mainnet state,
economic certification or operational phase exit is claimed. Activation remains
false and Observer remains untouched.
