# Full persistent state acquisition — preregistration

Base PR15: `170148bf07920ae0e9112cc7f28507ca6051dd77`. Publish this code,
policy and source lock before any RPC in this experiment. Earlier protocols and
original evidence remain immutable. This is a new bounded research capture,
not live trading, production admission, or an unattended execution engine.

## Selection, tail-only continuation and cold start

Start only from the PR14 registry identified in policy.json: root
`3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de`, through
89,902,197. PR15 did not advance it. No backward scan in this experiment.
Copy the validated source before RPC. Check chain identity and initial boundary,
obtain a latest header and target 64 blocks earlier. Revalidate the old checkpoint
and append only contiguous missing tail segments (at most 40, each at most 10,000
blocks). Preserve raw logs, all accounts and segment links. No ranking by health,
profit, known liquidations or subsequent outcomes. Overflow stops, never trims.

Use the unchanged PR12 index validator/update logic, PR13 single-call lens and
PR15 bounded persistent transport. Every HTTP request is sequential and uses the
same authorized demo endpoint, including indexing/authentication. Recheck the
target canonical header; authenticate fixed protocol runtime and market parameters
at that anchor. Freeze all accumulated accounts only after the target is covered
and authenticated, keeping accounts whose debt later becomes zero. New accounts
cannot be added or dropped during observations.

After successful freeze, close the preparation pool exactly once and open a new
pool lazily for observation 0's header. This deliberate, preregistered boundary
isolates a cold acquisition; it is **not** retry/failover. Preserve the SAME reader,
method counter, accumulated bytes, run start and remaining time budget. No pool
rotation is allowed after a failure or after this one planned transition. Socket
tags are scoped to their pool epoch; do not compare tag 1 across the two epochs.

## Twelve sequential observations

For each round, without deliberate sleep or HTTP parallelism:

1. Request latest header using the observation session. Require height above the
   enrollment anchor. Retain repeated identical heads and flag them; stop on a
   regression or a different header at equal height. Do not retry to get a nicer
   sample. The existing freshness guard allows head timestamp age -5 to 30 seconds.
2. Call the exact fixed lens with the frozen cohort and EIP-1898 hash pin,
   requireCanonical=true, gas cap 2,000,000, no state overrides or transaction send.
   Decode and derive all positions, shares coverage and the prior 100-bps screen.
3. Request that same header number through the same session and compare full
   canonical identity. Mark verification only AFTER comparison succeeds.

Round 0 is planned cold; rounds 1–11 are reuse-eligible, not presumed reused.
Record actual client socket tags/reuse observations for header, view and canonical
check. A server-closed idle connection can cause a new connection before a new
request, but a failed request may never be repeated. One proxy/client socket is
not proof of backend-node connection behavior.

Primary metric: monotonic time from immediately before starting the header
request to successful final canonical comparison. Includes connection setup where
applicable, all three requests, parsing, derivation and intervening evidence
writes. Excludes initial enrollment/authentication, the one deliberate pool close,
and final observation-journal persistence. Report preparation duration separately
from observation acquisition. It is **state acquisition**, not opportunity birth,
route simulation, transaction inclusion or a trading cycle.

Also report header response time, view inputs, request-to-all-inputs, and
received-header-to-verified time. Preserve header timestamp age at receipt of the
final response; chain timestamps are second-granular and local clock agreement is
not independently proven. Do not equate subsecond request duration with subsecond
age of on-chain information. Preserve tail distance from the frozen checkpoint.

## Limits, failure and analysis

One entire execution: at most 512 RPC methods and 900 seconds, not per stage.
The PR15 transport caps each HTTP wall deadline at min(20 s, remaining run time),
body at 2 MiB (+1 overflow-detection byte), successful body total at 32 MiB.
Keep configured proxy/no_proxy and CA, TLS verification, exact dependency versions
and fixed endpoint. No retries (including Retry-After), redirects, concurrent
HTTP, endpoint substitution, credentials extraction, subscriptions or spending.
No new network API is introduced: the exact PR15 implementation and API references
are reused and source-locked. `requirements.txt` remains the PR15 one.

Stop the entire run on any transport, JSON, identity, canonicality, ABI or budget
failure. Preserve negative evidence, available raw prefixes, request ledger and
the exact last saved registry (including invalidation). Do not freeze an incomplete
target. A later observation failure does not manufacture a completed sample.
No replacement capture or outlier deletion. No batch comparison in this protocol.

Report all 12 planned observations and completed count, unique/repeated block
counts, cold round separately and all later rounds together; report min/median/max
and fraction within assumed 1,000 ms. This is descriptive, not a production SLA,
probability estimate or proof of one-second opportunity detection. Reconcile
observed borrowShares to totalBorrowShares per hash and report missing coverage.
Zero candidates is negative evidence for this cohort/time only, not the whole market.
No gas/Nitro/DA cost, bundler admission, financing or realized profit is measured.

Before RPC: synthetic faults at every request boundary; failures before/after
rotation; time/count/byte caps unchanged; resume/anchor/observation reorgs; repeated
heads retained and regressions rejected; exact saved-prefix replay; tampering;
PR15 transport tests and prior regressions/isolation. Auditor replays the exact
registered flow into a temporary output directory and compares persisted registry
and cohort bytes, requests, journal, derived state and timings. This is reproducible
consistency checking, not independent cryptographic attestation of RPC truth.
