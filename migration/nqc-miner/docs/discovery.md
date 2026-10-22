# Discovery and local EVM evidence

This module is an offline, bounded implementation of discovery primitives. It
contains no observer client, private key, signing call, RPC client, broadcast
method, deployment method, or spending mechanism. Network acquisition belongs to
the separately scoped Miner ingestion layer.

## Implemented APIs and limits

| Capability | Implemented behavior | Evidence still needed for operational use |
|---|---|---|
| Birth and liquidation events | `decode_log` validates chain, emitter, block interval, removal flag, event signature, exact ABI length, canonical scalar encoding and the Morpho market hash. | Authenticated/finalized provider evidence; deployed code and proxy validation. |
| Supported ABIs | Morpho Blue `CreateMarket` and `Liquidate`; original Aave v3 core `ReserveInitialized` and `LiquidationCall`. | Deployment/version registry. Later Aave variants require their own explicit ABI. |
| Fork candidates | Deterministic SHA-256 MinHash of bytecode shingles; disassembly-aware `PUSH4` candidates; Jaccard comparison. | Decompiled analysis such as heimdall-rs, configuration/proxy inspection and differential arithmetic parity. |
| Timelocks | Queue, cancel, earliest timestamp eligibility, predecessor gating and separately recorded observed execution. | Governance-specific event ingestion, reorg journal, target decoding, protocol position reconstruction and execution-time simulation. |
| Interest | Checked uint256 arithmetic reproduces Morpho Blue's supplied-rate Taylor accrual and `toAssetsUp` rounding, including virtual assets/shares and uint128 asset bounds. Binary search identifies the first conditional threshold crossing. | Certified IRM/market state, future rate evolution, collateral/oracle changes and intervening actions. |
| Whales | Evidence-scoped multichain address graph, as-of-time connected candidates, confidence filter. | Live activity acquisition and calibrated heuristics. Associations never prove ownership. |
| Incentives | Bounded campaign end calendar and latest known borrow/supply ratio. | Campaign ingestion and validated causal relation to position deleveraging. An expiring reward does not imply liquidation. |
| Maturity | Deduplicated as-of-time maturity calendar. | Protocol-specific settlement semantics and maintained official schedules. |
| Local EVM | Actual REVM execution for Shanghai/Cancun, with all accounts, code, slots and ancestor hashes supplied explicitly; gas/input/output bounds; no persistent state mutation. | Authenticated prestate, precise state position/transaction prefix, chain-specific VM semantics and a full historical replay corpus. |
| Differential comparison | Compares output, status, gas, logs and state changes for an identical supplied snapshot/call. | An independently implemented adapter and independently acquired reference cases. This is not the property/fuzz/certification gate. |
| Toxicity assessment | Verifies transfer call identity, supplied before/after balance deltas, return status and oracle-cost evidence; incomplete evidence stays unknown. | Independently attested balance provenance, multiple actors/sizes/timestamps, changing permissions, proxy upgrades and complete oracle dependency analysis. |

All numerical liquidation amounts remain native token base units as decimal
strings. No conversion to USD, liquidation bonus or realized profit is inferred
from event amounts. Aave liquidation identity includes the pool and both assets;
reserve birth identity includes the configurator and reserve. Resolving these to
one certified market registry is a separate requirement.

`CodeBinding::verify_supplied_hashes` compares explicitly supplied runtime and
implementation hashes at a pinned block. It does not acquire code or authenticate
proofs. ABI matching and bytecode matching never grant trading authority.

Fingerprinting preserves all raw bytecode bytes, including possible metadata or
unreachable tails. An incomplete PUSH operand stops only linear selector
extraction and sets `selector_scan_truncated`; Keccak and MinHash still cover the
entire input. This flag neither rejects nor certifies EVM runtime validity. A
`PUSH4` operand remains only a candidate, including when the scan completes.

## State witness boundary

`PinnedSnapshot` records the block, state root, fork, block environment, account
existence, balance, nonce, runtime bytecode/hash, every accessed storage slot, and
accessed ancestor hashes. An absent account is **unknown**, unless an explicit
nonexistence record is supplied. A missing slot is **unknown**, including slots
that would be zero on the real chain. Both cases reject execution.

The module verifies runtime-code hashes and internal witness consistency. It does
not verify Merkle-Patricia proofs or prove that the state root belongs to the
canonical chain. `canonical_state_authenticated` therefore remains false for
both synthetic fixtures and historical witnesses. The witness provider must
identify the exact prestate independently; setting a block number does not make
post-block state a valid pre-transaction state.

Supported execution uses the Ethereum REVM handler. Setting another chain ID
does not certify L2 system calls, fee rules, special precompiles or sequencing.
EOF and EIP-7702 delegation bytecode are rejected because the supported fork
models stop at Cancun. Malformed bytecode envelopes return an error rather than
calling REVM's panicking unchecked constructor.

The state, call, result, logs and state deltas are retained for finite-case
comparison. Snapshot/call SHA-256 digests bind the exact serialized input bytes;
they are integrity identifiers and do not attest the origin of those inputs.
Reordering equivalent account entries changes the snapshot digest intentionally.

## Toxicity reports are finite and conditional

`TransferProbe` binds the supplied outcome to the exact ERC-20 `transfer` token,
sender, receiver and amount. Return data must be empty or canonical boolean true;
both sender debit and receiver credit must equal the requested amount. A revert,
halt, noncanonical return, hidden fee or inconsistent delta rejects the case.

The before/after balance values and oracle stress bounds are supplied evidence,
not independently produced or authenticated by `assess_toxicity`. A passing
report is named `pass_for_supplied_cases`, always retains `globally_safe=false`,
and cannot constitute an adapter certification or a live-use approval. Missing
transfer cases, unknown manipulation cost, unknown extractable value, or
incomplete oracle dependencies yield `unknown`.

## Audited source references

Protocol identities and ABIs were checked against primary source files. These
references identify the source definitions used, not a deployed-contract audit.

- Morpho Blue source revision
  `9cf6d5b844625ba108e36d1cf911f5d2faf7c136`:
  [EventsLib.sol](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/EventsLib.sol),
  [MathLib.sol](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/MathLib.sol),
  [SharesMathLib.sol](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/SharesMathLib.sol).
  The retrieved branch versions were compared with these pinned files and were
  byte-identical. Original source license: MIT.
- Aave v3 core source revision
  `782f51917056a53a2c228701058a6c3fb233684a`:
  [IPool.sol](https://github.com/aave/aave-v3-core/blob/782f51917056a53a2c228701058a6c3fb233684a/contracts/interfaces/IPool.sol),
  [IPoolConfigurator.sol](https://github.com/aave/aave-v3-core/blob/782f51917056a53a2c228701058a6c3fb233684a/contracts/interfaces/IPoolConfigurator.sol).
  Original source license: AGPL-3.0. Only interface event declarations are used;
  no Aave protocol implementation is embedded.
- [Alloy Solidity types 1.4.1](https://docs.rs/alloy-sol-types/1.4.1/alloy_sol_types/)
  and [REVM 19.5.0](https://docs.rs/revm/19.5.0/revm/) are pinned in Cargo.

## Validation

Run from the standalone crate:

```sh
cargo test --locked --offline --test discovery_tests --test evm_tests
```

Tests include independently assembled event payloads, forged market IDs, wrong
emitters/chains/ranges, removed logs, trailing data, noncanonical address/bool
padding, proxy identity changes, truncated PUSH operands, deterministic MinHash,
cancelled/dependent timelocks, exact arithmetic and overflow, temporal graph and
campaign boundaries, and randomized malformed input.

REVM tests execute bytecode rather than mocking the VM. They verify known return
values, missing/explicit-zero storage, unknown/explicitly absent accounts,
ancestor hashes, gas/nonce/fork limits, mismatching code hashes, malformed EOF,
reverts, halts, deterministic state deltas, differential mismatches and toxicity
evidence confusion. These are explicitly synthetic software tests, not evidence
of historical profitability, protocol certification or live captures.
