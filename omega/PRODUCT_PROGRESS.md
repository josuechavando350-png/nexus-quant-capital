# Product completion and the requested 20 → 45 batch

The earlier approximately 20% figure was a coarse construction estimate, not an
audited numerator/denominator. It cannot become an audited 45% merely by assigning
25 points to convenient new work. The requested target is retained as a target,
not marked achieved. The source design requires evidence at phase gates.

Authoritative scope is the 36 components in `architecture_v3.json`, derived from
the original Omega PDF. Census/Shadow/Canary/Escala contain 9/9/4/14 components.
Miner's independent work is not imported or credited here. Existing foundation
coverage is 9/9 Census partials, not 9/9 complete components.

| Product gate | Evidence still required |
|---|---|
| Census truth | independent three-way parity across the declared scope |
| Census coverage | all scoped positions reconciled across real protocol adapters |
| Census economics | bonuses, winners, oracle-to-winner timing, builder payments and net costs |
| Shadow recovery | real reorg replay and complete durable state recovery |
| Shadow predictions | resolved simulation disagreement, temporal competition, measured latency |
| Shadow economics | complete cost accounting and calibrated detection/capture comparison |
| Canary safety | executor invariants/formal verification, kill switch and loss limits |
| Canary outcome | independently verified bounded real capture after separate authorization |
| Scale | out-of-sample net-margin improvement for each activated capability |

H14 adds concrete engineering acceptance items: authentic transaction intake,
all raw liquidation legs, partial gas accounting, transactional evidence storage,
crash/concurrency/recovery tests, full local pipeline replay, broader CI triggers
and bounded authenticated-by-readback runtime artifacts. Their audited status is
recorded in `AUDIT_H14.md`. None substitutes for missing market evidence above.

H15 additionally identifies the protocol-event liquidator for 127/127 historical
transactions, 49 distinct liquidator addresses and 127 borrowers, by matching all
139 raw log payloads to original commitments. Gas metadata agrees with the dRPC
receipt stage. This does not prove current coverage, oracle causality, complete
costs or NQC profitability; details and limits are in `AUDIT_H15.md`.

Progress reporting must keep three quantities separate:

1. Completed engineering increments and their exact tests/producer evidence.
2. The approximately 20% historical estimate, explicitly uncertain until a
   complete effort-weighted implementation inventory has been reviewed.
3. Certified product components: **0/36**; Census **0/9** until terminal criteria
   are actually demonstrated. Neither passing tests nor adding documents changes
   this number.

No automatic phase advancement, funds, signing or execution authority is derived
from a percentage. A future weighted plan must be versioned before credit is
counted, cover all 36 components, preserve unmet gates, and state that weights
are planning estimates rather than physical proof of readiness.
