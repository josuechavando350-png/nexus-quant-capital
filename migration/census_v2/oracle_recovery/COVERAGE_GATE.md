# Set-exact historical coverage check

This is an offline integration check of the **existing third checkpoint**, not
new acquisition, an increased score, independent review or terminal Census
closure. The worker is not restarted or contacted by either new script.

`verify_coverage.py` replays the original oracle archive, both earlier direct
captures (including the 429), all 55 closed continuation files, the complete
event scan and all full receipts. It does not use a saved readback as a substitute
for those raw inputs. Eight consumer dependencies are bound byte-for-byte to
Git objects at `5f13f585a84048af7d1a3cd383aa9d2dacacfca2`; the new consumer is
identified by SHA-256 in each report and by its publishing commit/tree.

## Actual readback

| Component | Verified blocks / boundary |
| --- | --- |
| Retained Nodies chunks | 4,650 |
| Earlier direct Nodies captures | 2,080; overlaps the retained set in 1,560 blocks |
| Exact prior union | 5,170, not 6,730 |
| Closed continuation prefix | 55,000; all 3,685,000 prices match original dRPC chunks |
| Final union for this snapshot | 60,170 of 215,036; 4,031,390 unique block/asset price coordinates |
| Still missing | 154,866 blocks, enumerated as exact ranges |
| Open capture observations | 20 excluded from verified coverage |
| Executed-event and receipt replay | 139 events and 127 complete receipts reconcile again |

The result remains `PARTIAL_COVERAGE_NOT_A_MILESTONE`. The captured progress
snapshot is from checkpoint 003, not the worker's later live counter. Its
closed sources and counters are never added to checkpoint 002 a second time.
`coverage-gate/partition.json` makes the prior overlap, disjoint continuation,
verified union and remaining ranges independently inspectable.

The checker rederives the missing-block plan as the **exact set complement** of
the prior observations. Equal counts with different block identities fail. It
checks the source identities, worker/batch/rate declaration, Retry-After start,
counter types, preserved failure state and terminal-file consistency. Those
declarations and chronology checks do not add a new measurement of RPC pacing;
the unchanged collector's controller tests remain separate from price parity.

A terminal label alone is insufficient. The current CLI needs every closed
capture byte and matching `progress.json` / `acquisition.json`, all 209,866
planned continuation blocks, every price comparison and the complete event/
receipt replay before `milestone_10_coverage_ready` can become true. That field
does not send a notice. A human-facing notice must still authenticate durable
evidence and follow `MILESTONES.md`, including duplicate-notice checks.

There is deliberately no positive path for 15/20 or 20/20 here. Independent
underlying nodes, full header lineage, original decision-time receipt, candidate
execution/funding/costs/capture and independent terminal acceptance remain
outside this coverage check. The four 403 ZIPs still have no recovered bytes.

## Reproduce from immutable evidence

Use the version-four recovery bundle identified by
`../evidence/server-recovery/retention.json` (SHA-256
`63265e4a0910dbbea3f8ab0966b494ad4d08b44b42acd79d0c8727c15b4d5feb`),
the original D08 ZIP `11237887761.zip`, and this Git checkout. `WORK` must be a
fresh directory with sufficient temporary space. The preparer only extracts
authenticated copies; it never changes original archives, source trees or the
live worker directory. It combines checkpoint 002's 43 files with the 12 new
files in checkpoint 003, checking the exact prefix and shared source bytes.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/prepare_coverage_inputs.py \
  --recovery "$RECOVERY_VERSION_FOUR" --out "$WORK/inputs"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_coverage.py \
  --original "$WORK/inputs/original-oracle-evidence.zip" --d08 "$D08" \
  --pilot "$WORK/inputs/pilot-bundle/pilot" \
  --partial "$WORK/inputs/partial-bundle/remaining" \
  --checkpoint "$WORK/inputs/closed-prefix" --primary "$WORK/inputs/original/drpc" \
  --full-window "$WORK/inputs/full-window" --out "$WORK/readback"
PYTHONDONTWRITEBYTECODE=1 NQC_COVERAGE_INPUTS="$WORK/inputs" NQC_ORACLE_D08="$D08" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_coverage.py -v
```

For a later checkpoint, supply a separate, immutable complete-prefix snapshot
as `--checkpoint`. The fixed preparer above intentionally continues to reproduce
checkpoint 003; it does not silently read the live acquisition directory.

The 19 new checks include two byte-identical full replays and adversarial cases
for a changed prior set, out-of-window blocks, inflated or boolean counters,
forged completion, erased failure, noncanonical metadata types, source/operator
substitution, Retry-After backdating, and corrupted archive input. The synthetic
full-set arithmetic case tests only set conservation, never historical coverage.

An initial attempt to materialize the preserved recovery package failed with
`No space left on device`; the exact message is retained. The same package was
then authenticated and the same checks run using temporary RAM-backed space.
No source was deleted and no assertion was weakened. Affected suite and original
isolation results are recorded alongside the five readbacks: **56 oracle tests,
7 event/receipt tests and 9 isolation tests pass**, with zero failures or skips.
The 19 new cases are included in the 56, not added to them again. Original Git
objects verify for all 637 imported entries; zero workflows are active. Rust and Solidity
are unchanged and were not rerun. No network acquisition, gas, signing,
broadcast, workflow activation or independent certification is performed here.
