# H14 — transaction intake, durable recovery and runtime artifacts

Status: local regression and isolation PASS; remote exact-producer execution
pending. This record will be updated with actual remote outcomes after audit.
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
