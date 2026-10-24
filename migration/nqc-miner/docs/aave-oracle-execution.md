# Observed AaveOracle code composed with explicit synthetic feeds

The synthetic Pool composition now calls the actual historical runtime of
`0x54586be62e3c3580375ae3723c145253060ca0c2`. AaveOracle recompiles byte for byte,
including metadata, from its published unchanged seven-source Solidity 0.8.10
input. The original Berlin target, optimizer (100000 runs), metadata and settings
are preserved. Only six compiler-declared immutable locations are filled with
observed provider/base-currency/unit words. No metadata patch or stripping occurs.

The earlier synthetic oracle is replaced. **Feeds and fallback remain explicit
test doubles**, with supplied answers and state. The actual oracle's routing and
branch behavior are exercised; deployed feed/adaptor/aggregator code, authenticated
round state and freshness are not. This is not a historical liquidation replay.

## Historical code and routing observations

A bounded capture makes 144 read-only RPC requests to two providers at the three
previously retained block hashes. Chain, finality and block/event headers are
checked before and after; code, storage and calls use EIP-1898 canonical hash pins.
The original event anchors are unchanged; no new liquidation event is claimed.
The capture is independently replayed offline with exact request/response order.

The provider routes to this oracle at all three samples. Its base currency is
zero (USD), base unit 100000000, and fallback address zero. The selected sources:

| Asset | Observed source |
| --- | --- |
| USDC | `0x3f73f03aa83b2a48ed27e964ed0fdb590332095b` |
| WETH | `0x5424384b256154046e9667ddfaaa5e550145215e` |

| End-of-block sample | USDC price, raw | WETH price, raw |
| --- | ---: | ---: |
| 26248075 | 99983478 | 240275000000 |
| 26248113 | 99983478 | 240029113527 |
| 26248378 | 99983478 | 240029113527 |

At every sample both providers agree, each feed answer is positive, and the
oracle's price equals that answer. Complete feed code is retained for later
verification but is **not executed** in the composed fixture. Provider agreement
and hash pins are observations, not Merkle/account-state authentication, price
freshness or transaction-boundary prestate. The selected oracle code matches the
local compiler across all six provider/block comparisons and published source data.

## Original routing behavior and atomicity

Seven Rust tests cover 24 seeded cases in both delivery modes, without counting
those invocations as separate unit tests. Full 47-word outputs, ordered logs and
storage changes match the independently checked account/amount/payment reference.
The source slot is derived from the observed route; feed answers in the simulation
remain artificial. eMode and account calculation continue to feed both payments.

The original oracle returns its immutable unit for base currency, uses positive
signed answers directly, and routes absent sources, zero and negative answers
to its fallback oracle. A positive answer does not require fallback storage to
be present in the closed witness. A reverting feed or malformed response propagates
the failure; the oracle does not recover it through fallback. Tests cover both
assets, signed minimum/maximum boundaries, fallback reverts and a zero-address
fallback, missing routing/code/answer witnesses, and late USDC failure. All
rejections preserve complete rollback, including updated reserves and copies.

The **price fallback** exercised here has no relation to gas funding. Operator gas
fallback remains forbidden under the Titan-only policy.

Twelve Python tests verify request scope, dual-provider replay, semantic tampering
even with rewritten file hashes, original sources/settings/selectors, immutable
ranges and metadata equality, inherited dependencies and explicit feed limits.
Both CLI examples reproduce complete outputs. Additional CLI checks cover signed
fallback prices, no recovery from feed errors, missing state, base currency and
late-payment rollback.

Default artificial outputs retain debt/collateral 166/156, health
751807228915662650, payment 40, collateral to liquidator 41 and fee 1. These use
zero decimal reserve units and artificial feed prices of 100000000000; the public
sample prices above are not presented as the transaction's simulated state.
The aToken route emits 19 logs and changes 45 slots; underlying emits 16 logs and
changes 46 slots. Gas 1076591/1084128 is only diagnostic of these wrappers.

## Reproduction and remaining boundaries

Pinned compilers are 0.8.27 for the unchanged Pool-source wrapper/doubles and
0.8.10 for the oracle. The wrapper is 16886 bytes; AaveOracle is 3405 bytes. Fresh
runs of both compilers reproduce complete output/stderr exactly. The initial
0.8.10 invocation rejected an unsupported `--no-import-callback` flag; its stderr
is retained. The corrected invocation uses all literal dependency sources in a
fresh empty directory, with no source modification.

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests aave_oracle_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_oracle*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-oracle-execution-20261023/synthetic/atoken/input.json
```

Regenerate with `research/build_aave_oracle_execution.py --compiler <solc-0.8.27>
--oracle-compiler <solc-0.8.10> --output <fresh-directory>`. Capture replay never
uses the network. Only explicitly rerunning `capture_aave_oracle.py` performs
the bounded public reads.

Pending: actual feed/adaptor/proxy/aggregator execution and authenticated fresh
round state; more reserves, same-asset/multireserve paths, real Pool entry,
WETH/USDC metadata parity and authenticated historical transaction prestate under
the correct fork. The sandbox uses Cancun. No historical, economic, Foundry or
operational certification is granted. Progress stays 43/100. Titan-only gas,
zero operator exposure and disabled signing/spending remain unchanged.
