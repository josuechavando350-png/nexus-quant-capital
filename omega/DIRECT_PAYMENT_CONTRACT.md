# H23 — one observed direct fee-recipient payment

This offline reader covers only historical WETH rank 1, transaction
`0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba`.
It retains five public, keyless HTTPS GET responses from Routescan: three indexed
operation pages, transaction metadata and the Etherscan-compatible value-transfer
view. Raw response strings, request URLs, retrieval times and SHA256s are retained
inside a canonical pinned capture. The two API representations have the same
provider and are not two independent witnesses.

Documentation reviewed:
[indexed operations](https://routescan.io/docs/api/transactions) and
[internal transfers](https://routescan.io/docs/api/etherscan/accounts).

The first two pages advertise an exact count of 57; the terminal page reports
`lowerBound=57`. Coverage requires all three linked pages, no next cursor on the
last page and precisely the unique operation indices 0–56. Every indexed operation
has matching chain, transaction, block, index and timestamp and reports success.
Transaction block hash and gas fields agree with retained H22/original dRPC data.
Native transaction value also agrees with the prior Blockscout observation.
This is complete pagination of the indexed listing, not a raw trace, receipt-trie
proof, full call ancestry proof or independent native balance reconciliation.

| Observed value flow | Wei |
|---|---:|
| Initial sender → executor value, operation 0 | 9975 |
| WETH → executor native transfer, operation 54 | 96156124691020450 |
| Executor → block fee recipient, operation 55 | 95915734379292898 |
| Executor → another recipient, operation 56 | 240390311727552 |
| Execution gas charged to transaction sender | 19694395579376 |

The latter two internal transfers sum to the observed WETH unwrap amount, which
matches the historical same-asset gross liquidation delta. The direct payment
is approximately 99.75% of that delta; integer WAD arithmetic preserves rounding.
It is separate from execution gas. Root value is preserved separately and is not
silently counted as an internal transfer or gas. The residual goes to a different
address than the transaction sender; shared control is unproven. It is not
reported as realized profit, and no exact net profit is calculated.

The fee recipient's builder identity is unknown. This is neither a Titan payment
attribution nor evidence that Titan funded NQC. Total builder compensation,
other bundle/side payments, refunds, failed attempts and full cost attribution
remain open. Eight other WETH rows have no direct-payment observation. Complete
paid-cost rows remain 0/127 and Titan-covered executions remain zero. Current
Titan-only policy still prohibits operator gas, prefund and own-gas fallback.

H22 source/report bytes and its exact-producer audit retain their original scope.
This H23 reader has no eighth store batch, new runtime record, Rust transport or
remote physical execution claim. Those are subsequent integration work.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/direct_payment_intake.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s omega -p test_direct_payment_intake.py -v
```
