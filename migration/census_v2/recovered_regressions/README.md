# Four historical regression suites recovered

The five original archives previously listed as unavailable in
`../evidence/historical-regressions/missing-inputs.json` were recovered on
October 9, 2026. Every ZIP matches its already-pinned SHA-256, size and original
run/commit/tree/artifact identity. The missing-input record is preserved as an
historical observation; this directory records the later resolution.

| Original suite | Real artifacts | Result |
| --- | --- | ---: |
| Four-native source join | 11576077535, 11577315781 | 21 passed |
| Seven bounded rejections | 11571178483 | 22 passed |
| Thirteen-source pins | 11576204678, 11576077535, 11577315781 | 22 passed |
| Discovery admission | 11577503474 | 49 passed |

**114 original tests pass, zero skipped.** Test assertions and imported source
bytes are unchanged. Tests use authenticated real archives as positive inputs;
adversarial mutations and dummy output-producer identities remain test fixtures.
This resolves the four outstanding archive/setup dependencies. It does not turn
the earlier broad discovery result (664 tests, seven setup errors, three skips)
into a passing run. The earlier separate 63-test replay remains distinct.

The offline runner makes three fresh directories outside the repository. It
restores the exact nine- and thirteen-resolved-family catalogs only in those
copies. All resolved family records match the current catalog, including JSON
types. Every other copied source file and the disabled workflow definition
remain byte-identical to dedicated-repository commit
`d03333d5a4c8c503afc06ad295c8292afaaa3ba0`. Original source identities are retained;
no source certificate is transferred to this runner.

## Reproduce

The five small ZIPs, 15 decoded GitHub metadata snapshots and historical catalog
are retained under `inputs/`. Their bindings are rechecked before tests run.
Choose a nonexistent output directory outside the repository:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/recovered_regressions/run.py \
  --out /absolute/path/new-regression-replay
```

The runner makes no network requests. `evidence/report.json` records source
hashes, archive identities, metadata hashes, catalog compatibility, commands,
fixture environment, individual test counts and complete log hashes. Fresh-copy
and original source equality are checked again after testing. The isolation
verifier also authenticates all 531 imported source files and 106 disabled
workflows against original Git objects; zero workflows are active.

## Failures preserved

The first attempt ran 21 four-native tests, with six errors because the original
unit-test producer requires `GITHUB_WORKFLOW`. The final runner supplies the
explicit label `OFFLINE_TEST_FIXTURE_NOT_GITHUB_ACTIONS` only to that suite.
It does not spoof an actual workflow or alter real archive metadata. All
inherited `GITHUB_*` variables are removed from these offline test processes.

The second attempt passed all original suites, including all 49 discovery
tests. The runner nevertheless rejected the final log: an intentional duplicate
ZIP-member warning separated one test header from its `ok`. The parser now
counts unique test headers and requires their count to match the final unittest
total, a successful process exit and a bare `OK` (no passing skips). Original
warnings and both failed-attempt logs are preserved under `evidence/`.

No live state, positive execution eligibility, gas funding, complete economic
costs or NQC profit is established. The MXN 2,000 cumulative gas-only policy and
all existing economic classifications remain unchanged. Census remains open;
see `../CLOSEOUT.md` for the material coverage, execution and review requirements.
