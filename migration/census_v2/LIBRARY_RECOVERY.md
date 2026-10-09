# Additional historical evidence recovery

Census remains open. Nine pre-existing Library archives were recovered through
the supported file channel. This did not retry the denied RPC or GitHub artifact
download paths. Their file identities, sizes, SHA-256 values and exact reviewed
documents are in `evidence/library-recovery/`.

Two archives contained useful evidence for the existing census. The other seven
contain prior engineering candidates or earlier scoped evidence; they do not
supply the missing original D15B ledgers or the five regression archives. In
particular, the ASTRA D13 package describes a local complete-state EVM reference
and explicitly withholds production historical acquisition and final closure.
Its archived build/test claims were not rerun or promoted here.

## Economic meaning of the historical risk population

The recovered risk package was reproduced using the independently acquired D08
and D09 API identities and authentic ZIPs. Its two unchanged Python programs
were run in a fresh directory with isolated Python and no network acquisition.

- All 246,929 D09 account rows were processed. The 28,275 positive-debt accounts
  retain their complete risk-band partition.
- The 400 accounts with health factor below one contain **12.36050759 USD** of
  protocol-enabled collateral and **58.55276759 USD** of debt at the historical
  oracle valuation. Only one has at least one dollar of enabled collateral;
  the maximum is **2.10893970 USD**. Two have zero enabled collateral.
- An independent SQLite calculation reproduces the selected accounts and exact
  sums. A separate position-level calculation agrees with all 400 collateral
  getters, using D08 reserve prices/decimals and collateral configuration bits.
- All supplied balances, including assets not enabled as collateral, total
  **1,521.04716861 USD**. That amount is not the enabled collateral amount.
- The 326 accounts with health factor in [1, 1.01) remain a historical watchlist.
  They are not liquidatable under this risk criterion.

All five original output files, including the 28,275-row borrower ledger, match
byte for byte. The separate crosscheck output also matches. Output hashes, raw
source hashes, upstream commits/trees and actual commands/logs are retained in
`risk/replay.json`. Only the compact reports are committed; the full deterministic
outputs are reproducible from the preserved original package and archives.

The scope is Ethereum Aave V3 Core at block 26,095,351, hash
`0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781`,
2026-10-01T05:23:35Z. Collateral is not liquidation bonus, realizable cash or net
profit. This snapshot neither proves nor disproves future monthly revenue. The
historical package's target flags remain unchanged; V2 governs current targets.
Separate calculations are not an independent institutional certification.

## Three paired transaction/header/receipt records

The second package contains 18 retained RPC responses: transaction, header and
receipt for three existing winners, each from labels `nodies` and `tenderly`.
Every package member and content-addressed source is checked. Requests, response
hashes, transport metadata and acceptance-marker chains are reconciled. The
recorded acquisition times remain distinct from historical block timestamps.

Both archived providers agree on the full supplied block objects and normalized
transaction/receipt objects. Every receipt log and actor also agrees with the
already recovered BlockPI/dRPC observations for those same transactions. The
three transactions are already within the 127-winner universe; none is added to
the denominator or charged gas again.

| Existing gas component | Wei |
| --- | ---: |
| Full receipt gas for these three records | 1,823,155,915,785,314 |
| Base-fee component | 1,301,339,799,819,240 |
| Priority-fee component | 521,816,115,966,074 |

The last two rows sum to the first. They are an explanatory breakdown, not new
cost deductions. EIP-1559 effective-price arithmetic, transaction index within
the supplied block and actor bindings are checked. Observed top-level values
are 0, 4 and 171 wei; these do not establish total native transfers or builder
payments. Unknown costs, original Nexus observation time and net profit remain
null. All three remain `INSUFFICIENT_EVIDENCE`.

Six representation differences are retained: Nodies supplies a transaction
timestamp absent from Tenderly, and Tenderly supplies `blobGasUsed=0` on these
type-2 receipts. Timestamps must equal the header. Zero blob-field normalization
is restricted to type 2; positive blob quantities and other types fail.

This verifies agreement and arithmetic of retained bytes. It does not reverify
TLS/provider authenticity, infrastructure independence, signed transaction or
header hashes, inclusion proofs, state roots or original producer Git identity.
The original acquisition bundle is referenced by hash but is not materialized;
its acceptance semantic commitments are cross-linked, not recomputed by the
missing original acquisition verifier. Raw data are compared anew here.
The source package's original builder and 20 archived tests were not rerun. The
new consumer has nine passing real-source/adversarial checks. These include
tampering, re-sealed chronology drift, wrong header position, fee drift, missing
pairs, provider disagreement, unsafe blob normalization and offline determinism.

## Reproduction

Use fresh absolute output paths. `ARCHIVES` holds the existing historical ZIPs
and recorded RPC directories. `LIBRARY` and `EARLIER` hold the two downloaded
packages; their exact names and transport pins are in `inventory.json`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/replay_library_risk_screen.py \
  --package "$EARLIER/NQC_corte_economico_y_diagnostico_V3_20261003.zip" \
  --archive-root "$ARCHIVES" \
  --metadata migration/census_v2/evidence/historical-api \
  --out "$FRESH_RISK"

PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/reconcile_library_witnesses.py \
  --package "$LIBRARY/nqc-observed-economic-ledger-20261009.zip" \
  --archive-root "$ARCHIVES" --rpc-root "$ARCHIVES" \
  --metadata migration/census_v2/evidence/winner-api \
  --out "$FRESH_PAIRED"

PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_library_witnesses.py \
  --package "$LIBRARY/nqc-observed-economic-ledger-20261009.zip" \
  --risk-package "$EARLIER/NQC_corte_economico_y_diagnostico_V3_20261003.zip" \
  --archive-root "$ARCHIVES" --rpc-root "$ARCHIVES" \
  --metadata migration/census_v2/evidence/winner-api
```

Missing or altered original input fails. No synthetic replacement is admitted.
The enclosing Git commit/tree binds the new consumers and reports; null source
producer identities are not filled using the new repository's identity.

These recoveries leave the final authority lock blocked. Full temporal coverage,
original censored/decision-time ledgers, capital admissibility, complete route
economics and independent authority remain the closure requirements described
in `CLOSEOUT.md`. MXN 2,000 remains the cumulative authorized gas-only budget;
no funds or operational permissions were changed.
