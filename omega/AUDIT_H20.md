# H20 audit — declared transitive evidence invalidation

Predecessor: H19 closure `2a15c564fd03aa17703ab9df540c4383c45a0fa0`;
H19 physical producer `fcbe6cac8c69c58b55d4ccf67c399dd359db6a96`.

H20 adds explicit dependency manifests and a source-authenticated five-stage
intake. Root revocation must block all declared descendants while preserving
forensic bytes and an unrelated branch. Historical manifests keep their IDs and
batch-local scope. See `DEPENDENCY_REVOCATION_CONTRACT.md`.

The four closure gates are implementation, local regression/isolation,
exact-producer remote execution, and final post-audit. Final results are pending.
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

Engineering checklist: **2/4 (50%)**. Exact-producer remote execution and its
post-audit are pending. Product certification remains 0/36.
