# H24 — one historical Morpho principal/repayment observation

The first WETH winner's retained H23 operation listing calls `flashLoan` at
`0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` and receives the
`onMorphoFlashLoan` callback. This matches the Morpho Blue Ethereum address in
[official deployment documentation](https://docs.morpho.org/developers/contracts/addresses/).
The [official contract](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol)
and [event declaration](https://github.com/morpho-org/morpho-blue/blob/main/src/libraries/EventsLib.sol)
describe principal transfer, callback and repayment. These references do not prove
the deployed runtime's historical code identity or current available liquidity.

A new retained public Routescan `eth_getTransactionReceipt` response has 17 logs,
indices 7–23, for the exact H23 transaction/block/index. The frozen original receipt
normalizer reproduces the retained dRPC gas/event summary and its commitment. This
is agreement for that normalized projection of one transaction, not full raw receipt
parity, full-corpus two-provider agreement, receipt-trie proof or call ancestry.

The Morpho `FlashLoan` event and WETH transfers bind principal and repayment of
**10684013854557827871 wei each**. The observed WETH repayment premium is **zero**.
The reader also reconciles the liquidation's WETH collateral/debt transfers and
the final withdrawal with H23's native unwrap. It rejects changed anchors, removed
or missing logs, malformed ABI words, wrong participants, principal/premium changes,
and callback disagreement. Method display labels are not used as proof.

This zero is narrow: repayment minus principal in this observed WETH flow.
Other financing costs remain unknown. Execution gas and the direct fee-recipient
payment remain separate, and the residual remains unproven as realized profit.
The retained Aave-based fork's simulated 5342006927278914 wei fee is not rewritten
or attributed to this winner. A Morpho route for NQC, its execution/gas profile,
liquidity, competitive bid and all-in profitability still require validation.

Morpho is observed here as the historical principal lender. **Titan remains the
required NQC gas payer**, with zero operator allowance, no prefund and no own-gas
fallback. Neither the loan nor its repayment proves Titan funding for NQC.
All nine historical rows remain; eight financing witnesses stay null. Complete
paid-cost rows remain 0/127 and Titan-covered NQC executions zero.

The ninth SQLite batch declares H23's direct-payment batch as its only parent.
Reads recursively verify the parent, byte-identical inherited objects, exact
inventory, the pinned receipt capture and a recomputed financing report. Changing
the parent, adding objects or resealing altered evidence cannot admit a valid view.

Runtime v7 requires a `flash-financing` record in the physical disconnected worker.
It reconstructs nine batches, revokes their root and restores the exact snapshot.
Normal reads of all nine batches must fail in both stores while each batch's
forensic object bytes remain identical. The consumer independently reproduces the
exercise and binds H23's batch/root/report, H21's economics commitment and the exact
Titan policy. All records must share the same isolated network namespace.

The new proof covers SQLite dependencies and recovery, not a canonical reorg, new
Rust transport or NQC Morpho execution. Runtime v1-v6 preserve their original code
inventories and proof scopes. H23's run cannot certify H24; a new exact-producer
run and independent artifact/API/log audit remain required.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/flash_financing_intake.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s omega -p test_flash_financing_intake.py -v
```
