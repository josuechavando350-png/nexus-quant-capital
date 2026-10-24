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
