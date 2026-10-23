# H19 audit — artifact-only Rust transport

Local regression passes **531/531**, including **33 new H19 tests** (28 transport,
3 runtime-packet and 2 HTTP-429 retry cases). Local Rust store tests pass **66/66** without failures
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

Exact-producer remote physical checks and their artifact/API/log post-audit are
pending. Nine rejection cases are required by the remote bridge exercise, along
with original H2 forks and disconnected replay. Runtime packet v2 binds both
adapter sources and requires the new bridge report on replay; v1 compatibility
retains its historical scope. Workflow bytes and permissions remain unchanged.

H18 remains the preceding audited baseline: 498 unique local tests, producer
bd4b120e78603617473f2750bcff367271459375, run 39889427564. Those results are not
inherited as evidence for H19. Certified components remain 0/36.

## Independent local post-audit

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
The final full local suite passes 531/531; exact-producer remote validation is
still required after this correction.

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
