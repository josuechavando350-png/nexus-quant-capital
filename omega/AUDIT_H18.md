# H18 — retained time-only diagnostics

Full local regression: **498/498 PASS**, including **27 new tests**, with no
failures, errors or skips. Local source-byte isolation passes for 138 reviewed
Omega files, 531 original files and 106 disabled historical workflows. The remote
source checkout also verifies original Git objects. Exact-producer physical
execution and independent artifact/API/log post-audit both **PASS**; identities
and commitments are recorded below.

Original run 37740704145 completed successfully. Its single job 113190514122 was
independently read through GitHub, with the full retained job log. Artifact
11533288894 is 13030 bytes, SHA256
`7d813c6cad278a5044d1c4ce57492efb07c5c0d73d69481769f92a4cc4151185`.
Producer `030d95c705a1fce77c3345cada4c8cd698f4a1db`, tree
`b1c02d1e1ade0c9e2ed9a370cc32df6361f3f1a6`.

The original reviewed metadata capture has SHA256
`38e0c15398dbbbeae7380cb6477537399e851ba3f221dfb7ecd18a71199fe363`;
the complete intake pin is
`35d536ca5a238f3c2c76f8a63edd76fed5fbb02f5a715a07645a68284e07bb83`.
Source files, all nine ZIP members and eight inner-manifest payloads are verified.

| Rank | Previous HF (WAD integer) | Time-only endpoint HF | Delta | Below one |
|---|---:|---:|---:|---|
| 1 | 1000000001993818630 | 999999999704293538 | -2289525092 | yes |
| 2 | 1000701093031081909 | 1000701096098308225 | 3067226316 | no |
| 3 | 1000489719586999148 | 1000489713637144623 | -5949854525 | no |

Each interval is 12 seconds between consecutive blocks. Two operators corroborate
the timestamps; only dRPC supplies the original fork executions. Six of the nine
WETH cases retain null temporal witnesses. No first crossing time is estimated,
no linear predictor is inferred, and the original winner selection uses hindsight.

Tests exercise source replacement, operator disagreement, timestamp type/order,
wrong transaction/borrower/block/health identities, duplicate or malformed log
measurements, failed/skipped forks, strict threshold equality, fabricated profits
or causality after rehashing, offline replay, durable restore/idempotence,
revocation, upstream report laundering and append-only CLI output safety.

Original build logs include timestamp-comparison lint warnings; the original code
and warnings are preserved. The timestamps here are authenticated historical
anchors, not a claim that validator-chosen timestamps provide a live guarantee.

Certified components: **0/36**. This increment integrates retained diagnostics;
it does not perform a new temporal fork or close Census.

The review also confirms that revocation is batch-local. Cross-batch dependency
invalidation, Rust-store integration, remote recovery and real canonical reorg
handling remain open; passing local restore tests does not demonstrate them.

## Independent local post-audit

A separate standard-library verifier imports no Omega implementation. It checked
all inner-manifest payloads, original report commitments, the three transaction/
borrower/block joins, exact log measurements and deltas, one crossing, two
non-crossings and six unknowns. It also checks authority, provider and causal
limits. Result: **PASS**.

Derived report commitment: `0fb18af4afefb60c81b9651a5af15fc96cd35e94a6f9926922c67ce38f250304`.

- h18-full-tests.json: SHA256 `f2fc4b97d67bb94e784313afd7cb5a11a9fdd7f11e591ed5eadbe0ba2f160dc6`.
- h18-isolation.json: SHA256 `9109046f62bd9deb8508fc332a85626248a8af61ff81c3ae502e4cbecb5f4f58`.
- h18-independent-data-audit.json: SHA256 `4f92d47cbc19eae79574e84695fa29f310dcfdc93d2707be2b0611cafe1e4762`.
- h18-original-job.log: SHA256 `a0442a4c8ffa935d7aec063f906e4adbcd66a60a00f6b5bdac11b32609ad1a6a`.

## Next execution source: review only

Original run 37741109591, artifact 11534051574, source commit
`5b5402ff373f06804f8714d91dfe247f0c230c92`, ZIP SHA256
`9af974b4f87a68ef9e9dcf932e146b2440f197939b8bd75a7e993755b06c8bf1`,
was independently retrieved and checked against its five inner-manifest payloads,
original source, report commitment and two retained passing tests. Its fee
arithmetic within the original fork and simulated surplus agree with the raw log.
It preserves the lack of complete costs, native gas funding, inclusion and real
capture. This is a reviewed next-step source, not an H18 execution or integration.

Original gas-budget run 37742063251 / artifact 11533854519 was also reviewed.
ZIP SHA256 `2f31b24005ac3050574d6669b904415d09a438648575cdcbdbbd2b5a4dcf40e9`,
producer `0d700182e776b8efc261e8e5c9ebcebdcbaf9d11`, tree
`a99c1b46456423888874a47a85ba6c5c09d3f992`. Its six payloads, source file hashes,
report commitment, raw log and five budget scenarios agree. The 562357 gas units
measure only the EVM call; assumed overhead, tips and ETH/WETH parity remain
assumptions. This review does not integrate those costs or execute a new fork.

## Final physical outcome and post-audit

Run **39889427564**, attempt 1, completed **success** at 2026-10-23T02:48:00Z. Both jobs
and all their steps succeeded. Tested code producer `bd4b120e78603617473f2750bcff367271459375`,
tree `85ac4a7db38ab666d484db777d62e3c136e51cb2`. Later changes are Markdown only;
these results do not claim physical execution of the later documentation commit.

| Stage | Job | Artifact | ZIP SHA256 | External API capture SHA256 |
|---|---|---|---|---|
| forks | 120205346661 | 12474246955 | `eda2df42b5c779ec173b80ae9010f756c0a9e89b312440f0c626635c2436fbc2` | `0ff2859dbb2b3638d5071ce9be710577bdf2cdae63b4431a93474674ed22c7cc` |
| replay | 120205346516 | 12475007112 | `1d6e25db87a05922513f3fca8cbcf27502b75dfbd0841abea0a7a3e38248b563` | `d6c00ade8c6aa8c1a19c004323ecb248c8a423aed111e4a9b62fc21441daf0af` |

The post-audit matches all 43 forks and 39 replay packet records to the complete
raw logs and verifies every selected test-source hash against the producer. Both
stages reproduce the source-bound pipeline and match independent GitHub run,
commit/tree, jobs and artifact metadata. Both include 108 intake tests (25 historical,
18 liquidator, 12 cashflow, 26 predecessor and 27 temporal), plus 41 runner,
38 capture, 16 store, 10 pipeline and 12 artifact tests.

Physical checks: **56 PFT Rust**, **528 Census Rust**, **14 Solidity unit tests**,
**4 historical fork executions** and **16 verified disconnected replay steps**.
Cumulative replay-step time: approximately 1252.310 seconds. The replay
namespace has loopback only and differs from its parent. Original bytes and
store root `e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03`
remain identical. These are the established H2 runtime gates; the three original
time-only forks and the reviewed next-step execution/gas cases are not rerun here.

Post-audit commitments and full raw-log SHA256 digests:

- forks audit: `b13232a0eeb6e1fd7b11bb32de3a0442e6bcebe6c27384697146008f444e4f0f`; log: `4d2e4451142ddcad338873e1659fd7a434111899481b7f8c3a8ebbd10b515235`.
- replay audit: `88870d83038185bb8870589c7490d9f1db11e11fae51e55ac68cd91e67873d70`; log: `90a3fd65cd9bca29530c9b967b5c4fb90f20d718b1b9ce4dad0a1f92aab1aaa4`.

Full local Omega coverage remains **498 unique tests**, including **27 new H18
cases** and 146 additions since the 352-case baseline. Repeated physical runs do
not increase that unique count. Inherited generic Python discovery preparation
errors and original formatting findings retain their earlier classification.
The sole active workflow remains unchanged at SHA256
`8c1c20a8684a21728d7ebd83d0aac7ad93dc5840df34ec455e80e5eb0b3813be`.

Certified components remain **0/36**. No complete paid-cost, prospective prediction,
real reorg, canonical recertification or phase closure is granted by this audit.
