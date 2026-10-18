# NQC023 - Offline admission and retained-evidence audit

Status: RETAINED_RECEIPT_AUDIT_PASS_NOT_PROVIDER_ACCEPTANCE.

This note transcribes the NQC023_AUDIT emitted by the successful job. It is not a new EVM replay, a Titan admission or a commercial certificate. The underlying positions, actors and financing remain NQC021 laboratory fixtures.

## Exact provenance

- Repository: josuechavando350-png/nexus-quant-capital only.
- Branch: research/nqc-023-offline-admission-20261018.
- Tested auditor commit: 29648e089426d51445ab57e3bbb8497ea179b984.
- Successful audit run: 39146275163; job: 117730643501; attempt: 1.
- Source producer: 7e4018d575084bc18f857a2466d1fde447f62d34.
- Source run: 39102577514; job: 117601680768.
- Original export: 77 files, 200 chunks, 898082 compressed bytes.
- Original gzip SHA-256: 3ed88604eac3b379d65281dbe269c1b31b68c371c4bc210d7b9d9484888c867e.
- This documentation commit does not change the tested auditor or workflow and does not trigger another run.

## What actually ran

The audit recovered the complete pinned source export inside the standard GitHub runner, verified its compressed hash and all 77 file hashes, and independently reconciled native ETH balances, base-fee burn and committed transfers across 52 retained receipts. It verified receipt/block identities and index continuity, the unchanged operator-request digest, and sufficient maximum-fee reserves at every retained operator prefix. There were 38 committed native transfers in the inspected traces. It did not independently replay Solidity, validate the full EVM state, re-audit ERC20 accounting, or verify historical mainnet liquidity.

Nine new auditor unit tests passed locally and were repeated in CI; those repeated runs are not additional unique tests. The director's separate local necessary-condition examiner has 42 tests. The local delivery therefore has 51 new unique Python tests, not 60. The 42-test examiner itself was not executed in this workflow. Its 500 small arithmetic domains enumerate 26413 cost sequences; these are not blockchain executions.

## Retained-case observations

All amounts below are synthetic ETH. The minimum is specific to the retained prefix state and fee schedule, not an offer from Titan or a guaranteed amount for future execution.

| Case | Receipts | Three operator steps succeeded | Minimum upfront from retained prefixes (ETH) | Builder after observed payout (ETH) |
|---|---:|---|---:|---:|
| net_020 | 5 | yes | 0.012822358 | 0.029908602 |
| net_030 | 5 | yes | 0.012822358 | 0.019908602 |
| net_040 | 5 | yes | 0.012822358 | 0.009908602 |
| net_049 | 5 | yes | 0.012822358 | 0.000908602 |
| net_050 | 5 | yes | 0.012822358 | -0.000091398 |
| net_060 | 5 | yes | 0.012822358 | -0.010091398 |
| no_advance | 1 | no | unavailable: incomplete path | -0.042489410 |
| insufficient_011 | 2 | no | unavailable: incomplete path | -0.053510410 |
| omitted_proposer | 4 | yes | 0.012822358 | 0.062398012; payout omitted |
| gas3_same_operator | 5 | yes | 0.013267371 | 0.019866602 |
| slippage_revert | 5 | no | 0.012822358; includes reverted call | -0.070226422 |
| wrong_header_revert | 5 | no | 0.012822358; includes reverted call | -0.070557671 |

For net_050 the directly recorded builder delta before its separate proposer payout is +0.042398012 ETH; after that payout and its gas it is -0.000091398 ETH. A positive intermediate balance is not full economic viability. Unknown commercial costs, surplus ownership and personal liability remain unresolved in all cases.

The omitted-proposer row was deliberately UNKNOWN for operator completion in the director's initial summary-only projection. The retained-receipt audit now verifies all three operator statuses; the initial projection remains preserved rather than silently replaced. Missing proposer payment still rejects the NQC complete-payment criterion.

## Public-policy interpretation, not a provider clone

The examiner distinguishes mandatory steps from optional revert/drop permissions, unsigned intent from a signed RPC request, reserved maximum gas from actual expenditure, and documentary compatibility from real acceptance.

The Titan tracing page defines IncludedInBlock as a candidate-block stage that did not reach relay submission; Submitted does not establish that the submitted block won. Neither status alone proves canonical inclusion or profit. Public sources read on 2026-10-18: https://docs.titanbuilder.xyz/api/eth_sendbundle ; https://docs.titanbuilder.xyz/bundle-tracing ; https://docs.titanbuilder.xyz/ ; https://eips.ethereum.org/EIPS/eip-1559 . No provider endpoint was called.

## Failures and isolation limits

The first audit run, 39146086814 on 60b464836f8c60c3d5eeec0c2f6574fd106ee4ca, failed because the GitHub CLI refused to output terminal escape sequences in the historical log. Its nine unit tests had passed. The correction saves authenticated HTTPS bytes directly to a file, never rendering those bytes in a terminal. Same endpoint and permissions; no weakened TLS, new identity, or retry of an access denial. The successful run is a separate producer, not a relabelled failed attempt.

A duplicated test definition introduced during publication was removed before activating the workflow; there are nine unique auditor tests, not ten.

The unmodified global import isolation verifier returned exit 1: it forbids any .github/ files, including the explicitly scoped workflows. It was not edited and is NOT reported as PASS. A separate Git comparison verified that all parent files and modes remain unchanged: exactly the two new audit files and one new workflow existed at the tested producer. This later report is one additional documentation file. No new global source certification is claimed. Rust and the full historical Solidity suites were not run.

No EVM execution, chain signatures, public transactions, builder contacts, subscription, cache or artifact upload was initiated by this audit. No main or other repository was modified. The standard public runner was used with read-only contents/actions permissions, six-minute timeout, exact branch and one attempt per approved producer. The source contracts were never executed by the audit.

## Next evidence

Use this offline gate on a same-state authentic candidate with exact request/receipt/trace bindings. Source-plan and native-accounting compatibility can be investigated without waiting for email. Actual provider funding, disposition of surplus, exclusion of personal recourse, competitive capture and recurring profit remain separate external gates. Do not repeat these 12 scenarios merely to manufacture progress. No real NQC profit or monthly-income estimate is certified.
