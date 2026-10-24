# H24 — historical flash financing and dependent replay

Base: H23 producer `3448f173305d765f3cdf9a5494571b34a16c0e34`.
H23's exact-producer remote run completed successfully; it has no H24 scope.

Read-only public Routescan acquisition returned the exact historical rank-1 receipt
with 17 logs. HTTP 200, the exact URL, retrieval time and original response body
are retained. No credential, account, subscription or Blockscout retry was used.

- Capture SHA256: `8bb0bde55bd501175f54148561a508fcab0bf296e5bfa10123b4fde3acdc8701`.
- Raw response SHA256: `4eb761445a70860837872e6eb5d2e7bba0ad0c78640185d12ebed9a3dbf08e43`.
- Report commitment: `857b497bebdb95c1c12e1c9dcca74abb81bb38776ff6e349893b7ee6cdf308ca`.

The event, outgoing principal and repayment each carry 10684013854557827871 WETH
wei. The observed WETH repayment premium is zero; full financing costs and NQC
profit are unknown. The immutable original normalizer reproduces the retained
dRPC receipt summary. H23's operation selectors/counterparties corroborate the
loan and callback. See `FLASH_FINANCING_CONTRACT.md` for scope and references.

The first local CLI probe rejected an acquisition timestamp expressed with a
`+00:00` suffix. The capture was normalized to the same instant in required UTC
`Z` format before publication and repinned; no receipt response bytes changed.
An optional independent hashing probe could not import PyCryptodome; the runtime
reader has no such dependency. These probes are not counted as passing tests.

The targeted suite passes **18/18 tests** (5.546 seconds), without failures, errors
or skips. Cases reject wrong chain/anchors/participants, gas or Aave-event drift,
receipt failure, missing/removed/duplicate logs, malformed ABI padding, altered
principal/repayment/withdrawal, callback disagreement and resealed route, cost or
Titan claims. Full local regression is still running at this checkpoint.

Isolation passes with 176 reviewed Omega files, 531 original files, 106 disabled
historical workflows and the unchanged active workflow. Original Git objects are
not supplied locally; no remote H24 validation is claimed.

An independent stdlib-only Keccak implementation, checked against the empty-string
and ERC20 Transfer vectors, reproduces the FlashLoan topic and both call selectors.
It also checks the raw response hash, all 17 log indices, exact principal repayment,
collateral/debt/withdrawal arithmetic and gas without importing Omega modules.
The missing optional PyCryptodome package did not require installation or a runtime
dependency. The independent check passes.

| Local check | SHA256 |
|---|---|
| Targeted tests | `da58fa6a697015bf5d43e938d5ac15ca826ffa89e5aa70ba0ff97ef61146108d` |
| Isolation | `4b5f1c8abce1b3008500444cfa2c31772274726684812cceae31575494d056a6` |
| Independent signatures/arithmetic | `f4f110953e4446b53b48f5e1d744d24d839b13925f43f434506d26c0d71ea6b8` |

These are session results, not remote CI artifacts. No ninth store batch or new
runtime/physical execution is claimed. Original sources, workflow and Titan-only
zero-operator-gas policy remain unchanged. Product certification 0/36, complete
paid-cost rows 0/127, Titan coverage 0.

## Complete local regression

**672/672 unique Omega tests pass**, including 18 new financing cases, with zero
failures, errors, skips or expected failures (654.659 seconds). All recorded test
source hashes still match the published code. Full result SHA256:
`16f3a5cb7a9d811ec483e9ed4d7a9b76ce0df3c70b95a4230a77756c8477d025`;
commitment `7a89111a55093e89aba63e2ed030c22ef7c94584efb6de55b35dbeaa9739a9a9`.
Final isolation passes with the same 176/531/106 counts and unchanged workflow.

Feature commit: `a33fa4249d1f96765854c9d29c5e3d9e089d6521`; tree:
`3bcd8e67397bc431eaae88ddd3dec4bffd3fe54b`. PR #33 remains a local-tested draft.
Only Markdown is updated after this tested source checkpoint. No H24 remote run,
NQC Morpho execution, new store/runtime integration or Titan coverage is claimed.

Next bounded work: bind this reader as H23's dependent ninth batch and add an
independently reproduced disconnected runtime record. A separate Morpho execution
experiment must use an additive overlay/fresh build copy, authenticate the lender's
deployed code and anchor liquidity, and measure repayment plus gas. Do not reuse
the Aave fork's gas profile or infer savings from its different fee. Preserve Titan
as gas payer and keep executable admission blocked until operation-specific
coverage, repayment, compensation and complete costs are evidenced.

## Upstream documentation synchronization

H23 Markdown-only closure `92867c001394ae3aa8091c8b82fcf0bfd13b4ce6` is merged into this draft.
The H24 feature/test/capture bytes remain those of `a33fa4249d1f96765854c9d29c5e3d9e089d6521`.
The successful H23 run does not validate H24; this PR remains a local-tested draft.

## Ninth-batch and runtime integration

Continued from documentation head `72123d3ed24d47b8619f587b9a8dc730cfc42c91`.
The original receipt capture and financing observation report are unchanged.
The ninth SQLite batch declares H23 as its sole parent and recursively verifies
the inherited bytes, exact inventory, pinned capture and recomputed report.
Revoking H23 blocks its financing child and readmission of that child.

Runtime v7 requires the `flash-financing` record in the disconnected worker. Both
worker and consumer reconstruct the nine batches, revoke their root and restore
the exact snapshot. All nine normal reads fail in both stores, while every batch's
forensic object bytes survive. The new record binds H23's batch/root/report and
H21's economics report, matching the physical network namespace and Titan policy.
Historical v1-v6 retain their original inventories and proof scopes.

Thirteen store/replay cases and three runtime v7 cases are added. Targeted checks
and the full integration regression are pending at this checkpoint. The previous
672-test result covers the intake draft only. Original Git objects are not supplied
locally; remote isolation must verify them. No source, workflow, permission,
Rust/Solidity implementation, Miner or execution authorization is changed.

The read-only execution review confirms the recovered `NqcAaveV3Executor.sol`
couples flash borrowing and liquidation through the same Aave pool. Substituting
Morpho's address cannot create a valid route. A later experiment must explicitly
separate lender and liquidation pool, authenticate the callback against an active
plan, verify historical deployed code and liquidity, and measure its own gas.
The existing H2 fork's different transaction and USDC debt route cannot supply
rank-1 WETH/Morpho execution evidence. This review adds no execution code.

## Targeted integration verification

The financing/store/replay suite passes **31/31** tests (134.171 seconds), and
the runtime suite passes **28/28** (574.856 seconds), with zero failures, errors,
skips or expected failures. All recorded test-source hashes match. The complete
688-case regression is running; the remote exact-producer audit remains pending.

Authentic H23 v6 artifacts pass the new consumer with their original 43/45 record
scopes. This is compatibility verification, not a new remote H23 or H24 execution.
Independent retained-byte checks confirm unchanged H23/H24 captures and reports,
active workflow, original source files and Miner. Isolation passes 176/531/106;
original Git objects remain unchecked locally.

| Integration check | SHA256 |
|---|---|
| Financing/store/replay | `cd3e7008a5df0f2240da814d4505618e07e35fda10bf18ab0c370a53aec4794b` |
| Runtime v7 | `765feb4a90d6d43f8f10f619c96b4e3a6de61c1f2fc5be9ea0e550e06ed59295` |
| Isolation | `4b5f1c8abce1b3008500444cfa2c31772274726684812cceae31575494d056a6` |
| Independent retained bytes/boundaries | `c77f473d5cbe2714796e65b10f2132d6afbed700ca07d4ddf071803774d8e2b9` |
| Authentic H23 v6 compatibility | `5523c478bc0d381b3d95b4ddbad40061c8376e8016a4c91ee4813152f57b70d4` |

## Complete integration regression

The first full invocation omitted `NQC_D15_ARCHIVE` and `NQC_D16_ARCHIVE`.
It executed 688 cases but skipped six real-archive cases, so the strict recorder
correctly reported `TESTS_INCOMPLETE_OR_FAILED` despite unittest's permissive
success flag. It is not counted as a full pass. Report SHA256:
`6e2c6142f0ae4918dd2e3b53e648d003f821faba464965f2357780981029b3c9`.

The same producer was rerun with the retained D15/D16 archives supplied.
**688/688 unique cases pass** in 1029.848 seconds: zero failures, errors, skips,
expected failures or unexpected successes. All 30 test-source hashes match the
producer. Strict report SHA256:
`db21ed8de60a05c4e18b40926e9f22e7bde3f930a39eb37b60b0140003394594`;
report commitment:
`0d19b86cf38278739c0eb902c497b1692456861bbfb9ac37b9e7dbc6c300c00f`.
Both reports and logs are retained so the incomplete invocation is not hidden.
No code was changed between the two invocations.

Exact producer `7dd91b7f95b400b6abecaba0119da5bce0491999`, tree
`8f5d85ad7cc22cd02c158791f4252f385cbc99b3`, was promoted by a non-force
fast-forward of the existing audit branch. Run 40054817457, attempt 1, started
at 2026-10-24T02:35:39Z using the unchanged workflow. PR #33 was automatically
marked merged by GitHub. These facts alone do not establish a successful remote
audit; the final API/artifact/log outcome is recorded below when complete.

## Separate read-only Morpho research checkpoint

After the H24 producer was fixed, a separate scratch experiment authenticated the
Morpho runtime at the end of historical block 25938048, hash
`0xf143f9988199037938e4dff57aaf24301a4c26770aefc0ec64774954cbf2dbe4`.
The verified source was compiled with exact Solidity 0.8.19 settings, and only its
two compiler-declared DOMAIN_SEPARATOR immutable slots were populated. All 15,623
runtime bytes, including metadata, matched two public RPC providers. Runtime
Keccak: `0xfa259fa317198f88f5fa3c119f06c066295dbcd47d715e0a30e1bcf94c02ef8c`.

Offline account-proof verification traversed eight nodes per provider, bound the
code hash to stateRoot and recomputed the 21-field RLP header to the previously
captured block hash. Fourteen deliberate proof/header/code alterations rejected.
This establishes membership relative to that captured block hash, not independent
consensus/finality verification, transaction-prestate or token storage proofs.

Both providers also returned the same read-only eth_call creation simulation:
10684013854557827871 WETH wei borrowed and repaid, one authenticated callback,
zero probe balance before/after, zero remaining allowance and unchanged lender
balance. Wrong-block and wrong-code controls rejected on both providers (4/4).
The measured 161955 inner-call gas excludes deployment, intrinsic gas and final
refund accounting; it is not an all-in execution cost, gas saving or paid fee.
No signed transaction, public-chain deployment, state override or funding occurred.

Five offline research verifiers pass, including request/compiler/response hash
bindings. Their source, captured responses, compiler inputs/outputs and reports
are retained in the evidence bundle. The first large-literal probe compiler attempt
terminated with SIGSEGV; only the compact code-hash-guard probe produced successful
compilation and simulation. The failed input is retained separately.

This later experiment is not an H24 runtime record or an NQC liquidation route.
It does not alter H24's original witness flags or inherit the producer's remote
execution. Current liquidity, transaction-prestate, complete costs, realized profit
and operation-specific Titan coverage remain unproven. Admission stays blocked:
Titan must pay gas, operator allowance is zero and own-gas fallback is forbidden.

| Separate research report | SHA256 |
|---|---|
| Source/runtime reproduction | `a6dd309bed068379f661beb4177ea29ffe45a130bf4c2d074702f531d7849311` |
| Header/account proof | `30f59938887269167cc7ec966cfc23df4506fa477dffe947274ff3ab36d4f8c2` |
| Two-provider round trip | `398bb96a908c8e172965c27b66b870c26876b3cfa22f54bfb2be1fcd6e488617` |
| RPC negative controls | `bbc000588bf4f04fd8de2d62f63a126ba7fba292d1d6b7a20c51d3cdd0f79e31` |
| Request/compiler bindings | `fcccc0d97592386921b98e9ed2f3ca43bd821e6823ce0e2d37de70f4ebbf5318` |

A local final-isolation precheck rejected one generated `omega/__pycache__` file.
Only that generated `.pyc` was removed; no tracked bytes changed. Rechecking with
`PYTHONDONTWRITEBYTECODE=1` passes the same 176/531/106 boundary. The rejected
precheck and successful result are both retained. Original Git object verification
remains a remote-job responsibility.

## Final exact-producer outcome

Run **40054817457**, attempt 1, producer
`7dd91b7f95b400b6abecaba0119da5bce0491999`, tree `8f5d85ad7cc22cd02c158791f4252f385cbc99b3`,
completed successfully at 2026-10-24T03:12:02Z. Both jobs and every step passed.
Closure edits after this producer are Markdown only; later code cannot inherit
this execution.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120755351970 | 12545945409 | `1b39a9041ed2ee14b1095a3c8103d89a1cbc70597ea22fe4b59ce8d96ed96981` | `e8c3edfd1b3fc60b611d385557c53238332684c10acc26c541fd99296de9ac3c` |
| replay | 120755351762 | 12545957463 | `8717e18e2c1de3d1da09563aea59549467e1925c9fd9d9b67de86262fb8e978c` | `3a856c8b0ae9f37389b67f49b33fa0e15d2c862fe9dd58499adb7d575779d85c` |

Independent GitHub API readback, downloaded ZIPs and full decoded job logs agree
on repository, commit/tree, workflow, run/attempt and all evidence records: 43 for
forks and 46 for replay. Each job passes 261 intake, 43 runner, 38 capture, 33 store,
10 pipeline and 28 runtime tests: 413 executions per job, not additional unique
cases. Every recorded test-source hash matches the producer. Physical checks pass
56 PFT Rust, 528 Census Rust, 14 offline Solidity tests, four historical fork
executions and 16 verified disconnected replay steps.

Original Git objects and isolation pass before/after both jobs: 176 reviewed Omega
files, 531 original files, 106 disabled legacy workflows and the unchanged active
workflow/permissions. Historical source/store roots remain unchanged. Existing
H19/H20 Rust transport probes and historical Aave execution retain their scope.

The new H24 record is reconstructed in the same physical disconnected worker:
loopback only, a namespace distinct from its parent and no routable network. All
nine normal batch reads fail after controlled root revocation in both source and
restored SQLite stores; every batch's forensic object bytes survive. The emitted
worker report equals the v7 artifact and binds H23's batch/root/report, H21's
economics commitment and the exact Titan policy. This is not new Rust transport,
canonical reorg recovery or a Morpho liquidation executed by NQC.

Independent checks retain the same historical principal and repayment:
10684013854557827871 WETH wei each, with zero observed WETH repayment premium.
The H24 runtime record leaves other financing costs, deployed lender-code identity,
current liquidity and the NQC Morpho route unproven. The later code/account proof
has its separate scope above. Gas and direct fee-recipient payment remain separate.
No zero total-cost or realized-profit claim is admitted.

Titan remains the required gas payer: zero operator allowance, no prefund and no
own-gas fallback. Policy hash:
`e2c0b1ea247597de667d093385990880a31519b594f68cae31618ba425f87540`.
No Titan submission, coverage receipt, signing, broadcast, funding or deployment
was added.

- Forks post-audit commitment: `08c274e021f2e81d01158394f9663d72063968a30dfe981e049434f9dd88606f`; log SHA256: `8a9c288dddda645f63436f22a7b29bf78407aedeed5f6fbcad5b5ac9769cdacf`.
- Replay post-audit commitment: `a757920ef41553b2e0413ac05071d0fb10a0839f99d276cafe8a83fed598dd73`; log SHA256: `e6cca668913b636f7e3ecf14b8cdb70d9f84d93fbb25cf0e4cc9e8bc70ea17fa`.
- Financing replay commitment: `8344a3c4c66fffa5778d17415ab8c84f5eb24b0f53425d2522e7d9a317d7ec93`.

H24 engineering closure: **4/4 (100% of this increment)**, with **688/688** unique
local tests, 34 new cases over H23 and 16 over the initial H24 intake. Product
certification remains 0/36, Census 0/9, complete paid-cost rows 0/127 and
Titan-covered NQC executions zero. The next execution experiment remains separate.
