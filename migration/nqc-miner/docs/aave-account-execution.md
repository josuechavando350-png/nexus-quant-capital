# Original account health, eMode and oracle calls composed with payments

The new synthetic Pool wrapper calls unchanged `GenericLogic.calculateUserAccountData`
after both reserve updates and before the original initial liquidation validator.
It derives aggregate collateral/debt and health from observed token code, updated
indices, reserve configuration and an explicitly synthetic oracle. The original
eMode/default-bonus selection and price calls then feed the amount calculation,
debt burn, both collateral-delivery modes, fees and observed-USDC payment.

The ABI no longer accepts health, aggregate totals or prices. Prices remain
supplied **in the oracle's synthetic storage**, not authenticated. Category and
eMode configuration are also synthetic inputs. There is no claim that a real
Aave oracle, Chainlink feed, price freshness, Pool entry or historical state has
been verified. Original source bytes/settings remain untouched.

## Scope and storage

The exercised account holds WETH collateral and USDC variable debt. Both selected
reserves are copied after their updates into synthetic storage mappings required
by GenericLogic: reservesData at slot 21, reservesList at 22, eModeCategories at 23.
The prior fixed reserves remain at slots 0 and 11, and user configuration at 10.
These copied reserves deliberately record the pre-burn updated state, whereas the
original wrapper reserves continue through burn/rate/payment execution. This
instrumentation is not the real Pool layout. Every added storage change is checked.

Explicit zero-address list gaps are tested, including the highest user-config bit.
Empty/no-borrow cases retain the original maximum health rule and fail initial
validation. Arbitrary additional reserves, reverse asset roles and multireserve
bad-debt handling are not certified. eMode bitmap membership changes the health
threshold and liquidation bonus; excluded assets fall back to reserve values.
Isolated/zero-LTV configuration is exercised, but average LTV/threshold return
values are discarded by the original liquidation call and are not separately
certified by these output comparisons.

The explicit `SyntheticAccountOracle` returns supplied prices and can reject reads.
Missing oracle/account/price/list/token storage witnesses fail closed. There is
no fallback that invents missing values. The synthetic oracle has no production
runtime identity or historical price-state claim.

## Results and verification

The wrapper returns 47 words: the prior 43 plus computed health, aggregate
collateral, aggregate debt and selected bonus. Independent integer expectations
derive floor collateral value, ceil debt value and half-up WAD health division.
Those values feed the independent amount model and prior reserve/delivery/payment
composition. All output words, ordered logs and exact storage changes are compared.

In the default artificial zero-decimal example, updated selected debt/collateral
are 166/156, prices are 100000000000, threshold is 8000 bps, and computed health
is 751807228915662650. Aggregate collateral/debt are 15600000000000/16600000000000;
the default bonus is 10500 bps. A request for 40 computes payment 40, liquidator
collateral 41 and fee 1. Final wallet/vault/allowance are 460/240/460 raw units.
These are synthetic quantities, not Ethereum USDC/WETH economic amounts.

The aToken route produces 19 logs and 45 changed slots; underlying produces
16 logs and 46 slots. Gas 1062339/1069876 belongs only to this instrumentation.
It must not be interpreted as production cost or sponsor coverage.

Nine Rust tests include 32 seeded sets in both modes, without inflating unit-test
counts. They cover computed health exactly one and a price step below it, eMode
membership/eligibility/bonus changes, empty/gap flags, zero prices, overflow,
malformed oracle return data, oracle failure before validation, reserve failure
before oracle access, missing witnesses, ignored former supplied totals/health,
and complete rollback after late USDC failure. Eight Python tests bind source,
settings, ABI/layout and explicit limits; replay both examples; independently
derive health from reserve CLI reports; and exercise eMode, oracle and payment
failures through the actual simulation CLI.

Pinned solc 0.8.27 produces a 16886-byte Pool wrapper without diagnostics. A fresh
build reproduces complete compiler output and stderr. No new public RPC calls
are required, and all earlier historical evidence remains unchanged.

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests aave_account_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_account*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-account-execution-20261023/synthetic/atoken/input.json
```

Regenerate with `research/build_aave_account_execution.py --compiler <solc-0.8.27>
--output <fresh-directory>`. Remaining work: observed oracle/feed dependencies and
authenticated prices, additional reserve configurations, same-asset/multireserve
paths, actual Pool entry, WETH/USDC metadata parity and authenticated transaction
prestate under its correct fork. The sandbox uses Cancun. No complete historical,
economic, Foundry or operational phase certification is granted. Progress remains
43/100. Titan-only gas policy and zero operator exposure remain unchanged; no
signing, broadcasting, deployment, activation or spending occurs.
