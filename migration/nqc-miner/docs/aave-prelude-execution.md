# Original reserve updates and initial validation composed with payment

The synthetic Pool wrapper now runs Aave's original debt-reserve cache/update,
then collateral-reserve cache/update, followed by the original scaled-balance
reads and `ValidationLogic.validateLiquidationCall`. These unchanged excerpts
precede the existing debt burn, both collateral-delivery branches, fees and
observed-USDC payment in the same transaction.

Caches now read `scaledTotalSupply` through the observed variable-debt proxies
and implementation. The WETH variable-debt token is
`0xea51d7853eefb32b6ee06b1c12e6dcca88be0ffe`, whose routing/runtime was retained
at two previously audited blocks. No fresh public observations are added.

Debt is derived from the borrower's actual supplied scaled token state using
the updated borrow index, with ceil rounding; collateral balance uses the
updated liquidity index, with floor rounding. The ABI no longer accepts a
precomputed selected debt, cache total or updated indices. Reserve state itself
is initialized synthetically by the wrapper, and all token storage is supplied.

## What is and is not computed

Reserve liquidity/borrow indices, treasury accrual, timestamps, reserve factors,
selected debt and selected collateral balance now flow from the original
functions into the later token/rate/payment execution. Both reserves update
before validation, including when the liquidator requests aTokens. The latter
still avoids a WETH asset transfer but now needs the WETH variable-debt token
for the initial cache.

**Aggregate health is still supplied.** GenericLogic account-data/eMode
calculation, prices and integrated liquidation amount calculation are not
executed. The requested repayment, collateral amount, fee and aggregate base
collateral remain supplied. Calling the original validation on those values
does not certify historical eligibility or full liquidation correctness.

The shared wrapper returns 37 words: the prior 25 delivery/payment words plus
eight reserve index/treasury/timestamp values, initial selected debt/collateral
balances and both initial scaled debt totals.

Default artificial example after one year:

| Result | Value |
| --- | ---: |
| USDC reserve liquidity index, RAY | 1155000000000000000000000000 |
| USDC reserve borrow index, RAY | 1657750000000000000000000001 |
| WETH reserve liquidity index, RAY | 1560000000000000000000000000 |
| WETH reserve borrow index, RAY | 1304282407407407407407407407 |
| USDC / WETH treasury accrued, scaled | 20 / 24 |
| Derived selected debt / collateral | 166 / 156 |
| USDC wallet / vault / allowance after repayment | 60 / 240 / 60 |

Receive-aToken produces 19 events and 29 changed storage slots; receive-WETH
produces 16 events and 30 changed slots. Synthetic gas is 636438 and 643971,
respectively. Those numbers do not estimate production execution costs.

## Validation and rollback

Seven Rust tests compare the full 37-word output, ordered events and exact
storage changes with independent reserve/condition models plus the previously
checked delivery/payment composition. Thirty-two seeded sets run in both modes
without inflating the unit-test count. Same-timestamp skipping, zero rates,
zero collateral debt, varied rates/factors, recipient=treasury and reward
configuration changes are covered. aToken mode preserves nonzero collateral
rates from the initial reserve while underlying mode updates them.

All eight original validation rejections are exercised after reserve updates:
self liquidation, inactive/paused reserves, grace equality, non-liquidatable
health, invalid collateral ID, disabled collateral and zero selected debt.
Each reverts index/treasury initialization and accrual as well as all later
contract effects and events. Treasury overflow, index downcast overflow and
future timestamps preserve their exact original error bytes/order. A debt
update failure precedes the collateral cache, even with its witness absent.
A later USDC pause also rolls back the initial updates. Missing variable-debt
proxy, implementation routing or total-supply witnesses fail closed.

Eight Python tests bind unchanged source/settings/excerpts, storage layout,
dependency identity and remaining limits. Both examples replay through the
real CLI; independent `project-aave-reserve` and `check-aave-conditions` commands
reproduce the model reports retained beside each example. Early update failure,
health rejection, late payment rollback and missing cache witnesses are tested.
Pinned solc 0.8.27 produces a 9919-byte wrapper; a fresh compilation reproduces
the exact output and stderr.

## Reproduction and remaining limits

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests prelude_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_prelude*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-prelude-execution-20261023/synthetic/atoken/input.json
```

Regenerate using `research/build_aave_prelude_execution.py --compiler <solc-0.8.27>
--output <fresh-directory>`. The original reserve setup is artificial, the Pool
entrypoint remains synthetic and the sandbox uses Cancun. WETH/USDC metadata
gaps, same-asset handling, multi-reserve bad debt, GenericLogic health/eMode,
calculated amounts, real Pool execution and authenticated transaction prestate
under its correct fork remain open. No phase credit, financing, profitability
or full historical certification is granted. Progress stays 43/100. Titan-only
gas policy, zero operator exposure and disabled signing/spending remain unchanged.
