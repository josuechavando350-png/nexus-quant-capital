# Local evidence store and recovery

`evidence_store.py` implements a bounded local SQLite store with FULL synchronous
transactions. Immutable content-addressed objects and batch inventories are
committed with one hash-linked journal admission. Repeated identical ingestion
is idempotent. Concurrent writers serialize. UPDATE/DELETE triggers and exact
schema verification protect the append-only contract.

Queries verify schema, SQLite integrity, every object digest and length, every
manifest reference, journal sequence/link and admission/revocation consistency.
They fail on corruption or partial inventories. Bounds: 2 MiB per object,
256 objects/batches, 16 MiB total object bytes and 10000 journal events. This is a
bounded historical store, not an unbounded production archive.

Exports include all original evidence, including revoked batches. Restoration
builds a new sibling database, verifies its entire inventory and journal, then
publishes without overwriting an existing destination. An external expected
journal head detects rollback to a previously valid prefix. A self-hash alone
cannot detect an adversary replacing the database and its external checkpoint.

Local revocation excludes a batch from ordinary queries and preserves its bytes.
It never establishes a canonical chain or authenticates a supplied conflict
witness. The controlled revocation test is **not a real chain reorganization**.

`historical_pipeline.py` combines retained-source authentication, ledger
construction, transactional storage, independent local restoration and replay.
Every query rebuilds the ledger from original pinned inputs, so internally
consistent fake economics in a content-addressed store still fail. It verifies
the actual exported snapshot and both retained databases, plus the controlled
revocation copy. The deterministic report is retained at `evidence/h14-pipeline.json`.

Tests terminate separate processes before and after commit, exercise concurrent
writers, corruption, rollback checkpoints, revocation and no-clobber recovery.
They do not establish physical power-loss guarantees, remote replication,
multi-host consensus or integration with the Rust store. All Census and trading
authority remains false. This component still requires those remaining gates.

Threat boundary: use a private local directory on a POSIX filesystem. Symlinks
and sidecars are rejected; protection against an attacker concurrently replacing
parent directories is not claimed. A database checksum is integrity, not origin
authentication. Trusted source pins and separately retained journal heads supply
the relevant trust anchors.


The logical 16-MiB object limit is not a physical SQLite-file quota. SQLite's
integrity scan can inspect a much larger corrupt file before logical payload
bounds reject it. This prototype assumes a private local store directory; a
production service admitting hostile database files still needs an operating
system file-size/I/O budget or an explicit physical file-size admission limit.
This is an outstanding resource-hardening requirement, not a tested capacity claim.
