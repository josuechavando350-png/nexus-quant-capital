# Census progress notices: 10/20, 15/20 and 20/20

The user requested continued work and notices at these three milestones on
October 9, 2026. The earlier **8/20** was a qualitative assessment of overall
progress, not a measured completion percentage. These milestones make the
future notices evidence-based. They do not alter ARCHITECTURE.md or certification
requirements, and cannot be reached merely by elapsed time or passing unit tests.

| Notice | Required evidence |
| --- | --- |
| **10/20: historical coverage checkpoint** | The declared Ethereum 215,036-block window has complete, reconciled executed-event coverage and all 127 full receipts; all 67 asset-price vectors at every block have matching observations from two named operators, with exact source/acquisition commitments, preserved failures and deterministic offline reproduction. No unresolved mismatch in that scope. This does not assert independent underlying nodes, original decision-time knowledge, execution admission or completion of the entire Census. |
| **15/20: execution and economics ready for final review** | In addition to 10/20, every candidate in each declared population has a reproducible, evidence-supported disposition. Token behavior, admissible funding, repayment, monetizable routes, full costs, conflict/capacity constraints and competition/capture assumptions are checked; every material unknown preventing that disposition is resolved. Any positive executable admission requires all corresponding gates. Negative findings are valid. The complete Market/Capital/Economic Truth package is ready for independent exact-producer review. |
| **20/20: Census closed** | The complete declared Census scope satisfies all governing requirements; independent Market Truth, Capital Truth and Economic Truth authorities accept the exact new producer/consumer commits, trees and hashed evidence. Replays, adversarial checks, temporal/censored-opportunity treatment and mismatch/unknown resolution are complete. An authenticated terminal closure exists. Self-certification, inherited old-repository certification, missing evidence or an unreviewed draft PR cannot satisfy this milestone. |

Reaching 20/20 closes **Census only**. It does not certify live trading, realized
P&L, revenue reliability, Shadow completion or Canary. The cumulative **MXN
2,000 gas-only** amendment remains in force; no principal, collateral, signing,
broadcast, paid infrastructure or subscription is authorized by these notices.

At commit `97971ef45d03b2f2e775b77081458a8a9fca721f`, none of the three thresholds
is reached. Oracle secondary coverage is 5,170 / 215,036 blocks. The validated
remaining plan has 209,866 blocks, excludes all prior coverage, uses one worker
and a minimum 1.1-second request interval after the prior `Retry-After` period.
Any continuation checkpoint must be verified before it increases coverage.

## Continuation and notification protocol

- Work only in `josuechavando350-png/nexus-quant-capital`; PR #3 is stacked on
  PR #2. Read its current head and AGENTS.md before edits. The original
  `nexus-engine` repository is a read-only evidence source.
- Inspect the existing worker before launching anything. A device lock prevents
  duplicate oracle continuations. A process or a progress counter alone is not
  proof of matched historical prices.
- Preserve source hashes, exact request/response bytes, failed requests and
  actual acquisition times. Do not repeat already verified blocks. Honor
  Retry-After and service limits; no new identities, endpoints or subscriptions
  to evade access/rate controls. An access/rate error stops the collector.
- Persist and reconcile completed evidence, run affected tests and original
  isolation checks, and publish with an expected-head lease. Never modify old
  sources or activate workflows to manufacture a passing result.
- Notify the user once when each threshold first becomes demonstrably true.
  Include the supporting commit/artifact and remaining limits. A higher
  milestone also requires every lower milestone. Use prior notification history
  to avoid duplicate notices; a regression invalidates the current claim.
- Keep working within existing permissions between notices. If essential user
  action or independent authority is needed, identify the concrete blocker;
  never raise the score just to satisfy the requested notification.
