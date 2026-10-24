# Historical token and strategy implementation identities

This separate read-only research probe links the reserves in the three retained
Aave condition observations to their aToken and variable debt token proxies. It
reads their ERC-1967 implementation slots, proxy code, implementation code and
the shared rate-strategy code at exactly the original block hashes. Two public
providers must agree on every byte. Header and finality checks precede/follow
reads and are repeated after both providers finish.

The capture is bounded to blocks 26248075, 26248113 and 26248378 and four token
proxies per block. There are eight distinct proxies, twelve proxy observations,
three strategy observations and 132 retained RPC requests. These are the same
three historical events already in the project, not additional observations
of positions or liquidation eligibility.

| Implementation | Contract | Compiler | Runtime bytes |
| --- | --- | --- | ---: |
| `0xadc45df3cf1584624c97338bef33363bf5b97ada` | ATokenInstance | 0.8.27 | 10477 |
| `0xb27c52c7f84819e3157993489741cb60786ae330` | VariableDebtTokenInstance | 0.8.27 | 7198 |
| `0x9ec6f08190dea04a54f8afc53db96134e5e3fdfb` | DefaultReserveInterestRateStrategyV2 | 0.8.20 | 4038 |

Sources and original compiler settings come from retained Sourcify responses.
Compiler binaries are checked against the previously retained official solc
index. Every source is literal, every import resolves inside the source set,
and compilation runs in a fresh empty directory. Only output selection is added;
source, optimizer, EVM, remapping and metadata settings are unchanged. solc
0.8.20 lacks the newer `--no-import-callback` flag, so the explicit closed-import
check applies before either compiler is invoked.

The audit compares the entire runtime, including metadata. Only the exact
immutable offsets emitted by the independently run compiler may be substituted.
AST identifiers determine immutable names. Unknown names, unexpected coverage,
links, wrong widths, overlaps, out-of-bounds offsets and nonzero placeholders
are rejected. Values are fixed in the audit program: Pool, addresses provider,
chain ID 1, treasury and rewards controller. Nothing is inferred by ignoring
arbitrary differing byte ranges. Thirty provider/code comparisons cover the
fifteen implementation/strategy observations; repeated implementations are not
counted as new contracts.

The token source reveals the nonzero rewards controller
`0x8164cc65827dcfe994ab23944cbc90e0aa80bfcb`: mint/burn/transfer paths may invoke
`handleAction`. The aToken treasury is
`0x464c71f6c2f760dda6093dcb91c24c39e5d6e18c`. Their runtime/state/behavior is not
certified by substituting their address into a compiled token. They remain
explicit external dependencies for complete replay.

## Reproduce offline

From `migration/nqc-miner`, with the checksum-pinned compiler binaries named
`solc-0.8.20` and `solc-0.8.27` in a local directory:

```bash
python3 research/build_aave_dependencies.py \
  --compiler-directory /absolute/path/to/compilers \
  --output /absolute/path/to/new-compilation
python3 research/audit_aave_dependencies.py \
  --output /absolute/path/to/new-audit.json
python3 -m unittest discover -s research -p test_aave_dependencies.py -v
```

The builder requires exact reproduction of the retained compiler output hashes.
The auditor replays all recorded requests offline, verifies source/retrieval,
input/output and profile bindings, then compares compiled runtimes with each
provider response. Source records are evidence, never executed as instructions.

A fresh network capture is an explicit separate command:

```bash
python3 research/capture_aave_dependencies.py --output /absolute/new/capture
```

Only public `eth_chainId`, `eth_getBlockByNumber`, `eth_getCode` and a fixed
ERC-1967 `eth_getStorageAt` query are permitted. Code/storage calls require
`blockHash` and `requireCanonical=true`. There is no signing, broadcast, state
override, RPC credential, background collector or Observer integration.

## Limits

Byte equality establishes equivalence of these compiled implementation artifacts
with provider-reported code. It does not prove unique historical source text,
cryptographically authenticate Ethereum state, verify proxy dispatch semantics,
or execute token/rewards/underlying-asset behavior. Strategy storage/rate inputs,
user balances, intrablock transaction prestate and all other liquidation
requirements remain unverified. The previous debt/collateral models still use
supplied external outcomes. All activation and eligibility flags stay false.
