# Omega Liquidation Order Book — Census contract

This module is an exact, offline threshold index. It consumes thresholds whose
protocol math and provenance must already be established elsewhere.

Every threshold is a positive rational represented by canonical decimal strings
and reduced by GCD. Floating-point inputs are rejected. Entries bind a position,
oracle, liquidation direction, threshold and upstream evidence commitment.

Two directions are supported:

- `AT_OR_BELOW`: the position becomes liquidatable when the observed oracle price
  is at or below the threshold.
- `AT_OR_ABOVE`: the position becomes liquidatable when the observed oracle price
  is at or above the threshold.

`crossed` returns only positions that become newly liquidatable between two exact
prices, in price-encounter order. A position already liquidatable at the previous
price is not emitted again. Oracle groups are isolated.

The sealed book is tied to an exact chain/block/hash and content commitment.
Signing, broadcasting, spending, phase advancement and Census closeout are all
explicitly false.

This does not compute Aave/Morpho liquidation thresholds, accrue debt, validate
oracle semantics, populate a current market, or certify component 8. Those remain
upstream and integration requirements.
