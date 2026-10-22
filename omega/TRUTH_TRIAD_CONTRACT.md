# Omega Truth Triad — Census contract

The Truth Triad compares exactly three independently evidenced lanes at one exact
chain/block/hash/state-root and one semantics commitment:

1. event + storage reconstruction;
2. direct contract read;
3. EVM replay.

Each lane carries a result commitment, a source commitment and a producer
commitment. Source and producer commitments must be pairwise distinct so that
three labels cannot disguise one underlying authority.

Parity is exact commitment equality. Any disagreement produces `MISMATCH` plus a
three-entry mismatch ledger. No tolerance or majority vote exists.

Batch evaluation requires an explicit expected subject set. Missing or duplicate
subjects fail closed, preventing a passing subset from masquerading as complete
coverage.

`PARITY` is not `PROTOCOL_FORK_TRUTH_CLOSED`. This module always returns
`certification_claimed: false` and `phase_advance_authorized: false`. It has no
signing, broadcasting, spending or Census-close authority.

Component 6 remains partial until the triads are populated from real independent
sources, the original Protocol/Fork runtime closeout is re-established for this
producer identity, and complete scoped market/position coverage is proven.
