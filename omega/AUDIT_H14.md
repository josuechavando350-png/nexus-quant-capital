# H14 — transaction intake, durable recovery and runtime artifacts

Status: local regression, isolation, exact-producer remote execution and
independent post-audit PASS. The producer identity and artifacts are below.
The requested 45% product target is not yet demonstrated. Certification 0/36.

Scope: original 139 events / 127 receipts / 139 decoded legs, retained metadata,
strict partial ledger, transactional SQLite store, independent local restoration,
controlled revocation, pipeline replay and bounded CI artifact migration.

Original artifacts: 11524139188, 11524199698, 11525823668 from nexus-engine.
The receipt parent run 37719091371 remains **failure**, despite its complete dRPC
stage. All original bytes and identities remain fixed. The new pin digest is
`b249194b3274abc42ecc936a3581e1b4fb6658d716880b57ffa5934d421b4bb0`.

The local real pipeline conserved 139 events, 127 transactions and
448369976498898050 wei of transaction gas. It preserves 53 distinct asset pairs,
12 same-asset raw gross deltas, zero known winner addresses, zero oracle delays,
zero complete cost rows, and null net profit. Hashes are recorded in
`evidence/h14-pipeline.json`. No USD totals or NQC earnings are inferred.

Development audit caught a bytes-dictionary JSON comparison bug in the pipeline
reverification. Two tests failed in that intermediate run; the comparison was
corrected and the affected 35 tests then passed. The failure remains recorded in
the local development log; it is not counted as a passing run.

Final local regression: **415/415 tests**, zero failures/errors/skips, including
25 intake, 16 store, 10 pipeline and 12 artifact tests (63 new). Original D15B/D16
archives were supplied, so the six historical-data cases were executed. Isolation
passed with 104 explicitly reviewed Omega files, 531 original source files,
637 original payloads, 106 disabled historical workflows and exactly one reviewed
active Omega workflow. Active/template SHA-256:
`8c1c20a8684a21728d7ebd83d0aac7ad93dc5840df34ec455e80e5eb0b3813be`.

Pipeline commitment `9950c04105fc1556695afabbbc7d3d9cece3e620a3a592bcc379ad999fa8bf2a`;
ledger commitment `a8e854f96a4261b4b0787c3c545e344f32411bb9fc08ecb0b6d5ad3fb4c1ea13`.

Limits: local process-crash durability is not physical power-loss certification;
local restoration is not remote replication; controlled revocation is not a
real chain reorg. Rust-store integration remains pending. The external API capture
trust anchor must be established independently. Runtime artifact correspondence
does not certify Census or transfer original authority to the new producer.


## Remote execution and independent post-audit

Producer `a82aed357513653d6cfb9375af54223657db7b1f`, tree
`6b15c09d721a58faf9e040da23f860c1a15611b5`, run **39872518839**, attempt 1,
completed successfully at 2026-10-22T23:56:03Z. Jobs 120150118729 (forks) and
120150118501 (replay) both succeeded, including their bounded uploads.

| Stage | Artifact | ZIP SHA256 | Captured API metadata SHA256 |
|---|---|---|---|
| forks | 12467560072 | `41424573ced6ebb2c4f5ffb68aa18c8f2f9712d768053b9b0deca0a37914ff90` | `1bebeffb615a732c620ec013ae0d3ae70e60981ae29916fef3d264c9128889b1` |
| replay | 12468435387 | `68daf40b70e8ab88f1a9000af1d87fa2b3d88545221f567569e1c0f101b68545` | `be31ec71e32ec367a5cf817faa180032455251a5d1b52df7e103485f85e13761` |

Both archives were downloaded through GitHub after their jobs completed. The
external captures were independently retrieved and include the run, exact Git
commit/tree, artifact identity and complete two-job metadata. The offline consumer
reproduced the H14 pipeline and matched these captures. A separate post-audit
also matched every packet record against the raw job logs (43 forks / 39 replay),
verified all test-source hashes against the producer, and checked physical counts:

- 56 PFT Rust tests, 14 Solidity tests and 4 historical fork test executions.
- 528 Census Rust tests, zero ignored; 16 matched replay STARTED/VERIFIED pairs,
  1258.949 cumulative step seconds; distinct network namespace, loopback only,
  exact original/result store root and unchanged original source.
- Both jobs executed 41 runner, 38 capture, 25 intake, 16 store, 10 pipeline and
  12 artifact-consumer tests. Repeated tests in two jobs are not unique new tests.

Post-audit commitments: forks
`27beeecd0cf409aaf8195251d9025c1d10064a3173a9b916ffb15f38bc44c4b8`;
replay `108f7213a387542730a583991a436915bcbb6f01508850322d120f12d1d1fdb6`.
These results belong to the producer above, not automatically to later commits.
They neither repair the seven inherited generic Python setup errors nor convert
historical validation into product certification. Census remains 0/9 certified.
