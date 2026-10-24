# H20 audit — declared transitive evidence invalidation

Predecessor: H19 closure `2a15c564fd03aa17703ab9df540c4383c45a0fa0`;
H19 physical producer `fcbe6cac8c69c58b55d4ccf67c399dd359db6a96`.

H20 adds explicit dependency manifests and a source-authenticated five-stage
intake. Root revocation must block all declared descendants while preserving
forensic bytes and an unrelated branch. Historical manifests keep their IDs and
batch-local scope. See `DEPENDENCY_REVOCATION_CONTRACT.md`.

The four closure gates are implementation, local regression/isolation,
exact-producer remote execution, and final post-audit. All four now pass; exact identities appear below.
No remote result is inherited from H19. Product certification remains 0/36.

## Local validation before publication

Full Omega regression: **561/561**, zero errors, skips or expected failures;
**29 new tests** over H19 (17 store, 10 real-source/dependency intake, 2 packet).
Original D15B/D16 ZIPs are supplied under their existing hash pins. The 33 store
and 17 runtime-packet targeted cases also pass. The first 10-case intake run had
one test-harness failure: patching the module function did not replace its already
bound validator tuple. The fault injection now targets that tuple, and the full
suite passes. That failed attempt is retained as a failure, not a passing gate.

Independent stdlib SQL/graph audit (no Omega imports): six batches, four declared
edges, one explicit revocation, four invalidated descendants and one active
unrelated control. All source and restored table bytes match. The transport
inventory is **29 artifacts / 3,155,162 logical bytes**; the additional control
and proof do not count as new market observations. This local check is neither
Rust execution nor network-isolated evidence.

Snapshot ID: `34044b9330b4128421a914749bf8975638ba8b0692c441fcab631a2c1c73e4f6`.
Journal head: `50303b84a46ac955833fe5f1a5c7911cce82114e35ac0433b1346d06ad423d53`.
Independent report commitment:
`dfb01c1149b753463e2b61e81f2e7912972b71abe62a8dbef0569f32a28a651b`.

Isolation passes with 147 reviewed Omega files, 531 original files and 106
historical workflows disabled. The active workflow is unchanged. Local source
Git objects were not supplied; the remote run must perform that stronger check.
The authentic H19 v2 replay artifact/API/log post-audit still passes with the new
reader, preserving its old batch-local scope and exact report commitment.

- h20-full-tests.json: SHA256 `e1ed3251ae88aef5a784b94fb08f9ca4abe9156ab20f087039e3d5e3c623e017`.
- h20-isolation.json: SHA256 `f753002f899a3837981de12fbefbd9d4c1f75316ca2d0df42c1e6f4965f756b0`.
- h20-independent-local.json: SHA256 `0d92ac444eae454a487b51b958427d085a6ab23fa4dc0f6b55f2d610379cf53d`.
- h20-h19-backcompat.json: SHA256 `2cb8387b5888e0a61cb49895865638a7fb17fa44f8979ff79158f82d49a93d40`.

Pre-publication checkpoint: **2/4 (50%)**, with remote execution and its
post-audit then pending. The final outcome below closes those two steps.

## Final exact-producer outcome

Run **40019225049**, producer `641ffb4c5a49514fdca346e57b06f6526f4b7dcf`, tree
`0d15b379d16bce9d693e424263afb200921c04e3`, completed successfully at
2026-10-23T20:52:36Z. Later closure changes are Markdown only.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120639119045 | 12530521004 | `976754fbfab47070a4d310dd0ba7a5143f22d307251f2dee1f965bf0f839bb7e` | `61780cfc569c3a300c288c5ec508c7513597f057f5fa4279e610227ceba05a03` |
| replay | 120639119434 | 12530628506 | `a682035a93373726a193195fe8d7250e09cf5c7643202e288317efcc626d4d32` | `db7141689c3dd416cc7c1fbdc1321c5ccdf9b6e92d5670a6aa38e9ebe28b35e0` |

Both jobs and every step pass. Independent API captures and complete job logs
match 43 fork records and 42 replay records, including all selected test-source
digests. Each job passes 147 intake, 43 runner, 38 capture, 33 store, 10 pipeline
and 17 packet tests (288 executions, not additional unique tests). Physical checks
pass: 56 PFT Rust, 528 Census Rust, 14 Solidity unit tests, four historical fork
executions and 16 verified disconnected replay steps. Original-source Git-object
checks pass before and after execution; source and store roots remain unchanged.

H19's separate 28-artifact transport still passes its own physical probes. H20's
new physical span contains three successful Rust processes: import, standalone
verify and independent export. Their commands, result codes and stdout digests
match the retained log. H20 transports **29 artifacts / 3,155,162 logical bytes**
with zero streams or certified ranges. This adds a control/proof/snapshot scope,
not a new historical market observation. All artifacts are explicit orphans.

The post-audit independently traverses the reported graph: six batches, four
edges, one revoked ledger, four invalidated descendants and one active unrelated
control. Restore preserves exact inventory, table contents and query status.
The worker rejects the pre-revocation snapshot against the current external head
without publishing a destination. The standalone verifier's full stdout is
reconstructed and hashed. The graph operation executes inside the same isolated
network namespace as the historical replay. Old v1/v2 artifacts retain old scope.

- forks post-audit commitment: `1ea9b821a6b5667fc1d405587a71c1aa1db301f1b33e65262c77856fbe3dd69a`; raw log SHA256: `e82a4df069d4ae0e0e1d530e1df58050799db6367b4678965d03d61cf9a23a80`.
- replay post-audit commitment: `fa5f4bb66a192ccf549158df6f9f65a6f804db3350bc35aad4ce8c63260e98a1`; raw log SHA256: `c5a1392d647685453b856ef9420b247a71167b2c6aa6c31f29bb863fd7f43a93`.
- Dependency report commitment: `3bfb62c1feff9aeacde2bed4e59a36e3efc947ababb9b1e61cfa44a1735b98e1`.

The final suite remains **561/561 unique Python tests**, **29 new** over H19.
The first failed local fault-injection test is preserved separately; it is not
counted as a passing execution. Repeated CI tests add no unique test cases.

H20 engineering checklist: **4/4 (100% of this increment)**. This closes declared
dependency invalidation and its local Rust recovery path for the demonstrated
five-stage intake. Existing legacy IDs are not retroactively migrated; undeclared
edges are not discovered. Whole-chain atomicity, inter-host replicas and actual
canonical chain reorg authority are not claimed. Complete market coverage and
complete execution costs still need evidence. Certified components remain
**0/36**, Census **0/9**, temporal sample coverage **3/9**, complete paid-cost rows
**0/127**. There is still no supported overall product-completion percentage.
