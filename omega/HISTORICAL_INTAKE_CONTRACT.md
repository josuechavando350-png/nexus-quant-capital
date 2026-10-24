# Historical intake — retained original artifacts

`historical_intake.py` replays three authentic original GitHub artifacts into a
new **partial** ledger. The source repository remains read-only and every
original producer/run/artifact identity remains unchanged.

| Source | Original run | Artifact | Original result |
|---|---:|---:|---|
| 139 events / 127 transactions | 37718661409 | 11524139188 | success, one event operator |
| 127 dRPC receipts | 37719091371 | 11524199698 | **failure overall**, complete dRPC stage only |
| 139 decoded liquidation legs | 37722878737 | 11525823668 | success, single-operator quantities |

The exact retained metadata, ZIP bytes and every member are bound by the
reviewed `evidence/historical-intake-pin.json` digest in code. Metadata were
obtained independently through the connected GitHub API. Offline replay is not
a fresh API authentication or a new observation. Modifying a caller checksum
cannot replace the reviewed pin. ZIP parsing is bounded, in memory, and rejects
unknown members, duplicate names, unsafe modes and changed bytes.

All five transitive original Python source modules are frozen and verified by
Git blob before execution. They are loaded without modifying `sys.modules` or
the original source tree. The original receipt and leg reconcilers run unchanged
on frozen copies. No network, signing or broadcast occurs.

The new schema `nqc.omega.historical-receipt-ledger.v1` is an explicit partial
intake, not a weakened version of the H11 complete-identity ledger. Event identity,
receipt block/transaction index, raw debt/collateral quantities and original
fingerprints are preserved. Gas is counted **once per transaction**. The sum is
448369976498898050 wei, not USD and not profit. All 139 events and 127 receipts
must conserve exactly. The 53 asset pairs are not added across token units.

Twelve same-asset events permit exact raw collateral-minus-debt subtraction.
This is gross token quantity only. Fees, builder payment, prices, route costs and
NQC capture do not follow from that subtraction. Borrower/liquidator SHA-256
fingerprints do not reveal winner addresses or complete protocol position IDs.

Unknown subject/winner/oracle/monetary fields remain null. Complete costs,
independent receipt parity, full independent event coverage and all authorities
remain false. The parent workflow failure is retained. These records cannot be
admitted as H11 full-identity rows by filling missing fields with guesses.

`verify_ledger` recomputes the entire output from original artifacts. It rejects
even self-consistently rehashed fake winners, altered amounts or invented zero
costs. No original D16 per-transaction economics file is fabricated.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/historical_intake.py --output /new/ledger.json
PYTHONDONTWRITEBYTECODE=1 python3 omega/historical_intake.py --ledger /new/ledger.json
PYTHONDONTWRITEBYTECODE=1 python3 omega/historical_pipeline.py --output-directory /new/run
PYTHONDONTWRITEBYTECODE=1 python3 omega/historical_pipeline.py --output-directory /new/run --verify
```

Publication paths must be new. Artifact origin remains the original repository;
reproducing the ledger in NQC does not transfer original certification.
