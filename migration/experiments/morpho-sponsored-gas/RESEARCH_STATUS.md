# NQC research continuity — 2026-10-17 UTC / 2026-10-16 Mexico City

## Current continuation: preserved prospective evidence and cost frontier

Current published base: **`bc46cbef64bdf66d16563150c09446bad95a86f2`**, tree
`1cd55a15258b7646e10f5a1169bdd77967759a99`; byte-identical to tested local
`5fa4d3160bbcb4eb1ea444735bd5ad2edf84b501`. This continuation belongs to the
commit containing this file (`git rev-parse HEAD`); publication identity is also
recorded in the Git commit message. Only the authorized research branch changes.

Executed after workspace recovery: **168 Python / 50 Solidity (33+17) / 9
isolation passed**, zero failures or skips. This supersedes earlier totals below.
New checks concern transaction ordering (4), prospective evidence (4) and the
strict cost frontier (1), not additional synthetic profit scenarios.
Preserved logs/commands are in `evidence/2026-10-17-prospective-recovered/`:
`validation-run.json` records the rebuilt Solidity execution; the subsequent
`temporal-validation-run.json` records all 168 Python and 9 isolation checks after
the final timing correction. `INPUT_SHA256SUMS` identifies current executable
inputs; `SHA256SUMS` checks evidence bytes. No failed check was hidden or skipped.
The older monthly checksum command reports two source-version mismatches in this
new checkout; both match their historical Git bytes. All historical raw evidence
is unchanged (`historical-manifest-check.json`). Old manifests were not rewritten.

Environment restored and verified: Python 3.12.14, PyCryptodome 3.23.0, Forge
1.7.1 at `4072e48705af9d93e3c0f6e29e93b5e9a40caed8`, NQC solc 0.8.24.
Original sources use pinned solc 0.8.19 / 0.8.28 / 0.5.16 and commits documented
in `toolchain.json` and `REPRODUCE.md`. No Solidity source changed. Original Git
objects remain unavailable (`original_objects_checked=false`); Rust, remote CI
and authentic historical EVM replay remain unexecuted. 106 workflows are disabled.

Implemented and observed:

- `prospective_observation.py` collects a finite public read-only sample with
  immutable envelopes, fixed selection, exact amounts, state heights, block hashes
  and acquisition times. The one preserved sample has market/position/oracle
  heights **26210230 / 26210231 / 26210229**. Incoherent state and unverified REST
  accrual semantics block liquidation and profit classification.
- Temporal validation now requires completion of all data, including headers,
  before a candidate event. A stricter check prevents retrospective header reads
  from supplying an earlier claimed availability time. Complete saved data arrived
  at **2026-10-17T05:38:26.670478Z**. This does not prove opportunity or capture.
- A frozen 95-second follow-up in that market returned zero indexer records.
  Coverage/lag is unknown; this is neither absence proof nor a frequency estimate.
- A newly tried official public BlockPI endpoint returned HTTP 403/error 1010
  on its first header request. Raw evidence is retained; the remaining planned
  calls were not made and there was no retry or bypass.
- `case_b_route_audit.cost_frontier` retains the observed conversion, 745509 gas
  units and full **0.368092735714237547 ETH** coinbase payment. Strict positivity
  before unknown costs requires effective gas price at most **2.481140052 gwei**.
  At 3 gwei the residual is **-0.000386814760229962 ETH-equivalent**. The observed
  0.001651296044494913 residual remains an upper bound, not certified profit.
  Pre-existing **0.006392502690919791 WETH** is excluded from new income.

Details: `PROSPECTIVE_OBSERVATION.md`, `CASE_B_PRESTATE.md`,
`PROFITABILITY_RESULTS.md`, `MONTHLY_POTENTIAL.md`, `PUBLIC_DATA_PROGRESS.md`.
The 143-event / 141-transaction historical census is unchanged. Authentic positive
NQC replays and economically admitted operations remain **0**. Monthly capacity
is **not estimable**; target tables are requirements under explicit hypothetical
margins. Titan/Quasar acceptance, builder income and owner-zero-ETH funding remain
unproved. No transaction, signature, public deployment or spending occurred.

Next decisive test: authenticated B parent account/code/storage, applicable block
transitions and execution of transaction 0, then original Morpho/Fluid receipt
parity at transaction 1. For prospective work, obtain one coherent pinned state
with verified accrual and real Fluid liquidity before its subsequent event.
Only then compare both NQC routes from identical state with total deployment,
gas and evidenced financing costs. Missing historical state and executable DEX
liquidity remain the primary engineering blocker; capture and financing are
separate economic gates. Do not turn the new read-only collector into a daemon.

The sections below preserve prior checkpoints and their historical test totals.

## New continuation: authenticated transaction ordering

Starting head independently checked: `55e83bcb85d1e8f13e16d359f9954e611e4b1560`.
`historical_order_audit.py` now reconstructs B's 602-transaction trie and matches
the pinned header's transactionsRoot. Four new adversarial checks pass; full
Python suite after workspace recovery: **163 passed**, isolation **9 passed**.
See `CASE_B_PRESTATE.md` and `evidence/2026-10-17-prospective-recovered/`.
The earlier statement below that no transaction trie was verified is superseded
for B only. Prefix effects, receipt trie, consensus finality and prestate remain
unverified. Economic admissions remain zero; monthly capacity is not estimable.

An execution-environment disconnect erased the temporary checkout and new raw
prospective responses. GitHub was intact; code was restored and revalidated.
Pre-disconnect baseline 159/50/9 was executed, but its lost raw logs are not
represented as preserved evidence. Do not backfill the missing response files
from narrative observations. Continue with newly timestamped bounded observations.
The following sections retain the previous published checkpoints.

## Scope and commit identity

Branch: `research/morpho-sponsored-gas-20261016` only.
Starting commit: `37ee15bb48a7a002a60e473e56c2ee7b90b2f299`.
Published baseline independently checked and reproduced: `a96be36b2540dafe257d384c17333468c62201a6`
(tree `55a2a65b4e52be073071dd02c40e5ffc834a6c04`). Prior checkpoint: `fd9c1ff`.
Published economic continuation: `31cb31e58e223c2b1769bf38be1f2a59afe598b3`,
tree `a4665af1cb0b3d2b71449702351fc28c2e89ab00`, byte-identical to local
`8feaef29dca4c72ccfb8cec905a1354d241909c3`.
Published historical continuation independently checked this session:
`1e21bbc40ac87f89f89a0eb9d277124103db589c`, tree
`42e3e54c52f66e794add1b2fa4f8f1b3109b8fe7`. Both reported commits exist on
GitHub; the authorized branch started this session at `1e21bbc`.
Published monthly evidence: **`c53c341426d668ef324f6f914892294e2a595bd8`**,
tree `2aab7267d2cacfc85975c9e9b7d6cc4f64f43792`, byte-identical to tested local
commit `4cfe503ff4a61ddb973c05097065db40ccac3a64`. GitHub branch read-back and
local fetch verified that identity. This subsequent documentation-only commit
records publication; executable inputs and raw evidence are unchanged.
The current file and subsequent additions belong to the research commit that
contains them; obtain its exact identity with `git rev-parse HEAD` and
`git log -1 -- RESEARCH_STATUS.md`. A file cannot contain its own commit hash.

The two pending corrections were published through the authorized GitHub connector
because local HTTPS Git push lacked authentication. Commit metadata changed;
each published Git tree was verified byte-identical to its local counterpart:

| Local commit | Published commit | Identical tree |
| --- | --- | --- |
| `2d6252a7f98d28909a0eaac0d4a7d7d67971fd2d` | `68fb0f69b417db1ac24f8b9cace7bb51c2ea2165` | `14de60273c0957deda2e38013bc78d082efef2f3` |
| `8db6099eecaa010a08e86feddb69e641fdbb0d69` | `b29db31c0268869e6e97c7bb16423809fe817dff` | `34f9b38b210710e4177b481ec0f39eb7b6534b3d` |

All changes stay under `migration/experiments/morpho-sponsored-gas/`.
`main` observed at `16e352225ba8a6a931834c4edf3d86d9a2924b7d`; no write to main,
other owner projects, original sources/certificates or workflow configuration.
No signatures, broadcasts, real deployments, transfers, subscriptions or spending.
Contract creation in tests occurs only in the local EVM test process.

## Latest executed verification

Checkpoints **132/39** and **136/41** were local results; the latter was
re-executed at `fd9c1ff` before this continuation. New tests replace fixed-price
swap assumptions with original Uniswap V2 behavior and verify observed accounting.
The `a96be36` baseline was reproduced as 141 Python / 48 Solidity / 9 isolation.
The exact-profitability continuation adds six Python checks and two Solidity
functions that test the economic threshold and compare identical-state calls.
The historical RPC follow-up adds three focused integrity checks.
The monthly-evidence continuation reproduced **150 Python / 50 Solidity / 9
isolation** from `1e21bbc`, then added nine targeted evidence checks. Current result:

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Experimental Python | **159** | 0 | 0 |
| Default Solidity: 29 executor tests + 4 parity tests | **33** | 0 | 0 |
| Original-source Solidity: 4 Morpho + 4 Bundler + 9 liquidity-boundary tests | **17** | 0 | 0 |
| Solidity total | **50** | 0 | 0 |
| Repository isolation regressions | **9** | 0 | 0 |

The Solidity totals count test functions, not fuzz iterations or vectors. One
balance-invariant test runs 256 deterministic fuzz cases. Parity compares 65
liquidation and 65 interest vectors plus nested ABI/callback encoding.
Latest run: `evidence/2026-10-17-monthly/validation-run.json`, with exact commands,
exit codes and input hashes. All 50 Solidity tests were re-executed this session;
`baseline-solidity.log` records 33 and `baseline-core.log` records 17 passes.
No Solidity source changed in the monthly continuation. The full 159-test Python
suite and 9 isolation tests passed. Previous Python/isolation run:
`evidence/2026-10-17-profitability/historical-validation-run.json`.
Economic validation: `evidence/2026-10-17-profitability/validation-run.json`.
Logs and both checksum manifests (`HISTORICAL_SHA256SUMS`, `SHA256SUMS`) are in
that evidence directory. Previous evidence remains unchanged under `evidence/2026-10-17/`.
Previous continuation evidence also remains unchanged.
Local checks do not imply a remote CI run. Legacy workflows remain disabled.

Environment: Linux x86_64, Python 3.12.14, PyCryptodome 3.23.0, Forge 1.7.1
(commit `4072e48705af9d93e3c0f6e29e93b5e9a40caed8`). NQC uses solc
0.8.24, Cancun, optimizer 200, no via-IR. Original Morpho is built with solc
0.8.19/Paris/optimizer 200; Bundler3 and adapter with 0.8.28/Cancun/via-IR/999999.
The original Uniswap V2 pair uses 0.5.16/Istanbul/999999 optimizer runs.
Binary hashes and complete free setup commands: `toolchain.json`, `REPRODUCE.md`.

Core commands, from this directory with the toolchain installed as documented:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/nqc-python/bin/python -m unittest discover -v -s tests -p 'test_*.py'
/tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 -vv
FOUNDRY_PROFILE=core /tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 --match-path 'tests-core/*.t.sol' -vv
/tmp/nqc-python/bin/python generate_parity_fixtures.py --check
/tmp/nqc-python/bin/python historical_trace_audit.py
# Last command deliberately exits 2: reconciled observation, not certified replay.
```

Build original-source artifacts before the core suite, following REPRODUCE.md.
From repository root also run `python3 migration/verify_isolation.py` and the
nine `migration/test_isolation.py` tests. No Rust code changed; Rust tests were
not executed in this session. Original Git objects were unavailable, so isolation
reports `original_objects_checked=false`; no historical recertification claimed.

## Corrected errors and negative test history

- Actual baseline: 91 Python tests, 75 passed / 16 errors because OpenSSL lacked
  Keccak-256. Shared hash-pinned `evm_hash.py` resolves this; no SHA3 substitution.
- Actual Solidity baseline: solc 0.8.24 failed with Stack too deep; 0 tests ran.
  Extracting event emission fixed compilation without changing optimizer/via-IR.
- Three newly introduced adversarial tests failed before fixes: inconsistent
  returned seizure, incomplete debt collection and short operator token receipt.
  NQC now reconciles exact observed amounts. These are NQC guard corrections,
  not claimed vulnerabilities in the original Morpho protocol.
- Further guards cover callback caller/data/state, duplicate callbacks, repayment,
  prior token/native balances, false approvals, insufficient/misreported swaps,
  failed native payments, operator reentry and complete revert behavior.
- Strict hex/ABI integers, pinned market identity and trace provenance checks
  reject malformed or substituted observations. Supplied evidence remains untrusted
  without independent authentication; booleans do not certify chain truth.
- New RPC parsing initially failed on a null receipt despite HTTP 200. The
  verifier now records unavailable receipts explicitly; the failure log and raw
  responses remain intact. No historical receipt was invented.
- New Fluid route decoder initially assumed `swapInWithCallback`; the selector
  check failed. It is actually `swapIn` (`0x2668dfaa`), with a separate Morpho
  callback. `evidence/2026-10-17-monthly/route-selector-failure.log` preserves the
  failed run. Source ABI, call return and raw Swap/LogOperate events now agree.
- Baseline/pre-fix failures are retained in evidence logs. They are not hidden by
  the latest successful run. Blocking model/audit exits 2 are expected, not passes
  authorizing trading.

## Functional components and economic findings

- Exact supplied-input liquidation and interest model, with Python/Solidity parity.
  The interest model does not reconstruct historical adaptive IRM storage itself.
- NQC executor compiles and settles locally against original Morpho source.
- Original Bundler3/adapter/Morpho call sequence settles a synthetic flash-funded
  liquidation; wrong callback hash and insufficient conversion roll back.
- Both local routes start the operator without ETH or loan tokens. The harness
  supplies artificial external market/DEX liquidity and does not prove EOA gas
  funding. B now has local original-pair conversion and synthetic native payments; historical
  DEX state and authenticated sponsor settlement remain unproved.
- New liquidity comparison: A's callback works with zero Morpho debt-token cash;
  B's flash route fails in that state. External DEX liquidity remains essential.
- Per-asset economic ledger separates liquidation payment, flash principal,
  conversion, sponsor advance/return, coinbase and proposer costs. All economics
  are theoretical unless independently backed by execution evidence.
- Case B trace arithmetic reconciles exactly. **368092735714237547 wei**
  (~0.36809 ETH) was withdrawn and entirely sent to `block.coinbase`.
  It was not retained profit and is not automatically builder income.
- The external executor already held **6392502690919791 WETH units**
  (0.006392502690919791 WETH). This case does not demonstrate zero initial funds.
  Its inferred incremental WETH is 1849712239770038 units; subtracting sender gas
  gives 1651296044494913 wei-equivalent arithmetically, not certified consolidated
  profit, and never NQC P&L.

Exact economic limits and architecture gas comparison: `PROFITABILITY_RESULTS.md`.
New public data, byte verification and remaining replay gaps: `PUBLIC_DATA_PROGRESS.md`.
Detailed baseline: `RESEARCH_FINDINGS.md`. New controlled experiments, EVM traces,
fee/impact accounting and provider findings: `LIQUIDITY_BOUNDARY_RESULTS.md`.

New results: original pair confirms A settles with no Morpho loan cash while B
needs all 8 WETH (one wei less reverts). Small pools block both routes. The old
0.5 ETH allocation is not covered at the oracle-aligned pool price. An earlier
swap invalidates both plans; donated route balances stay untouched. Python
reconciles 21 EVM scenario rows. Historical audit now cross-checks normalized
token movements against direct token calls, retaining unknown balances as null.
The original 0.5 ETH allocation is impossible at any pool depth at this fixture
price: the fee-adjusted infinite-depth surplus is less than
0.3256784968684759857064 WETH. Both routes cross the exact 8.11 WETH output
boundary in the EVM, one wei apart. At equal Morpho cash and pool reserves,
local gross call gas is 516339 for A versus 400205 for B; it excludes intrinsic
gas, refunds, deployment and funding and is not a production estimate. The 0.1
native allocation includes 0.01 returned to the operator, not an external expense.
New fixture serialization initially failed because of a trailing newline; the
corrected generator and actual passing trace are preserved with the failed trace.
Economically admitted authentic operations remain **0**.
**No NQC realized gains are certified. Neither $0 architecture is yet economically
validated. No Titan/Quasar sponsorship of NQC has been demonstrated.**

## Monthly-evidence continuation

See `MONTHLY_POTENTIAL.md` for the full economic ledger, sample criteria,
architecture/funding comparison and exact target requirements.

- New `case_b_route_audit.py`: official pinned Fluid deployment/ABI identifies
  the actual ezETH/native-ETH route. Swap and signed Liquidity events agree with
  the original trace. Four observed storage reads now have semantic slot names,
  but are not an authenticated pretransaction witness. Revenue-cut/precision
  accounting is distinguished from total swap fees; no V2 reserves are fabricated.
- B sale minus debt is **369942447954007585 wei**. Subtracting the entire observed
  coinbase payment and sender gas leaves an upper bound of **1651296044494913
  wei-equivalent before unknown obligations**, excluding old WETH. This is not
  consolidated certified profit or a counterfactual NQC quote.
- New `monthly_census.py`: frozen UTC windows [September 17, October 17) and
  [October 10, October 17) contain **143 events / 141 transactions** and **29 /
  28**, respectively. Forward/reverse cursor pagination and a separate 7-day
  query match. Chain-wide completeness is not proved. 43 events report bad debt;
  no winners or negative records were filtered away.
- A new `eth_getLogs` known-positive control omits B's event despite its saved
  receipt. The source cannot certify a complete census. A predefined diagnostic
  sample has 23 transactions: B receipt available, **22 new null receipts**.
  The collector is read-only, bounded, cached and stops on access/errors.
- Realized NQC gains: 0 certified. Authentic NQC positive replays: 0. Monthly
  expectation: **not estimable**. Conditional target tables use explicit margins
  and exact ceiling arithmetic; no win probability or production cost is invented.
- Baseline 150/50/9 reproduced, final **159/50/9** passed. New targeted checks
  reject incomplete/duplicate pages, changed amounts, floating-point integers,
  wrong receipt membership and altered Fluid events. No Solidity change or
  additional deployment infrastructure was needed for this evidence task.

## Pending, blocked and unexecuted

1. Authentic historical replay: A/B full blocks and B parent header now available
   from public Flashbots RPC. Header hashes verified locally; state contents under
   the roots and prefix execution remain unavailable. B prefix hash is identified
   in the full block, but its receipt is null. A requires 226 prior transactions.
   B's transaction trie is now verified against its pinned header; this is not
   consensus finality, receipt-trie validation or state execution. B's receipt
   independently corroborates gas and five token/wrap events.
2. Public RPC access: original archive probe failed; continuation basic reads
   returned PublicNode HTTP 403 and Llama HTTP 405; new 1RPC/dRPC reads returned
   HTTP 405/403. Etherscan retrieval also failed. dRPC trace methods are documented
   as paid-only and were not attempted. This is an access blocker,
   not evidence that a historical state cannot exist. Free indexer quota exhausted.
   New Flashbots reads work for blocks/B receipt, but parent code returns
   `state at block #26190955 is pruned`; prestate tracing returns HTTP 403
   `rpc method is not whitelisted`. A, B-prefix and C receipts return null.
   MEV Blocker access denied; no bypass/retry. Morpho public API confirms B
   immutable parameters but supplies no authenticated historical state here.
3. Historical runtime/immutables: source snapshots and partially verified explorer
   metadata agree, but actual code identity at the chosen prestate is unproved.
4. Real DEX prices/reserves, actual flash capacity, adaptive IRM/oracle storage,
   historical fork rules and complete external token/native ledgers are missing.
5. Builder funding address/receipts, advance policy, creation support, top-up cost,
   proposer settlement, failure liability, inclusion and competition unproved.
6. No production swap adapter, audited deployed route, authentic fork gas estimate
   or empirically grounded capture/failure probability. Bundler3 is deprecated.
7. Fixed-day API selection (no profit filters) returned B and an additional
   0.513394-USDT liquidation C. Both consolidated results remain undetermined.
   A bounded recent-history selection returned zero records. Population
   completeness and profitable/capture frequency are unknown.
   The new 7/30-day census expands the observed sample but does not solve these
   economic gates. Unknown margin/capture/financing is not a zero-cost assumption.
8. No Reth/Geth archive provisioned; no paid infrastructure. Remote CI not run;
   Rust tests and original source object verification not run (scope/tool limits).

## Next objective and approval criteria

Prioritize case B because its prefix has one transaction. Use the read-only
`fixtures/case_b_replay_requests.json` with an accessible authorized archive node.
No request signs, sends or funds a transaction. Full A/B headers/transactions
and B receipt are saved; the next missing input is authenticated historical
code/storage and prefix replay. Preserve null/error responses. Do not refetch
blocked methods or treat available post-block roots as intermediate state.
A prestate trace covers only touched slots and is not a proof or a sufficient
witness for every counterfactual route.

Files: `historical_trace_audit.py`, `historical_prestate_probe.py`,
`tests-core/`, `contracts/NqcMorphoSponsoredLiquidation.sol`, `bundle_gate.py`,
`economic_ledger.py`, `profitability_boundary.py`, `historical_rpc_audit.py`,
`PROFITABILITY_RESULTS.md`, `PUBLIC_DATA_PROGRESS.md`.
New evidence files: `case_b_route_audit.py`, `monthly_census.py`,
`collect_census_receipts.py`, `fixtures/fluid_case_b_reference.json`,
`MONTHLY_POTENTIAL.md`, `evidence/2026-10-17-monthly/`.

Required experiments: reproduce the original at its exact pretransaction state;
compare both alternatives from a restored identical state using actual DEX code
and liquidity; reconcile all balance changes and complete financing separately.
Pass only with original receipt/state parity, no future information or silent
state fabrication, full repayment, preserved prior balances, measured gas and
positive residual after evidenced sponsor/proposer costs. A local simulation
still does not prove builder acceptance or market capture. Missing evidence stays
pending; an observed revert is recorded with its exact cause. Do not spend funds
or request signatures to clear these research gates.
