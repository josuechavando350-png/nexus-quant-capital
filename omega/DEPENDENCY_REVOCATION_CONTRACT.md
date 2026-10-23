# H20 — explicit dependency revocation

Acceptance is four engineering gates: implementation, complete local regression
and isolation, exact-producer remote execution, and artifact/API/log post-audit.
These gates describe this increment, not the 36-component product percentage.

`admit(..., parents=[...])` commits a new immutable dependency-aware manifest.
Parents are unique canonical SHA256 batch IDs. Every parent must already be
admitted and active under the same SQLite writer lock. Missing, forward, cyclic
or blocked parents are rejected. `parents=None` retains legacy manifest bytes,
IDs and batch-local semantics. No old snapshot or report acquires new authority.

One explicit revocation journal event invalidates all declared descendants in
the same committed state. The audit derives the transitive closure in admission
order and preserves every blocking revocation root. It never updates/deletes
original objects or invents a separate revocation witness for each descendant.
An already invalidated descendant may receive its own explicit revocation proof.
Default reads and readmission reject blocked batches. `include_revoked=True` is
an explicit forensic read of both directly revoked and transitively invalidated
bytes. Unrelated branches remain active. Shared bytes do not imply dependence.

`dependency_intake.store_chain` authenticates five original historical stages
and re-admits their unchanged object inventories under new IDs with four declared
edges: ledger, identities, cashflow, state, temporal. It is an explicit new intake
entry point, not an automatic migration. Each stage is atomic; the entire five
stage sequence is not. A retry can reuse complete prior stages, while a revoked
ancestor prevents any dependent stage from being admitted or resurrected.

Required tests cover transitive/multiple-root invalidation, unrelated branches,
forensic preservation, rejected admission order, incomplete manifests, concurrent
admission/revocation, and real process death before/after the SQLite commit.
The real-source fixture revokes the ledger, blocks all five stages, retains one
explicit synthetic unrelated control and rejects the temporal query.

The remote disconnected worker also imports this snapshot through the unchanged
Rust adapter, independently exports it, restores exact bytes/status and rejects
a pre-revocation snapshot against the current external journal head. The full
inventory and snapshot identity remain external trust inputs; Rust's orphan-
excluding root alone cannot establish replica identity. Runtime packet v3 must
bind the dependency adapter and its new report; v1/v2 keep historical scope.

Not established: undeclared edge discovery, malicious concurrent filesystem
protection, inter-host replication, actual canonical reorg authority, exhaustive
market coverage, complete costs, realized profits or any component certification.
