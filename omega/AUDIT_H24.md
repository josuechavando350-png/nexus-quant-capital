# H24 — historical flash financing, initial draft

Base: H23 producer `3448f173305d765f3cdf9a5494571b34a16c0e34`.
H23's exact-producer remote run completed successfully; it has no H24 scope.

Read-only public Routescan acquisition returned the exact historical rank-1 receipt
with 17 logs. HTTP 200, the exact URL, retrieval time and original response body
are retained. No credential, account, subscription or Blockscout retry was used.

- Capture SHA256: `8bb0bde55bd501175f54148561a508fcab0bf296e5bfa10123b4fde3acdc8701`.
- Raw response SHA256: `4eb761445a70860837872e6eb5d2e7bba0ad0c78640185d12ebed9a3dbf08e43`.
- Report commitment: `857b497bebdb95c1c12e1c9dcca74abb81bb38776ff6e349893b7ee6cdf308ca`.

The event, outgoing principal and repayment each carry 10684013854557827871 WETH
wei. The observed WETH repayment premium is zero; full financing costs and NQC
profit are unknown. The immutable original normalizer reproduces the retained
dRPC receipt summary. H23's operation selectors/counterparties corroborate the
loan and callback. See `FLASH_FINANCING_CONTRACT.md` for scope and references.

The first local CLI probe rejected an acquisition timestamp expressed with a
`+00:00` suffix. The capture was normalized to the same instant in required UTC
`Z` format before publication and repinned; no receipt response bytes changed.
An optional independent hashing probe could not import PyCryptodome; the runtime
reader has no such dependency. These probes are not counted as passing tests.

The targeted suite passes **18/18 tests** (5.546 seconds), without failures, errors
or skips. Cases reject wrong chain/anchors/participants, gas or Aave-event drift,
receipt failure, missing/removed/duplicate logs, malformed ABI padding, altered
principal/repayment/withdrawal, callback disagreement and resealed route, cost or
Titan claims. Full local regression is still running at this checkpoint.

Isolation passes with 176 reviewed Omega files, 531 original files, 106 disabled
historical workflows and the unchanged active workflow. Original Git objects are
not supplied locally; no remote H24 validation is claimed.

An independent stdlib-only Keccak implementation, checked against the empty-string
and ERC20 Transfer vectors, reproduces the FlashLoan topic and both call selectors.
It also checks the raw response hash, all 17 log indices, exact principal repayment,
collateral/debt/withdrawal arithmetic and gas without importing Omega modules.
The missing optional PyCryptodome package did not require installation or a runtime
dependency. The independent check passes.

| Local check | SHA256 |
|---|---|
| Targeted tests | `da58fa6a697015bf5d43e938d5ac15ca826ffa89e5aa70ba0ff97ef61146108d` |
| Isolation | `4b5f1c8abce1b3008500444cfa2c31772274726684812cceae31575494d056a6` |
| Independent signatures/arithmetic | `f4f110953e4446b53b48f5e1d744d24d839b13925f43f434506d26c0d71ea6b8` |

These are session results, not remote CI artifacts. No ninth store batch or new
runtime/physical execution is claimed. Original sources, workflow and Titan-only
zero-operator-gas policy remain unchanged. Product certification 0/36, complete
paid-cost rows 0/127, Titan coverage 0.

## Complete local regression

**672/672 unique Omega tests pass**, including 18 new financing cases, with zero
failures, errors, skips or expected failures (654.659 seconds). All recorded test
source hashes still match the published code. Full result SHA256:
`16f3a5cb7a9d811ec483e9ed4d7a9b76ce0df3c70b95a4230a77756c8477d025`;
commitment `7a89111a55093e89aba63e2ed030c22ef7c94584efb6de55b35dbeaa9739a9a9`.
Final isolation passes with the same 176/531/106 counts and unchanged workflow.

Feature commit: `a33fa4249d1f96765854c9d29c5e3d9e089d6521`; tree:
`3bcd8e67397bc431eaae88ddd3dec4bffd3fe54b`. PR #33 remains a local-tested draft.
Only Markdown is updated after this tested source checkpoint. No H24 remote run,
NQC Morpho execution, new store/runtime integration or Titan coverage is claimed.

Next bounded work: bind this reader as H23's dependent ninth batch and add an
independently reproduced disconnected runtime record. A separate Morpho execution
experiment must use an additive overlay/fresh build copy, authenticate the lender's
deployed code and anchor liquidity, and measure repayment plus gas. Do not reuse
the Aave fork's gas profile or infer savings from its different fee. Preserve Titan
as gas payer and keep executable admission blocked until operation-specific
coverage, repayment, compensation and complete costs are evidenced.

## Upstream documentation synchronization

H23 Markdown-only closure `92867c001394ae3aa8091c8b82fcf0bfd13b4ce6` is merged into this draft.
The H24 feature/test/capture bytes remain those of `a33fa4249d1f96765854c9d29c5e3d9e089d6521`.
The successful H23 run does not validate H24; this PR remains a local-tested draft.
