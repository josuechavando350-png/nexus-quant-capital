# Both collateral-delivery branches with observed USDC payment

The shared synthetic Pool wrapper now executes the original `receiveAToken`
if/else branch, followed by the original capped treasury fee, USDC
`safeTransferFrom` and `LiquidationCall` event. Both modes use the same compiled
runtime. The original branch bytes are retained exactly; its internal collateral
burn call forwards to the unchanged original library helper.

The distinct assets remain WETH collateral and USDC debt. The original same-asset
cache condition appears in the source excerpt but is **not exercised** by these
fixed assets. Initial reserve updates/validation, health/eMode, multireserve bad
debt, real Pool entry and authenticated historical state remain unimplemented in
this composition.

## State and behavior

The new wrapper returns 25 words: the previous 19 debt/aToken results, three
collateral-reserve fields, then USDC wallet balance, vault balance and allowance.
The two previous diagnostic WETH balance getters are removed, so the aToken mode
requires no WETH contract or underlying-asset/rate witnesses. This does not remove
the actual WETH dependency from the underlying-delivery branch.

Default artificial inputs: collateral amount 40, fee 10, liquidity index 1.5 RAY,
USDC repayment 40, initial USDC wallet/vault/approval 100/200/100.

| Result | Receive aTokens | Receive underlying WETH |
| --- | ---: | ---: |
| Borrower scaled aToken balance | 66 | 66 |
| Liquidator scaled aToken balance | 47 | 20 |
| Treasury scaled aToken balance | 14 | 14 |
| Scaled aToken supply | 1000 | 973 |
| Collateral virtual liquidity | 1000 | 960 |
| USDC wallet / vault / approval | 60 / 240 / 60 | 60 / 240 / 60 |
| Ordered events | 19 | 16 |
| Changed storage slots | 21 | 24 |
| Synthetic harness gas | 433684 | 480994 |

In aToken mode the supply and collateral rates remain unchanged, and no WETH
transfer occurs. In underlying mode the library burns aTokens, updates collateral
rates/liquidity and delivers WETH. Actual observed USDC code collects repayment in
both cases. The final event encodes the selected mode. The two snapshots and full
expected results are retained under `synthetic/atoken` and `synthetic/underlying`.

## Verification

Nine Rust tests cover both modes through independent prior delivery models and
the payment reference. Eighty seeded input sets are each run in both modes; these
160 main executions are not counted as additional unit tests. Cases include fee
capping/full collateral exhaustion, zero fee, recipient=treasury, no rewards,
exact approval and maximum approval decrement.

Both modes revert all earlier contract changes and logs for insufficient USDC,
pause, blacklisting, receiver overflow and proxy-admin fallback denial. Synthetic
fault tokens test false/malformed/no-code responses without claiming those are
observed USDC behavior. Missing payment witnesses fail closed. A treasury overflow
takes precedence over a simultaneous USDC pause, proving the retained ordering.
Malformed or truncated ABI mode values revert before contract effects.

The aToken path succeeds with no WETH account, no aToken underlying-asset slot
and no collateral rate mapping. It also succeeds with insufficient artificial
underlying liquidity and a collateral factor invalid for the burn path, because
that path is not executed. The corresponding underlying case fails. Switching
the mode in a minimal aToken witness set to underlying fails closed.

Nine Python tests bind original sources/settings/excerpts, both exact CLI
examples, mode switching, rollback, invalid ABI and missing-witness behavior.
All previous dependency runtime identities and explicit metadata gaps are
preserved. Pinned solc 0.8.27 produces a 7638-byte wrapper; a fresh compilation
reproduces identical output and stderr.

## Reproduction and limits

After preparing the pinned dependencies and historical Git objects:

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests delivery_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_delivery*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-delivery-execution-20261023/synthetic/atoken/input.json
```

Regenerate with `research/build_aave_delivery_execution.py --compiler <solc-0.8.27>
--output <fresh-directory>`. Retained source/settings and compiler outputs are
under `evidence/aave-delivery-execution-20261023/compiler`.

No new public capture is performed in this increment. The previous USDC capture
at three historical blocks is reused and audited offline. The unchanged complete
observed WETH/USDC runtimes still differ from compiled source metadata; full parity
remains false. The sandbox is Cancun, with artificial state and a synthetic Pool
entrypoint. No historical transaction, executable eligibility, financing, profit,
Foundry fuzzing or operational phase is certified. Titan-only gas policy remains
unchanged, with zero operator prefunding/fallback/principal/collateral/guarantees.
Global progress remains 43/100; signing, broadcasting, deployment and spending
remain disabled.
