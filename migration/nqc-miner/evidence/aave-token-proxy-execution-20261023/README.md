# Audited Aave token-proxy execution evidence

Tested source: `19f0e23e30845f9790c3ed2a7dc7fdc9063e75a1`.
Bundle prerequisite: `009d8c923633f98fd590394702af10ddf1f8560c`.

`source.json.gz` is the unmodified complete Sourcify response for the USDC debt
proxy. `retrieval.json` binds its URL and raw SHA-256. `profile.json` pins source,
settings, compiler and output hashes. `compiler/` contains the original-source
compilation. Only compiler-declared immutable positions are populated, and full
runtime bytes including metadata match the retained dual-provider history.

The family covers six distinct proxies and ten observations in the same three
historical sample blocks, with twenty provider code comparisons and twenty slot
comparisons. The other two proxies have a different runtime and are explicitly
excluded. No new RPC reads or source events occurred. `retrieval-notes.json`
records the unsuccessful compiler/source URLs and successful compiler fallback;
`recompilation.json` records three identical compiler runs.

`synthetic/` contains the complete CLI input/output with the real proxy. It retains
exact return data, ordered logs and contract storage changes; balances/parameters,
Pool entrypoint, rewards probe, administrator account and alternate implementation
addresses are synthetic. The example's 215726 gas is not a production fee estimate.
No signing, broadcast, real upgrade or contract-admin execution occurred.

`targeted-initial-slot-failure.txt` retains an honest initial failure: an aToken
getter required supply slot 54 while the test incorrectly supplied debt slot 58.
The test now takes each slot from the audited compiler layout. It does not add
unobserved zero slots or patch original contract code. `targeted-final.txt` records
16 passing Rust tests (eight existing and eight added), and `python-targeted.txt`
records seven added provenance/CLI tests. See `execution-notes.json` for attempt
counts; six hundred seeded executions are inside a test, not extra test cases.

`offline/` records the full final battery and source/build identities.
`verification.json` binds current inputs, raw logs, artifacts and final documents.
The source bundle reconstructs the exact tested commit without changing existing
source provenance. Progress remains 43/100; no historical execution-state,
liquidation eligibility, full-liquidation, economics or operational certification
is claimed. Observer and previous evidence are unchanged.
