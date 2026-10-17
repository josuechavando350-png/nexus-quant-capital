# Case B: committed order, missing execution state

2026-10-17 continuation from `55e83bcb85d1e8f13e16d359f9954e611e4b1560`.

`historical_order_audit.py` reconstructs all 602 transaction byte envelopes and
the hexary transaction trie from the already published full block. It verifies
the header hash and each transaction hash, including 115 legacy, 473 type-2,
2 blob and 12 authorization transactions. The computed root is:

`0xc408c2823145b6f024162fd4c51bc8e34d4bae302bd2fa456bd8556d0e41167f`

It equals `transactionsRoot` in pinned block
`0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8`.
This strengthens the previous list-order observation: relative to that header,
case B really occupies index 1 and its only preceding transaction is
`0x0c5ba40ae213874eb37df22686f53729371378171d81dc9899a599351d2759f0`.
Omission or reordering fails even if transaction-index metadata is relabelled.
Changed blob hashes or authorization bytes also fail. Small embedded trie nodes
and the standard empty-trie root are checked separately.

This does not establish consensus finality, sender recovery, the receipts trie,
the effects of transaction 0, or state before transaction 1. Neither the parent
state root nor the end-of-block root supplies those missing account/storage bytes.
No historical EVM replay has been performed. The existing Morpho/oracle/IRM and
Fluid observations inside the winning transaction remain observations, not an
authenticated counterfactual execution state.

## Reproduction

Use the existing pinned Python environment with PyCryptodome 3.23.0:

```sh
python historical_order_audit.py
# Expected exit 2: byte/order evidence only, never economic admission.
python -m unittest discover -v -s tests -p 'test_historical_order_audit.py'
```

Four focused checks pass. The full Python suite was re-executed after restoring
the workspace: **163 passed**, no failures or skips. Isolation: **9 passed**;
original source object verification remains unavailable. Executed logs and
command records are in `evidence/2026-10-17-prospective-recovered/`.

## Access and recovery limitations

Before an execution-environment disconnect, baseline 159 Python / 50 Solidity /
9 isolation passed again. A new pinned current-state `eth_call` to Flashbots
returned HTTP 403, `rpc method is not whitelisted`. The documented public
Cloudflare trial gateway returned HTTP 502 to one historical account-proof read.
Neither denied request was retried or bypassed.

The temporary workspace was subsequently lost. Those new raw HTTP responses and
initial logs are not claimed as published evidence: only tool-session observations
remain. The repository was restored from GitHub; the order verifier was reapplied
and tested again using the unchanged, previously published B block. Fresh public
observations must have new timestamps and must not masquerade as recovered raw data.

The precise replay requirement remains: authenticated account/code/storage at B's
parent state, applicable block system transitions and transaction 0 execution,
then original receipt parity. Morpho debt, oracle, adaptive IRM and Fluid actual /
imaginary reserves, balances and time-dependent limits must share that state.
Only after parity should NQC alternatives be evaluated from identical restored
state with all funding and payment obligations independently reconciled.

Sources: Ethereum's [Merkle Patricia trie specification](https://ethereum.org/developers/docs/data-structures-and-encoding/patricia-merkle-trie/),
[EIP-4844](https://eips.ethereum.org/EIPS/eip-4844),
[EIP-7702](https://eips.ethereum.org/EIPS/eip-7702),
[Cloudflare node types](https://developers.cloudflare.com/web3/ethereum-gateway/concepts/node-types/)
and [documented gateway](https://developers.cloudflare.com/web3/how-to/use-ethereum-gateway/).
