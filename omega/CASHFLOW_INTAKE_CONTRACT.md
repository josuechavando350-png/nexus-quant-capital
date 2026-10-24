# Source-bound WETH gross-minus-gas observations

This intake enriches exactly nine historical WETH/WETH transactions from the
139-event / 127-transaction corpus. It executes the unchanged original cashflow
auditor through the H14 verified transitive-source loader. Actual decoded debt,
collateral and full transaction gas are joined to H15 event-liquidator identities.
The entire transaction gas is charged to the selected WETH leg, including any
unrelated work in that transaction. No allocation to individual internal calls
or inference about a transaction sender/beneficial owner is made.

The original price archive has SHA256
`5ae6c45b53ded26f327270758c248f7f4ec0ff1365f550e54dcf28feb4a83a03`.
Its independently retrieved GitHub run/commit/artifact capture is retained and
hard-pinned at SHA256
`d4806f0f3478f80f035a6e60f5ae9969e3defc66690d9984d2199f67ce8285d3`.
The remote origin was established by the connected GitHub read, not self-hashing
arbitrary JSON. Offline consumption makes no fresh query. Original source code,
artifacts, event commitments and canonical producer identities are preserved.

The source report covers two previous-block price references, at ranks **1 and
3**, not the actual top two in the nine-transaction universe. Those prices are
not exact transaction prestate. A difference between previous-block and block-end
prices does not establish the oracle update transaction or causal delay. Seven
unpriced rows retain null USD valuations; no current spot price is substituted.

All monetary arithmetic uses integers; signed USD reference conversion follows
the pinned original auditor's truncation toward zero. Gross-minus-gas is not net
profit. The original five-bps flash fee remains a distinctly labelled sensitivity,
never a historical paid cost, lender quote, funding commitment or NQC gas expense.
Builder payments, other costs, complete net profit and oracle delays stay null.

Store batches include all underlying evidence and prior derived reports. Every
query rechecks the base ledger, identity report and cashflow report against original
sources. A self-consistent database or rehashed report cannot authorize fabricated
profit. Restore conserves the bytes; revoked batches are excluded while evidence
is retained. No inference about live chain reorgs or remote durability follows.

No live execution, current market coverage, monthly profit, capture probability,
Census closure or phase advancement is established by this historical sample.
