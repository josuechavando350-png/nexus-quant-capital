# Real Aave rewards accrual evidence

Tested source: `35dbcbe891f7199e29770b55dde0414057cf1a1e`.
Bundle prerequisite: `c8134f4a448f22f55f7829ae89722e59e219185a`.

`public/` contains one complete 72-request, two-provider capture of the rewards
proxy slot and proxy/implementation runtimes at three previously retained blocks.
Chain, finality, canonical block-hash pins and header rechecks bind every sample.
`public-initial/` retains the failed first attempt; diagnostics show pruning at
PublicNode and successful slot reads elsewhere. `capture-notes.json` records
provider changes. Complete-capture replies are not assembled across attempts.

`sources/` retains unmodified Sourcify responses for rewards and an unmodified
Etherscan page for the second token-proxy family. `retrieval.json` binds source
URLs/hashes and unsuccessful lookups. The source-page string is decoded as data,
never evaluated. `profiles.json` pins source/settings/compiler/output identities;
`compiler/` retains actual input/output bytes; `recompilation.json` records two
identical compiler runs per profile.

`audit.json` records exact runtime comparisons, including metadata, for rewards
proxy (2400 bytes), RewardsController (18645 bytes) and second token proxy (1853
bytes). New comparisons total sixteen provider code replies. Combined with prior
evidence, all eight token proxies in twelve observations have compiled coverage.
This is scoped historical code identity, not authenticated state or a liquidation.

`synthetic/` is a complete closed-state real CLI input/output using actual rewards
code. `targeted-initial.txt` has seven passing new Rust tests; `targeted-final.txt`
has eight passing new tests after boundary additions. Both intentionally filter
sixteen existing tests, which are included in the final full suite. Four hundred
seeded combined cases are inside those tests and paired with a reference execution;
they are not four hundred additional tests or historical liquidations.
`python-targeted-final.txt` retains fourteen provenance/replay/CLI tests.

The original debt/token/rate reference checks independent arithmetic. New reward
expectations use separate integer arithmetic and compare all ordered logs and
changed contract storage. Boundary/late/multireward failures require full rollback;
missing nested slot or implementation witnesses fail closed.

`offline/` retains the complete final verification. `verification.json` binds
current source inputs, logs, example, compiler files, source bundle and final docs.
All previous evidence and Observer remain unchanged. Execution distributions,
balances, Pool entrypoint and standalone asset callers remain synthetic. Actual
claiming, transfer strategies, deployed administrator behavior, historical state
proofs, full liquidation, economic certification and operational phase exits are
pending. No signing, broadcast, deployment, real upgrade or spending occurred.
