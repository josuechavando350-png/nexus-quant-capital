# Preparatory lifecycle and budget controls

This module implements local admission controls and audit reconstruction. It is not a live approval service, Temporal deployment, signer, wallet, financial authorization, or completed Canary phase.

## Scope and evidence

`MineIdentity` pins a mine identifier, chain, source digest, and candidate adapter digest. The candidate can be unvalidated, but its code must already be pinned before this lifecycle is instantiated. Discovery before that point remains discovery data.

Every `GateEvidence` carries an `EvidenceScope`, including the identity, a canonical block number/hash, observation and production timestamps, and an exclusive expiration timestamp. The caller injects time and a `CanonicalView`. Missing blocks, mismatched identities, unfinalized blocks, reorgs, future evidence and expired evidence fail closed. Every prior admission report is revalidated on later advancement and proposal creation.

A canonical view is caller-supplied metadata, not an independently authenticated chain proof. Artifact hashes establish consistency and content references, not factual truth or signatures. External producers still need independent source verification and content retrieval. The proposal artifact labels this limitation explicitly.

Synthetic reports cannot advance this lifecycle. Historical tunnel evidence must show positive net results and nonzero episodes. Shadow admission requires realtime observations, positive net results, minimum duration and sample count, and observations starting after Shadow admission. Offline unit tests construct fixtures that exercise these metadata checks; they are not actual historical or realtime economic validation.

All three adapter test families must pass: differential, property, and fuzzing. They must have distinct report digests and match the same mine, source, adapter, and canonical block. The control module does not execute those test engines or certify their authors.

## State and journal

The enum contains all nine architectural states. This build can advance only through:

1. Detected -> Classified: transfer and oracle toxicity checks pass.
2. Classified -> Valued: three adapter test families pass.
3. Valued -> WindTunnel: expected net, priority score and scenario count meet thresholds.
4. WindTunnel -> Shadow: positive historical replay evidence.
5. Shadow -> Proposed: sufficient realtime paper observations.

`Active` and `Watched` are represented for the architecture but cannot be entered by any public API in this build. `request_activation` always returns `OperationalBridgeDisabled`, including when an opaque `ExternalApprovalReference` is supplied. There is no approval boolean, signer, broadcast API or background activation path.

A mine can be retired with a reason. Reactivation returns to Detected and clears accepted evidence, requiring the complete sequence again. Source and adapter versions may change on restart; mine and chain cannot. Expired or invalidated evidence is not silently refreshed.

Every transition stores its input, previous state, new state, injected timestamp, sequence, previous digest and SHA-256 digest. Each advancement additionally stores the claimed canonical context used at that time: chain, finalized head and hash, and the block identities required by the incoming and previously accepted evidence. Unrelated blocks are omitted. The context is covered by the transition digest and its constructor is revalidated during deserialization.

`MineLifecycle` cannot be deserialized directly. `replay` reconstructs each advancement through the same shape, time, admission, scope and canonical checks using that entry's recorded context and timestamp. It compares every reconstructed journal entry, then validates the still-accepted evidence of the current admission cycle against the caller's current canonical view and requested time. A retired cycle remains auditable after its blocks reorganize or its evidence expires. A reactivated mine must repeat all gates; a reorg or expiry affecting its current evidence still rejects replay and proposal creation. Older journals without the required historical context are rejected instead of silently synthesizing it.

Historical contexts are caller-supplied claims about what was known at a transition, not independently authenticated chain snapshots or finality proofs. Replay establishes internal consistency with those claims. Hash chaining detects modifications relative to an expected journal; it is not source authentication or proof against an attacker who can replace an entire journal and its trusted tip. A trusted external checkpoint and independent source verification are required for those guarantees.

## Budget accounting

Amounts are integer MXN centavos. Defaults are zero. Planning policies cannot exceed:

- Own gas: 200,000 centavos (MXN 2,000).
- Single top-up: 50,000 centavos (MXN 500).
- Stop with no realized capture: 100,000 centavos consumed (MXN 1,000).

The limits implement prior project constraints; they do not authorize spending. `spending_enabled()` is always false. `request_spend()` always fails with `OperationalBridgeDisabled`.

`assess_top_up()` is a numerical assessment only. Observed accounting entries are retained even when they show that a limit was exceeded, so a breach cannot be hidden by refusing to record the observation. Such entries latch a halt. A later capture cannot clear the stop requiring review.

Simulation and Shadow results have separate counters and never increment realized capture count or replenish a budget. Realized entries require canonical transaction and evidence references, are deduplicated per chain/transaction/accounting category, and are retained as immutable accounting records. The caller remains responsible for verifying receipt contents, successful settlement, net P&L, and any conversion to MXN; local metadata validation alone cannot establish those facts.

`audit_canonical()` rechecks retained receipts for the supplied chain and latches a halt if their canonical evidence disappears or changes. Imported historical totals remain visible when invalidated; they must not be used for economic decisions after that halt. The function must be called for each chain with a refreshed canonical view. This module does not automatically query chains or silently rewrite history.

No self-financing transfer or budget-clearance operation is implemented. A production implementation must add authenticated approvals, externally verified settlements, durable transaction boundaries and operator-reviewed halt clearance before any operational bridge can be considered.
