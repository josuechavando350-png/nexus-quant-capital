# Local import validation, 2026-10-08

This report covers isolation and offline code checks. It is not a new canonical
PFT/Census certificate and does not establish deployment or trading authority.

## Passed

- Source-backed isolation verifier: all 637 source/workflow mappings, original
  Git blobs, modes and ten immutable original commit/tree references verified.
- All 106 archived NQC workflows are byte-identical to original definitions and
  have `.yml.disabled` filenames outside `.github/workflows`.
- 525 original source files are unchanged. Six test-file edits only adapt paths
  to those disabled workflows; all assertions are preserved.
- Census Rust 1.98.1: 528 tests passed with locked dependencies and offline mode;
  formatting check, all-targets Clippy with warnings denied, and all-targets build
  passed. Cache and build output remained outside the public payload.
- D06 recertification code tests: 58 passed, zero skipped, with the authenticated
  original ZIP and recorded source run/artifact/commit metadata supplied. This
  exercises authentication negatives but does not run new canonical CI or perform
  a fresh full disconnected replay on this new repository.
- Isolation boundary tests: 9 passed, including changed source bytes, added
  active workflow, client tree, extra source file, substituted source repository,
  wrong destination ID, omitted mapping and symlink rejection.
- Independent corpus validator passed for its three immutable fixture cases.
  Its explicit `protocol_fork_truth: NOT_CLOSED` remains unchanged.
- All 33 recovered-source SHA-256 checks passed.
- Independent Python syntax and local Cargo dependency closure checks passed.
- Public-payload static credential/client scan and decoded-archive inspection
  found no production credential candidate, client code, client data or client
  configuration. Documented public development test keys/mnemonic remain
  historical fixtures. Static screening is not an absolute no-secret guarantee.

## Aggregate Python discovery is not green

The generic command `python3 -m unittest discover -s ci/nqc-census -p 'test*.py'`
reported 664 tests, seven setup errors and three optional-source skips. The exact
same seven error signatures and three skips reproduce on the immutable original
source snapshot before migration. No new discovery error was introduced.

Five suites require their artifact arguments through their existing CLI harness:

- `test_rmc011_four_native_original_source_join`
- `test_rmc011_independent_discovery_admission`
- `test_rmc011_independent_seven_bounded_rejections`
- `test_rmc011_independent_thirteen_source_pins`
- `test_rmc011_independent_two_debt_pins`

Two legacy original-source suites reject the current source-catalog blob under
their historical producer pin:

- `test_rmc011_original_d08_debt_producer`
- `test_rmc011_original_d08_native_flash_import`

These suites were not removed, skipped by a new aggregate runner, or weakened to
make migration appear green. Their historical-input execution remains separate
work. The three D06 optional-source skips were independently resolved by rerunning
all 58 D06 tests with the real authenticated source package, as reported above.

## Remaining boundaries and unrun checks

- The historical PFT materializer's original ancestry gate remains intact and
  cannot pass in an independent new root. A reviewed source-object-store or
  standalone authority adapter is required before using it here.
- No fresh full PFT build, Solidity fork execution, Reth integration, live RPC,
  canonical recertification or downstream D14 authority was established.
- The old T37 monolithic Base64 archive has an inherited invalid-padding issue;
  its authoritative split archive is valid, scanned and used by the preserved
  workflow. Do not silently repair historical bytes in this source import.
- Original source artifact IDs and expiration metadata remain historical. Verify
  current availability and authorized cross-repository access before future CI.
- No external mutation occurred during local preparation. Only the reviewed
  independent root is eligible for a separately authorized new-repository import.
- An all-files initial-import whitespace check reports two preserved historical
  bytes: a final blank line in the disabled mismatch-ledger workflow, and a
  whitespace-bearing context line in the immutable PFT-COMPAT-009 patch. They are
  intentionally not rewritten during an evidence-preserving source migration.
