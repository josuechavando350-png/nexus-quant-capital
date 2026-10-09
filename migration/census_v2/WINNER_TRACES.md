# Historical winner traces: authenticated read-back with explicit mismatches

All 127 original winner records and cast logs are recovered. The archive has
828,195 bytes and SHA-256
`9323bf262e1f9695fcfc68a96a10b1a2e987544d3395c046aa31b13271a60c92`.
Every record matches the original core ledger byte for byte; every log matches
its original `cast_log_sha256`. The 255-member transport includes one manifest.
This is offline interpretation of retained producer output, not a new fork
execution or independent authentication of the original RPC run.

| Observation | Result | Treatment |
| --- | --- | --- |
| Complete parsed call trees | 127 transactions, 15,001 call frames | One successful root and matching transaction gas per log; no truncated tree accepted |
| Reverted frames | 20 | Failure ledger retains call and parent coordinates; their subtrees do not establish settled execution, and gas is not charged twice |
| Returned oracle quotes | 719 | All target the pinned historical Aave oracle; four occur within reverted ancestors |
| Quote versus block-end comparison | One mismatch | Preserve both values and state scopes; no automatic replacement of execution prices |
| Rendered native-value fields | 350 | Observations only; forwarding, root/delegate contexts and ownership prevent summing them as net flows or builder payments |
| Whole-transaction competitor gas | 448369976498898050 wei | Matches the original 127-transaction ledger, counted once per transaction |
| NQC executable admission | Zero | Every transaction retains explicit financing, cost, decision-time, capture and authority gaps |

## Price-scope mismatch

Transaction `0x8f0ab391fcf8c1454f9665460a5d675a0821b4a53e01301c17bc239ac2fcad65`,
block 25,888,740, log `0007-8f0ab391fcf8c145.cast.log`, line 233:

- WBTC asset: `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599`.
- Returned trace quote: **7691878258344** raw oracle units.
- End-of-block reference: **7652143127459** raw oracle units.
- The call has successful ancestry. The cause of the difference, and whether
  this value priced an actual liquidation leg, remain unproven.

This is recorded in `price-scope-mismatch-ledger.jsonl`. It prevents treating
block-end oracle vectors as demonstrated transaction execution prices. It does
not by itself prove an incorrect liquidation amount, an oracle update within
the block, or a revised profit figure. Full net P&L stays null.

## Evidence and reproduction

The checkpoint version 4 preserves the original trace archive. The repository
stores the five observation/failure ledgers plus the
report in `evidence/winner-traces/`. Records carry block hash, transaction hash,
trace hash, member and line where applicable. The report binds input archives,
consumer source and every output hash. The enclosing Git commit/tree identifies
the new producer; the producer does not certify itself.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_winner_traces.py \
  --archive "$CHECKPOINT/original-winner-traces.zip" \
  --core "$CHECKPOINT/original-temporal-core.zip" \
  --output "$FRESH_TRACE_READBACK" -v
```

Six checks cover actual totals and the mismatch, reverted ancestry, missing
returns despite a success footer, multiple roots, duplicate gas and a reverted
root. All pass. The command requires a new output directory.

Original cast records contain compact receipt projections, not full raw receipt
responses. This recovery therefore does not close the four missing raw receipts
or increase independent receipt coverage. No new RPC call, cast execution,
signing, broadcast, gas spending or capital permission was performed.
