# NQC research continuity — 2026-10-17 UTC / 2026-10-16 Mexico City

## Scope and commit identity

Branch: `research/morpho-sponsored-gas-20261016` only.
Starting commit: `37ee15bb48a7a002a60e473e56c2ee7b90b2f299`.
Published correction head: `b29db31c0268869e6e97c7bb16423809fe817dff`.
The current file and subsequent additions belong to the research commit that
contains them; obtain its exact identity with `git rev-parse HEAD` and
`git log -1 -- RESEARCH_STATUS.md`. A file cannot contain its own commit hash.

The two pending corrections were published through the authorized GitHub connector
because local HTTPS Git push lacked authentication. Commit metadata changed;
each published Git tree was verified byte-identical to its local counterpart:

| Local commit | Published commit | Identical tree |
| --- | --- | --- |
| `2d6252a7f98d28909a0eaac0d4a7d7d67971fd2d` | `68fb0f69b417db1ac24f8b9cace7bb51c2ea2165` | `14de60273c0957deda2e38013bc78d082efef2f3` |
| `8db6099eecaa010a08e86feddb69e641fdbb0d69` | `b29db31c0268869e6e97c7bb16423809fe817dff` | `34f9b38b210710e4177b481ec0f39eb7b6534b3d` |

All changes stay under `migration/experiments/morpho-sponsored-gas/`.
`main` observed at `16e352225ba8a6a931834c4edf3d86d9a2924b7d`; no write to main,
other owner projects, original sources/certificates or workflow configuration.
No signatures, broadcasts, real deployments, transfers, subscriptions or spending.
Contract creation in tests occurs only in the local EVM test process.

## Latest executed verification

The previously reported **132 Python / 39 Solidity** results were a real local
checkpoint. This continuation adds four trace-provenance regressions and two
original-core liquidity tests. Current result:

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| Experimental Python | **136** | 0 | 0 |
| Default Solidity: 29 executor tests + 4 parity tests | **33** | 0 | 0 |
| Original-source Solidity: 4 Morpho + 4 Bundler integration tests | **8** | 0 | 0 |
| Solidity total | **41** | 0 | 0 |
| Repository isolation regressions | **9** | 0 | 0 |

The Solidity totals count test functions, not fuzz iterations or vectors. One
balance-invariant test runs 256 deterministic fuzz cases. Parity compares 65
liquidation and 65 interest vectors plus nested ABI/callback encoding.
See `evidence/2026-10-17/validation-run.json`, `final-*.log` and `SHA256SUMS`.
Local checks do not imply a remote CI run. Legacy workflows remain disabled.

Environment: Linux x86_64, Python 3.12.14, PyCryptodome 3.23.0, Forge 1.7.1
(commit `4072e48705af9d93e3c0f6e29e93b5e9a40caed8`). NQC uses solc
0.8.24, Cancun, optimizer 200, no via-IR. Original Morpho is built with solc
0.8.19/Paris/optimizer 200; Bundler3 and adapter with 0.8.28/Cancun/via-IR/999999.
Binary hashes and complete free setup commands: `toolchain.json`, `REPRODUCE.md`.

Core commands, from this directory with the toolchain installed as documented:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/nqc-python/bin/python -m unittest discover -v -s tests -p 'test_*.py'
/tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 -vv
FOUNDRY_PROFILE=core /tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 --match-path 'tests-core/*.t.sol' -vv
/tmp/nqc-python/bin/python generate_parity_fixtures.py --check
/tmp/nqc-python/bin/python historical_trace_audit.py
# Last command deliberately exits 2: reconciled observation, not certified replay.
```

Build original-source artifacts before the core suite, following REPRODUCE.md.
From repository root also run `python3 migration/verify_isolation.py` and the
nine `migration/test_isolation.py` tests. No Rust code changed; Rust tests were
not executed in this session. Original Git objects were unavailable, so isolation
reports `original_objects_checked=false`; no historical recertification claimed.

## Corrected errors and negative test history

- Actual baseline: 91 Python tests, 75 passed / 16 errors because OpenSSL lacked
  Keccak-256. Shared hash-pinned `evm_hash.py` resolves this; no SHA3 substitution.
- Actual Solidity baseline: solc 0.8.24 failed with Stack too deep; 0 tests ran.
  Extracting event emission fixed compilation without changing optimizer/via-IR.
- Three newly introduced adversarial tests failed before fixes: inconsistent
  returned seizure, incomplete debt collection and short operator token receipt.
  NQC now reconciles exact observed amounts. These are NQC guard corrections,
  not claimed vulnerabilities in the original Morpho protocol.
- Further guards cover callback caller/data/state, duplicate callbacks, repayment,
  prior token/native balances, false approvals, insufficient/misreported swaps,
  failed native payments, operator reentry and complete revert behavior.
- Strict hex/ABI integers, pinned market identity and trace provenance checks
  reject malformed or substituted observations. Supplied evidence remains untrusted
  without independent authentication; booleans do not certify chain truth.
- Baseline/pre-fix failures are retained in evidence logs. They are not hidden by
  the latest successful run. Blocking model/audit exits 2 are expected, not passes
  authorizing trading.

## Functional components and economic findings

- Exact supplied-input liquidation and interest model, with Python/Solidity parity.
  The interest model does not reconstruct historical adaptive IRM storage itself.
- NQC executor compiles and settles locally against original Morpho source.
- Original Bundler3/adapter/Morpho call sequence settles a synthetic flash-funded
  liquidation; wrong callback hash and insufficient conversion roll back.
- Both local routes start the operator without ETH or loan tokens. The harness
  supplies artificial external market/DEX liquidity and does not prove EOA gas
  funding. B still lacks real DEX and native sponsor-settlement integration.
- New liquidity comparison: A's callback works with zero Morpho debt-token cash;
  B's flash route fails in that state. External DEX liquidity remains essential.
- Per-asset economic ledger separates liquidation payment, flash principal,
  conversion, sponsor advance/return, coinbase and proposer costs. All economics
  are theoretical unless independently backed by execution evidence.
- Case B trace arithmetic reconciles exactly. **368092735714237547 wei**
  (~0.36809 ETH) was withdrawn and entirely sent to `block.coinbase`.
  It was not retained profit and is not automatically builder income.
- The external executor already held **6392502690919791 WETH units**
  (0.006392502690919791 WETH). This case does not demonstrate zero initial funds.
  Its inferred incremental WETH is 1849712239770038 units; subtracting sender gas
  gives 1651296044494913 wei-equivalent arithmetically, not certified consolidated
  profit, and never NQC P&L.

Detailed evidence, architecture comparison and accounting: `RESEARCH_FINDINGS.md`.
**No NQC realized gains are certified. Neither $0 architecture is yet economically
validated. No Titan/Quasar sponsorship of NQC has been demonstrated.**

## Pending, blocked and unexecuted

1. Authentic historical replay: no canonical state/root or complete prefix replay.
   Case B index 1 requires its one prior transaction; case A index 226 requires
   226. Parent-block calls and winner traces are insufficient by themselves.
2. Public RPC access: original archive probe failed; continuation basic reads
   returned PublicNode HTTP 403 and Llama HTTP 405. This is an access blocker,
   not evidence that a historical state cannot exist. Free indexer quota exhausted.
3. Historical runtime/immutables: source snapshots and partially verified explorer
   metadata agree, but actual code identity at the chosen prestate is unproved.
4. Real DEX prices/reserves, actual flash capacity, adaptive IRM/oracle storage,
   historical fork rules and complete external token/native ledgers are missing.
5. Builder funding address/receipts, advance policy, creation support, top-up cost,
   proposer settlement, failure liability, inclusion and competition unproved.
6. No production swap adapter, audited deployed route, authentic fork gas estimate
   or empirically grounded capture/failure probability. Bundler3 is deprecated.
7. No Reth/Geth archive provisioned; no paid infrastructure. Remote CI not run;
   Rust tests and original source object verification not run (scope/tool limits).

## Next objective and approval criteria

Prioritize case B because its prefix has one transaction. Use the read-only
`fixtures/case_b_replay_requests.json` with an accessible authorized archive node.
No request signs, sends or funds a transaction. Collect full headers/transactions,
receipt and prestate/call traces; independently authenticate the block and state.
A prestate trace covers only touched slots and is not a proof or a sufficient
witness for every counterfactual route.

Files: `historical_trace_audit.py`, `historical_prestate_probe.py`,
`tests-core/`, `contracts/NqcMorphoSponsoredLiquidation.sol`, `bundle_gate.py`,
`economic_ledger.py`, `RESEARCH_FINDINGS.md`.

Required experiments: reproduce the original at its exact pretransaction state;
compare both alternatives from a restored identical state using actual DEX code
and liquidity; reconcile all balance changes and complete financing separately.
Pass only with original receipt/state parity, no future information or silent
state fabrication, full repayment, preserved prior balances, measured gas and
positive residual after evidenced sponsor/proposer costs. A local simulation
still does not prove builder acceptance or market capture. Missing evidence stays
pending; an observed revert is recorded with its exact cause. Do not spend funds
or request signatures to clear these research gates.
