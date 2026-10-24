# H23 — direct payment observation and dependent replay

Source base: H22 producer `811c549b3561dcdd0719993a2a12852068f5920b`.
The H22 physical run does not validate H23 code or evidence.

Public read-only Routescan acquisition recovered the first historical winner's
57 indexed operations across three pages, matching transaction metadata and the
same provider's separate positive internal-transfer representation. All five raw
response bodies and their exact request URLs are retained in the capture. No
account, API key, paid subscription, Blockscout session or permission was added.

Capture SHA256: `b139de8b1dd63d1c87c629b6dbab4f4239c7a03b7a2d69082cffff61d6c43f12`.
Report commitment: `42cc6a948cad0bd4677e69a676b6b1fb41807b710b68b2451c2feeaa17aabbd7`.

Observed direct transfer to the historical block fee recipient:
**95915734379292898 wei**, approximately 99.75% of the observed gross WETH delta.
This is not a claim of total builder compensation, verified builder identity,
Titan funding, exclusive liquidation cost attribution or realized NQC profit.
The distinct 9975 wei root value and the residual's different recipient are
explicitly retained. See `DIRECT_PAYMENT_CONTRACT.md` for exact arithmetic and
remaining evidence limits.

Development probes first rejected a bytes-vs-JSON comparison and then an assumed
exact count label on the last cursor page. The byte comparison was corrected;
pagination now verifies the captured final `lowerBound` label against the earlier
exact count, all 57 unique indices and a terminal cursor. These failed probes are
not counted as passed tests or used to weaken the evidence scope.

## Initial local intake verification

**638/638 unique Omega tests pass**, including 16 new direct-payment cases, with
zero failures, errors, skips or expected failures (402.651 seconds). The targeted
16/16 suite also passes. Cases reject pagination truncation, missing/duplicate
indices, cursor changes, cross-chain/block drift, failed calls, inconsistent
amounts, gas/native-value disagreement and resealed profit or Titan claims.

Isolation passes with 170 reviewed Omega files, 531 original files and 106 disabled
historical workflows; the one active workflow is unchanged. Original Git objects
were not supplied locally (`original_objects_checked=false`). No Rust/Solidity
implementation was changed or rerun for H23.

An independent stdlib-only check (no Omega imports) validates every retained raw
response hash, all operation indices, block identities, native split, exact payment
ratio, separate root value, gas and unknown-profit fields. It passes.

| Local result | SHA256 |
|---|---|
| Full regression | `6fe25462324395e33865503758d94f8b56dfccd580e2bb2c36b51f859db773ff` |
| Targeted direct-payment suite | `0bbd0cf0b9e9a93d43645ec1f7b980c61ae297342ef44dfcb6e4e87be6bcae01` |
| Isolation | `0b9f54179341cfb8943453deba88e1d308dd37d9f668f714f1e835fde0f11dd7` |
| Independent arithmetic | `fee308b24f5226504d1e651df36010acb387a4ee741c49d13e643f945fbaf82d` |

These local result files are session outputs; their hashes do not claim durable
remote CI artifacts. Source, tests, raw capture and reproducible report are kept
with the initial draft. At that checkpoint no eighth dependent store batch, new
runtime proof or H23 remote validation was claimed. Product certification remains
0/36, complete paid costs 0/127, and execution-specific Titan coverage zero.

## Store and runtime integration

Continued from draft head `761ac40c68b525ab495e59607f446b85cb022438`, which
includes H22's Markdown-only closure. The raw capture and observation report bytes
remain unchanged. The new eighth SQLite batch declares only H22 as its parent;
queries recursively verify that parent, exact inherited bytes, complete inventory,
the pinned Routescan capture and the recomputed report. Parent revocation blocks
both querying the child and readmitting it as an active batch.

Runtime v6 adds a required `direct-payments` record to the existing disconnected
worker. It reconstructs eight batches, revokes the root, restores the exact export
and rejects normal reads of all eight before and after restore. Every batch's
forensic object bytes are compared. The packet consumer independently reproduces
this exercise and requires the same namespace, root and inclusion batch as H22,
the same H22 report commitment and the exact Titan-only policy. The new batch does
not claim Rust transport, canonical reorg recovery or execution-specific coverage.

An initial integration smoke probe failed because the JSON comparison helper was
used on byte dictionaries. It was corrected to direct byte equality before the
test runs; this failed probe is not counted as a passing check.

An authentic H22 v5 replay artifact, already independently retrieved for its
closure, passes the new consumer with 44 records and its original scope. Its ZIP
SHA256 is `5a0641ebafb2839a8905bf43d19d2e43d714eb80b4da4775f3d6637f9867c63d`;
compatibility-result SHA256 is
`8b89a4eb9ffd0abe3eb9274b513d4a1fddaab8cf77cf27722efc93d31b35574c`.
This recheck is not a new remote H22 run or H23 execution.

Historical v1-v5 schema/code inventories stay frozen. No active workflow,
permission, provider, Rust/Solidity source, original PFT/Census byte or Miner file
is changed. Targeted integration checks pass: 29/29 direct-payment tests and
25/25 runtime-packet tests, without failures, errors or skips. Thirteen store/replay
cases and three v6 cases are new in this continuation. The complete regression
and remote exact-producer audit are pending at this writing; the earlier 638-test
result covers the initial draft only.

| Integration check | SHA256 |
|---|---|
| Direct-payment suite | `77d7fa05e8176678d77cea5cb75658a2c0285462d4b49deda865a86560709899` |
| Runtime suite | `0550113feb23a26f7a538e8e1869ea2746ee4163abe83a74980e03333c5c7463` |
| Isolation, 170/531/106 files | `0b9f54179341cfb8943453deba88e1d308dd37d9f668f714f1e835fde0f11dd7` |
| Independent bytes/arithmetic | `dd603382d80336a61017f865858d926f6cae53546866604ed96a7ae4b368bed9` |

The independent stdlib check confirms all five raw response hashes, operation
indices 0–56, the direct/native split and unchanged retained captures, reports and
workflow bytes. Original Git objects remain unchecked locally; remote isolation
must verify them. These result files are session outputs, not remote CI artifacts.

## Complete local regression and remote launch

**654/654 unique Omega tests pass**, with zero failures, errors, skips or expected
failures (650.999 seconds). There are 32 new cases over H22 and 16 over the initial
H23 intake. The full result SHA256 is
`2148d586598b4b0fe7ab2a542722668ba261b91e99c9aac23daad09133c39404`;
its commitment is `3c048b95a67e1b1a1dd660d3eb0a512936cf8c341f52381726e1d4fd43ce4f0a`.
All recorded test-source hashes still match the producer; final isolation passes.

Exact producer `3448f173305d765f3cdf9a5494571b34a16c0e34`, tree
`0a67bcd30deffc6da5cc71e55278c57d3b406527`, was fast-forwarded to the existing
audit branch after those local checks. Run
[40050771588](https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/40050771588),
attempt 1, started at 2026-10-24T01:39:17Z. Remote checks and independent artifact,
API and log verification remain pending at this launch checkpoint. Subsequent
closure edits are Markdown only and cannot claim execution of new code.

## Final exact-producer outcome

Run **40050771588**, attempt 1, producer
`3448f173305d765f3cdf9a5494571b34a16c0e34`, tree
`0a67bcd30deffc6da5cc71e55278c57d3b406527`, completed successfully at
2026-10-24T02:13:09Z. Both jobs and every step passed. Closure edits after this
producer are Markdown only; later code cannot inherit this execution.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120742714686 | 12543218899 | `fba452f736f0499871f1b299db60f3470083c42a304cc6021b09ea856b545040` | `1e22f8afb663b4be208e7e97876ebdb7dc65e21b4095368a56400c2bd47c00c4` |
| replay | 120742714941 | 12544675202 | `9fca63cb7c1ebb88d0bf95473b10408d27f4fdf0dea726649e6cd4719500fd89` | `4c13e8ab6f6296882f1e185ad83a8ad3de207f0270b05ff989e2fd9668f599bf` |

Independent GitHub API readback, downloaded artifacts and full decoded job logs
agree on repository, commit/tree, workflow, run/attempt and every evidence record:
43 for forks, 45 for replay. Each job passes 230 intake, 43 runner, 38 capture,
33 store, 10 pipeline and 25 runtime tests: 379 executions per job, not additional
unique cases. Every selected test-source hash matches the producer. Physical
checks pass 56 PFT Rust, 528 Census Rust, 14 offline Solidity tests, four historical
fork executions and 16 verified disconnected replay steps.

Original Git objects and isolation pass before/after both jobs: 170 reviewed Omega
files, 531 original files, 106 disabled legacy workflows and the unchanged active
workflow/permissions. Historical source/store roots remain unchanged. Existing
H19/H20 Rust transport probes keep their original scope.

The new H23 record is reconstructed inside the same physical disconnected worker
as the prior replay records: loopback only, a network namespace distinct from its
parent, and no routable network. All eight normal batch reads fail after controlled
root revocation in both source and restored SQLite stores; every batch's forensic
object bytes survive. The emitted worker report equals the v6 artifact and binds
H22's batch/root/report commitment plus the exact Titan-only policy. No new Rust
transport, canonical reorg recovery or NQC liquidation execution is claimed.

Independent integer checks reconfirm the historical direct payment of
95915734379292898 wei, its split with the residual, the separate 9975 wei root value
and 19694395579376 wei execution gas. Builder identity, complete costs and actual
profit remain unknown. The policy remains Titan-only, zero operator allowance,
no prefund and no own-gas fallback; its hash is
`e2c0b1ea247597de667d093385990880a31519b594f68cae31618ba425f87540`.
No Titan submission, coverage receipt, signing, broadcast or funding was added.

- Forks post-audit commitment: `8653467cc8a43522b32e5068556262a4fdf256b30e4e64f4fdb5d14093780d9f`; log SHA256: `7de554f2d92893d42a1a176fd5cd8a0595992e2a370928dbd1ed72b1c8596df8`.
- Replay post-audit commitment: `72f2f21ffa0d1c2f0e0a852804a6eb4cccd68297bf2591b79663244b6ddf5bd2`; log SHA256: `320d75896f307f9497af78345838c9fca5deac18221e789cdff2df7d4605f77d`.
- Direct-payment replay commitment: `6fbd23e386c3340bccceb8772c49ed3e1989ffecb59c4c86995bcf903e5f6fa6`.

H23 engineering closure: **4/4 (100% of this increment)**, with **654/654** unique
local tests and 32 new cases over H22. Product certification remains 0/36, Census
0/9, complete paid-cost rows 0/127 and Titan-covered NQC executions zero.
Separate H24 financing research remains a draft and does not inherit this run.
