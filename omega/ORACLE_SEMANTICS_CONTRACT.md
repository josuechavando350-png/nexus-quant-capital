# Omega Oracle Semantics / Depeg Radar — Census contract

This registry classifies an oracle only from explicit, evidence-bound semantics.
It never guesses from token symbols, names or market reputation.

Supported classes:

- `MARKET_PRICE`: the oracle directly reflects the referenced market price, so a
  spot depeg is directly visible to this oracle.
- `EXCHANGE_RATE`: the oracle reports an exchange/conversion rate. A spot depeg
  is not directly reflected by this oracle; that statement does **not** mean the
  position can never liquidate for other reasons.

Markets bind collateral and debt oracle IDs to exact evidence commitments.
Unknown classes, unresolved oracle IDs, missing evidence, duplicate records and
non-canonical ordering fail closed.

The registry is tied to one exact chain/block/hash and has no signing,
broadcasting, spending, Census-close or phase-advance authority.

Component 10 remains partial until protocol-specific semantic evidence is
populated for all scoped markets and historical depeg cases are replayed.
