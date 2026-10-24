# Reserve projection evidence

Source: `085101caafa6927725213c22de552c72ef00b0da`.
Delivery and recovery verification: 2026-10-23. Directory date reflects preparation.

- `compiler/`: original pinned-solc input/output and stderr, recovered unchanged.
- `targeted-initial.txt`: original five-test result retained inside the source bundle.
- `targeted-recovery.txt`: new targeted run after restoring the source commit.
- `recompiled.txt`: new compiler result; all artifacts compare byte-for-byte.
- `offline/`: fresh full offline check logs and source manifest after recovery.
- `offline-initial/`: failed first recovery run (58 Python errors from missing
  historical commits in a shallow clone); original history was restored before
  repeating the full suite, without source changes.
- `recovery.json`: exact source, bundle, compiler and recovery boundaries.
- `source-history.bundle`: recoverable source commit; requires `ac41b44` from
  `../aave-amounts-20261022/source-history.bundle` and its documented prerequisites.
- `verification.json`: hashes and delivery result; no executable eligibility claim.

The full pre-reset logs were lost and are not represented as retained evidence.
The fresh logs replace them for this delivery. All state in the reserve harness
is synthetic; this evidence adds no authenticated historical position or event.

See `../../docs/AUDIT_AAVE_RESERVE_20261022.md` for counts, limits and recovery.
