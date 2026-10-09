# Census V2 — evidence recovery and bounded own gas

**Census remains open. No economic or operational certification is issued.**
This change records the user's V2 architecture and later gas-only MXN 2,000
authorization, adds bounded read-back consumers, recovers independently acquired
API metadata and reports, and adds an offline gas-accounting model.

Base: `16e352225ba8a6a931834c4edf3d86d9a2924b7d` in
`josuechavando350-png/nexus-quant-capital`. All additions are under
`migration/census_v2/`; historical source and disabled workflows are unchanged.

## What has been established

- New-repository D06 run `37893144639`, artifact `11599957605`: all 4,327 indexed
  members match, the original seed/store is preserved, ten closeout outputs
  match their reruns, and the stored 22-negative-case inventory is consistent.
  This consumer verifies actual output bytes and final API metadata; it does
  not rerun the semantic Rust producer or establish producer-review authority.
- Historical D06–D10 transport pins resolve to recovered ZIPs with matching
  SHA-256, API run/commit/tree identities and per-file manifest hashes. Their
  snapshot/transition references agree at Ethereum block **26,095,351**, hash
  `0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781`,
  timestamp `2026-10-01T05:23:35Z`. This is historical scope, not live coverage.
- D08's authenticated summary records 67 Aave markets and 523,424 V2 markets.
  It explicitly records **zero execution-proven-compatible tokens** among
  514,279 token records. State reconstruction is not execution admission.
- D09's authenticated summary records 246,929 indexed accounts, 28,275
  actionable accounts and 400 accounts with health factor below one. Those
  labels do not establish liquidation profitability, financeability or capture.
- The source-universe file resolves 13 families for discovery/readiness.
  Its scope is `SOURCE_UNIVERSE_READINESS_ONLY`; D11 terminal closure is false.
  A successful preflight run with no terminal artifact cannot close D11.

Summary counts above are read from hash-authenticated historical summaries;
this change does not independently reconstruct every position from chain state.
Hash integrity is not semantic truth, current availability or independent
certification. The archived `generated_at` derives from the anchor timestamp;
it does not prove decision-time receipt.

## Files and reproduction

`ARCHITECTURE.md` contains the governing requirements. `capital-policy.json`
records the amendment. `gas_budget.py` rejects over-budget funding, concurrent
overcommitment, nonce/receipt reuse, future witnesses, invalid integers and
non-gas purposes. Replacement accounting retains older higher-exposure variants;
reverted gas consumes balance. All outputs explicitly withhold certification
and executor integration.

The consumers require actual archives and API snapshots. Missing input is an
error, not a synthetic replacement or a skipped integration test. Recover the
original pins in `ci/nqc-census/rmc011-real-source-inputs.json`; the new D06 pin
is in `verify_d06_readback.py`. API snapshots are included in `evidence/` with
their original acquisition bytes. Acquire current metadata independently to
verify origin and artifact expiry. Offline JSON cannot authenticate its own
API provenance.

From the repository root (use fresh output paths):

```bash
python3 -m unittest discover -s migration/census_v2 -p 'test_*.py'
python3 migration/census_v2/check_d06_readback.py \
  --archive /absolute/path/d06-37893144639.zip \
  --metadata-dir migration/census_v2/evidence/d06-api
python3 migration/census_v2/check_historical_inputs.py \
  --archive-root /absolute/path/archives \
  --metadata-root migration/census_v2/evidence/historical-api
python3 migration/census_v2/verify_d06_readback.py \
  --archive /absolute/path/d06-37893144639.zip \
  --metadata-dir migration/census_v2/evidence/d06-api \
  --output /absolute/path/new-d06-report.json
python3 migration/census_v2/verify_historical_inputs.py \
  --archive-root /absolute/path/archives \
  --metadata-root migration/census_v2/evidence/historical-api \
  --output /absolute/path/new-historical-report.json
python3 migration/verify_isolation.py
python3 -m unittest discover -s migration -p 'test_isolation.py'
```

Historical archives are named `d06-original.zip` through `d10-original.zip`.
D06's original ZIP can also be recovered byte-for-byte as
`original-seed/source.zip` inside the new D06 archive. Raw archives are not
committed as large Git blobs. Evidence reports pin their exact transport bytes,
producer commits/trees, metadata and verifier source hashes. The enclosing Git
commit binds the reviewable consumer and its report; these are non-certifying
read-backs, not an upstream authority lock.

## Remaining closure work

| Gate | Current evidence or gap | Required treatment |
| --- | --- | --- |
| New producer authority | New D06 output integrity passes; separate producer review is unproven. | Review exact new producer/adapter and independence before downstream acceptance; preserve original scope. |
| Capital Truth | Thirteen source families resolved for readiness; terminal D11 open. Original Rust model still enforces zero own capital. Own-gas model is offline only. | Integrate a separately versioned gas-only policy, authenticate balance/cost basis, external principal/fees/obligations, then produce and independently replay terminal D11. Historical zero-capital results cannot be relabeled. |
| Execution and Economic Truth | Token transfer compatibility unproven; D12/D13 inputs await predecessor closure. | Prove admissible token behavior, routes, complete costs, conservative executable margins and resource/conflict limits for each scoped candidate. Treat insufficient evidence explicitly. |
| Temporal / competitive evidence | Recovered D15B artifact contains aggregate/certificate files, not the detailed episode/censored/winner/economic ledgers named by their hashes. The separate 857-account temporal study also lacks 6,720 of 7,200 blocks. | Recover authentic raw ledgers and decision-time observations; complete declared temporal scope without future-data leakage; assess competition/inclusion with uncertainty. Do not combine different study populations. |
| Final independent closure | Final Census authority lock remains `BLOCKED`, with no pinned terminal stages. D16 aggregate evidence does not establish positive capture. | Independent reconciliation of each authority, complete candidate classifications, treated material unknowns, failure/mismatch ledgers and reproducible exact evidence. Negative economics remains an admissible result. |

The D15B transport artifact is `11504276505`, run `37669899465`, SHA-256
`aff472236ff5177f123e4a6ccc95d4dae5fb37833f8645984116c407c179d790`.
Its archive contains three members, including the evidence JSON and certificate;
raw detail hashes are commitments to unavailable data, not replacements for it.
Its 29,998-account historical aggregate must not be confused with D09's 246,929
accounts or the separate 857-account temporal study.

Read-only recovery inspection found the existing source device offline. The
DigitalOcean recovery snapshot `248761092` is available; no SSH key is present
in this execution environment. Reconnecting the existing machine or supplying
its raw evidence is necessary to continue that recovery path. No new server,
subscription, live transaction or gas expenditure was made.

## Validation limits

See `evidence/validation.json` and the preserved logs for exact commands/results.
The broad historical Python discovery was not green: 664 tests ran, seven setup
errors and three skips. Five setup errors require explicit real-artifact CLI
arguments; two bind historical source-catalog blobs that differ from current
catalog bytes. They were not patched or counted as successes.

The pinned Rust 1.98.1 toolchain was installed locally, but `rustc -vV` failed
with SIGBUS before compilation. `cargo test --locked -p nqc-census-capital`
therefore did not run. No Rust pass is claimed and no substitute toolchain was
used to evade the pin. This environment failure remains in the failure ledger.

Passing the new read-back and accounting tests cannot close any of the gates
above. No completion percentage or profitability forecast is justified by the
current evidence.
