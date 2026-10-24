# H19 audit — artifact-only Rust transport

Local regression passes **532/532**, including **34 new H19 tests** (29 transport,
3 runtime-packet and 2 HTTP-429 retry cases). Earlier local Rust store tests
passed **66/66** without failures
or ignored tests. The new Rust example compiles with toolchain 1.98.1 and the
unchanged lockfile in a disposable copy. Local isolation passes with 143 Omega
files, 531 original files and 106 disabled historical workflows.

The local physical roundtrip imports and independently exports **28 artifacts**,
**3,154,093 logical bytes**. SQLite restore is byte-identical at snapshot level,
the temporal report reconstructs from original sources, revoked reads fail, and
a deliberately corrupted Rust frame fails the original standalone verifier.
The local host cannot create the required namespace (`uid_map: Operation not
permitted`); this local check is explicitly not network-isolated evidence.

Snapshot artifact SHA256:
`bd8ddfc334d10442780ea6cb3002cdab91471c4f4ac2fe766a2548f19c29f37b`.
External journal head:
`97cff86f1beeae6688ce2b7957597573b96f5556ec43bff7842ce1ac7141adb4`.
The standalone verifier reports 125 chunks, 1,186,326 stored bytes, 28 orphan
artifacts, zero orphan chunks and zero ranges/streams. Its root is
`28f637cfdc23156428f73df3e45fe47376aba85f38b8e04bf8ee97b7ed6d2116`;
that root does not bind orphan artifacts and cannot substitute for the complete
external inventory and snapshot commitment.

Two development defects were caught before publication: JSON canonical comparison
cannot compare dictionaries containing raw bytes, and intentional corruption of
a copied immutable Rust frame requires temporarily making only that copy writable.
Both were corrected; original files remain untouched. Source tests and the actual
Rust roundtrip cover the corrected paths. No skipped or failed development run
is presented as a passing execution.

Exact-producer remote physical checks and their artifact/API/log post-audit
PASS; final identities and evidence-retention limits are recorded below. Nine
rejection cases are checked by the remote bridge exercise, along
with original H2 forks and disconnected replay. Runtime packet v2 binds both
adapter sources and requires the new bridge report on replay; v1 compatibility
retains its historical scope. Workflow bytes and permissions remain unchanged.

H18 remains the preceding audited baseline: 498 unique local tests, producer
bd4b120e78603617473f2750bcff367271459375, run 39889427564. Those results are not
inherited as evidence for H19. Certified components remain 0/36.

## Earlier local post-audit (pre-reset evidence)

A standard-library verifier importing no Omega implementation confirms all
SQLite table bytes, all 28 exported logical objects, snapshot/journal bindings,
134 unchanged Rust source files and nine direct Rust process outcomes (one
healthy verifier and eight deliberate rejections). This is still a local check,
not isolated remote execution.

- h19-full-tests-final.json: SHA256 `a74cb0a93ae2fc88e0d1169cc49c19b6f4b8281e42a3a87e0ac434812245d946`.
- h19-isolation.json: SHA256 `31c7e821e300220862c3537450c77864d80ef39834d8bdc40641a2d709b0b3ad`.
- h19-rust-tests.log: SHA256 `9e443211f82c36ba6e90449e7f12a6156c0d46a6bd221f06e71973833f432d5e`.
- h19-independent-local-audit.json: SHA256 `46748d90334da4d7737685cd6932169d5b1426be09f7150fecec7fa71fa49cc3`.

## First remote attempt and bounded RPC correction

Run 39895197550, producer `1f54481ccb763a2fd1a547f84cf9fda654808085`,
failed its forks job 120223904070 before forks because BlastAPI returned HTTP
429 to `eth_chainId`. Mevblocker passed. This is not a successful gate. The
full failed log is retained; the concurrent replay retains its own outcome.

The read-only preflight now retries HTTP 429 up to four total attempts, waiting
2, 4 and 8 seconds. Persistent rate limits still fail; other errors retain their
original behavior. No provider, credentials, workflow or permission changes.
Two regression cases verify identical-request retries and terminal failure.
The retry-fix suite passed 530/530 at that intermediate revision. The final
producer subsequently passed both remote stages and their post-audits below.

- h19-full-tests-retry-fix.json: SHA256 `642c90ebd95a68483eebd97dfbd510c8d6f8d8c5a643f5dced10277e460f929e`.
- h19-rpc-retry-tests.json: SHA256 `e06e5a4e1c6fad7ce7eb47ae392edb9578026be035a7528e14078875b6bef64e`.
- h19-first-forks-failed.log: SHA256 `49e94d3b57b32a3f834877e99a4f7455b81dcb9c90edae932910f11569103ce1`.

## Rust source pin review

The unchanged workflow triggers Python but not standalone Rust edits. The
adapter now binds its Rust source to explicit SHA256
`6befee0d4e6d3ab1a2e778a1654ceb6682514fb83447134e10cc57afd375de39`.
Compilation materialization and report validation reject drift. A legitimate
Rust revision must update the reviewed Python pin, triggering the existing CI.
The added rejection test brings the unique local suite to 531/531 (33 new).

- h19-full-tests-source-pin.json: SHA256 `fd8952bfc82ae5c063877bb42bfb3327da1fd0905f7bec8ca11eb4371c1fd66a`.

## Final remote outcome

Run **39897180333**, producer `fcbe6cac8c69c58b55d4ccf67c399dd359db6a96`, tree
`ef536fa4a73e62d2832c131861ea3199cee0c36e`, completed successfully at
2026-10-23T04:16:23Z. The closure commit changes Markdown only.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120230541728 | 12477456500 | `3c5c408633378c4cc9192024935385cc40932b98e6572aaf2135b96f0fcd815c` | `1a80b0b7fe12787a1e3d72f6b04ecf51d45f0816fe499700d7e71c583e01f525` |
| replay | 120230542161 | 12478162352 | `f377d635f29d5369d9ed926ca4907c06e81e58b083368bbd187cecc8667f2935` | `05abf0d40d3558e327e39a735fc6548090e1d85d27ec80983cd539391f5cac11` |

Both jobs and all steps succeed. The post-audit binds 43 fork records and 41
replay records to complete raw logs and freshly captured GitHub metadata.
Selected test-source digests match the producer. Each job runs 137 intake,
43 runner, 38 capture, 16 evidence-store, 10 pipeline and 15 artifact tests
(259 selected Python tests per job, not additional unique cases).

Physical checks pass: 56 PFT Rust, 528 Census Rust, 14 Solidity unit tests,
4 historical fork executions and 16 verified disconnected replay steps. Original
source/store roots remain identical. The added Rust bridge executes in the same
disconnected namespace. Its three positive process results, eight expected
rejections and missing-snapshot rejection match the raw log. Standalone verifier
stdout hashes match all retained numeric fields. No failed or ignored Rust tests
are accepted. The 66 earlier local Rust store tests are a subset of that complete
528-test remote Census suite, not an additional certification count.

The bridge transports 28 artifacts containing 3,154,093 logical bytes. They remain
explicit orphan artifacts with zero streams/ranges. Snapshot inventory, source
evidence, the temporal report and batch-local revocation survive exact restore.
Recovery still requires the external inventory, snapshot ID and journal head;
the Rust evidence root alone does not bind orphan artifacts. This proves local
Python/Rust transport inside a disconnected runner. Remote replica recovery,
cross-batch dependency revocation and real canonical chain reorgs remain open.

- forks post-audit commitment: `2a2e3f2df1fdf7b49e4e82c37b95e2ffeea8f3307a767463080913416b77babe`; raw log SHA256: `92a810dd90dcf5fa39273c54b89f12bc75563245959dd3cfe7447a5ab77b2a27`.
- replay post-audit commitment: `20a8faf4eae5c38bc0f5da56ad7965b01a2423a65f31e2b1f8a9b60665b492ae`; raw log SHA256: `69f2d9d6e6316473a0c0e4da2fbbbdbbb25a6ab9e7c37d502d7306d2aea7d0e2`.
- Rust transport report commitment: `793caea52ec05c90ddbef4cb890324457c8b74723b3137e3ecac5c9b623dcea1`.

## Recovery and final local verification

The temporary local workspace was reset during the pause. Published source and
GitHub evidence survived. The earlier local report hashes above remain historical
records; their original local files/binaries are not included in the final bundle
and were not reconstructed as if they had survived. Both runtime ZIPs and complete
job logs were fetched again and audited against fresh API captures on 2026-10-23.
An initially incomplete local log transfer failed JSON parsing; a complete copy
replaced that transfer before the replay post-audit passed. Runtime bytes were
never repaired or inferred from the packet.

The first fresh local discovery found all 532 tests but skipped six real-archive
tests because their inputs were absent. That run remains incomplete. Original
D15B and D16 ZIPs were recovered from nexus-engine read-only and matched their
previously pinned SHA256 values. With both explicit input paths, a fresh full
regression passes **532/532**, with no errors, skips or expected failures.
H19 adds 34 unique tests over H18's 498. Repeated runs add no unique cases.

Final regression JSON SHA256: `4a0a8f29cf052102061a3fc4d37a2fe152ba6d6b5459fdaecd7912d177ac2207`.


Final local isolation passes: 143 reviewed Omega files, 531 original source files,
106 disabled historical workflows and the unchanged active workflow SHA256
`8c1c20a8684a21728d7ebd83d0aac7ad93dc5840df34ec455e80e5eb0b3813be`.
Local source Git objects were not supplied; the exact-producer remote isolation
records perform that stronger original-object check.

The final path review resolved parent traversal before source containment checks;
its regression confirms no protected destination is created. The Rust source pin
and four-attempt HTTP-429 backoff are included in the tested producer. Run
39895197550 remains an overall failure even though its replay succeeded. Queued
superseded runs 39895773963 and 39896381296 were cancelled and earn no passing gate.

The retained H14 pipeline's `rust_store_integrated=false` still describes that
earlier Python-only pipeline. H19 transport is a separate v2 runtime record;
earlier report commitments are never rewritten to inherit later scope.

H19 engineering increment: **4/4 closure steps (100%)** — implementation,
local checks, exact-producer remote execution, and final post-audit. This ratio
applies only to H19. Certified product components remain **0/36**, Census **0/9**,
temporal sample coverage **3/9**, and complete paid-cost rows **0/127**.
The requested 45% overall product target is still not demonstrated.
