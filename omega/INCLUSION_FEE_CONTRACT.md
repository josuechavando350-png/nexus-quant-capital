# H22 - observed inclusion fee decomposition

The reader adds six retained Blockscout MCP responses: transaction and block
observations for historical WETH ranks 1, 2 and 3. Selection is retrospective
within the existing nine-case sample and 127-transaction corpus. No new winner
or current opportunity is counted. Native tool structured responses are preserved
with a SHA256 pin; they are not raw RPC receipts, receipt-trie proofs or an
independent EVM execution. The transaction tool omits its block hash. Its number,
position, timestamp and fee fields are joined to the separately observed block
hash and the original dRPC receipt, without claiming full receipt parity.

For these Ethereum type-2 transactions only:

- Execution fee = receipt gas used * effective gas price.
- Burn = receipt gas used * block base fee.
- Priority fee = execution fee - burn; it is already included in execution fee.

Reference: [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559). Arithmetic uses
bounded integers, never floats, current exchange rates or guessed fee caps.
The receipt gas already incorporates refunds. Reject wrong chain, block hash,
index, pending/failed status, non-type-2 or blob-bearing data, differing gas or
prices, inconsistent fee caps, API totals, burn or priority amounts.

All three observed priority fees are zero. **This does not establish zero builder
compensation.** Direct fee-recipient transfers, separate bundle payments, side
payments and their attribution to this liquidation are unobserved. The gas fee
recipient is an address, not an independently identified builder. The transaction
sender and protocol-event liquidator remain distinct roles.

An internal-transfer request exceeded the native API response-size limit. The
documented large-response REST path with the same session then returned HTTP 403
for unavailable session access. Preserve these failures; no trace bytes were
retained, no zero transfer is inferred and no new session or subscription is
created. Token-transfer truncation and internal-call errors do not affect the
narrow execution-fee join, but preclude any claim of complete cashflow accounting.

The six other sample rows remain unobserved. Complete cost rows remain 0/127,
Titan-covered NQC executions 0, and certified components 0/36. The active
Titan-only gas policy remains unchanged; competitors' gas is not NQC funding.

Store admission creates a seventh batch with an explicit dependency on H21.
Queries authenticate that parent, all inherited bytes, the new capture and the
recomputed report. Ancestor revocation blocks normal queries while restoration
preserves forensic bytes. Local tests do not prove physical Rust transport,
canonical reorg recovery, inter-host recovery or remote exact-producer execution.

Runtime v5 adds a required `inclusion-fees` record on the replay stage. The worker
reconstructs the seven batches inside the existing disconnected namespace, binds
the H21 economic report and its exact Titan-only policy, revokes the root, restores
SQLite and checks blocked queries plus unchanged forensic bytes. The packet
consumer independently reproduces this result and requires the same namespace as
the physical replay and the same economic commitment/policy as the H21 record.
Payer, zero operator allowance, no prefund, no own-gas fallback and the absence of
execution-specific Titan coverage are source-bound; resealing a changed claim
cannot authorize it. Historical v1-v4 packets retain their prior scope and cannot
substitute for this v5 record. The H22 capture/report bytes remain unchanged.

The workflow, permissions, providers, Rust/Solidity sources and authority gates
are unchanged. The worker adds no network request, Titan submission, signing,
funding or new liquidation EVM execution. Any exact-producer remote result must
be independently retrieved and documented in `AUDIT_H22.md`.

Reproduce from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/inclusion_fee_intake.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s omega -p test_inclusion_fee_intake.py -v
```
