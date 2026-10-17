# Bounded prospective observation — 2026-10-17 UTC

One newly preserved observation was collected, with no persistent process, wallet,
signature, transaction submission or expense. It demonstrates collection and
rejection of incoherent inputs, not an eligible or profitable liquidation.

## Selection and provenance

`prospective_observation.py` performs one finite sample per invocation. A saved
selection limits the session to at most three samples, rejects overwrites and
stops after an unavailable response. This session's recovered selection permits
**one** sample: two earlier observations were lost with the temporary workspace
and are not included in the published raw evidence or statistics.

The selection was saved at `2026-10-17T05:38:03.588908Z`, before reading results.
It fixes case B's Ethereum market and borrower, independently of current profit:

- Market: `0xa0534c78620867b7c8706e3b6df9e69a2bc67c783281b7a77e034ed75cee012e`.
- Borrower: `0x018d6cc992eb576e2f36dc485b92d168ada37156` (20 bytes, including the leading zero).
- REST configuration, market state, position and oracle: public Morpho API.
- Headers at the API's reported heights: public Flashbots RPC, without full transactions.

Raw request/response envelopes, local receipt times and the selection are in
`evidence/2026-10-17-prospective-recovered/sample-00/`. The offline analyzer
validates market-parameter hashing, address identity, integer amounts and each
header's RLP/Keccak commitment. REST data has no account/storage proof against
those roots. Matching a header does not authenticate the indexer's state or
establish consensus finality.

## Actual observation

Times below are UTC. Delays are from the reported block timestamp to local
response receipt; they are not measured network latency or an SLA.

| Input | Indexed height | Local receipt time | Block-to-receipt seconds |
| --- | ---: | --- | ---: |
| Market | 26210230 | 05:38:10.802423 | 11.802423 |
| Position | 26210231 | 05:38:14.020207 | 3.020207 |
| Oracle | 26210229 | 05:38:17.557055 | 30.557055 |

All data, including header responses, was available only at
**05:38:26.670478 UTC**. The analyzer's temporal predicate requires that completion
time, every state receipt and all observed heights to precede a candidate event.
This is a necessary ordering condition only, never proof of opportunity or capture.
An earlier version used only state-response times; the new guard prevents later
header retrieval from being presented as information already available earlier.
`sample-00/report.json` preserves the initial collection output; reproduce the
current analysis in `final-prospective.json` without overwriting that snapshot.

| API field | Exact raw units |
| --- | ---: |
| Market supply assets | 17089951946419811409 |
| Market borrow assets | 403752291226362858 |
| Market borrow shares | 367449650232108460673583 |
| Position collateral assets | 994323950097753677 |
| Position borrow shares | 2370415599405678275695 |
| Oracle price | 1088377151872222433000000000000000000 |
| Reported last accrual timestamp | 1792136411 |

The market/position/oracle heights differ. Whether REST asset totals include
projected interest is also unverified; do not accrue them again as though they
were raw `market()` storage. The oracle update timestamp is null. Therefore
liquidation eligibility, synchronized debt, executable Fluid output and net
profit remain **unknown**. No post-event values substitute for a prior state.

Supply minus borrowing is 16686199655193448551 WETH units for this market.
This accounting difference is **not Morpho's aggregate WETH balance** and cannot
establish Bundler3 flash capacity. Neither architecture is economically admitted.

## Short event follow-up

A separately frozen query covers this market only during
`[2026-10-17T05:38:03Z, 2026-10-17T05:39:38Z)`, a 95-second interval.
The complete query and response are in `followup-selection.json` and
`followup-events.json`. It requested all Liquidation records without a profit
filter, limit 100, and returned HTTP 200 with zero items and countTotal zero.

This immediate indexer response does not prove absence of onchain events: indexing
delay and completeness are unverified. There is no observed subsequent event to
pair with this sample. The interval also starts before all sample inputs arrived.
Do not convert this short observation into a liquidation frequency, zero success
probability, monthly expectation or temporal evidence for historical case B.

## Independent public state-access attempt

BlockPI's official Ethereum page advertises a credential-free public endpoint.
A separate capability selection allowed at most four read requests, stopping on
the first failure. Its first `eth_getBlockByNumber(latest, false)` returned
**HTTP 403, `error code: 1010`** at 05:44:20.844574 UTC. The remaining market,
historical proof and prefix receipt requests were not executed. No retry,
client-identity alteration, private endpoint or new account was used.
Both selection and exact failed response are preserved in `blockpi/`.
This access failure says nothing about the economic viability of a liquidation.

## Reproduction and decisive next input

```sh
python prospective_observation.py --analyze evidence/2026-10-17-prospective-recovered/sample-00
# Expected exit 2: observation only, no economic admission.
python -m unittest discover -v -s tests -p 'test_prospective_observation.py'
sha256sum -c evidence/2026-10-17-prospective-recovered/SHA256SUMS
```

The four focused checks reject changed headers, wrong borrowers, lossy amounts,
after-event observations and exhausted/forbidden collection. Even equal reported
heights never certify REST state or profit. A fresh collection requires a newly
saved selection and separate evidence directory; no process runs in the background.

For prospective eligibility, obtain Morpho/position/oracle/IRM and real Fluid
state at one identified block, with verified accrual semantics and runtime/state
provenance. Preserve acquisition times before evaluating subsequent events.
For historical B, obtain authenticated parent state and execute transaction 0
and applicable block transitions before reproducing transaction 1. These remain
distinct experiments. Financing and competition require additional evidence.

Primary references reviewed: [Morpho API](https://docs.morpho.org/developers/api/get-started/),
[Flashbots limits](https://docs.flashbots.net/flashbots-protect/ratelimiting),
[BlockPI public endpoint](https://blockpi.io/chain/ethereum/) and
[BlockPI read-only eth_call](https://docs.blockpi.io/build/api-reference/ethereum/ethereum-raw-api/eth_call).
