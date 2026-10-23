# Aave token proxy execution

The combined debt experiment can now use the actual deployed 2,400-byte
`InitializableImmutableAdminUpgradeabilityProxy` runtime. The preceding synthetic
forwarder and its evidence remain available. The additional fixture is
`fixtures/aave_proxy_execution.json`.

## Exact scope

Original sources for the USDC variable-debt proxy are retained from Sourcify.
Solc 0.8.10 is pinned by SHA-256 to the retained official compiler index. Source
bytes, optimizer settings, Berlin compilation target and metadata settings are
unchanged. Only output selection is expanded. The sole immutable is `_admin`;
its six compiler-declared 32-byte positions receive the fixed admin address
`0x64b761d848206f447fe2dd461b0c635ec39ebb27`. Full runtime equality includes metadata.
Three compiler executions produced identical inputs and outputs.

This runtime matches ten existing observations covering six distinct token
proxies in blocks 26248075, 26248113 and 26248378. Twenty retained provider code
replies and twenty implementation-slot replies are checked at their original
block hashes. No new RPC capture or historical event is added. The two observed
1,853-byte proxies are excluded: the attempted source lookup returned HTTP 404.
The compiler's primary download returned HTTP 403; the official solc-bin GitHub
copy passed the same pinned checksum. Retrieval details and failures are retained.

## Execution and tests

The original debt function, exact variable-debt implementation and rate strategy
execute through the audited proxy in one synthetic REVM transaction. The proxy
reads the explicit ERC-1967 implementation slot. The implementation runs in proxy
storage; return bytes, caller checks, events and reverts cross the real delegatecall
boundary. Six hundred seeded cases compare all ten outputs, all ordered logs and
all changed contract storage against independent arithmetic. Callback failures and
later token/Pool/rate failures require full rollback.

For each of the ten historical code/slot observations, separate synthetic states
exercise `admin()`, `implementation()` and `scaledTotalSupply()`. The last getter
executes the actual corresponding aToken or variable-debt implementation. Supply
slots come from their independent compiled layouts: 54 for aToken and 58 for debt.
No historical balance is inferred from these supplied values.

Directed tests check that the immutable admin cannot use fallback; non-admin calls
to admin selectors delegate into the token; only local admin calls can change the
implementation slot; a subsequent getter follows the changed slot; non-contract
upgrade targets fail; failed `upgradeToAndCall` rolls back slot and event; and an
already-initialized proxy rejects another initialization. Missing slot/target
witnesses fail closed. Admin callers and alternate implementation addresses are
synthetic test accounts; the deployed administrator contract is not executed.
Nothing calls an on-chain upgrade or uses a signing key.

The eight new Rust tests contain 654 attempts: 634 successes (including 600 seeded
cases), 18 expected completed reverts and two missing-witness errors. The earlier
eight tests remain in the same test target. Seven new Python tests bind exact
sources, compiler output, immutable positions, provider code/slot/block pins,
explicit exclusions and a complete replay through `nqc-miner simulate`. They
reject metadata/code/slot mutations and missing/tampered CLI witnesses.

## Reproduction

From `migration/nqc-miner`, with the pinned compiler and existing offline toolchain:

```sh
python3 research/build_aave_proxy_execution.py --compiler /absolute/path/solc-0.8.10 --output /fresh/compiler-directory
cargo test --locked --offline --test aave_debt_execution_tests
NQC_MINER_TEST_BINARY=/absolute/path/nqc-miner python3 -m unittest discover -s research -p test_aave_proxy_execution.py -v
nqc-miner simulate --input evidence/aave-token-proxy-execution-20261023/synthetic/input.json
```

The build command replaces only the new fixture/profile and writes compiler files
to a fresh directory. It validates unchanged prior evidence. Exporting a new
example is optional via `NQC_MINER_PROXY_EVIDENCE_DIR` and requires a fresh directory.

## Limits

The proxy runtime and original observed implementation words are historical;
execution balances, parameters, Pool entrypoint and rewards probe are synthetic.
The administrator's own behavior, remaining proxy family, real rewards controller,
aToken transfers, underlying token transfers, aggregate health/eMode, multireserve
bad debt and transaction-boundary state are not certified. Compilation targets
Berlin; the execution sandbox uses Cancun, without a historical fork claim.

The retained example uses 215,726 gas in this artificial harness. It does not
estimate production liquidation fees or profitability. Full liquidations,
historical eligibility, hermetic builds, Foundry certification and operational
phase exits remain open. Progress stays 43/100; Observer and original evidence
are unchanged.
