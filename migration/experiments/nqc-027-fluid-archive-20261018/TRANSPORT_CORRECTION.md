# NQC027 transport correction, before first RPC acquisition

The first producer 664ca274ef84b0ac31b79c867603950591692c60 contained an incorrectly
transcribed/truncated compressed payload. This was a publication error by this
assistant, not a Fluid, RPC, GitHub or original NQC failure.

Run 39161037751, job 117774211942, attempt 1 failed on the payload length/hash
assertion BEFORE unpacking or running the collector. No RPC acquisition occurred.
The log verifies base isolation PASS (531 source files, 106 disabled workflows,
original_objects_checked=false), 9/9 base isolation tests PASS, two-file producer
addition check PASS, then AssertionError. Preserve this failure in the record.

Correction: abandon compressed source transport. Publish the unchanged, already
locally tested collector and tests as plain UTF-8 files under this experiment.
Their SHA-256 locks remain exactly those in REVIEW.md. The replacement workflow
must check these locks, copy only those two files to a separate runtime, repeat
the 14 tests, and then make the FIRST bounded acquisition attempt.

The complete reviewed base-to-producer scope now consists of five ADDED files:
- .github/workflows/nqc-027-fluid-archive.yml
- migration/experiments/nqc-027-fluid-archive-20261018/REVIEW.md
- migration/experiments/nqc-027-fluid-archive-20261018/TRANSPORT_CORRECTION.md
- migration/experiments/nqc-027-fluid-archive-20261018/source/collect_fluid.py
- migration/experiments/nqc-027-fluid-archive-20261018/tests/test_collect_fluid.py

No existing base file or mode may change. The untouched-base verifier remains a
pre-network gate. This addendum supersedes REVIEW.md only regarding packed input
transport and the two-file addition allowlist; its other limits remain binding.
No re-run of the failed job, no duplicate RPC acquisition, no retry of an external
denial, no spending, secrets, signatures, broadcasts or main changes. The new
workflow update produces a distinct exact producer identity and a new push run.
This correction is not a newly demonstrated trading opportunity.
