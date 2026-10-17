# Local reproduction (Linux x86_64)

Research only. Commands install free development dependencies and run local
processes; no wallet, signer, broadcast, paid service or active workflow is used.
Run from `migration/experiments/morpho-sponsored-gas/`. Use fresh external paths
below (or equivalent paths of your choice). Downloads need public network access;
all tests are offline after setup. Python tested: 3.12.14.

## Toolchain

```sh
python3 -m venv /tmp/nqc-python
/tmp/nqc-python/bin/pip install --require-hashes -r requirements.txt
npm install --prefix /tmp/nqc-toolchain --save-exact @foundry-rs/forge@1.7.1
curl -fL 'https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9' -o /tmp/nqc-toolchain/solc-0.8.24
curl -fL 'https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.19+commit.7dd6d404' -o /tmp/nqc-toolchain/solc-0.8.19
curl -fL 'https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.28+commit.7893614a' -o /tmp/nqc-toolchain/solc-0.8.28
```

Before executing downloaded binaries, verify them against the recorded SHA-256:

```sh
python3 - <<'PY'
import hashlib,json
from pathlib import Path
metadata=json.loads(Path('toolchain.json').read_text())
checks={'solc-0.8.24':metadata['solc_sha256'],
        'solc-0.8.19':metadata['reference_compilers'][0]['sha256'],
        'solc-0.8.28':metadata['reference_compilers'][1]['sha256'],
        'node_modules/@foundry-rs/forge-linux-amd64/bin/forge':metadata['forge_binary_sha256']}
for name, expected in checks.items():
    path=Path('/tmp/nqc-toolchain')/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected, name
    path.chmod(path.stat().st_mode | 0o111)
    print(name, 'SHA256 verified')
PY
```

Compiler identities were checked against the official solc-bin linux-amd64 index.
The Python requirements pin PyCryptodome 3.23.0 and the tested Linux x86_64 wheel
hash. Another platform needs its own verified wheel and compiler binary hashes.

## Default Python and Solidity checks

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/nqc-python/bin/python -m unittest discover -v -s tests -p 'test_*.py'
/tmp/nqc-python/bin/python generate_parity_fixtures.py --check
/tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 -vv
```

Expected current result: 136 Python and 33 Solidity test functions pass. The
Solidity suite includes 256 seeded fuzz iterations and 130 arithmetic parity
vectors plus ABI tests. `--check` does not silently regenerate the committed
vectors. To intentionally regenerate after a reviewed model change, omit it,
inspect the diff and repeat independent Solidity parity.

## Original-source integration (local synthetic state)

Clone upstream into fresh external directories and fetch only pinned dependencies:

```sh
git clone https://github.com/morpho-org/morpho-blue /tmp/nqc-morpho-blue
git -C /tmp/nqc-morpho-blue checkout --detach 9cf6d5b844625ba108e36d1cf911f5d2faf7c136
git clone https://github.com/morpho-org/bundler3 /tmp/nqc-bundler3
git -C /tmp/nqc-bundler3 checkout --detach b4014349e3527f44ceaab697b26e29f2b11457f3
git -C /tmp/nqc-bundler3 submodule update --init lib/morpho-blue lib/openzeppelin-contracts lib/permit2
git -C /tmp/nqc-bundler3/lib/permit2 submodule update --init lib/solmate
python3 compile_morpho_reference.py --source /tmp/nqc-morpho-blue --solc /tmp/nqc-toolchain/solc-0.8.19
python3 compile_bundler_reference.py --source /tmp/nqc-bundler3 --solc /tmp/nqc-toolchain/solc-0.8.28
FOUNDRY_PROFILE=core /tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 --match-path 'tests-core/*.t.sol' -vv
```

Expected: 8 integration tests pass. Combined with default profile: **41 Solidity
functions**. `--match-path` prevents imported mock test contracts from being counted
a second time. No onchain deployment occurs; `create` executes inside Foundry only.
Compiler scripts read pinned Git blobs, verify binary hashes, and never rewrite
upstream sources. The import manifests record 22 Morpho and 41 Bundler source
files. Generated `out-upstream/`, `out/` and caches are ignored.

The two retained explorer source files can be checked against the pinned checkout:

```sh
cmp evidence/2026-10-17/Bundler3.deployed.sol.txt /tmp/nqc-bundler3/src/Bundler3.sol
cmp evidence/2026-10-17/GeneralAdapter1.deployed.sol.txt /tmp/nqc-bundler3/src/adapters/GeneralAdapter1.sol
```

This checks source equality, not historical runtime identity. Different compiler
versions build the original contracts independently; NQC's harness remains 0.8.24.
Local oracles, tokens, market state and exchange are synthetic. Gas reported by
test functions is not a production transaction estimate or sponsorship quote.

## Read-only evidence and blocking gates

```sh
/tmp/nqc-python/bin/python historical_trace_audit.py
/tmp/nqc-python/bin/python historical_receipt_gate.py observations/ethereum_morpho_2026-10-14_complex_winner.json
/tmp/nqc-python/bin/python bundle_gate.py fixtures/synthetic_two_transaction_bundle.json
/tmp/nqc-python/bin/python historical_prestate_probe.py
```

Each should exit **2**, intentionally: observation/model is incomplete or RPC is
not configured. Exit 3 means invalid inputs or a failed configured RPC. Never
silence these codes and call the output a production pass. Trace audit recomputes
case B interest, liquidation and native/WETH accounting from saved data; it does
not access an RPC or reproduce state transitions on a fork.

Evidence integrity, from this directory:

```sh
sha256sum -c evidence/2026-10-17/SHA256SUMS
```

This verifies snapshot bytes only, not the provider's truth or a consensus root.
`validation-run.json` records actual commands, exit codes and hashes of local
code/configuration/fixture inputs. `final-*.log` records the actual run output.
Baseline/pre-fix logs preserve previously observed errors.

`fixtures/case_b_replay_requests.json` contains only read-only JSON-RPC requests.
Send them individually to an accessible authorized archive node if available;
no sender key is needed. No successful responses are currently saved. The full
block transaction list and exact pretransaction state are still missing. See
RESEARCH_FINDINGS.md for authentication and replay acceptance requirements.

## Isolation

From repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 migration/verify_isolation.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v -s migration -p test_isolation.py
git diff --check
```

Expected: isolation verifier and 9 regressions pass. Original source object store
is unavailable, so `original_objects_checked=false` is expected and must be
reported. No Rust code changes or Rust test execution are part of this increment.
No original PFT/Census certificate is renewed by any of these checks.
