# Original server: D15B/D16 ledgers recovered

The 71-member core archive is fully recovered and hash-authenticated. The
previously missing D15B episode/censored ledgers and D16 transaction economics
match their historical commitments. **D16's four output files reproduce byte
for byte. Census remains open.** D15B's larger producer inputs were located
and hashed remotely, but a second connection interruption left their transfer
incomplete; the D15B producer has not been rerun.

## Verified scope

Source device: 97869e36-ef95-481f-ac75-85ab90bce0e7.
Source directory: /root/workspace/RMC015_REPLAY_30D.
The copy-only core archive contains 988,991 bytes, SHA-256
cc51fc5c9a3ea76daa59d42cc5eef6aed3909955d1bf5a68795ac3bf5b210ede.
All 70 original files match the recovery manifest. Material authority files
separately match previously pinned historical commitments. The recovery
manifest is a transport inventory, not independent certification.

| Check | Result and boundary |
| --- | --- |
| Temporal accounts | 29,998 distinct accounts: 556 definite, 29,442 censored, disjoint. This reconciles the existing partition; it does not rederive the full original envelope. |
| Episodes | 571 unique records: 432 left-censored starting states and 139 observed liquidation events in 127 transactions. Starting states are not arrivals. |
| Source bindings | All seven D15B input summaries and both terminal ledgers match historical commitments. Full upstream trigger/oracle/risk reconstruction is not rerun. |
| Later witness comparison | All 139 event coordinates, quantities and borrower/liquidator identities agree with the later decoded-legs archive. No extra transactions. |
| Economic reconstruction | Independent integer calculations reproduce event/transaction principal, oracle collateral, gross edge, receipt gas and all 30 daily buckets. |
| Gas conservation | All 127 transactions match the prior economic ledger: 448,369,976,498,898,050 wei, counted once per transaction. Competitor gas, not NQC expenditure. |
| D16 producer | Four byte-identical files in a fresh tree. Only the R path assignment is adapted. All other staged inputs remain unchanged. Original script Git identity remains unauthenticated. |
| V2 disposition | All 29,998 temporal candidates receive explicit INSUFFICIENT_EVIDENCE reasons; zero positive executable value. The separate D09 snapshot's 42 non-executable / 432 insufficient pairs remain unchanged. |

Gross oracle edge totals 138,045.17469031 USD; observed winner gas totals
1,144.134260592713842029 USD. The difference subtracts **only** gas. Eight
historical cost categories are explicitly omitted; full NQC execution costs,
financing and capture remain unproven. The 83 positive / 44 nonpositive
after-only-gas observations are not complete profit classifications, forecasts
or proof of either V2 revenue hypothesis.

All 123 historical price rows contain a zero base_fee_per_gas field. This is a
recorded limitation; that field is never used to decompose or price gas. Gas
comes from receipt effective gas price times gas used. Price vectors are bound
to event block hashes, but reserve-decimal invariance and original acquisition
RPCs are not independently replayed. Complete net P&L remains null. Historical
unknown_count=0 is not promoted to a global V2 uncertainty claim.

## Reproduction

The persisted nqc-server-recovery-checkpoint-20261009.zip version 1 contains
the complete original core archive, candidate classification ledger, two
historical reference archives and earlier partial-transfer evidence. Its
identity/digest are in evidence/server-recovery/retention.json. Extract it
into a fresh directory and run from the repository root:

    python3 migration/census_v2/reconcile_temporal_core.py \
      --core "$CHECKPOINT/original-temporal-core.zip" \
      --prior migration/census_v2/evidence/economics/replay/winner-economic-ledger.jsonl \
      --output "$NEW_READBACK"
    python3 migration/census_v2/replay_server_producers.py \
      --core "$CHECKPOINT/original-temporal-core.zip" --stage d16 \
      --output "$NEW_D16_REPLAY"
    PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_temporal_core.py \
      --core "$CHECKPOINT/original-temporal-core.zip" \
      --prior migration/census_v2/evidence/economics/replay/winner-economic-ledger.jsonl -v
    PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_server_recovery.py \
      --root "$CHECKPOINT/partial-core" \
      --d15b "$CHECKPOINT/original-d15b-37669899465.zip" \
      --legs "$CHECKPOINT/winner-legs-original.zip" -v

Eleven new real-input/adversarial checks pass: historical totals and nonclaims,
corrupted transport/summary, changed prior costs, wrong authority domain,
omitted/duplicated events, changed quantities/actor, boolean confusion and
duplicate JSON fields. Nine isolation tests pass. Rust code is unchanged;
the broader historical test failures remain recorded.

## Interruption history and remaining recovery

First ping failure: 2026-10-09T19:32:08.610523+00:00, timeout with no device
response. Its 393,216-byte prefix and 39 complete files remain preserved.
The user restored access; the complete core was then verified.
Second ping failure: 2026-10-09T19:40:56.34135+00:00, same error. A stale online
label did not establish working access. Both failures have separate records.

Resume /tmp/nqc-census-recovery-20261009/d15b-terminal-inputs.zip on the same
device at byte 262,144. Expected size: 11,691,061; remotely computed SHA-256:
e29c4a3cde343268df165c83e6f98cfcf55799734c4e58f1f4ab8d45c2ac4d3f.
It contains the 91,018,538-byte starting-risk ledger and 11,365,714-byte
candidate envelope; both remote hashes match authenticated core summaries.
Authenticate complete local bytes before using --stage d15b --inputs.
The 46,543,521-byte full-block oracle transition ledger was also located,
but it was not recovered or rederived.

Original files/repository were not modified. No new RPC acquisition, network
denial workaround, subscription, live execution or gas expenditure occurred.
The MXN 2,000 gas-only amendment remains authoritative; legacy zero-capital
fields are preserved solely as historical evidence.
