# Isolated infrastructure contracts and local Parquet export

## Delivery status

The local v2 collection archive now has verified atomic publication, owner-bound
receipts, crash recovery and explicit quarantine propagation. It uses local
filesystems and the existing Parquet exporter. See `docs/archive.md` and
`docs/AUDIT_ARCHIVE_20261022.md`; this does not validate a remote object store or
a PostgreSQL service. Those operational integrations remain open.

The rolling historical collector is now executable and audited with a bounded
public restart capture. See `docs/collector.md` and
`docs/AUDIT_COLLECTOR_20261022.md`. No persistent collector service is running.
Other server integrations below remain unexecuted.

The Parquet exporter is executable and tested against the actual Rust journal verifier and Polars. The PostgreSQL DDL has now passed a retained synthetic contract test in a new local Termux cluster, which was shut down afterward. A journal import preparer is now offline-tested, with a candidate SQL migration awaiting runtime validation; production integration remains unimplemented. ClickHouse, Redpanda, Temporal and Nix remain prepared contracts without server execution. No external infrastructure or Observer services were used.

Every resource belongs to `nqc_miner_v1`. The namespace is distinct from any existing observer; ownership cannot be adopted by copying a name into an existing state directory. `infra/ownership-contract.json` defines the proposed database/schema/role/topic/workflow/bucket IDs. The bucket is a logical name only: no globally unique cloud bucket has been reserved. Export writes only to a new local directory and has no upload path.

Signing, broadcasting, the observer bridge, Telegram, KMS, spending and runtime deployment remain disabled. The configured gas budget is zero. A contract file is not permission to provision resources or enable any integration.

The returned PostgreSQL 18.6 evidence passed the exact-source runtime audit:
30 SQL checks, three writer denials, schema guards and restart comparison.
See `docs/AUDIT_POSTGRES_TERMUX_20261022.md`. This earns one infrastructure
point (41/100 overall); importer and production gates stay open.

## Contracts

| File | Implemented content | Validation boundary |
|---|---|---|
| `infra/postgres.sql` | Dedicated-database guard, run provenance, append-only journal mirror, registry, gate reports, lifecycle journal and transactional outbox schema | Exact DDL applied to a new PostgreSQL 18.6 Termux cluster under a dedicated owner; 30 SQL checks, writer denials and orderly restart audited. No verified-journal importer or production integration |
| `infra/clickhouse.sql` | Raw delivery ledger, event projections, whole-scope completion, invalidation cutoffs, scoped saturation and coverage views | Parsed with a ClickHouse SQL dialect parser; no server execution or performance validation |
| `infra/redpanda-contract.json` | Three class-specific ledger topics, stable run keys, deduplication/ordering rules, literal-resource ACL intent | JSON and namespace reviewed; no broker/ACL application or producer/consumer integration |
| `infra/temporal-contract.json` | Workflow identity, Rust lifecycle transition mapping, retry/retirement/reactivation rules | JSON and Rust transition mapping reviewed; no SDK worker or Temporal deployment |
| `infra/default.nix` | Official nixpkgs commit pinned to Rust 1.90.0, checked-in Cargo.lock, offline test build target | Official source pin inspected; Nix unavailable, expression evaluation/build unrun |
| `research/export_parquet.py` | Bounded source snapshot, actual Rust verification, lossless Parquet batches, manifest hashes | Actual Rust + Polars roundtrip and rejection tests |
| `schemas/*.schema.json` | JSON Schema 2020-12 structural contracts for owner, journal envelopes and completed exports | Schema definition and generated fixture/manifest validation; Rust remains semantic authority |

### PostgreSQL: immutable facts and transaction boundary

The DDL refuses any database whose name is not exactly `nqc_miner_v1`. It intentionally uses `CREATE SCHEMA` without `IF NOT EXISTS`, so it cannot silently adopt an existing installation. Public schema/table access is revoked. Dedicated runtime role creation, credentials, privileges and connection policies are a future deployment step; a schema name alone is not an access-control boundary.

`runs` binds each run ID to one evidence class, owner hash, configuration hash, source commit and Cargo.lock hash. It preserves original owner/configuration bytes. `journal_ledger` preserves every original JSONL line, line hash, envelope hash and sequence. The importer must run the Rust verifier on the exact immutable segment before any transaction. SQL shape constraints do not establish source authenticity or recompute the Rust ABI/hash-chain rules.

The candidate importer in `infra/postgres_import.sql` is designed to insert ledger rows and outbox rows in one transaction; its runtime validation is still pending (see `docs/postgres-import.md`). A duplicate primary key is accepted only after comparing the existing hashes **and original bytes**; conflicting content quarantines the run. An unconditional `ON CONFLICT DO NOTHING` would conceal corruption and is prohibited. A future consumer commits its broker offset only after durable, idempotent insertion. This provides a recoverable delivery design, not a claim of currently implemented end-to-end exactly-once processing.

The outbox cannot dispatch: `delivery_enabled` must remain false and `delivered_at` must remain null under this schema. No relay is implemented. The registry supports research states through `proposed` plus `retired`; `active` and `watched` require a separately reviewed migration and remain inaccessible here. The Rust lifecycle validates transitions, evidence, expiration and reorgs; a SQL row never substitutes for a gate pass. Retirement can restart at `detected` with a reason, the same mine/chain, and all accepted evidence cleared.

### ClickHouse: retries and invalidations cannot inflate counters

`raw_ledger` retains repeated deliveries for audit. `verified_envelopes` deduplicates logical sequence keys, while `conflicted_runs` excludes a run if a sequence has multiple envelope/raw-line hashes or the run has multiple provenance identities. This view relies on a future verified importer; no existing runtime is currently populating it.

Normalized `event_versions` and `scope_completions` use `ReplacingMergeTree(sequence)`. Every correctness-sensitive query reads these tables with `FINAL`. Background merges are not assumed to have happened. The projector must reject inconsistent projection bytes for the same envelope hash before insertion; source-to-projection fidelity is a required importer integration test, not something a table engine can prove.

`run_publications` is a final publication barrier for an exact verified snapshot. It binds owner, total record count, last sequence, last envelope hash, source journal hash and verifier/report hashes. `published_runs` requires an exact match with the entire currently visible raw ledger, plus all expected observed/scope envelope keys and exact projection counts. A missing projection blocks publication; any new raw sequence invalidates an old publication until the new snapshot is fully verified and projected. Identical redeliveries do not change the logical tip. Invalidations are read directly from verified original JSON bytes, so no separate invalidation projection can lag and hide a reorg.

ClickHouse multi-table inserts are not represented as an atomic database transaction. The future query API must bind reads to a published immutable snapshot, read its verified raw tip before and after the query, and reject a changed tip or publication. It must fence concurrent import/publication operations and test crash/partial-write/concurrent-read cases on a real server. These query and importer services are not implemented here; the prepared views and barrier are not a claim of serializable runtime behavior.

Only an actual `scope_completed` envelope closes a scope. A `chunk_completed` envelope records durable progress but cannot qualify a scope as fully scanned. Finalized event views join each normalized row to its verified raw envelope and a whole-scope completion marker. Repeated invalidations collapse to `min(from_block)` for each run/class/chain. If that cutoff affects any block in a completed scope, its entire coverage claim is excluded. This conservative rule prevents a partially invalidated range from becoming a denominator.

Saturation is a dynamic grouped view using `uniqExactIf` event/transaction identities and explicit normalized liquidator addresses. A liquidation projection requires a nonnull address from its decoded ABI payload; birth records carry no liquidator. Addresses are not asserted to be independent actors or owners. There is no `SummingMergeTree` and no additive insert-trigger aggregation. Redelivery does not increase distinct counts; later invalidations remove affected scopes at query time. Every result keeps run ID, evidence class, chain, scope, contract, topic, protocol and market dimensions. It does not aggregate synthetic, historical and shadow data into a single claim.

Event logs alone do not contain counterfactual eligibility times, competitor tips, realized profit or authoritative whale identities. Delay and tip columns therefore remain nullable, and the classification remains `uncalibrated`. Zero-event completed scopes remain visible in `coverage_ranges`; a missing saturation row cannot be interpreted as a virgin market. The richer Rust analytics require their own measured evidence and calibration.

### Redpanda and Temporal

The three proposed broker topics are `nqc_miner_v1.synthetic.ledger.v1`, `nqc_miner_v1.historical.ledger.v1` and `nqc_miner_v1.shadow.ledger.v1`. All records of a run, including invalidations and completion markers, use the stable key `nqc_miner_v1/{data_class}/{run_id}`. A run cannot migrate partitions midstream; partition-count changes require a reviewed run boundary. Broker retention is seven days with a byte ceiling and is not an archive. Immutable journal/Parquet storage remains the long-term evidence design.

ACL intent grants only literal listed topic and consumer-group resources to dedicated Miner identities; there are no wildcard grants or auto-creation permissions. Three broker replicas and `min.insync.replicas=2` are a production contract, not a claimed local deployment. Broker-version-specific idempotent producer permissions must be tested before granting any cluster-level permission.

Temporal workflow IDs include namespace, class, run and mine. A Temporal Run ID is not a mine identity. The future worker calls the existing Rust gates and journals results, rather than creating a second transition implementation. Transient retries cannot convert failed/unknown evidence into a pass. Retirement clears evidence; explicit reactivation restarts admission. Live activation, spending, signing, broadcasting and automatic approvals have no allowed activity. No SDK implementation, task poller, namespace, timer or background schedule has been deployed.

## Parquet export: actual executable path

Install the pinned research dependencies from `research/requirements.txt` in an isolated environment and compile `nqc-miner` from the same reviewed source. A local invocation is:

```bash
python research/export_parquet.py \
  --state /absolute/path/to/miner-owned-state \
  --output /absolute/path/to/new-miner-export \
  --verifier /absolute/path/to/nqc-miner \
  --batch-rows 5000 \
  --maximum-bytes 67108864 \
  --maximum-records 100000
```

The output parent must already exist. The output directory must not exist and must lie outside the source state directory. Symlink components, foreign namespace/producer, mixed owner/configuration class, duplicate JSON keys and malformed owner values are rejected. The supplied verifier executable is a trusted local dependency: hashing and inspecting its `about` output records its identity but is not binary signature authentication.

The exporter performs these operations:

1. Reads bounded owner/configuration metadata and confirms exclusive Miner ownership and class.
2. Exclusively creates a new output directory and copies the exact owner, configuration and journal bytes into its `source/` subdirectory. Descriptor-based change checks reject a source that changes during copying. It creates no source lock and never edits source files.
3. Invokes the actual `nqc-miner verify-journal --state <private-copy>`. The verifier validates raw/decoded equality, configuration ownership, chain hashes, sequence ordering, chunk reconciliation and scope completion rules. It briefly locks only that private copy.
4. Exports **all** records, including provisional observations, chunk/scope markers and invalidations. It preserves each original line including its newline in a Parquet `Binary` column, alongside SHA-256, run/class/commit/lock/config provenance, envelope sequence/hash and derived event state.
5. Writes batches with exclusive file creation, flushes them, rereads each through Polars and compares exact schema, rows, binary bytes and order. The manifest records both each Parquet file hash and the SHA-256 of its original concatenated raw lines.
6. Rechecks copied source hashes and verifier binary hash. Writes `manifest.json` last, then syncs the directory. Absence of that marker means an incomplete export. A failed export is never overwritten or auto-adopted; choose a new output path after inspecting the failure.

Defaults cap the journal at 64 MiB and 100,000 records. Hard limits are 512 MiB, 1,000,000 records, 10,000 rows per batch and 1 MiB per JSONL line (plus newline). A separate 16 MiB raw-payload ceiling bounds each batch regardless of row count. The Rust verifier may hold the bounded journal in memory; the byte ceiling is an input limit, not a guarantee that process RSS equals journal size. The caller should select a smaller ceiling where memory is constrained.

`event_state` distinguishes `provisional`, `chunk_committed`, `scope_completed` and `invalidated`. A completed export of an empty journal is valid but does not imply a completed scan. `manifest.complete` refers only to export completion. `authenticity_verified` always remains false: local hashes do not authenticate an RPC provider or replace canonical chain proof. No existing journal is relabeled into a different class, and realized profit is not an ingestion class.

The files are immutable by the tool's write policy, not by a filesystem write-protection mechanism. Another process with filesystem privileges could replace them after completion; consumers must validate the manifest hashes against a trusted manifest/checkpoint. This exporter does not provide a signed external trust anchor or remote retention policy.

## Nix pin and reproducibility boundary

`infra/default.nix` pins official NixOS/nixpkgs commit `0b0c249f090b05e3a47dcdd523c54921e5223409`. At that exact commit, `rust = rust_1_90` and the compiler definition specifies Rust 1.90.0. The expression asserts the version and builds from the actual checked-in Cargo.lock. No fabricated `narHash` or unverified flake lock is supplied.

Nix is not installed in the validation environment, so no successful Nix evaluation, derivation, sandboxed build or cross-machine reproducibility result is claimed. The prepared command is `nix-build infra/default.nix` from the crate directory, in a separately reviewed environment.

A source-only Nix build deliberately has no Git checkout. The current `build.rs` then reports an unknown commit and dirty/unknown source provenance, and live read-only scan admission refuses that binary. Offline verification and replay can still work. A scan-capable hermetic release needs a separately reviewed source-attestation mechanism bound to actual source bytes. This expression does not bypass the identity check or invent a source commit.

## Audit evidence and remaining gates

The Parquet suite passed all 10 tests using actual synthetic ABI/log journals, the compiled Rust verifier and Polars 1.34.0. Tests cover lossless binary/provenance roundtrip, scope versus chunk completion, invalidation, empty journal behavior, foreign namespace and mixed class, corrupted evidence, duplicate/nonstring owner fields, no-overwrite/symlink isolation, input bounds and torn records. Fixtures are synthetic and are not mainnet replay or economic evidence.

Run from the crate directory:

```bash
PYTHONDONTWRITEBYTECODE=1 \
NQC_MINER_TEST_BINARY=/absolute/path/to/nqc-miner \
python -m unittest discover -s research -p test_export_parquet.py -v
```

Static audits used pglast 7.21 for PostgreSQL parsing, sqlglot 27.29.0 with its ClickHouse dialect, and jsonschema 4.25.1 for JSON Schema 2020-12 definitions and fixture/manifest structure. These temporary audit tools are not production dependencies. Parser success is not database integration validation.

Before deployment, the missing gates include real ClickHouse DDL execution and permission tests, PostgreSQL candidate-importer execution/permission/concurrency tests, importer/projection transaction and restart tests, late-invalidation integration tests, dedicated broker ACL/replication tests, a pinned Temporal worker with replay tests, cloud resource ownership/retention policy, Nix evaluation/build, authenticated source attestation and explicit operational authorization. No external resource is implied to exist because its contract is present.

## Primary references

- PostgreSQL schema and privilege boundaries: https://www.postgresql.org/docs/current/ddl-schemas.html
- ClickHouse ReplacingMergeTree and query-time deduplication: https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/replacingmergetree
- Redpanda ACL model: https://docs.redpanda.com/streaming/current/manage/security/authorization/acl/
- Temporal Workflow ID versus Run ID: https://docs.temporal.io/workflow-execution/workflowid-runid
- Polars native Parquet writer: https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html
- Pinned nixpkgs compiler: https://github.com/NixOS/nixpkgs/blob/0b0c249f090b05e3a47dcdd523c54921e5223409/pkgs/development/compilers/rust/1_90.nix
- Pinned nixpkgs default compiler selection: https://github.com/NixOS/nixpkgs/blob/0b0c249f090b05e3a47dcdd523c54921e5223409/pkgs/top-level/all-packages.nix
