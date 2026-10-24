# Original amounts composed with updated reserves and payments

The synthetic Pool wrapper now executes the original revision-11 amount segment
after both reserve updates and initial validation, before debt burn, collateral
delivery, treasury fee and observed-USDC payment. The exact contiguous excerpt
derives units from reserve decimals, applies the close factor and request cap,
calls the unchanged collateral/bonus/fee helper, and enforces minimum leftovers.
No recovered source bytes or compiler settings are patched.

The ABI accepts a requested debt-to-cover limit; actual repayment, collateral
delivery and fee are computed. It no longer accepts supplied actual amounts,
fee or collateral unit. The bonus comes from the original reserve-configuration
expression. This wrapper explicitly covers borrower eMode category zero only;
the eMode selection branch is not executed. Both reserve and token states remain
synthetic. Health, oracle prices and aggregate debt/collateral totals are supplied.
No aggregate-account computation, price authentication or eligibility is claimed.

The 43 output words contain the earlier 37 composition words plus maximum
liquidatable debt, actual repayment, liquidator collateral, fee before the final
scaled-balance cap, and selected debt/collateral in base currency. The earlier
fee word still reports the final capped fee. Both outputs are compared in full,
along with every ordered event and storage change, against independent amount
and reserve models composed with the previous delivery/payment reference.

The default deliberately artificial example uses zero decimal reserve units,
equal supplied prices of 100000000000 and reserve bonus/fee of 10500/1000 bps.
After one year of index accrual, selected debt/collateral are 166/156. A request
of 40 computes repayment 40, liquidator collateral 41 and protocol fee 1.
Wallet/vault/allowance become 460/240/460. These are raw synthetic units, not
Ethereum USDC/WETH economic quantities. A separate test uses 6/18 decimals
with adjusted synthetic prices to exercise the configuration-derived units.

Seven Rust tests include 48 seeded sets in both modes, without counting those
executions as separate unit tests. Coverage includes health exactly at/above
the close-factor threshold; aggregate-debt and requested caps; collateral
exhaustion; fee/bonus variation; zero-divisor and uint256 overflow errors; exact
minimum-dust acceptance/rejection; reserve accrual rollback; initial validation
before amount errors; late USDC failure; and missing-state rejection. An exhausted
selected reserve sets the global no-collateral flag only when the supplied
aggregate collateral agrees, preserving the original distinction.

Eight Python tests reproduce both complete CLI examples and the independent
amount/reserve CLI reports, pin original excerpt order and source/settings,
compare inherited contract bytes, and exercise error order, dust rollback and
missing witnesses. Pinned solc 0.8.27 produces an 11578-byte wrapper; a fresh
compiler run reproduces the complete output and stderr exactly.

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests aave_sizing_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_sizing*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-sizing-execution-20261023/synthetic/atoken/input.json
```

Regenerate with `research/build_aave_sizing_execution.py --compiler <solc-0.8.27>
--output <fresh-directory>`. Original sources and all earlier evidence remain
immutable. No new public RPC calls are needed. Synthetic gas is diagnostic only.

Remaining work includes GenericLogic health/eMode and oracle calls, same-asset
cache handling, multi-reserve bad debt, actual Pool entry, authenticated historical
transaction prestate under its correct fork and WETH/USDC metadata parity.
The closed sandbox uses Cancun; this is not full historical liquidation replay,
profitability validation, Foundry certification or an operational phase exit.
Progress stays 43/100. Titan-only gas policy, zero operator exposure and disabled
signing, broadcasting, deployment and spending remain unchanged.
