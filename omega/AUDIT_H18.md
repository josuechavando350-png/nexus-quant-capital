# H18 — retained time-only diagnostics

Full local regression: **498/498 PASS**, including **27 new tests**, with no
failures, errors or skips. Local source-byte isolation passes for 138 reviewed
Omega files, 531 original files and 106 disabled historical workflows. Original
Git-object verification awaits the remote source checkout. Exact-producer remote
execution and post-audit are pending; H17's result is not inherited as H18 evidence.

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
