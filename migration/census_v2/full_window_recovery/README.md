# Complete executed-liquidation window and full receipt parity

The new read-only acquisition completed the original 30-day event scan and
receipt comparison on October 9, 2026. This resolves the earlier partial log
scan and partial dRPC receipt acquisition. Their original failures remain in
history; the 7,200-block successor study is a separate window.

| Evidence | Verified scope |
| --- | --- |
| BlockPI log scan | All 215,036 blocks, 25,880,316–26,095,351, in 210 contiguous shards; 213 RPC requests including chain/anchor checks. |
| Original discovery agreement | All 139 event commitments and 127 transaction identities match the authenticated Blockscout archive. |
| Liquidation amounts | All 139 raw event logs decode and match original event commitments. |
| New dRPC receipts | All 127 original transactions match the original normalized checkpoint. |
| Complete receipt/log comparison | All 127 new dRPC semantic receipts, including every log and sender/recipient, match the retained Tenderly observations. |
| Historical gas | 448369976498898050 wei, counted once per transaction; not NQC expenditure. |

The BlockPI scan ran from `2026-10-09T22:23:34Z` to `22:27:27Z`; dRPC receipt
collection ran from `22:24:03Z` to `22:26:21Z`. Each new RPC request and response
JSON body is preserved with HTTP status, response headers, exact byte digests
and send/receive timestamps. These are current acquisition times, not evidence
that NQC observed these historical opportunities before their execution.

The collector and four dependencies were copied byte-for-byte from dedicated
repository commit `cb4db600301c49196eac6e3b45e308c8b1d09e8b` into a fresh temporary
directory on the authorized original server. Source identities are rechecked
against Git objects. The normal public endpoints were used after a successful
read-only chain preflight. No old repository was written, no proxy or alternate
access-control mechanism was introduced, and no workflow, subscription, signing
or broadcast was performed. The unchanged collector stops on access/rate errors.

## Preserved evidence and reproduction

`complete-historical-evidence.zip` contains 699 files (665,007 compressed bytes),
SHA-256 `f5683de132f26671e62ee31a82c9e1c05fcaf2ff8e7a0a8ad2a0c447bc9efeeb`.
It includes both complete acquisition directories, preflight records, collector
sources and their manifest. It contains no private keys or credentials.

Extract this exact ZIP into a fresh directory outside the repository and use
its absolute path as `CAPTURED`. The readback verifies the archive hash, entire
extracted inventory and every file byte before consuming the records:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/full_window_recovery/reconcile.py \
  --evidence "$CAPTURED" --out /absolute/path/new-full-window-report.json
PYTHONDONTWRITEBYTECODE=1 NQC_FULL_WINDOW_EVIDENCE="$CAPTURED" \
  python3 -m unittest discover -s migration/census_v2/full_window_recovery \
  -p test_reconcile.py -v
```

Seven real-input/adversarial checks pass, zero skips. They reject omitted empty
shards, missing/duplicate/reordered receipts, changed logs and foreign producer
identity. Two complete offline readbacks are byte-identical. Isolation preserves
531 original source files, 106 disabled workflows and zero active workflows.
Rust code was unchanged and Rust suites were not rerun.

## Remaining boundaries

This is complete coverage of executed events for the stated pool and window,
not all eligible or censored opportunities. It does not complete the separate
67-asset oracle reconstruction: 210,386 secondary-provider oracle blocks remain
missing. Canonical header lineage, distinct underlying-node independence,
original decision-time observations, token execution compatibility, complete
costs, NQC funding/capture and independent review remain separate requirements.
The MXN 2,000 policy and all original economic classifications are unchanged.
Census is not certified by this evidence consumer.
