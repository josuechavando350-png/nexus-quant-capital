# Original USDC payment after collateral delivery

The synthetic Pool experiment now executes the original `safeTransferFrom`
payment and `LiquidationCall` event after debt burn, rate updates, rewards,
collateral burn, WETH delivery and the capped treasury fee. The unchanged Aave
source supplies the payment/event excerpt and GPv2SafeERC20 implementation.
The new wrapper assigns the supplied repayment and the observed aUSDC destination.
No original contract source or previous fixture is modified.

## Observed runtime identity

The retained read-only capture uses 84 requests across Blast and dRPC at blocks
26248075, 26248113 and 26248378. Both providers agree on complete USDC proxy and
implementation code, proxy routing/admin words and aUSDC's underlying-asset word.
Reads are pinned to canonical block hashes, with chain/finality and repeated
header checks. These are end-of-block observations, not authenticated state-root
proofs or transaction prestate. There are no new liquidation events in this sample.

USDC proxy `0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48` routes to
`0x43506849d7c04f9138d1a2050bbf3a0c054402dd`. Its old Zeppelin implementation/admin
slots are checked against original compiler AST constants. The payment destination
is aUSDC `0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c`. USDC's implementation layout
places pause at slot 1/offset 20, combined balance/blacklist mapping at slot 9 and
allowances at nested mapping slot 10. Actual getter execution confirms these
supplied slots. The SignatureChecker library is outside the executed transfer path.

Checksum-pinned solc 0.4.24 and 0.6.12 compile unchanged Sourcify sources/settings.
The observed proxy is 2,186 bytes and implementation 23,464 bytes. Their executable
prefixes match the independent compiler outputs (2,143 and 23,411 bytes), but each
differs in 32 metadata-hash bytes. Exact CBOR envelopes and lengths are checked.
**Full source/runtime parity remains false for both contracts.** The complete
observed runtimes, including deployed metadata, are executed. Compiler outputs
are never patched. The prior WETH metadata difference also remains open.

## Expected behavior and tests

The default artificial example transfers 40 USDC from the liquidator to aUSDC:
wallet 100 to 60, vault 200 to 240, approval 100 to 60. USDC decreases even a
maximum `uint256` approval; it does not treat that value as an infinite allowance.
The preceding WETH delivery remains 40, with fee 10 in aTokens. All 27 return
words, 16 ordered events and 24 changed storage slots match the independent
composition model. The last events are USDC Transfer and Pool LiquidationCall.

Ten Rust tests include 120 seeded compositions and exact balance/approval limits,
maximum approval, recipient=treasury and disabled rewards. Insufficient balance
or allowance, paused USDC, blacklisted Pool/liquidator/vault, 255-bit recipient
balance overflow and proxy-admin fallback denial revert all previous contract
writes and logs, including WETH already delivered. Dust debt repayment that
rounds to zero scaled burn is rejected. Missing account, code, routing, pause,
blacklist, balance or allowance witnesses fail closed. Explicit synthetic fault
tokens also exercise GPv2 rejection of false, malformed and no-code responses;
these stand-ins are never represented as observed USDC.

Fifteen Python tests cover the bounded collector, retained-reply replay, compiler
identity, metadata boundaries, layouts, original excerpts, fixture rebuilding,
actual getters, exact CLI output and late rollback. Rehashing a modified capture
does not bypass its semantic chain/pin/provider/routing checks. Fresh recompilation
of all three profiles reproduces identical output bytes.

## Reproduction and limits

After preparing the repository's pinned dependencies and historical Git objects:

```bash
export CARGO_TARGET_DIR=/tmp/nqc-miner-target
cargo test --offline --locked --test aave_debt_execution_tests payment_execution
NQC_MINER_TEST_BINARY="$CARGO_TARGET_DIR/debug/nqc-miner" \
  python -m unittest discover -s research -p 'test_aave_payment*.py' -v
"$CARGO_TARGET_DIR/debug/nqc-miner" simulate \
  --input evidence/aave-payment-execution-20261023/synthetic/input.json
```

`research/build_aave_payment_execution.py --compiler-directory <directory>
--output <fresh-directory>` recompiles with the three pinned native solc binaries.
The retained original inputs/outputs are under `evidence/aave-payment-execution-20261023/compiler`.
The collector is a separate, bounded read-only action; replay/tests do not use RPC.

This is the distinct USDC/WETH, receive-underlying composition. The receive-aToken
branch still needs payment composition. Initial reserve updates/validation,
health/eMode, amounts derived from actual state, same-asset cache handling,
multi-reserve bad debt, full deployed Pool/proxy entry and authenticated historical
transaction prestate under its correct fork remain open. The supplied Pool,
balances, allowances, indices and rates are artificial; the sandbox uses Cancun.
Neither simulated USDC nor its approval proves principal financing. Titan's
execution-specific gas commitment is still unauthenticated; operator gas,
principal, collateral and guarantees remain prohibited. No activation, economic
certification, spending or operational phase credit is granted. Progress: 43/100.
