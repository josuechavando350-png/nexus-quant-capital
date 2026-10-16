# Two-source registry recovery, registered before any real RPC

Base PR21 `276883828ef921c4f3b55b3dd5ea395615222c73`. This protocol is new. PR21's stopped capture and every earlier protocol remain immutable. Study selection is solely the saved contiguous Borrow history; no health, liquidation outcomes or profitable accounts select membership.

## Capacity change

`capacity_registry.py` is a fresh copy of PR12 registry.py. Its sole behavioral change separates explicit cumulative `max_registry_event_blocks=256` from unchanged per-segment/response `max_event_blocks=128`. The cumulative parameter must be an integer between the segment limit and 256. Both log limits remain 512; both borrower limits remain 64. No trimming, promotion of a partial cohort, or increase after a stop. Transport body, lens gas, time and method caps are unchanged.

`tail.py` copies the PR12 updater verbatim with only its registry binding changed. `merge.py` binds the PR13 pure merge to the new registry. `observe.py` copies PR19's observation block unchanged. Prior modules are neither edited nor monkey-patched. `audit_recovery.py` is a separate PR19 replay copy adapted to both inputs and the recovery journal event; it compares presence and exact bytes of all generated state files and preserves both sources.

## Fixed real inputs

Both paths are under `migration/robinhood-history-extension-20261016T1416/evidence/pilot/`:

- `registry.json`: file SHA256 `915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f`; root `c6b124c940c29d2a876e9d3efdafaf6c678e5654aa1cabcdb2de1309fd4e1a86`. Interval 87846281–90109721; 125 Borrow / 52 accounts.
- `older-registry.json`: file SHA256 `83e307af76b631167350471366ac9d44713a9ecbd21613150bca3411745abceb`; root `1c2ef15961ad7d1d3552afad9eee4aaeb8cabaf54e62b92e9e2c56477f675076`. Interval 87446281–87846280; 20 Borrow / 11 accounts, two previously unseen.

These are historical validated prefixes, not guaranteed current canon. The proposed union has 145 events / 145 event blocks / 54 accounts, and is not a new measurement. Never rescan the older 400000 blocks.

## One sequential execution and exact order

1. Verify dependency versions, the transitive source lock, both file/root hashes, valid prefixes, adjacency and shared boundary equality. Preserve both raw input files. Write baseline principal and older state files in a new output directory.
2. In one persistent session: chain ID; principal checkpoint; oldest start header; shared join boundary; pure merge; principal checkpoint again. Any mismatch/error stops all execution.
3. Save the merged state and `merged-before-catchup.json`, then journal `history_recovered`. Read latest head and anchor at latest minus 64. Update only the contiguous tail starting 90109722; at most 40 segments of 10000 blocks. Revalidate checkpoint and final anchor. Retain prefixes on interruption.
4. Authenticate contract runtimes and market identity at the anchor. Freeze every enrolled account, including zero debt, only after complete target and successful authentication.
5. Three sequential observations, each latest header + fixed lens call pinned to its hash + canonical header verification. Reconcile positions against totalBorrowShares at each hash. Retain repeated heads and slow rounds; reject regression or changed hash at the same height. Keep the same session throughout; no cold rotation or rescue.

Endpoint only `https://docs-demo.robinhood-mainnet.quiknode.pro/`. Global 512 RPC methods / 900 seconds, including preparation and admission waits; no reset at any phase. Minimum 350 ms between local dispatch starts, no burst credit. Global gate and budget are the unchanged PR19 Reader and PR17 Pacer. Preserve TLS verification, proxy/no_proxy/CA, 20-second HTTP wall timeout, 2 MiB reply / 32 MiB total body limits. No redirects, retries, parallel HTTP, alternative provider or session after error. Any denial or other error stops the whole capture; exit 1 is a preserved result, never permission to repeat it. Stop beyond capacity rather than discard accounts.

## Outcomes and timing

Primary `admission_to_verified_ms`: BEFORE waiting for header admission through verified state. Also retain time from local HTTP dispatch, initial wait, inputs, all raw round values, and intervals between header admissions and dispatches. Three requests with 350 ms spacing imply at least 1050 ms sustained dispatch cadence. A single round below 1 s is not sustained subsecond acquisition. This is three coverage observations, not a new transport benchmark or trading cycle. Client socket reuse does not prove backend reuse, quota or SLA.

Report current coverage, missing shares, zero debt accounts, candidates and unhealthy counts only if observed. Attribute added shares using the prior cohort and the new historical/tail cohorts evaluated in the same hashes. If interrupted before observations, these outcomes remain unmeasured. Historical blocks, borrowed amounts and simulation outputs are never income.

No trading, signatures, transactions, real wallet keys, subscriptions, deployments or spending. Own principal available: none. Flash financing availability, gas sponsorship funding, admission conditions and net profitability remain separate unproved requirements. Workflows stay disabled. No Rust/Solidity changes or new runtime APIs.

## Offline acceptance and artifacts

Tests cover cumulative 128/129/256/257, per-segment 129 rejection, cumulative logs 512/513 and accounts 64/65, immutable real inputs, isolated old modules, 35 synthetic interrupted RPC positions, HTTP/JSON/RPC after merge before catch-up, shared budgets, reorgs and tampering. Synthetic traces are artificial and never real source registries. Prior regression and isolation checks run before registration. Registration commit is published before invoking recovery.py. Source lock is never regenerated after capture. Responses, admissions, hash-chained journal, stopped prefixes, exact offline replay and manifests are retained.
