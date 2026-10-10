# Additional historical receipt and successor-window evidence

This supplement salvages the new evidence from the separate research branch in
`josuechavando350-png/nexus-engine` into the dedicated NQC repository. It is based
on NQC commit `81a268b93841f5d5df5970c547363c6c00dd76ef`. The existing V2 gas policy,
economic ledger and immutable source import are unchanged. It does not repeat
the already completed D06 or D11 reconstruction.

## What this adds

| Evidence | Result | Limit |
| --- | --- | --- |
| Tenderly receipt observations | All 127 receipts agree with the archived dRPC checkpoint for 139 liquidation events; zero normalized mismatches. | The original dRPC workflow failed after producing the retained checkpoint. Its overall result stays failed. |
| Join to the existing V2 economic ledger | All transaction identities, block positions and gas amounts agree. 123 previously known senders match; four previously unknown senders now have separately recorded receipt observations. | No historical ledger is rewritten. Every execution classification remains `INSUFFICIENT_EVIDENCE`. |
| Gas accounting | Whole-transaction historical gas remains 448369976498898050 wei, counted once per transaction. Incremental gas charged by this supplement is zero. | This is historical competitor gas, not NQC spending, funding or demonstrated profit. |
| Complete successor window | Nodies and Tenderly agree on two executed liquidation events across blocks 26,095,352–26,102,551; all 7,200 blocks are covered. | This is the window after the original anchor, not the original 215,036-block historical study or its oracle coverage. |
| Fixed-cohort membership | Neither executed event belongs to the original 857-account cohort, reconstructed privately from authenticated D08/D09 inputs. | Zero observed executions does not prove zero eligible unexecuted opportunities, detection quality or capture. No future winner is used to select the cohort. |

The recordings preserve **canonical JSON of decoded RPC results**, not original
HTTP request/response bytes. Acquisition manifests have overall start/end times;
they do not retain per-request receive times. Historical decision-time availability
and independence of the underlying nodes are unproven. Original fields named
`raw_exchanges_sha256` identify the retained decoded JSON, not HTTP transport bytes.

`origins.json` pins all nine copied files by size, SHA-256 and Git blob. Eight
come unchanged from source research commit
`0200519ef1969accf274898162812c4bbe7e508d`; the cohort selector is the separate
original blob `5542bbec0840335994cbbab272e6228756ba6eb0`. Source identities stay
source identities. None acquires a new certification by being copied here.

## Reproduction

Use the real, authenticated original artifacts, not synthetic replacements:

| Argument | Original artifact ID | SHA-256 |
| --- | --- | --- |
| `--events` | 11524139188 | `6b4098c1acf153106ac5b67d2c5c7db5cd0295a16c782ad8c34ae75303306204` |
| `--drpc` | 11524199698 | `182b5e81b00ca04e53c9193c1496a725dc152ade9a17d3ab2dfaeb5045ac86b6` |
| `--d08` | 11237887761 | `9431ea07144ae78e68e0ffcc7f650fa32068ee63fb53ca41ff8a062b87845913` |
| `--d09` | 11159396055 | `9aa6a4beb3ebc90f40d07d1889f84c1bcf94b3dea90b0e7b596dc6ff70fda0f6` |

From the repository root, define `EVIDENCE` as their absolute directory and use a
new output path outside the checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/additional_evidence/reconcile_additional.py \
  --events "$EVIDENCE/11524139188.zip" --drpc "$EVIDENCE/11524199698.zip" \
  --d08 "$EVIDENCE/11237887761.zip" --d09 "$EVIDENCE/11159396055.zip" \
  --out "$EVIDENCE/new-supplement-report.json"

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=ci/nqc-census:migration/census_v2:migration/census_v2/additional_evidence \
RMC016_EVENT_ARCHIVE="$EVIDENCE/11524139188.zip" \
RMC016_DRPC_ARCHIVE="$EVIDENCE/11524199698.zip" \
python3 -m unittest discover -s migration/census_v2/additional_evidence -p 'test*.py' -v
```

Two complete offline reconciliations produced byte-identical reports. The 33
supplement tests passed without skips: 13 receipt checks, 14 window checks and
six V2 integration guards. Nine isolation tests and 19 existing gas-policy tests
also passed. The isolation verifier authenticated all 531 imported source files,
106 disabled workflows and original Git objects; there are zero active workflows.
The exact commands and scope are in `evidence/validation.json`.

The first V2 integration attempt rejected four `null` historical payer fields.
Those unknowns were investigated rather than replaced in the existing ledger.
The final join verifies the 123 known payers and appends four distinct observations
to this report. Transaction identity and every gas amount remain mandatory checks.

The broader historical suite was not rerun or relabelled green. Rust code was
unchanged and Rust tests were not rerun for this supplement. No network acquisition
is performed by this consumer, no workflow is activated and no transaction is
sent. Original 30-day log/oracle coverage, token execution compatibility, complete
routes/costs, authenticated gas funding and independent producer review remain
open. Census is **not closed** by this supplement.
