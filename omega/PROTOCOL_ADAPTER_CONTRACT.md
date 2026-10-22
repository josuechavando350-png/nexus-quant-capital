# Omega Protocol Adapter Registry — Census contract

The registry defines a common, offline identity and capability contract for
protocol adapters. It does not perform RPC or certify protocol semantics.

Every adapter binds:

- protocol family and chain;
- deployment address;
- version/source commitments;
- implementation Git blob;
- an exact capability matrix.

The capability matrix contains market discovery, state reads, position
enumeration, liquidation math, oracle semantics and route evidence. A capability
may be marked supported only when it carries an evidence commitment. Unsupported
capabilities must carry `null` evidence; they cannot silently inherit support
from another protocol.

`require_capabilities` is a conformance check only. It explicitly returns
`certification_claimed: false`.

The registry permits Aave V3, Morpho Blue, Morpho Midnight and Dutch-auction
families, but naming a family does not implement it. A Morpho adapter with no
supported capabilities remains non-conformant.

Signing, broadcasting, spending, phase advancement and Census closeout are
always false.

Component 1 remains partial until real adapters for the target protocol families
are implemented, bound to deployed versions and pass cross-adapter conformance
and protocol/fork truth tests.
