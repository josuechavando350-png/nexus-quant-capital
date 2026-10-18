# NQC 018 - Funding boundary: observed local results

Status: TWELVE_LOCAL_CASE_ASSERTIONS_PASS_NOT_COMMERCIAL.

This is a transcription of the NQC018_STATUS emitted by the successful job, not an independent replay or a provider acceptance. All assets, positions and financing are synthetic. The two funding policies are explicit hypotheses, NOT implementations of Titan or Quasar rules.

## Provenance

- Repository: josuechavando350-png/nexus-quant-capital (public).
- Experiment branch: research/nqc-018-funding-boundary-20261018.
- Tested producer: bfe251bd7f9b8ef768fc9ce99f42ed0ded3f73db.
- Parent: 6da36867faad9f915355188dbefd890a7498d93f.
- Original EVM base: f9d876990a85e55ba196702c32fe3668b49fda71.
- Workflow: .github/workflows/nqc-018-funding-boundary.yml.
- Workflow Git blob: b74b42303a8c50d7ad3cf73a9292558c5d09f168.
- Run: https://github.com/josuechavando350-png/nexus-quant-capital/actions/runs/39094293890
- Job: 117577385192. Run attempt: 1. Conclusion: success.
- Run created 2026-10-18T03:37:44Z; updated completed 2026-10-18T03:38:02Z.
- Main verified after the run: 16e352225ba8a6a931834c4edf3d86d9a2924b7d.

The producer adds only one scoped workflow relative to its parent; this later document does not change the tested code. The workflow contains a SHA-256-checked compressed payload with ci_funding.py, funding_matrix.py and test_funding_matrix.py. It permits one attempt on the exact branch, a standard ubuntu-24.04 runner and a twelve-minute timeout. No artifacts upload, cache, public-chain transaction, signature or provider contact.

## Executed and counted

Twelve new EVM cases passed their assertions, with 68 final transaction receipts. Eight packages completed all mandatory steps. Six also passed the narrow local economic gate (complete package, zero residual financing, positive builder cash and positive operator WETH). This is NOT a success rate or a commercial admission rate.

The 154 discarded planning blocks are separate from the 68 retained receipts. Each final candidate starts from its case snapshot. Twenty-four new Python tests passed locally and in CI; these are the same tests repeated, not 48. Nine historical isolation tests passed. The unmodified isolation verifier passed on the pre-workflow original base only; that is NOT a claim that it approved the new active workflow. A separate Git diff checked preservation of all parent files and modes. Fourteen original bytecodes were recovered and checked; both contracts compiled. The full historical fifty-test Solidity suite and Rust suite were not rerun.

## Results

ETH figures below are synthetic cash. Negative/partial rows do not represent admissible operation profits. Unknown commercial expenses remain excluded.

| Case | Initial advance ETH | Extra funding ETH | Gas | Final receipts | Complete | Financing residual ETH | Builder cash ETH | Local gate |
|---|---:|---:|---:|---:|---|---:|---:|---|
| shared_fixed_003 | 0.03 | 0 | 2482012 | 6 | yes | 0 | 0.045049578 | pass |
| separate_reference_003 | 0.03 | 0 | 2468410 | 5 | yes | 0 | 0.045063180 | pass |
| shared_gas_only_002 | 0.02 | 0 | 2440012 | 4 | no | 0.015161976 | 0.072398012 | reject |
| shared_full_002 | 0.02 | 0.01 | 2503012 | 7 | yes | 0 | 0.045028578 | pass |
| shared_fixed_004 | 0.04 | 0 | 2482012 | 6 | yes | 0.01 | 0.035049578 | reject |
| shared_requoted_002 | 0.02 | 0 | 2482012 | 6 | yes | 0 | 0.045049578 | pass |
| shared_requoted_004 | 0.04 | 0 | 2482012 | 6 | yes | 0 | 0.045049578 | pass |
| shared_full_capped | 0.02 | 0 | 2440012 | 4 | no | 0.015161976 | 0.072398012 | reject |
| shared_zero_gas_only | 0 | 0.012822358 | 2461012 | 5 | no | 0.007984334 | 0.079554654 | reject |
| shared_zero_full | 0 | 0.03 | 2524012 | 8 | yes | 0 | 0.045007578 | pass |
| shared_omitted_payout | 0.03 | 0 | 2461012 | 5 | no | 0 | 0.087538988 | reject |
| shared_high_gas | 0.3 | 0 | 2482012 | 6 | yes | 0 | -0.002108650 | reject |

Except shared_high_gas (21 gwei effective), the fixture uses 2 gwei effective. Every case completed the synthetic liquidation and retained 0.159365645570551238 new WETH at the operator. This alone is not enough: six cases fail the local gate.

Complete packages pay the distinct proposer exactly 0.042468410 ETH. Shared mode now executes a separate provider-owned payout transaction; separate mode supplies the same proposer total through its tip and priority fees. The comparable shared mode costs 13,602 extra gas and leaves 0.000013602 ETH less builder cash. Do not treat the pre-payout 0.087538988 ETH as net builder profit.

## What changed and what did not

Known-advance re-quoting works at 0.02 and 0.04 ETH in the deterministic fixture: return values are 0.015119976 and 0.035119976 ETH respectively. Operator instructions are frozen AFTER the declaration and local quote; the provider does not edit them. This does not solve an unknown advance after real signatures have been fixed. Unknown advance remains BLOCKED_INPUTS_UNKNOWN_ADVANCE.

The 0.02 ETH fixed-return case can close only when the hypothetical gas-and-value provider adds another 0.01 ETH. The 0.025 ETH cumulative ceiling blocks that extra funding. In the zero-initial-advance full-coverage case the provider actually contributes 0.03 ETH in THREE included transfers: zero operator capital is not zero total capital. One ETH is explicitly seeded to the synthetic provider before all case snapshots.

A single block is not a rollback guarantee across transactions. Partial cases intentionally study exposure and do not allege that an actual builder would admit such a candidate. Missing proposer payment, residual financing and negative provider margin fail admission independently of liquidation success.

## Evidence export and continuity

The job log emits 101 files in 253 NQC018_CHUNK records, announced by NQC018_EXPORT_META and closed by NQC018_EXPORT_END. Gzip size: 1136303 bytes. Gzip SHA-256: 34dc0bdc3516ff91057330532b337efd2a6c7c657020176074fff405afcd5a5a.

The payload is gzip-compressed JSON mapping relative paths to {sha256, bytes, base64}. Verify every index, the archive digest, every file digest and safe relative paths before extracting. It includes the retained executions, planning records and reconciliation outputs. This document does not claim that the entire export was independently re-downloaded into the director's container. The director rechecked the summary's financing and builder arithmetic separately.

Next decisive work: recover the exported evidence and audit the provider/operator boundary independently; then establish a documented funding declaration or bounded settlement mechanism applicable to an actual provider. Do not repeat the earlier eight-case exercise by default. Do not infer non-recourse terms, real financing, authentic liquidity, timely capture or monthly income from these cases. Commercial admission remains false. No real NQC profit was evidenced by this experiment.
