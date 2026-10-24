# H15 — source-bound historical liquidator identities

Two read-only Blockscout MCP calls retrieved all 139 Aave LiquidationCall logs
for the original source window, split into adjacent non-overlapping ranges:
25880316–25987833 (63 logs) and 25987834–26095351 (76 logs). Neither result reaches
the API's 1000-result cap; both complete responses are retained without pagination.
The query fixes Ethereum chain 1, the original Aave pool and event topic.

The original historical records remain unchanged. `liquidator_intake.py` binds
each newly retrieved topics/data payload to its ORIGINAL event commitment and
decoded leg, with exact transaction hash, block number, transaction index and
global log index. Missing, extra, duplicate, changed or malformed events fail.
All 139 commitments match. The capture ZIP and canonical API response envelopes
are pinned in code; origin was established through the native connected tool.
Offline reproduction never claims a new API request.

Important API limitation: this response omits block hash and `removed`. The
reconciler uses the pinned ORIGINAL block hash to reconstruct its commitment,
labels that provenance explicitly, and leaves `removed_status:null`. It does not
claim a newly observed block hash, fresh canonicality or an independent complete
event enumeration. Blockscout is the same event operator as the original source.

Addresses are decoded from the ABI bytes, not inferred from transaction senders:

- 139 events, 127 transactions, 49 distinct protocol-event liquidator addresses.
- Every observed transaction has exactly one distinct event liquidator here;
  the schema retains a list and returns null for a single address if multiple
  liquidators occur in a future admitted corpus.
- 127 distinct borrower addresses, explicitly scoped to Aave pool/chain.
- A `position_locator` hash names that scoped address. It does not certify a
  complete protocol position, health factor, deployment version or Truth Triad.
- Liquidator is the `LiquidationCall` argument, not a claim about beneficial
  ownership, transaction sender or NQC execution.

Blockscout's gasUsed/gasPrice metadata matches the dRPC receipt values for every
transaction. Execution gas totals 448369976498898050 wei, counted once per tx.
This is agreement of those two fields, **not complete dual-provider receipt
parity**, blob-cost parity, USD conversion, builder attribution or complete net
profit. Oracle update/delay and complete margin remain null.

The original H14 ledger remains a reproducible immutable partial intake. H15
publishes a separate identity report instead of rewriting its historical nulls
or weakening H11's required identity/oracle contract. Its local store batch binds
all original artifacts plus both new captures and the derived report. Read-back
revalidates the original ledger AND every identity. Restored/revoked batches obey
the same rules. A failed identity import may retain an independently valid H14
base batch; it never publishes a partially accepted identity batch.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/liquidator_intake.py --output /new/identities.json
```

This is a concrete reduction of the Census identity gap. It grants no phase,
certification, economic or trading authority. Remaining requirements include
independent truth/coverage, oracle causation/timing, complete costs and margin.
