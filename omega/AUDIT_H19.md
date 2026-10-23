# H19 audit — artifact-only Rust transport

Local regression passes **528/528**, including **30 new H19 tests** (27 transport
and 3 runtime-packet cases). Local Rust store tests pass **66/66** without failures
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
