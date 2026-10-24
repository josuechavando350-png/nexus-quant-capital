# H25 — separate Morpho liquidation research

This checkpoint prepares a same-asset WETH Aave liquidation funded by a Morpho
flash loan. It is research code, outside the admitted H24 runtime v7. It does
not modify recovered PFT/Census source, the active audit workflow, runtime
schemas, original certificates or any client application.

## Exact target and captured scope

The target is Ethereum transaction
`0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba`,
index 1 in block 25,938,048. Its preceding transaction is
`0xa5fb6c8b75e2d8f68542c4fd49a0fcc60c679bfb5db2269d899f07742509af50`.
The parent is
`0x42cf44b75185587327a1aa8fc859cc5f49a639e7256547511430d6068b6f09ab`.
Historical principal is 10,684,013,854,557,827,871 WETH wei; the receipt's
collateral amount is 10,780,169,979,248,848,321 WETH wei. These are observations
of the historical winner, not results of the new probe.

`evidence/h25-morpho-partial.json` retains exact request, response and metadata
strings for 15 successful RPC captures and two request-only attempts. Its
SHA-256 is `223ec00e267aad6b0bfe17a00b6b1b55f75f641d61150d4c1f5a31269f402303`.
The offline verifier requires this independent code pin before semantic checks.
Rewriting per-response hashes cannot admit different evidence.

Both public providers returned identical chain ID, winner/parent blocks,
transaction, full receipt, Morpho runtime and Aave proxy runtime. WETH runtime
has only one response. Neither provider supplied the Aave implementation slot,
implementation code, or full preceding transaction before the network-policy
block. Request-only files do not count as responses. Code observations are at
the parent block, using an EIP-1898 block-hash tag with `requireCanonical=true`.
They do not establish transaction-prestate storage or current liquidity.

The verifier checks transport digests, public endpoint identity, JSON-RPC
method/parameters/IDs, capture date, provider agreement, block anchors and
transaction ordering, all 17 receipt log anchors and the one exact Aave
liquidation event. It checks pinned SHA-256 hashes of code bytes. It does not
verify a receipt trie proof, current finality, independent node ownership, or
the complete block transition. H24's separate Morpho account proof retains
its original block-end scope and is not promoted to H25 prestate evidence.

## Probe invariants and fixture scope

`morpho_liquidation_probe.sol` fixes lender, pool, asset, operator and runtime
hashes. Every plan binds chain, block, timestamp, parent, borrower, principal,
minimum surplus and execution ID. The callback requires the fixed lender,
phase, amount and exact encoded plan. The probe starts with zero token/native
balance and zero allowances. Pool approval is bounded and cleared; Morpho
approval permits only exact repayment. Lender balance must be restored and
only the new surplus is swept. Replay, unexpected callbacks, insufficient
surplus and failed settlement revert atomically.

`morpho_liquidation_test.sol` uses clearly named synthetic token/pool/lender
fixtures, including minting for mock liquidation proceeds. Its 36 offline
tests include 256 fuzz cases. Fixture minting and state overrides are confined
to unit tests and provide no market or historical execution evidence.

The probe's Aave code hash identifies proxy bytes only. It is not a production
executor and does not by itself authenticate Aave's implementation. The
research event's `proceedsBeforeRepayment` includes any unused principal;
actual liquidation amounts must be checked against the Aave event.

## Historical scaffold and remaining admission work

`morpho_liquidation_fork.sol` is an **abstract, compile-only** harness with an
unimplemented reviewed-input function. No concrete fork test or executable
RPC runner is supplied. The offline preparer puts it under `src`, while only
the synthetic tests go under `test`. Compilation checks types and syntax;
none of its historical assertions has executed.

The scaffold uses a transaction-hash fork to replay the preceding transaction
before the target. A block-end fork plus time adjustment is not equivalent.
It checks chain/block/time/parent, runtime identities and the EIP-1967
implementation slot. It is designed to check an insufficient-surplus rollback,
fresh-principal liquidation, exact Aave event amounts, repayment, cleared
allowances and fresh-surplus settlement. A separate fresh fork replays the
original transaction and compares all ordered receipt logs. No funding,
storage override, minting, signing or broadcasting is present in this harness.

The receipt comparison folds each log as
`keccak256(previous || address20 || keccak256(topics32_concat) || keccak256(data))`,
starting with 32 zero bytes. The captured 17-log digest is
`0xb9168897e4a396ded65303ee084918c09e2e525e00567ded2a58d1d149557196`.
This is a payload/order check, not a receipt-root proof or full receipt parity.

Before any historical run: obtain missing independently bound inputs through
an allowed network path after the policy restriction is resolved; review
implementation identity and prestate reconstruction; add concrete pins; verify
the EVM execution configuration against the historical block; and separately
review an executable local-fork driver. Do not use CI, a different endpoint or
a proxy to bypass the current network-policy restriction.

Any inner gas observation would be diagnostic: the scaffold executes the
negative probe first, warming accesses, and excludes deployment and transaction
intrinsic gas. It cannot be substituted for full transaction costs or used to
claim savings relative to the older Aave-financed experiment.

## Offline reproduction

From the repository root, with a fresh destination outside the repository:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 omega/morpho_experiment.py
python3 omega/morpho_experiment.py --prepare-offline /tmp/h25-fresh-build
python3 -m unittest discover -s omega -p test_morpho_experiment.py -v
```

Then, inside that fresh build, use authenticated local Forge 1.7.1 and
Solidity 0.8.24 binaries with
`forge test --offline --use /absolute/path/to/solc-0.8.24 --fuzz-seed 0x25 -vvv`.
The preparer never downloads tools, calls RPC or executes Forge. Its manifest
records copied source hashes; it refuses existing destinations, symlinks and
repository overlap, including paths containing parent segments.

## Titan and authority

**Titan supplies gas; operator gas budget is zero and own-gas fallback is
forbidden.** A Morpho flash loan supplies WETH principal, not native transaction
gas. This experiment proves neither Titan coverage nor repayment economics.
The checkpoint always remains `NO-GO`, with historical execution, complete
profit, signing, broadcasting, spending and phase advancement all false.
