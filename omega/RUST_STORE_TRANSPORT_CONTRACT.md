# H19 artifact-only Rust transport

Omega exports its fully audited SQLite snapshot and every immutable payload as
SHA256-named logical artifacts into the preserved `nqc-census-store`. A caller-held
snapshot ID, full inventory and journal head anchor restore. Rust's evidence root
excludes unreferenced artifacts: it cannot replace those external commitments.

The adapter is compiled with Rust 1.98.1 and the unchanged workspace lockfile as
one temporary example in a disposable checkout. No preserved Rust source is
edited. The example is removed before the original replay checks. Both the
adapter and unchanged standalone verifier execute inside the replay's isolated
network namespace. No workflow bytes or permissions change.

The Rust adapter bytes have an explicit SHA256 pin in `rust_store_intake.py`.
The materializer and report verifier reject drift before use. The existing
workflow triggers Python changes but not standalone `.rs` changes: a legitimate
Rust update therefore requires a reviewed Python pin update, which also triggers
the existing workflow. Editing only Rust is never sufficient for admission.

Acceptance requires authentic H18 inputs, exact logical byte/ID conservation,
idempotent object insertion, independent-process Rust reopen/export, exact
SQLite snapshot restore, source-bound temporal query, preserved batch-local
revocation, rejected frame corruption and rejected incomplete transport. The
standalone verifier must expose every artifact as an orphan, with zero streams,
ranges, tips, staging files, orphan chunks or abandoned registrations. Missing
files never become valid merely because the Rust evidence root is unchanged.

Local unit tests with synthetic verifier output are parser/transport tests only.
Physical admission requires the successful exact-producer CI run, retained raw
logs, artifact and independent API capture, followed by a post-audit. Runtime
packet v2 requires the bridge report for replay. Historical v1 packets retain
their original evidence scope and do not acquire a Rust transport claim.

The imported data remains a sparse retrospective sample. This is local transport
and recovery, not remote replication, cross-batch dependency revocation, actual
chain reorg handling or a certified Evidence Vault. An upstream batch can be
revoked while its separately admitted descendant remains active under the old
batch-local policy; the adapter preserves, and does not conceal, that limitation.
No block-range checkpoints are manufactured. Certification remains 0/36.

The CLI is a bounded offline diagnostic for caller-owned directories. It rejects
symlinks, traversal, nonregular files and existing output directories. It is not
a hostile concurrent-filesystem sandbox; concurrent external mutation is outside
this contract. An interrupted Rust import is not atomic publication of a replica:
only successful full verification against external commitments admits it.
