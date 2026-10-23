# H17 — predecessor-state and conditional fee intake

`historical_state_intake.py` joins three retained original GitHub artifacts to
the H14–H16 event, receipt, liquidator and cashflow chain. The original H16 report
remains byte-for-byte reproducible with its two priced rows. The new report
separately enriches three of its nine WETH/WETH rows; six retain unknown state.

| Evidence | Original run | Artifact | Original producer |
|---|---|---|---|
| Rank-two price | 37732663268 | 11530582289 | `40e0918026c5fbfec0611d872dbb6d7258007948` |
| Three Pool premiums | 37733150542 | 11529984754 | `e2f4558a8bed604b6e3d0ce418f9235ecd2069b6` |
| Three predecessor health states | 37739986399 | 11533556749 | `1048bb5558138429873b4459b9339f2527abbd13` |

All original producers are in `josuechavando350-png/nexus-engine`. Their source
workflows remain disabled in NQC. Run/commit/tree/artifact metadata was retrieved
independently through GitHub. The exact retained captures, ZIP digests, member
names, lengths and hashes are pinned in `historical-state-pin.json`, whose SHA256
is compiled into the consumer. Capture time is distinct from the historical
chain observation. Offline ingestion makes no fresh chain observation.

ZIP manifests and report commitments are checked before use. The original dRPC
and BlastAPI provider rows must agree. Selected receipt commitments must match
the original 127-row ledger; borrower address/fingerprint and exact WETH log must
match the independently retained H15 raw event. Predecessor numbers and hashes
must agree across price, Pool rate and state witnesses. Three matching normalized
receipts do not establish full raw-receipt or 127-transaction parity.

The three observed Pool premium rates are 5 bps at predecessor block end.
Conditional fees use Aave integer half-up PercentageMath with overflow rejection:
`(amount * bps + 5000) // 10000`. These are not historically paid fees. Ranks two
and three differ by one wei from the older ceiling-based hypothetical sensitivity;
both meanings remain separate. USD-WAD uses a previous-block price, truncating
signed values toward zero. Whole competitor transaction gas remains charged to
the selected WETH leg; unrelated work can be present. This is not NQC net profit.

All three predecessor health factors exceed one: `1000000001993818630`,
`1000701093031081909`, `1000489719586999148` WAD. Zero of these three were below
one at predecessor end. This does not identify the later intra-block trigger.
Prior-end-block state is not exact transaction prestate, and a price change is
not oracle causality. The other six health states remain unknown.

Every row is selected retrospectively from eventual winners. None becomes a
prospective signal or executable candidate. Even a below-one HF would not alone
prove route viability, financing, inclusion or profit. Complete costs, actual paid
flash fees, builder payments, oracle delays and NQC profit remain null.

Store batches conserve every source and derived report. Query reconstructs and
checks the complete chain, so rehashed invented profits or a self-consistent
SQLite store cannot authorize substituted data. Restore preserves bytes, and
revoked batches cannot be queried as active. These are local tests, not proofs
of remote replication or actual chain reorganization.

```
PYTHONDONTWRITEBYTECODE=1 python omega/historical_state_intake.py --out /tmp/h17.json
PYTHONDONTWRITEBYTECODE=1 python omega/regression.py --start-directory omega \
  --pattern test_historical_state_intake.py --report /tmp/h17-tests.json
```

Existing CI's reviewed intake pattern includes these tests. No workflow,
permission, subscription, signing, broadcast or funds change is introduced.
