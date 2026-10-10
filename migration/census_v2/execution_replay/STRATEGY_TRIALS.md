# Same-case financing and timing boundaries

Input head `a1292b8a46e225934b1e1c5f375418718739a68b`. This adds two tests to
the exact native-realization source, retaining its four original tests and the
original executor unchanged. It uses only the already-retained 127-response
fork witness; no new upstream requests, gas or live transactions.

| Controlled variant | Reproduced result |
| --- | --- |
| Balancer at the modeled eligible time, observed native payment | Existing positive 240,390,311,727,552 wei native residual before gas/other costs remains |
| Aave with the same principal, liquidation and payment | Exact repayment/profit rejection; shortage 5,101,616,615,551,362 wei before gas; lender, operator, recipient and strategy balances and borrower health factor revert |
| Balancer at the predecessor time | Exact `HealthFactorNotBelowThreshold()` rejection (`0x930bb771`); all checked balances, borrower health and execution identity preserved |

Six tests pass in normal mode and the same six pass in isolated mode. These
are six tests over **one retrospective historical case**, not twelve operations,
independent strategies, holdout data or a capture success rate. Aave's exact
historical fee is 5,342,006,927,278,914 wei. This excludes that precise variant
under the observed payment; it does not exclude Aave across all sizes/markets.

The same limitations remain: predecessor-state plus a clock advance does not
replay the earlier transaction in the winner block; no exact transaction-time
state, NQC decision-time knowledge, full production gas, funding admission,
competitive inclusion or complete profit is proved. New inherited-test gas
measurements must not be compared as an executor optimization: its executor
bytes are identical and the harness changed.

## Failures and corrections retained

`offline-001` built but reported four passing and two failing tests. The Aave
rollback test initially queried the Pool coordinator's WETH balance, which the
retained state witness does not contain. The true underlying funding holder in
the retained `transferUnderlyingTo` trace is the aWETH contract
`0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8`. The corrected test checks that
holder's unchanged balance, using already-retained state. No synthetic balance
or new provider was inserted. The predecessor test initially expected a legacy
string error; the actual historical code returns the custom selector. The next
fresh source checks the exact custom error rather than accepting arbitrary
reverts. Both old sources and failure logs remain.

Foundry's optional `eth_getAccountInfo` requests were rejected by the local
read-only method guard in both attempts. Successful runs used retained standard
RPC responses instead; these local client-error records remain in the archive.
The localhost server also emitted broken-pipe diagnostics when the requesting
client disconnected. No upstream method, endpoint or permission was expanded.
An initial remote file-copy attempt lacked its new parent directory; no trial
ran before that directory was created. No failure counts as a successful trade.

## Exact evidence and reproduction

`inputs/strategy-trials.zip`: 401,802 bytes, 26 members, SHA-256
`f5d4b38801e98f46d72116a22806ec6484507f5ffd2459622679ac938617ffea`.
Its manifest commits both producer versions, both run registrations, source
copies, original witness bytes, logs, reports and local RPC records. Parent
native archive SHA-256 is
`46bdc3d97787154e286a8c210bdfdf07d2faf4788dc0fd8d52dc58357dd0643a`.
Trial registrations were written before compilation. These cases were already
selected retrospectively; registration does not erase that selection bias.

```bash
TMPDIR=/dev/shm PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/verify_strategy_trials.py \
  --archive migration/census_v2/execution_replay/inputs/strategy-trials.zip \
  --output /tmp/nqc-strategy-trials-readback.json
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/execution_replay/compare_strategy_families.py \
  --out /tmp/nqc-strategy-families-new
```

The family consumer reproduces all 127 transactions, 139 events and 53 pairs,
including the two explicitly retained legacy flash-index omissions documented
in `../STRATEGY_EXPANSION.md`. Its output never converts observed winners into
NQC profits or a requested 80% probability. This readback is not independent
Market/Capital/Economic certification and does not close Census.
