# Omega Candidate Coherence Gate — Census contract

This gate composes six already-sealed offline artifacts for **one candidate**:

1. Protocol Adapter Registry;
2. Truth Triad;
3. Causal Graph;
4. Liquidation Order Book;
5. Oracle Semantics Registry;
6. Opportunity Dossier.

It requires all state-bearing artifacts to describe the same chain, block and
block hash; the dossier and Truth Triad must also share the exact state root.

The Truth Triad subject must be the dossier position commitment. The Causal
Graph must bind that position to the dossier market and to one oracle. The
Liquidation Order Book must contain the same position and oracle. The Oracle
Semantics Registry must bind the same market and include that oracle.

The adapter must match protocol family, chain, deployment and version
commitment, and all declared Census adapter capabilities must be evidence-backed.

A successful result is **FOUNDATION_COHERENT** only. It explicitly sets
certification, GO, signing, broadcasting, spending, phase advancement and Census
closeout to false.

This gate does not acquire market state, compute missing economics, populate
historical competition records, certify Protocol/Fork Truth, or prove complete
market coverage. It exists to stop independently valid artifacts from being
combined when they refer to different positions, markets, or blocks.
