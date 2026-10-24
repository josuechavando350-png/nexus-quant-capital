# H22 - historical execution fee observations

Predecessor: H21 closure `0aaa9a51e125e29567602d2e8d09921271cfc944`.
The initial local checkpoint and subsequent exact-producer closure are recorded
separately below. H21 remote results do not certify this increment. H22's own
remote execution and independent post-audit now pass.

## New evidence

Six Blockscout tool responses supply three transaction/block pairs, reconciled
against the existing dRPC gas fields and historical block identities. Three of
nine WETH rows now have an observed execution-fee split. All three have zero
priority fee and positive base-fee burn. The aggregate observed execution fee is
`759296632646672` wei, all burned. Direct builder transfers remain unknown.

| Historical WETH rank | Block | Gas used | Execution fee / burn (wei) | Priority fee (wei) |
|---|---:|---:|---:|---:|
| 1 | 25938048 | 331267 | 19694395579376 | 0 |
| 2 | 26024990 | 1230724 | 523017715007964 | 0 |
| 3 | 26071849 | 1490601 | 216584522059332 | 0 |

Capture SHA256: `9d6bdcc2f3a91cb8aced6d64e19938925c497bf59fc92cf1eb402301d7ccd8b8`.
Report commitment: `83698a3891ba2687a42820344b886baa23761134c78339bbcae613b2d7ebfaf0`.
The report records the source representation, acquisition failure and exact
limits of the join. SHA pins preserve reviewed bytes; they are not cryptographic
proofs of chain state. See `INCLUSION_FEE_CONTRACT.md`.

## Initial fee-reader verification record

The 24 new tests pass. They exercise positive-priority arithmetic (the authentic
sample has zero priority), integer precision, invalid inputs, cross-source
disagreement, hash/index drift, forged payment/profit claims, offline replay,
seventh-batch ancestry, restore and transitive revocation.

Final full local regression: **613/613 unique Omega tests pass**, 24 new over
H21, with zero failures, errors, skips or expected failures (248.611 seconds).
Both original D15B/D16 archives were downloaded through the connected GitHub
reader and matched their existing SHA256 pins; no substitute fixtures were used
for the real-archive tests. The isolated 38-case CI-capture recheck also passes;
those repeated executions are not added to the unique test count.

Isolation passes with **164 reviewed Omega files**, 531 preserved original
source files, 106 disabled historical workflows and unchanged active workflow
bytes/permissions. Original source Git objects were not supplied to this local
isolation check; its `original_objects_checked=false` remains explicit. Rust and
Solidity implementations are unchanged and were not rerun. No remote forks,
disconnected worker execution or exact-producer CI is claimed for H22.

An independent stdlib-only audit (no Omega imports) reopens the original receipt
ZIP and the capture, recomputes all three gas splits, checks hash/number/index
joins and preserves every unknown builder-payment field. It passes.

| Local result | SHA256 |
|---|---|
| Full regression JSON | `3932a205d6ecec1f4474f8033275cc51377576b65a36e9680e4d697db6f49794` |
| Isolation JSON | `315faaa32eff0ed6b3db2a31b7fd1c5a8bb099f77051a748ad33f488bd5076ab` |
| Independent arithmetic JSON | `207603e905cf64c4c95d22563816640782b010cf3c7eb1a380a60a19abf56103` |
| New reader source | `8ffe1b237c9f3957b5276e9fd78b6445af30f638be8c6a690db8ef1b2c9cf5ff` |
| New test source | `7d8cbe330c416439a8327fb84808fe1eafb2630509596957ba2d20f2b7ba72ff` |

The local result files were produced in scratch; these digests record this run
and do not claim durable CI artifacts. Reader, tests, raw structured capture and
deterministic report are retained with this source change. Reproduction commands
are in the contract and the repository README.

The preliminary inherited 589-case run reported 587 passes and two errors:
the filtered Git clone lacked the historical workflow blob used by the retained
CI-capture tests. That run is not a passing baseline. The exact historical blob
is recovered before final regression; no historical source or test is weakened.
A first reader invocation rejected the capture timestamp's `+00:00` formatting;
the same recorded instant was normalized to the existing UTC `Z` contract before
pinning the final bytes and running tests.

Desktop Commander monthly usage is exhausted; no server access was obtained.
Blockscout internal transfers were unavailable (oversized response, then REST
session denial). The capture records these failures. No full transfer accounting,
complete paid-cost row, executable candidate, Titan coverage or new deployment
is asserted. Census remains open and certified components remain 0/36.

Next evidence target: retain complete internal value-transfer pages or raw traces
for these exact transactions, validate successful ancestry and native balance
effects, then attribute direct fee-recipient/bundle payments without double
counting execution gas. Zero priority fees alone cannot close that gate.

## Runtime v5 continuation

The user's Titan-only instruction is now also bound directly into H22's
disconnected-worker record. The active policy and historical capture/report bytes
are unchanged. Seven dependent batches are rebuilt, revoked from their root and
restored; all remain blocked while forensic bytes match. The packet consumer
requires matching network namespaces and the exact H21 economics commitment and
gas policy. It rejects a substituted payer, positive operator allowance, prefund,
own-gas fallback or invented execution-specific Titan coverage.

Targeted local checks: 30/30 inclusion tests and 22/22 runtime-packet tests pass.
These include six new worker cases and three new v5 packet cases. A freshly
retrieved authentic H21 v4 replay artifact (ID 12535070907, original ZIP SHA256
`59a2c1930a50ddd8a046ac60c41cab5d06097a6700e0b68bdd71372f8e059599`)
passes the new reader with its 43 records and old scope, without an H22 claim.
Compatibility result SHA256:
`00fad9dae099cfd957964b30507a765e1f56072622031c092c9aa9aba9acd8ae`.

Final full local regression: **622/622 unique tests pass**, with zero failures,
errors, skips or expected failures (399.422 seconds). Nine cases are new in this
continuation, 33 over H21. Full result SHA256:
`f0d591cae84b7d4256deb57476b031405187ecc1c85d716810e3eaefa3a2b367`.
Final isolation passes with the same 164/531/106 file counts and unchanged
workflow; its result SHA256 remains
`315faaa32eff0ed6b3db2a31b7fd1c5a8bb099f77051a748ad33f488bd5076ab`.
Original Git objects remain unchecked locally and must be checked in the remote
jobs. Remote exact-producer execution is pending at this pre-publication
checkpoint. No workflow, permissions, provider, Rust or Solidity source is changed.
The older source digests above identify the initial fee-reader checkpoint, not
these subsequently extended reader/test files.

Additional read-only research could not retrieve the exact historical transaction
through the public Etherscan page or either web search engine. No trace or payment
observation was added. Titan's official Sponsored Bundles documentation was
rechecked; its conditional sponsorship is not execution-specific coverage.

## Final exact-producer outcome

Run **40046132439**, attempt 1, producer
`811c549b3561dcdd0719993a2a12852068f5920b`, tree
`f3467c329333eb7397f6539cd1f0973be1c95868`, completed successfully at
2026-10-24T01:12:57Z. Both jobs and every step passed. Closure changes after this
producer are Markdown only; no later code is certified by this run.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120728173838 | 12541940779 | `a8eead11fef81761892836eb2c5b05533f5d3d7fa856832108e8c0eaae21d19b` | `42754c80aac6ca52d5c9ebd8093bd4a39e9ea8a8a598b23cb4ee7ae8947a4949` |
| replay | 120728174039 | 12542770356 | `5a0641ebafb2839a8905bf43d19d2e43d714eb80b4da4775f3d6637f9867c63d` | `d76de90e01b475d01daba60d653543b5657ee8f2b27d1aebebd04f4059755802` |

Independent GitHub API readback, downloaded artifact bytes and decoded full logs
agree on the exact commit/tree, workflow, run/attempt and every evidence record:
43 for forks and 44 for replay. Each job passes 201 intake, 43 runner, 38 capture,
33 store, 10 pipeline and 22 runtime-packet tests: 347 executions per job, not
additional unique tests. All selected test-source hashes match the producer.
Physical checks pass 56 PFT Rust, 528 Census Rust, 14 offline Solidity tests, four
historical fork executions and 16 verified disconnected replay steps.

Both remote isolation checks validate the original Git objects before and after
execution: 531 original files, 106 disabled legacy workflows, 164 reviewed Omega
files and unchanged active workflow bytes/permissions. Historical source/store
roots remain unchanged. The H19/H20 Rust probes retain their own scopes.

H22's inclusion report is reconstructed inside the physical disconnected worker,
with only loopback and a different network namespace from its parent. Seven
batches remain blocked after root revocation and SQLite restore; forensic bytes
match. The worker's emitted report exactly matches the v5 artifact. Independent
integer calculations confirm the three observed fee splits, without turning zero
priority fees into zero direct builder payments or complete costs.

The exact active gas policy remains Titan-only: zero operator allowance, no
prefund and no own-gas fallback. Its hash is
`e2c0b1ea247597de667d093385990880a31519b594f68cae31618ba425f87540`.
No Titan submission, coverage receipt, signing, broadcast, deployment or funded
wallet is added. The new seventh batch does not claim physical Rust transport.

- Forks post-audit commitment: `15dc12e73958090bb17c8074ad539115560848ce0f895672862500f268ca865f`; log SHA256: `84b0a3308a03fb65c3aef2f711734894e7ea2decc1194a4aca850adc2f8181dc`.
- Replay post-audit commitment: `bf4f3ea881357774446f90d8007d03c4bb0ee8e8a95ef7e8c567fd76b0e91b52`; log SHA256: `9916a7de29b7d2976d63e58815edb8a8287fdba902a2d8e615bec917f45d028f`.
- Inclusion replay commitment: `f48c72b8269bf0b6d7ab4e72c2c389f0b344ea3319b54399f4121301557d826c`.

H22 engineering closure: **4/4 (100% of this increment)**, with **622/622** local
unique Omega tests and 33 new cases over H21. Product certification remains 0/36,
Census 0/9, complete paid-cost rows 0/127 and Titan-covered executions zero.
Separate subsequent H23 research observes one direct fee-recipient transfer; it
does not rewrite this frozen H22 report or inherit H22's remote validation.
