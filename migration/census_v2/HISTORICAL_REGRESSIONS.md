# Historical regression preparation recovered

The earlier generic discovery result remains an historical failure: 664 tests,
seven setup errors and three skips. This increment resolves three setup failures
in separate, reproducible invocations and executes all three previously skipped
D06 integration tests. **63 selected original tests pass, with zero skips.**
It does not relabel the broad discovery command as successful or close Census.

## Original contexts, unchanged assertions

| Selected suite | Required context | Current result |
| --- | --- | ---: |
| Original D08 debt producer | Seven-resolved-family catalog, original blob `6754a74c5c1e348c0c731618332ba8feba96834e` | 20 passed |
| Original D08 native flash importer | Nine-resolved-family catalog, original blob `c1b9f136a13f220af9dceaae50e5caa3105121eb` | 20 passed |
| Independent two-debt audit | Nine-family catalog, actual original ZIP and run/artifact/commit metadata for all five upstream stages | 20 passed |
| D06 original package integration | Actual original ZIP, run/artifact/Git-commit metadata and actual expiry clock | 3 passed |

The first two suites exercise synthetic adversarial fixtures; they are not new
market observations or a fresh full-universe capital import. The debt audit
uses the actual previously recovered 7,057-byte archive, SHA-256
`151847cdf85b1b49298d59b41d1bf939f6854d4556060a03ab7dd5a2e1359916`.
The D06 integration uses the original 6,709,740-byte archive, SHA-256
`1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4`,
verifying its 4,234 indexed members, extraction roundtrip and CLI provenance.
Original positive evidence and mutated negative fixtures are labeled separately.

The original generic invocation omitted required archive CLI arguments and used
the current catalog for producers frozen to earlier catalog states. The new
runner verifies the exact imported source blobs against NQC parent commit
`0848d9946dda2b7f66b3715635db0c6239832033`, materializes separate directories and
changes only each copy's catalog to its original hash-pinned bytes. Every other
copied file must remain identical. The checkout is verified unchanged afterward.
All seven/nine previously resolved family rows must still match the current
catalog in canonical bytes, including JSON types. This compatibility check does
not authenticate later family resolutions or transfer historical gas policy.

Fresh GitHub Git-commit metadata for D06–D10 and the debt producer binds the
commit SHA and tree directly. The runner also checks each against its run's
actual head/tree and artifact identity before launching tests. REST commit
responses already present in the repository are preserved; they are not
silently rewritten into the different Git-commit schema. The new API snapshots
are decoded response records, not independently self-authenticating authorities.

Six additional context guards reject catalog substitution, family JSON-type
drift, a different commit with the same tree, changed run/tree/artifact identity
and reuse of an existing output directory. They check the original source bytes
remain unchanged. These six tests are separate from the 63 original tests.

## Reproduction

From the repository root, with the two actual ZIPs in the archive directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/replay_historical_regressions.py \
  --archive-root /absolute/path/archives \
  --out /absolute/path/fresh-historical-regression-replay
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2 -p test_historical_regression_contexts.py -v
```

The replay directory must be outside the repository and must not exist. No
archive is downloaded, no RPC is contacted and no original producer is
dispatched. Metadata expiry is checked at the real current clock by the D06
integration. These tests will correctly refuse expired metadata later; do not
backdate the clock to manufacture a pass. The report records commands, source
hashes, original archive identities, metadata hashes and individual logs.

## Four remaining integration suites

Four original suites still require five unique missing archives. Their absence
is an explicit unresolved dependency, never a synthetic fixture or a passing
skip. Exact requirements are in `evidence/historical-regressions/missing-inputs.json`.

| Suite | Missing original artifacts |
| --- | --- |
| Four-native source join | 11576077535, 11577315781 |
| Independent seven bounded rejections | 11571178483 |
| Independent thirteen-source pins | 11576204678, 11576077535, 11577315781 |
| Independent discovery admission | 11577503474 |

These are additional source-audit archive requirements. They do not replace the
missing D15B episode/censored/economic ledgers, incomplete RPC coverage or the
unproven economic admission conditions. The archived broad-suite result stays
unchanged; future review should use the explicit context-aware commands above.

No original source/workflow was changed. All 106 imported workflows remain
disabled. No independent authority, executable capital, positive capture or
Census certification is issued. The MXN 2,000 gas-only policy remains unchanged
and is not assigned retroactively to these historical source rejections.
