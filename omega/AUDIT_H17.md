# H17 — source-bound predecessor states and conditional Pool fee

Final full local regression: **471/471 PASS**, including **26 new tests**, with
no skips, failures or errors. Initial targeted run passed 25 tests; the subsequent
output-path hardening adds the 26th. Isolation passes for 130 reviewed Omega files,
preserving 531 original source files and 106 disabled original workflows.
Remote exact-producer execution is pending, not passing evidence.

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
