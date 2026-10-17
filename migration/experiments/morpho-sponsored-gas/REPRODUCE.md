# Local reproduction (Linux x86_64)

Research only. Commands below install free development dependencies and run
local tests; no node, wallet, signer, broadcast or active workflow is required.
Run from this experimental directory. Keep tool binaries outside the repository.

```sh
python3 -m venv /tmp/nqc-python
/tmp/nqc-python/bin/pip install --require-hashes -r requirements.txt
npm install --prefix /tmp/nqc-toolchain --save-exact @foundry-rs/forge@1.7.1
curl -fL 'https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9' -o /tmp/nqc-toolchain/solc-0.8.24
```

Before executing solc, verify SHA-256 equals
`fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f`.
This was checked against the official solc-bin index. `toolchain.json` records
the actual Forge binary identity and settings. The requirements hash pins the
tested Linux x86_64 wheel; other platforms need a separately verified wheel hash.

```sh
chmod +x /tmp/nqc-toolchain/solc-0.8.24
PYTHONDONTWRITEBYTECODE=1 /tmp/nqc-python/bin/python -m unittest discover -v -s tests -p 'test_*.py'
/tmp/nqc-toolchain/node_modules/.bin/forge test --offline --use /tmp/nqc-toolchain/solc-0.8.24 -vv
```

From repository root, also run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 migration/verify_isolation.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v -s migration -p test_isolation.py
```

Neither local isolation nor unit tests recertify original PFT/Census. The original
Git object store is unavailable here, so `original_objects_checked=false` is
expected and must be reported. No Rust code is changed by these experiments.
