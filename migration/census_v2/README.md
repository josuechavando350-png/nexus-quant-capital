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
- Historical D11 core artifact `11518151377` and D12 artifact `11519153831`
  have now been recovered. Every canonical D11 source was decoded: **1,045,459**
  rows. A derived view of 67 Aave reserves preserves the original provider
  predicate; it does not replace the full capital universe.
- The complete D11 producer path has now been reproduced in a fresh build copy:
  all **nine original files are byte-identical**, with **1,045,459 sources**.
  Both verification processes reimport the authentic D08/D09 inputs. The run
  took 371.5 seconds with peak child RSS 7,309,316 KiB. The adapter pins the
  original role-scoped importer separately from the imported address-only
  implementation; its source tree and all deviations are recorded. Historical
  commit/tree parameters are not the new producer identity or certification.
- The unchanged D12 Rust producer was executed on authenticated D08/D09 data
  and that derived view. All **474 actionability records** and **432 capital
  dispositions** are byte-identical to the historical artifact. Portfolio
  claims/resources/conflicts agree; producer commit, tree and their dependent
  portfolio commitment differ and are recorded explicitly.
- V2 classification covers all 474 pairs: **42 non-executable at the pinned
  state**, **432 insufficient evidence**, **zero executable value admitted**.
  The 42 are 12 disabled-collateral pairs and 30 zero-sized PFT outcomes.
  Insufficient evidence is not proof of universal economic impossibility.
- The source-universe file resolves 13 families for discovery/readiness.
  Its scope is `SOURCE_UNIVERSE_READINESS_ONLY`; D11 terminal closure is false.
  The recovered D11 core itself also explicitly withholds terminal Census closure.
- Five later historical winner archives were recovered: 139 liquidation events
  in 127 transactions, normalized receipts, integer legs and a two-transaction
  oracle report. Their failed parent runs remain failed. New raw RPC evidence
  corroborates 123 receipts through BlockPI and 87 through dRPC; the same 87
  match across both operators. A new scan covers 81,920 contiguous blocks and
  reconstructs 42 event legs. A network access denial stopped acquisition;
  full-window two-operator coverage remains false. See `HISTORICAL_RPC.md`.

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
| Capital Truth | D11 core recovered and fully decoded; its own terminal-capital flag is false. Conditional D12 replay proves zero admitted principal funding. Own-gas accounting is linked to each V2 candidate; balance/authenticity and execution integration remain unproven. | Integrate a separately versioned gas-only policy, authenticate balance/cost basis, external principal/fees/obligations, then produce and independently replay terminal D11. Historical zero-capital results cannot be relabeled. |
| Execution and Economic Truth | D12 actionability/capital dispositions reproduced; 43 required underlying assets remain transfer-blocked. Full costs and monetizable routes are unproven. | Prove admissible token behavior, routes, complete costs, conservative executable margins and resource/conflict limits for each scoped candidate. Treat insufficient evidence explicitly. |
| Temporal / competitive evidence | Five later winner archives recovered and partial new RPC evidence reconciled. Original D15B episode/censored/economic ledgers remain missing. The separate 857-account temporal study lacks 6,720 of 7,200 blocks. | Restore authorized RPC access, finish the missing source ranges/receipts and recover authentic censored/decision-time evidence; assess competition/inclusion with uncertainty. Do not combine different study populations. |
| Final independent closure | Final Census authority lock remains `BLOCKED`, with no pinned terminal stages. D16 aggregate evidence does not establish positive capture. | Independent reconciliation of each authority, complete candidate classifications, treated material unknowns, failure/mismatch ledgers and reproducible exact evidence. Negative economics remains an admissible result. |

The D15B transport artifact is `11504276505`, run `37669899465`, SHA-256
`aff472236ff5177f123e4a6ccc95d4dae5fb37833f8645984116c407c179d790`.
Its archive contains three members, including the evidence JSON and certificate;
raw detail hashes are commitments to unavailable data, not replacements for it.
Later RMC-016 winner archives are separate acquisitions; they do not satisfy
the missing original D15B file hashes or reconstruct its censored opportunities.
Its 29,998-account historical aggregate must not be confused with D09's 246,929
accounts or the separate 857-account temporal study.

Read-only recovery inspection found the existing source device offline. The
DigitalOcean recovery snapshot `248761092` is available; no SSH key is present
in this execution environment. Reconnecting the existing machine or supplying
its raw evidence is necessary to continue that recovery path. No new server,
subscription, live transaction or gas expenditure was made.

Public historical RPC recovery was attempted through supported read methods.
All collectors stopped at `2026-10-09T17:13:21Z` on a transport 403; the tool
reported network approval cancellation. Completed responses, acquisition
times, interruptions and failures are preserved. No access-control workaround
was attempted. Partial results cannot be promoted to complete coverage.

## Validation limits

See `evidence/validation.json` and the preserved logs for exact commands/results.
The broad historical Python discovery was not green: 664 tests ran, seven setup
errors and three skips. Five setup errors require explicit real-artifact CLI
arguments; two bind historical source-catalog blobs that differ from current
catalog bytes. They were not patched or counted as successes.

The pinned Rust **1.98.1** compiler was repaired from its exact SHA-verified
official package: the local LLVM shared library had been truncated. The original
workspace now passes **528 tests**, the PFT actionability bridge **9**, and the
new streaming consumer **6**; no toolchain substitution was used. The initial
SIGBUS remains recorded as resolved, not erased. Original Git objects now pass
isolation verification against all 637 imported entries and original refs.

The original monolithic D11 builder and two memory-only attempts exhausted
the 8 GiB limit; these failures remain recorded. A fresh-copy adapter now
separates bundle validation from upstream input lifetimes, compares regenerated
JSONL without duplicate large buffers, and pins the historical role-scoped
importer. Full D08/D09 reimport, two complete verifications and all-nine-file
byte parity pass. This resolves historical D11 reproduction, not terminal
capital admission or new producer authority. See `d11_memory/README.md` and
`evidence/d11-memory/full-replay-parity.json`.

The final adapted capital crate passes **256 tests**, including the original
cases and new comparison/replay regressions. The memory-only intermediate run
exposed 44 repeated token addresses with no duplicate token/role keys; its
address-only importer changed source IDs and commitments. That mismatch is
preserved, not relabelled as parity. The D11 main archive still exceeds the
connector 512 MiB limit; the separately pinned core is recovered, not the
entire main envelope.

Passing the new read-back and accounting tests cannot close any of the gates
above. No completion percentage or profitability forecast is justified by the
current evidence.

## Reproducing the recovered terminal evidence

Use `CARGO_TARGET_DIR` outside the repository for every Rust command. Keep
`PYTHONDONTWRITEBYTECODE=1` for historical Python consumers. Do not install
build outputs into the immutable source trees. Commands and limits are in
[CLOSEOUT.md](CLOSEOUT.md) and `evidence/validation.json`.

`capital_stream` validates every source with the original canonical decoder,
checks global identity/key uniqueness, exact producer/anchor/size/count/hash,
and limits row size and retained reserve count. Its selection is only the
non-candidate-specific necessary predicate of the unchanged Aave promotion
function; that function still checks each candidate's debt asset and capital
feasibility. Excluded flash-swap rows are fully decoded before exclusion.

`verify_terminal_recovery.py` binds the actual core/archive/API snapshots and
checks exact replay parity plus the explicit portfolio mismatch inventory.
`classify_historical_candidates.py` joins each real pair to its exact capital
requirement, asset amounts, original token blockers and gas-accounting journal.
No live wallet is inferred from the peso authorization. The empty journal means
no funding evidence was supplied to this work; it is not proof that a wallet
has a zero balance. Unknowns have required evidence and falsification criteria.

The Decision-Time ledger records the original state timestamp separately from
this recovery's classification time. Original receipt times remain unknown.
The gas authorization of October 9 is never assigned to October 1 candidates.
The gas engine also rejects accounting events before the authorization date;
precise intraday authorization and witness authenticity still need independent
verification before any operational use.
