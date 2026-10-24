# H13 — reproducible post-run evidence audit

Date: 2026-10-22. **H13: 100% of its retained-capture audit scope; post-audit PASS.**
This is not component certification or runtime artifact authentication.
Scope: Omega only, branch
`feat/omega-h2-executable-audit-20261022`; no Miner or original-source writes.

## Retained real evidence

The connected GitHub retrieval at `2026-10-22T22:25:54.894Z` captured run
`39859932654`, attempt 1, producer `e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7`,
tree `9964778862574102ac2cbe907d0f40ae6c78b847`, jobs `120107692904` and
`120107692521`. The successful historical execution is not attributed to this
new consumer commit.

The archive contains seven complete payloads, 665719 expanded bytes and
98297 compressed bytes. SHA-256:
`ff15cba21f4335efb4f88089e69964055397bb5a84ad4dc3c7cd7d96163de43f`.
Pin SHA-256:
`dc616afdad494a479d808dba7eacfa215dcb687a003871bba19c53895d135635`.

The new capture preserves the connector-returned decoded log bytes exactly:

| Log | Bytes | SHA-256 |
|---|---:|---|
| forks | 488606 | `707d0f81247269facafb34e60464760f84fd89985222555c22ffa883d3c21cf6` |
| replay | 155290 | `5aec49967756ad9466930b0e84c1d137d68c94e00666a474cd6e467275fca850` |

H2E's previously saved files each had one additional final newline. Their
documented hashes remain correct for those files; this capture does not rewrite
them. The difference is serialization only, not a new execution or observation.

## Validation

The real capture verifies: 54 commitments, 16 replay steps, API producer/job
identity and conclusions, actual Git commit/tree/workflow objects, all original
test counts and false authorities. Replay preserves the original observation
time `2026-10-01T05:23:35Z` and identical source/result store root.

38 adversarial tests passed initially, including rehashed identity substitutions,
failed/skipped jobs, missing evidence, duplicate JSON/ZIP members, path attacks,
size limits, altered source/roots, provider dissent, routing, command failures,
authority escalation and refusal to apply the run to another producer.

Full Omega regression: **352/352 PASS**, with original D15B/D16 archives and
zero skips, expected failures or errors. Report SHA-256:
`904999add782140ca7da4ee7100222a10abe0f4dc19df6d412bc84525b3cff10`.
Original source-object isolation: **PASS**, 83 explicit Omega files, 531
original source files, 106 disabled historical workflows and one unchanged
active Omega workflow. No Rust/Solidity source changed; their physical gates
will run again in the existing branch workflow.

The package consumer's report commitment is
`8d28de7033a7e897625373dc66808e82ba318b68bda1b4efbb078e2c99cbc930`.
Remote integration and independent API readback completed successfully below.
No pass is inferred from test collection or prior-head execution.

## Published consumer and remote fork audit

New consumer commit `4a521dd42a0c816cd6959cd0fb4ac4e5b871dab0`, tree
`3cecde2897e05c39a10c1b519eaf11adec53ee31`, was compared byte-for-byte with the
locally tested tree before and after publication. Its parent is
`87f0793b48cd16a4b76d63de56629a05e705ea93`; the user's checkpoint
`84fbaa2dd7a1b93c432f6611622b98d81fd3c679` remains an ancestor. All ten changed
paths are under `omega/`. Full source-object isolation passes on the published
checkout, and the working tree was clean before this documentation update.

Run [39866201976](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39866201976),
attempt 1, executes the exact new producer. Fork job `120128895402` succeeded.
Its post-run audit verified 32 JSON commitments, 38/38 new consumer tests,
41/41 runner tests, all-zero command exits, before/after isolation and the
original historical fork result commitment
`96338bad40dd243f0199172507cdca42849f5c1c76cae87da1687ce1a3b5a260`.
The consumer's complete JSON output is identical to the report committed in Git.
Fork log: 505205 bytes, SHA-256
`723891b9fcac2119ba4f840dbe61a2e3c8fdc714d385d5f09caa620de5de654f`.
Replay job `120128895735` also succeeded. Post-run audit verified 28 JSON
commitments, 38/38 consumer tests, 41/41 runner tests, **528/528 Rust Census**,
the release build and all 16 original replay command pairs. Fork validation
also preserves **56/56 Rust PFT, 14/14 Solidity and 4/4 historical forks**.

The replay verification ran from `2026-10-22T22:39:04.479452Z` to
`2026-10-22T23:00:16.233424Z`: **1271.753972 seconds**. The original source
remained unchanged; current/history replay and closeout remained byte-identical.
Source and result store root:
`e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03`.
The real network namespace `net:[4026532315]` differs from parent
`net:[4026531833]`, with only loopback and no routable network.
Replay commitment:
`aa179ca22ebeaaa0381a3ecde6c63e2bea9cefd413940237a8a5c5f8bfc1bfd6`.
Replay log: 171892 bytes, SHA-256
`e7c21cac5ecda01dced3d96f50d7ec948f08b3152f2c3c40afd27382ea2c6eb2`.

Independent GitHub readback confirms the exact repository ID `1411047452`,
producer commit/tree, branch, workflow ID `393369697`, attempt 1, both jobs
success on standard ubuntu-24.04 runners, and run completion at
`2026-10-22T23:00:20Z`. Artifact inventory remains **zero**. All authority flags
remain false. The final post-audit status is **H13_POST_AUDIT_PASS**.

The later audit commit edits documentation only. Physical results belong to
`4a521dd42a0c816cd6959cd0fb4ac4e5b871dab0`; no CI execution is attributed to the
later documentation SHA. PR 30 remains a draft on the dedicated Omega branch.

## Next data intake prepared, not certified

The original single-provider event artifact `11524139188`, run `37718661409`,
commit `abe54f1f23bd7bff8c37871200f7da7c59c45ac3`, tree
`c74f8d9d2c317a011284398643b2d4aa6de06e83`, remains available and its GitHub
identity agrees with `rmc016-dual-receipt-inputs.json`. Downloaded ZIP bytes:
56919, SHA-256
`6b4098c1acf153106ac5b67d2c5c7db5cd0295a16c782ad8c34ae75303306204`.
The original `load_source` validator independently admits exactly 139 events
and 127 unique transactions, with complete recorded coverage by Blockscout
and `independent_provider_consensus=false`. These are sanitized event identities,
not the missing D16 transaction economics ledger. Oracle linkage, winner identity,
independent receipt parity and full cost reconciliation still require their own
evidence. No competitor margin or NQC profit is inferred from this intake.

The dRPC checkpoint was also reauthenticated: artifact `11524199698`, 64349
bytes, ZIP SHA-256
`182b5e81b00ca04e53c9193c1496a725dc152ade9a17d3ab2dfaeb5045ac86b6`,
run `37719091371`, commit `569d4aaeecb3d066389c054efed695be02e3ef40`, tree
`ba648214fb5cb1cdca1db1f42f28059054d78e63`. The overall original run remains
**failure**. The unchanged `authenticated_drpc_checkpoint` validator verifies
only its completed dRPC stage: 127 exact transaction records, 139 event links,
all receipt commitments and `448369976498898050` wei of observed competitor gas.
Independent full receipt parity remains false; no USD valuation, complete costs,
oracle linkage, winner address or new acquisition is established by these rows.

## Limits and progress

H2 remains 100% of its audited integration milestone. Global construction is
still roughly 20%, a coarse estimate rather than a measured completion rate.
Census remains 0/9 certified and Omega 0/36; all nine Census bases remain partial.

The retained ZIP is not an Actions artifact, and the authenticator is not a
canonical recertification gate. Artifact authentication is explicitly false.
The new consumer does not repair the seven inherited Python discovery setup
errors or the inherited PFT formatting failure. Their earlier classifications
and separate historical validations remain in force.
