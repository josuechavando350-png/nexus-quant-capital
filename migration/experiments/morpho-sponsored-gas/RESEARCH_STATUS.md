# NQC research status — 2026-10-17 UTC / 2026-10-16 Mexico City

Branch: `research/morpho-sponsored-gas-20261016`.
Starting commit: `37ee15bb48a7a002a60e473e56c2ee7b90b2f299`.
Use `git rev-parse HEAD` for the current checkout commit; this file cannot contain
its own commit hash. All changes are confined to this experimental directory.

## Reproduced baseline

- 91 Python tests actually executed: 75 passed, 16 errors. Both ABI and historical
  modules required `openssl dgst -keccak-256`, unsupported in this environment.
- Solidity 0.8.24 actually invoked: compilation failed with `Stack too deep` at
  `ExperimentalLiquidation` event encoding. No Solidity tests ran at baseline.
- Local isolation verifier passed (531 source files, 106 disabled workflows,
  zero active workflows). Original Git objects not independently checked.
- 9 isolation regressions passed.
- Full baseline logs: `evidence/2026-10-17/baseline-*.log`.

## First corrections and verification

- Replaced duplicated OpenSSL subprocess hashing with shared `evm_hash.py`, using
  hash-pinned PyCryptodome 3.23.0 Keccak-256. No SHA3-256 fallback. Four regressions
  verify known digests, algorithm distinction and input typing.
- Extracted event emission into a private helper, resolving solc's stack limit
  without changing optimizer or enabling via-IR.
- Result: **95 Python passed; 9 Solidity mock tests passed; 0 failed or skipped**.
- Toolchain: Forge 1.7.1, solc 0.8.24, Cancun, optimizer 200, no via-IR. Compiler
  SHA-256 matched the official solc-bin index. See `toolchain.json` and `REPRODUCE.md`.
- Existing Solidity tests cover WETH debt, baseline asset preservation and invalid
  economic plans. The artificial 1:1 exchange is not real DEX liquidity.

## Pending / not executed

Real Morpho fork, exact pretransaction reconstruction, original runtime identity,
DEX execution, interest accrual differential verification, sponsorship receipt
verification, production builder acceptance and competition remain pending.
No live deployment, signature, transfer, subscription, workflow or main mutation.
No NQC realized gains certified. Historical external transactions are not NQC P&L.

## Continuation

Next: strengthen local callback/repayment/balance regressions, independently check
ABI and exact arithmetic against Solidity, inspect original Morpho/Bundler3 source
and reconcile sponsorship assumptions. Do not promote local unit results to
historical reproduction. A pass requires canonical pretransaction state, executable
DEX outputs and separately reconciled builder/proposer/operator cash flows.

## Executor hardening increment

First correction commit: `2d6252a`. Three new negative tests failed before the
corrections: inconsistent returned seizure, short debt collection, and short
operator token receipt. The executor now measures each obligation and requires
exact agreement with callback/return values. Empty callback data is rejected
before Morpho, and increased input balances yield SwapFailed rather than an
arithmetic panic. These are guards in NQC, not claimed defects in Morpho.

Latest local result: 28 Solidity mock tests passed, including 256 deterministic
fuzz cases for preservation of prior balances. New coverage includes non-WETH
debt/two swaps, output misreporting, input under-consumption, rejected approvals,
callback authentication and duplication, expiry, allowance cleanup, repeat
execution, rejected native payments and full rollback. Toolchain unchanged.
The native venue and token fixtures remain artificial. Historical trace research
is in progress and is not included in the above execution result.
