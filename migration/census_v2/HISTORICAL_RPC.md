# Historical winners: recovered evidence and bounded RPC reconciliation

**Later recovery, October 9:** the normal read-only endpoints are accessible on
the authorized original server. A fresh BlockPI scan covers all 215,036 blocks
and matches all 139 original events; a fresh dRPC acquisition covers all 127
receipts, with complete semantic log parity against Tenderly. Exact request and
response bodies and current per-request receive times are preserved. See
[full_window_recovery/README.md](full_window_recovery/README.md). The partial
observations and access failures below remain as historical records. This
resolves these event/receipt gaps, not oracle coverage or Census certification.

No Census, capture or profitability certification is issued.

Five original archives were recovered and authenticated against GitHub run,
artifact, commit/tree and inner-manifest evidence. They contain 139 Aave V3
Ethereum liquidation events in 127 successful competitor transactions, the
complete original dRPC normalized receipt checkpoint, a partial Blockscout
checkpoint, 139 decoded integer liquidation legs, and a two-transaction oracle
report. The two failed acquisition runs remain explicitly failed. A complete
substage is not a successful parent run or independent certification.

Scope: Ethereum blocks **25,880,316–26,095,351**. Original events were discovered
through Blockscout; this archive is single-operator coverage. It is not the
missing D15B episode/censored/economic ledgers and does not prove when Nexus
first observed an opportunity.

The new collector stores exact request/response bytes, HTTP status or transport
failure, provider attribution, timestamps, digests and append-only checkpoints.
It allows only read methods, has a finite call budget, spaces requests, and stops
on access/rate failures. Interrupted runs resume into new directories only
after verifying completed responses; original receipt times are preserved.

## Actual new observations

| Evidence | Verified result | Unresolved scope |
| --- | --- | --- |
| BlockPI receipts | 123 of the original 127 match the complete historical checkpoint | 4 receipts missing from this new source |
| dRPC receipts | 87 of 127 match | 40 missing from this new acquisition |
| Both new operators | Same 87 receipts, exact normalized values and event identities | Full 127-transaction two-operator consistency is false |
| BlockPI log scan | 81,920 contiguous blocks, 25,880,316–25,962,235; 42 raw events and decoded legs match | 133,116 blocks remain; full-window independent coverage is false |

At `2026-10-09T17:13:21Z`, all three collectors stopped on a transport
`Tunnel connection failed: 403 Forbidden`; the execution tool also reported
that network approval was cancelled. No workaround or alternate RPC path was
attempted after that access denial. Before it, dRPC rejected both a full-range
and an 8,192-block log query with its free-plan range error; those failures are
preserved and not counted as log coverage.

The original normalized receipts sum to **448369976498898050 wei** of gas paid
by historical winners. This is not Nexus gas spending, profit, current gas
funding, USD conversion, or complete transaction cost. Failed transactions,
private builder payments, financing obligations and complete route cashflows
remain unproven. Two branded RPC operators do not prove independent underlying
execution nodes.

Acquisition on October 9 cannot establish availability before the October 1
anchor or before earlier transactions. The new Decision-Time ledger records
actual receipt times; original pre-execution receipt times remain unknown.
The API snapshot files preserve origin metadata but not precise response
receipt times; their `snapshot_recorded_at` must not be interpreted as those
missing receipt times.

## Reproduction

`NQC_Census_Winner_RPC_Evidence_20261009.zip` contains the five original ZIPs,
all failed/interrupted/resumed raw acquisitions and an inventory of 1,046
files. Its SHA-256 is
`fdffde6d1dc14ab648f42033661a3667dc7b2a93e761c83f918f36d8c0849195`.
Extract it into a new evidence directory. API snapshots and consumers are
versioned in this repository. Offline reconciliation needs no network:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/verify_winner_recovery.py \
  --archive-root "$EVIDENCE" --metadata migration/census_v2/evidence/winner-api \
  --rpc-dir "$EVIDENCE/historical-rpc-drpc-receipts-resumed" \
  --rpc-dir "$EVIDENCE/historical-rpc-blockpi-receipts-resumed" \
  --rpc-dir "$EVIDENCE/historical-rpc-blockpi-logs-resumed" \
  --allow-partial --out "$NEW_REPORT"
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_winner_recovery.py \
  --archive-root "$EVIDENCE" --metadata migration/census_v2/evidence/winner-api \
  --rpc-root "$EVIDENCE"
```

Without `--allow-partial`, the verifier rejects these incomplete acquisitions.
With it, every successful raw response is replayed and reconciled, every final
failure remains visible, and all full-coverage/certification flags remain false.
Restored authorized RPC access is necessary to finish the missing acquisition;
it would still not replace censored-opportunity or economic evidence.
