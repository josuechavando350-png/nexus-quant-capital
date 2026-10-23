# H17 — source-bound predecessor states and conditional Pool fee

Final full local regression: **471/471 PASS**, including **26 new tests**, with
no skips, failures or errors. Initial targeted run passed 25 tests; the subsequent
output-path hardening adds the 26th. Isolation passes for 130 reviewed Omega files,
preserving 531 original source files and 106 disabled original workflows.
Remote exact-producer execution and independent artifact/API/log post-audit
both **PASS**. Final identities and evidence commitments are recorded below.

The three successful original runs, commits/trees and artifacts were independently
read through GitHub before download. Exact outer ZIP hashes:

- Rank-two price, 2481 bytes:
  `ece575718b4834293ffb0a6e42f4329f41b39fef4b1befcad96eac507df1a92f`.
- Pool rate, 5557 bytes:
  `b7ed74f7f1c73654d8eb0396ab9258e0546063bfd143c7b541380dc4bd01f56e`.
- Predecessor health, 9796 bytes:
  `069652fdb01f6921979edad188634a2fd6d72860163cbf6b3d47fab5fabe6fd6`.

Source-pin SHA256:
`5e9c18944805c8c4eab1b92200b16336b8d44155f633dbc07cf4188ed8d0405c`.
The pin preserves metadata hashes, exact trees, source reports and member hashes.

Three of nine WETH/WETH rows now have source-bound predecessor prices, Pool
rates and health. All three were NOT below HF=1 at predecessor end; six remain
unknown. Three normalized receipt commitments match original dRPC/BlastAPI
evidence, not whole-corpus independent receipt parity. Original H16 is unchanged.

Observed 5-bps rates are separate from conditional fees and paid costs. Half-up
rounding for ranks two/three differs from the old sensitivity by one wei. Complete
costs, oracle causal delays and NQC P&L remain null; prospective/executable rows
remain zero. Negative precursor results are retained as negative evidence.

Tests cover real joins, unknowns, integer/overflow/negative boundaries, provider
disagreement, predecessor/winner substitution, borrower and receipt commitments,
wrong HF classifications/counts, rehashed fabricated profit, missing/extra sources,
tampered archives/captures, symlinks, no-network replay, restore/idempotence,
revocation and CLI refusal to overwrite.

Certified components: **0/36**. Census remains open. This is a historical
engineering increment, not a 25-point product-completion award.


## Final local readback

Report commitment: `5d5f6dba379347a0babebf3e26c8ed72720c3b49fea4106d23030f4eb2993392`.

- h17-full-tests-final.json: SHA256 `3d8f179820e520418307f5cb9e65d05bc9fd522d44078d45e89c75f3ed3e7da1`.
- h17-isolation.json: SHA256 `ee599929fc6481e959c0effdccd26168a8732dc2980990eff060a600364e415d`.

The final review tightened CLI output validation to reject parent symlinks and
repository paths before writing. The original health source SHA256 in its
artifact manifest matches the imported, unchanged source bytes. The existing CI
workflow and template remain unchanged at their previously reviewed digest.

## Independent source and arithmetic review

The retained original job logs were checked against the original run/commit
metadata and source reports. These are old source executions, not new H17 tests.
Their SHA256 digests are:

- Rank-two price, job 113165115862:
  `940a2decd943621b4d6c8443e5b1c7f31ff3adf97f87ca3b4dfcf0023c6af1fa`.
- Pool parameter, job 113166640795:
  `7c32b292b9a3d9852521c044f935d0e554cc230f0701a8b746d5243f7950b17e`.
- Predecessor health, job 113188224730:
  `5d87ada28cb785b6150ef666da3927c88c8c4c5be01d3ddaf0df11e00bde05d0`.

A separate verifier, without importing the H17 implementation, independently
checked the three raw-source joins, integer fee arithmetic, receipt identities,
health classifications and six unknown states. Result: PASS. The complete
471-test local run includes 26 unique H17 cases; repeated execution in both
remote jobs does not increase that count.

## Next temporal source: review only

Original run 37740704145, artifact 11533288894, has authenticated ZIP digest
`7d813c6cad278a5044d1c4ce57492efb07c5c0d73d69481769f92a4cc4151185`.
Its eight retained members, report commitments, predecessor-health binding,
canonical provider anchors and three fork logs were checked independently.
Advancing only time and block number crosses HF below one for one case; two
remain above one. No original intra-block transactions were replayed. This is
a reviewed source for a future integration, not a new Omega execution, a
demonstrated oracle cause, an implemented predictor or an executable candidate.

## Final physical outcome and post-audit

Code producer `d99e0b332db7ef8cde70e195b67edd949ab17adb`, tree
`46c031a01b5f4a816a9c3ca4b064600211940730`, run **39884845749**, attempt 1,
completed **success** at 2026-10-23T01:58:38Z. Both jobs and every step passed.
Later edits change only Markdown; the physical evidence refers to this exact
code producer, not to the later documentation commit.

| Stage | Job | Artifact | ZIP SHA256 | External API capture SHA256 |
|---|---|---|---|---|
| forks | 120190493853 | 12472162444 | `00cb7fb795c049d15ef4dbd693cecd7d248707ff52ea65828b6da5a3763147df` | `e941e6edaf541d08fec533557b515f859e6f61a5333770cc2a9b22ce192a0ab8` |
| replay | 120190493588 | 12473326240 | `a701e42ee4ebf15a075c2dd2730af4a2a056ee354585a946d1888168c18959ba` | `87bda59fc9bbf67d0be199eb491492fce19f9e04b607850cedfd2ef05544a676` |

The downloaded archives reproduce the source-bound pipeline and match the
independently retrieved GitHub run, commit, tree, jobs and artifact metadata.
The post-audit matches all 43 forks and 39 replay records to the complete job
logs, including every selected test-source hash against the producer. Both jobs
pass 81 intake cases (25 historical, 18 liquidator, 12 cashflow and 26 state),
plus 41 runner, 38 capture, 16 store, 10 pipeline and 12 artifact tests.

Physical counts: **56 PFT Rust**, **528 Census Rust**, **14 Solidity unit tests**,
**4 fork executions** (two cases on two providers) and **16 verified replay
steps**, with approximately 1258.084 seconds of cumulative replay-step time.
The replay namespace has loopback only and differs from its parent. Source bytes
and store root `e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03`
remain unchanged. The existing workflow digest remains
`8c1c20a8684a21728d7ebd83d0aac7ad93dc5840df34ec455e80e5eb0b3813be`.

Post-audit commitments:

- forks: `9f1b9d280638a4f3f23bbeacf0f57a51138543cb993231eb71b4435a5c386e0d`
- replay: `b9120e74bd45ec7c5f82dc33d928b952e6a5181b48acc6f071c7f80a86a1b7e4`

Full raw-log SHA256 digests:

- forks: `fa7310a86e4496abf9890a8b7d6e155accb1338e7626949e8df1abc655a24523`
- replay: `74a3fdb7f3b91c3f61d28f9b824f6fca69f34d04e737a68361ecd8d90f2cf977`

There are **471 unique local Omega tests**, 119 more than the 352-case baseline;
remote repetitions are not additional unique tests. Inherited generic Python
discovery preparation errors and original formatting findings retain their
earlier classification. This successful runtime audit grants no component or
phase closure: certified components remain **0/36**, complete paid-cost rows
remain **0/127**, and unresolved costs remain null.
