# NQC027B: new candidate selection, not a retry of unavailable B

Previous acquisition run 39161342373 / job 117775122907 / producer
79de4c1b7c3fde974b0db24867633efc767b2923 made 3 read RPC requests.
It verified chain 1 and B's parent header, then STOPPED when pool eth_getCode
returned code 4444: pruned history unavailable: requested 26190954, earliest
available 26211623. This is missing archival state, not a demonstrated absence
of profitable opportunities. B's quote, proof and traces were NOT requested.
GitHub job success means the collector completed and exported the blockage,
NOT quote success, trade success, or admission. No external denial was retried.

## Distinct question, fixed before outcomes

Select ONE different recent Morpho liquidation whose parent is inside the state
window reported by the same public node. Do not claim latest state is B's state.
Freeze a fresh latest header for SELECTION ONLY, inspect at most 8000 prior blocks
ending two blocks before it, never earlier than 26211623+256. One getLogs request;
no expansion/retry if empty or rejected. Reject malformed, removed, duplicate or
out-of-window logs; exclude events with zero debt/collateral or reported bad debt
as an explicit study filter (not proof other events are unprofitable).
Screen at most six most-recent distinct transactions, reading each unique market
mapping at the frozen selection snapshot. Prefer the latest with WETH debt;
otherwise select the latest. Do NOT rank by profits or replace a chosen candidate
because of missing data. This is retrospective discovery, not live capture or a
market census with certified coverage.

Read the selected candidate's header/parent, receipt, transaction, callTracer and
prestateTracer at most once. Maximum 20 RPC calls, 20-second per-call timeout,
4 MiB response cap and 16 MiB aggregate cap; same no-key public endpoint, no
redirects/endpoints fallback, spending, signatures, transactions or contact.
Stop on any RPC/transport error. A trace is evidence for analysis, not replay or
state-proof verification. All commercial flags stay false.

## Source and preflight

New plain source source/recent_candidate.py SHA-256:
185db2009384e972b322e1a1a081d411cf14692e3052f1737a1fe702061f1a97.
Compiled and 7 offline fixture assertion groups passed (no network). Original
collector and its 14 tests unchanged; it is imported for pure helper functions
and constants, NOT executed. Original B plan must not run again.

The reviewed additive producer scope becomes the previous five files plus this
review and source/recent_candidate.py: seven new files total relative to main.
Only the new experimental workflow changes inside this branch; main, previous
experiments and legacy workflows remain untouched. Keep the base isolation/
9-tests gate and source digest checks. Run the new script, not collect_fluid.py.
One distinct new producer/push run; no schedule and no job reruns. No claim that
7 checks or 14 unit tests are actual liquidations.
