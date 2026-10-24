# H15 — 127 transaction liquidators, audited against 139 original commitments

Local validation: **433/433** full Omega tests, zero failures/errors/skips,
including 18 new identity tests. Original D15B/D16 data were supplied. Isolation
passed with 111 reviewed Omega files, all 531 original source files intact,
106 historical workflows disabled and one reviewed active workflow.
The unchanged H15 intake and its 18 tests passed in the combined H16 producer
`af4fe54f1dc25d1e3b1ab620db874549b15af2ea`, run 39874530238, including the
independent artifact/log post-audit documented in `AUDIT_H16.md`. The H15-only
run was cancelled while pending, as recorded below. Product target 45% is not
declared achieved; certified components remain 0/36.

Real captures: two native Blockscout `direct_api_call` requests against chain 1,
legacy getLogs with the original Aave pool/topic and adjacent original ranges.
First response 63 logs, second 76, no pagination, below the 1000 cap. Complete
raw response envelopes are retained in `evidence/liquidator-log-capture.zip`.

Archive: 20342 bytes, SHA256
`d2e83b8a2f44e2adaf85f4cb2db036a7a5abbfd7f1aa012527c86c298eb52140`.
Reviewed capture pin SHA256:
`65649ad0c3502e32edc430a33c1e09d7afe5fdfcfb3ef06b304d477d92ff057f`.
Derived report commitment:
`26f28047af0f1b06874975e04cadcf6f57e497fffce007b3fc8482d5e1ca93d6`.

All 139 raw payloads match the original commitments and decoded quantities and
fingerprints. Results: 127 transaction liquidators identified, 49 distinct
liquidator addresses, 127 borrowers, exact agreement of execution gas metadata
with all original dRPC receipts. No oracle-delay or complete-cost row is proven.

Tests cover exact known addresses, source conservation, same-output ordering,
changed quantities/addresses/anchors, malformed ABI/hex, gas disagreements,
fingerprint disagreement, pin/archive/symlink rejection, no network, recovery,
self-consistent identity fraud, altered base ledger and revocation. Test fixtures
are mutations of authentic captures and do not serve as market evidence.

The API omits block hashes and removal status; these are not manufactured as new
observations. The original block hash is used solely for commitment validation.
Gas-field agreement is not full receipt parity. Beneficial ownership, NQC
execution, causality, complete costs and Census closure remain unproven.

CI extends its existing intake test pattern to `test*intake.py` so both H14 and
H15 execute in the same two physical jobs. It preserves existing workflow bytes,
permissions, artifact bounds and physical gate requirements. The runtime packet
records the intake tests and their exact source hashes; its market pipeline
report remains the separately reproducible H14 report.


## Producer scheduling record

H15 was published as `9495a04bcc3efea8440383afb5c4de649fb4c71d`, tree
`c9f7163b8ccb489cbe5947f0a73f2beca783947a`. Its run 39873763981 was cancelled
while pending when H16 superseded the queued run under the existing concurrency
policy. It is **not** counted as a passing run. H16 includes this implementation
and its 18 tests; its physical outcome is recorded in `AUDIT_H16.md` after audit.
