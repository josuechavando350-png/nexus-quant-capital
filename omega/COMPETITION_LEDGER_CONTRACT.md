# Omega Competition & Margin Ledger — Census contract

This ledger materializes one historical market winner per transaction. It is
designed to answer the Census questions that aggregates cannot:

- who won;
- how many blocks elapsed from oracle update to winner;
- what fraction of liquidation bonus was paid to the builder;
- what observed winner margin remains after known costs.

Unknown monetary fields remain `null`; incomplete cost records never receive an
implicit zero. Derived net margin is emitted only when the record explicitly says
observed costs are complete.

The builder-payment share is exact integer floor in WAD units. Negative observed
winner margin is preserved rather than clipped.

Every row is evidence-bound and transactions are unique/canonically ordered.
This is historical market evidence only. It always emits `nqc_execution: false`,
`nqc_realized_pnl_usd_wad: null`, and never claims current-market validity or NQC
profitability.

Signing, broadcasting, spending, phase advancement and Census closeout are
always false.

Components 24 and 25 remain partial until real per-transaction rows are populated
from authenticated receipts/oracle events, full cost reconciliation is proven,
and current-market refresh/coverage is established.
