# Original server: D15B/D16 ledgers recovered

The 71-member core archive is fully recovered and hash-authenticated. The
previously missing D15B episode/censored ledgers and D16 transaction economics
match their historical commitments. **D15B's three outputs and D16's four
outputs reproduce byte for byte. Census remains open.** D15B's complete inputs
are now recovered and authenticated; its producer agrees in both environments.
Two upstream candidate/state producers and three start-risk producers also
reproduce their historical outputs. Retained oracle observations are rederived
with explicit single-provider coverage gaps.

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
| Source bindings | All seven D15B input summaries and both terminal ledgers match historical commitments. Retained candidate/state/risk computations are rerun; original acquisition and full upstream reconstruction remain unproven. |
| Later witness comparison | All 139 event coordinates, quantities and borrower/liquidator identities agree with the later decoded-legs archive. No extra transactions. |
| Economic reconstruction | Independent integer calculations reproduce event/transaction principal, oracle collateral, gross edge, receipt gas and all 30 daily buckets. |
| Gas conservation | All 127 transactions match the prior economic ledger: 448,369,976,498,898,050 wei, counted once per transaction. Competitor gas, not NQC expenditure. |
| D16 producer | Four byte-identical files in a fresh tree. Only the R path assignment is adapted. All other staged inputs remain unchanged. Original script Git identity remains unauthenticated. |
| D15B producer | Three byte-identical files executed locally and on the original server. Both use identical pinned source bytes and complete inputs; this is not independent certification. |
| Candidate envelope / state replay | Three reproduced outputs: 29,998 candidates and 134,275 relevant mutations. D08/D09 catalogs match original archive-member hashes; both retained pool/token provider streams match historical semantic hashes. |
| Start-risk reconstruction | Five reproduced outputs: 103,778 position accounts, 27,850 borrowers, 432 liquidatable at the start. All 27,850 direct comparisons match exactly; retained borrower provider ledgers agree. |
| Oracle observations | All 4,394 retained chunk digests recomputed. dRPC covers 215,036 blocks; Nodies covers 4,650. No mismatches in overlap; 210,386 blocks lack second-provider observations. |
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
to event block hashes. The recovered collector issues eth_call against that
block hash; it does not reconstruct the transaction pre-state or record when
NQC received the price. These block-state prices cannot establish a pre-winner
signal. Reserve-decimal invariance and original acquisition RPCs are not
independently replayed. Complete net P&L remains null. Historical
unknown_count=0 is not promoted to a global V2 uncertainty claim.

## Reproduction

The persisted nqc-server-recovery-checkpoint-20261009.zip version 3 contains
the complete core, D15B-input and retained-oracle archives, candidate
classification ledger, replay reports, two historical reference archives
and earlier partial-transfer evidence. Its
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

The interrupted transfer of d15b-terminal-inputs.zip resumed at byte 3,932,160
and is now complete. Size: 11,691,061; verified remote and local SHA-256:
e29c4a3cde343268df165c83e6f98cfcf55799734c4e58f1f4ab8d45c2ac4d3f.
It contains the 91,018,538-byte starting-risk ledger and 11,365,714-byte
candidate envelope; both remote hashes match authenticated core summaries.
Both original input hashes and all ZIP CRCs pass. The 46,543,521-byte oracle
transition ledger is also recovered and rederived byte for byte from retained
chunks; its hash is bbad1eb1a6fba097bd642b1abb5aa417fc86686dfe271da7c66017609bd3c519.

Original files/repository were not modified. No new RPC acquisition, network
denial workaround, subscription, live execution or gas expenditure occurred.
The MXN 2,000 gas-only amendment remains authoritative; legacy zero-capital
fields are preserved solely as historical evidence.

On the next reconnect a ping succeeded at 2026-10-09T19:52:38.951Z. Fifteen
262,144-byte chunks are now preserved (3,932,160 bytes). A third ping failed at
2026-10-09T19:58:26.481494+00:00. Four Remote agent processes were observed,
all reading /dev/null and writing /tmp/nqc-remote.log. Their causal role in
the interruption is unproven. No process was terminated. The attempted log
diagnostic returned no result. See third-recovery-attempt.json.

## Successful resumed recovery

The user started nqc-remote.service; ping succeeded at 20:16:11.814Z on October
9. At 20:37:13Z the service had zero restarts and exactly one Remote agent node
was observed. This establishes working access during the recovery, not the
cause of earlier interruptions or a guarantee of future availability.

The complete oracle archive has 34,422,855 bytes and SHA-256
d73716fa61495906c9cbfdcc4442c25804cd47550a9de0f4a32ca287459e2e50.
The verifier reconstructs each 67-asset vector and its observation digest,
rederives the original chunk manifest and transition ledger, compares every
overlapping provider observation and reconciles all 123 liquidation price
vectors and their block hashes through the next block's parent hash.
The chunks contain block-state observations selected by block number. They
do not prove the final block's own hash, independent canonical lineage,
transaction pre-state, or when Nexus received those observations.

Six actual-data/adversarial tests pass: complete retained-data reconciliation,
missing block, missing asset, duplicate asset, boolean index and a changed
interior timestamp despite unchanged endpoint records. Nine isolation tests
pass; the isolation verifier additionally checks original Git objects for
531 source files and retains 106 disabled / zero active workflows. No Rust
code changed, so the earlier broad-suite limitations remain in force.

Run D15B locally with the complete recovered archives:

    python3 migration/census_v2/replay_server_producers.py \
      --core "$CHECKPOINT/original-temporal-core.zip" --stage d15b \
      --inputs "$CHECKPOINT/d15b-terminal-inputs.zip" --output "$NEW_D15_REPLAY"
    python3 migration/census_v2/check_oracle_chunks.py \
      --archive "$CHECKPOINT/original-oracle-evidence.zip" \
      --core "$CHECKPOINT/original-temporal-core.zip" --output "$NEW_ORACLE_REPORT" -v

The upstream replays require the retained original server tree; their large
raw inputs are inventoried by hash, not all copied into the local checkpoint:

    python3 migration/census_v2/replay_temporal_upstream.py \
      --source-root /root/workspace --core "$CORE" --output "$NEW_UPSTREAM_COPY"
    python3 migration/census_v2/replay_start_risk.py \
      --source-root /root/workspace --core "$CORE" --output "$NEW_RISK_COPY"

Reports, original reviewed scripts, adapted scripts and stdout/stderr for both
remote replays are preserved in separate small archives. Each run used a fresh
copy and verified unchanged original input hashes after execution. Script Git
provenance, original RPC acquisition and independent new-producer certification
remain unproven. Capital admissibility, native gas authentication, token/route
compatibility, full costs and capture evidence still prevent Census closure.
