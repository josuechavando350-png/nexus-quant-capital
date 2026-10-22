# Omega Causal Graph — Census contract

The Causal Graph is an offline, content-addressed dependency graph. Its purpose
is to answer: when a market, oracle, interest model, liquidity source or route
changes, which positions must be recomputed?

Each position must have direct evidence-bound dependencies on a market, oracle,
interest model, at least one liquidity source and at least one route. Additional
market→oracle, market→interest and route→liquidity edges allow transitive
invalidation. Dangling edges, duplicate nodes/edges, invalid type pairs, cycles,
missing evidence and incomplete position dependency coverage fail closed.

The graph is tied to one exact chain/block/hash. Nodes and edges are sorted
canonically and the complete graph has a SHA-256 commitment.

`affected_positions` reverse-traverses dependencies and returns only POSITION
nodes. It does not acquire state, decide profitability, calculate liquidation
thresholds, sign, broadcast, spend, close Census or authorize phase advancement.

Component 7 remains partial until the graph is populated from the full admitted
market/position universe and replay proves completeness/invalidation correctness.
