# H13 — reproducible post-run evidence audit

Date: 2026-10-22. Scope: Omega only, branch
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
Remote integration remains pending until the new producer run and API readback
complete. No pass is inferred from test collection or prior-head execution.

## Limits and progress

H2 remains 100% of its audited integration milestone. Global construction is
still roughly 20%, a coarse estimate rather than a measured completion rate.
Census remains 0/9 certified and Omega 0/36; all nine Census bases remain partial.

The retained ZIP is not an Actions artifact, and the authenticator is not a
canonical recertification gate. Artifact authentication is explicitly false.
The new consumer does not repair the seven inherited Python discovery setup
errors or the inherited PFT formatting failure. Their earlier classifications
and separate historical validations remain in force.
