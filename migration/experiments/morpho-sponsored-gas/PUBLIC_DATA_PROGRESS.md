# Public historical data progress — 2026-10-17 UTC

Economic checkpoint published as **31cb31e58e223c2b1769bf38be1f2a59afe598b3**,
tree `a4665af1cb0b3d2b71449702351fc28c2e89ab00`, byte-identical to local
`8feaef29dca4c72ccfb8cec905a1354d241909c3`. This follow-up adds an offline
historical verifier and three targeted regressions: **150 Python / 50 Solidity /
9 isolation** overall. No historical EVM replay or new financial admission.

## The access blocker is now narrower

Legitimate, credential-free reads to `https://rpc.flashbots.net/fast` succeeded
for the full A and B blocks and B's parent header. B's receipt also arrived.
All request/response envelopes are retained; full blocks are losslessly gzipped.
The API limits and lack of batch support were checked, and the small read-only
request count remained below documented limits. No transaction was submitted.

| Requested evidence | Actual response | What it establishes |
| --- | --- | --- |
| A full block 25402186 | HTTP 200, full transactions | Header bytes and observed ordering; target index 226 |
| B full block 26190955 | HTTP 200, full transactions | Header bytes and observed ordering; target index 1 |
| B parent header | HTTP 200 | Parent hash and committed state root |
| B receipt | HTTP 200, receipt | Gas and raw event log cross-checks |
| A receipt, B prefix receipt, additional C receipt | HTTP 200, `result: null` | **Unavailable**, not evidence of failed transactions |
| Executor code at B parent hash, requireCanonical | JSON-RPC -32603, `state at block #26190955 is pruned` | This endpoint did not provide the requested historical state |
| B prestateTracer | HTTP 403, -32601, `rpc method is not whitelisted` | Trace method inaccessible; no retry/bypass |
| MEV Blocker parent-header read | HTTP 403, access denied | This source inaccessible; no retry or altered client identity |

Morpho's public REST API independently returned the same immutable B market
parameters as the prior trace: WETH, ezETH, oracle, IRM and LLTV 0.945. The endpoint
is a present query of immutable configuration; its response is **not** a historical
position/oracle/reserve witness. The existing indexer quota was not renewed or
bypassed. No account, subscription or paid trace endpoint was used.

## Byte checks and exact boundaries of the evidence

`historical_rpc_audit.py` reconstructs RLP and Ethereum Keccak for both block
headers and B's parent. The resulting hashes match the pinned observations.
It also re-encodes the already-public type-2 transactions for A, B and B's prefix,
checking their transaction hashes. This performs no signing and creates no
transaction for broadcast. Tampered state-root bytes or transaction value fail.

This verifies byte commitments against pinned hashes; it is **not** consensus
finality verification, a transaction/receipt trie proof or state execution.
The RPC's reported ordering is available, but its transactionsRoot is not locally
recomputed. Do not upgrade this to a cryptographic proof of every list position.

B parent state root (end of block 26190954):
`0xd1e393e15a1b2cbf4111ade0819b713b3cd7fe2237553013c12efa2765f6cdae`.
B end-of-block state root:
`0x05c6e460d928059a6ef7912eaf9eb750536751edea6696f3653c2650b4c6e124`.
Neither is the unprovided intermediate state immediately before transaction 1.
The hash alone supplies neither account storage nor contract runtime bytes.

The preceding transaction is now identified:
`0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`,
from `0x5875db54cd9ae2b2a875e09bb731772297ae9d92` to
`0x0000000aa232009084bd71a5797d089aa4edfad4`. Its input/signature fields are in the
full block. Its receipt and state changes remain unavailable. Do not assume it
did not affect a shared token, venue or oracle. A still requires its 226 preceding
transactions and applicable block-level state transitions.

The first verifier run exposed a parser error: a successful HTTP response was
mistakenly treated as containing a non-null receipt. It now keeps absent A/prefix
receipts explicitly null. The failed test log is retained; no historical response
was changed to make the test pass. A's 323793004345200-wei gas observation remains
indexer-only in this new comparison.

## Reconciliation strengthened for B

B's new receipt agrees with the prior indexer: **745509 gas**, effective price
**266148625 wei/gas**, total **198416195275125 wei**, priority fee zero.
The verifier checks this against the EIP-1559 fee caps and header base fee.
Three raw ERC-20 Transfer events match the collateral and debt movements. Actual
WETH Deposit and Withdrawal events separately match wrap/unwrap amounts; they
are not mislabelled ERC-20 mint/burn Transfer logs.

| Item | Exact raw units |
| --- | ---: |
| Previously held WETH, prior trace observation | 6392502690919791 |
| ezETH received then sent to venue | 24343983926960874121 |
| ETH wrapped into WETH, new receipt agrees | 26409680973611000000 |
| WETH paid to Morpho | 26039738525656992415 |
| WETH withdrawn | 368092735714237547 |
| Entire withdrawal sent to coinbase, prior native call trace | 368092735714237547 |
| Inferred ending WETH | 8242214930689829 |
| Incremental WETH | 1849712239770038 |

The coinbase payment is not retained liquidator profit or independently established
builder remuneration. Its native transfer still relies on the prior call trace,
not a nonexistent native-transfer receipt event. Initial WETH is not generated
capital. Sender gas, separate counterparties, financing and all other assets must
be consolidated before any external operator P&L conclusion. No NQC P&L exists.

## Additional cases selected without a profit filter

Before querying results, saved a fixed selection: Ethereum Morpho Liquidation
events on **2026-10-14 UTC**, ascending timestamp, first 25, without asset, size,
liquidator or profit filters. The public API returned two observations:

| Transaction | Position in block | Repayment | Seizure | Net economic result |
| --- | ---: | ---: | ---: | --- |
| `0xa0f739d97610ad4a9fd98f2b2f91745c8925c6ea01b0a8b266028ba3774f4746` (C) | 222 in 26189539 | 0.513394 USDT | 0.000171268871993022 wstETH | Undetermined |
| Case B | 1 in 26190955 | 26.039738525656992415 WETH | 24.343983926960874121 ezETH | Consolidated result undetermined |

C's receipt query returned null. No historical conversion price, sponsor ledger
or prestate was fabricated for it. The API returns raw units/decimals, which the
report preserves; amounts from different assets are not added together.
Two returned API records do not prove complete chain coverage or a profitable
frequency. Completeness and capture likelihood remain unmeasured.

A separate recent-history fallback was fixed using a fetched head hash and the
preceding 1440 seconds (120 nominal slots), again without profit filters. It
returned zero API observations. This was a bounded attempt to find a liquidation
whose prestate might still be retained, not a live trading search. Zero results
from this short indexed window prove neither a zero liquidation rate nor a zero
strategy success rate. There was no eligible recent replay candidate in that response.

## Reproduction and next decisive input

```sh
python historical_rpc_audit.py
# Expected exit 2: RPC/indexer corroboration, NOT a state replay.
python -m unittest discover -v -s tests -p 'test_historical_rpc_audit.py'
sha256sum -c evidence/2026-10-17-profitability/HISTORICAL_SHA256SUMS
```

Public reads are recorded verbatim with URLs, request bodies, timestamps and
responses. The audit works entirely offline on those files. Current state, later
prices and end-of-block balances are never substituted for the missing prestate.

The decisive missing input remains historical account/code/storage under B's
parent commitment plus replay of its prefix and block system transitions, or an
independently authenticated sufficiently complete immediate-pretransaction witness.
Then reproduce the original receipt, evaluate counterfactual routes on identical
restored state, and measure their actual gas/DEX flows. A favorable replay would
still require separate financing/recipient, full-cost and capture evidence.

Primary references checked 2026-10-17:

- https://docs.flashbots.net/flashbots-protect/quick-start
- https://docs.flashbots.net/flashbots-protect/ratelimiting
- https://docs.morpho.org/developers/api/get-started/
- https://docs.morpho.org/developers/api/morpho/
- https://ethereum.org/developers/docs/data-structures-and-encoding/rlp/
- https://eips.ethereum.org/EIPS/eip-1559
- https://eips.ethereum.org/EIPS/eip-4895
- https://eips.ethereum.org/EIPS/eip-4844
- https://eips.ethereum.org/EIPS/eip-4788
- https://eips.ethereum.org/EIPS/eip-7685
