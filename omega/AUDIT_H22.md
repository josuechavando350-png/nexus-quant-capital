# H22 - historical execution fee observations

Predecessor: H21 closure `0aaa9a51e125e29567602d2e8d09921271cfc944`.
Implementation and local verification are recorded here. H21 remote results
do not certify this increment; no new exact-producer remote audit is claimed.

## New evidence

Six Blockscout tool responses supply three transaction/block pairs, reconciled
against the existing dRPC gas fields and historical block identities. Three of
nine WETH rows now have an observed execution-fee split. All three have zero
priority fee and positive base-fee burn. The aggregate observed execution fee is
`759296632646672` wei, all burned. Direct builder transfers remain unknown.

| Historical WETH rank | Block | Gas used | Execution fee / burn (wei) | Priority fee (wei) |
|---|---:|---:|---:|---:|
| 1 | 25938048 | 331267 | 19694395579376 | 0 |
| 2 | 26024990 | 1230724 | 523017715007964 | 0 |
| 3 | 26071849 | 1490601 | 216584522059332 | 0 |

Capture SHA256: `9d6bdcc2f3a91cb8aced6d64e19938925c497bf59fc92cf1eb402301d7ccd8b8`.
Report commitment: `83698a3891ba2687a42820344b886baa23761134c78339bbcae613b2d7ebfaf0`.
The report records the source representation, acquisition failure and exact
limits of the join. SHA pins preserve reviewed bytes; they are not cryptographic
proofs of chain state. See `INCLUSION_FEE_CONTRACT.md`.

## Initial fee-reader verification record

The 24 new tests pass. They exercise positive-priority arithmetic (the authentic
sample has zero priority), integer precision, invalid inputs, cross-source
disagreement, hash/index drift, forged payment/profit claims, offline replay,
seventh-batch ancestry, restore and transitive revocation.

Final full local regression: **613/613 unique Omega tests pass**, 24 new over
H21, with zero failures, errors, skips or expected failures (248.611 seconds).
Both original D15B/D16 archives were downloaded through the connected GitHub
reader and matched their existing SHA256 pins; no substitute fixtures were used
for the real-archive tests. The isolated 38-case CI-capture recheck also passes;
those repeated executions are not added to the unique test count.

Isolation passes with **164 reviewed Omega files**, 531 preserved original
source files, 106 disabled historical workflows and unchanged active workflow
bytes/permissions. Original source Git objects were not supplied to this local
isolation check; its `original_objects_checked=false` remains explicit. Rust and
Solidity implementations are unchanged and were not rerun. No remote forks,
disconnected worker execution or exact-producer CI is claimed for H22.

An independent stdlib-only audit (no Omega imports) reopens the original receipt
ZIP and the capture, recomputes all three gas splits, checks hash/number/index
joins and preserves every unknown builder-payment field. It passes.

| Local result | SHA256 |
|---|---|
| Full regression JSON | `3932a205d6ecec1f4474f8033275cc51377576b65a36e9680e4d697db6f49794` |
| Isolation JSON | `315faaa32eff0ed6b3db2a31b7fd1c5a8bb099f77051a748ad33f488bd5076ab` |
| Independent arithmetic JSON | `207603e905cf64c4c95d22563816640782b010cf3c7eb1a380a60a19abf56103` |
| New reader source | `8ffe1b237c9f3957b5276e9fd78b6445af30f638be8c6a690db8ef1b2c9cf5ff` |
| New test source | `7d8cbe330c416439a8327fb84808fe1eafb2630509596957ba2d20f2b7ba72ff` |

The local result files were produced in scratch; these digests record this run
and do not claim durable CI artifacts. Reader, tests, raw structured capture and
deterministic report are retained with this source change. Reproduction commands
are in the contract and the repository README.

The preliminary inherited 589-case run reported 587 passes and two errors:
the filtered Git clone lacked the historical workflow blob used by the retained
CI-capture tests. That run is not a passing baseline. The exact historical blob
is recovered before final regression; no historical source or test is weakened.
A first reader invocation rejected the capture timestamp's `+00:00` formatting;
the same recorded instant was normalized to the existing UTC `Z` contract before
pinning the final bytes and running tests.

Desktop Commander monthly usage is exhausted; no server access was obtained.
Blockscout internal transfers were unavailable (oversized response, then REST
session denial). The capture records these failures. No full transfer accounting,
complete paid-cost row, executable candidate, Titan coverage or new deployment
is asserted. Census remains open and certified components remain 0/36.

Next evidence target: retain complete internal value-transfer pages or raw traces
for these exact transactions, validate successful ancestry and native balance
effects, then attribute direct fee-recipient/bundle payments without double
counting execution gas. Zero priority fees alone cannot close that gate.

## Runtime v5 continuation

The user's Titan-only instruction is now also bound directly into H22's
disconnected-worker record. The active policy and historical capture/report bytes
are unchanged. Seven dependent batches are rebuilt, revoked from their root and
restored; all remain blocked while forensic bytes match. The packet consumer
requires matching network namespaces and the exact H21 economics commitment and
gas policy. It rejects a substituted payer, positive operator allowance, prefund,
own-gas fallback or invented execution-specific Titan coverage.

Targeted local checks: 30/30 inclusion tests and 22/22 runtime-packet tests pass.
These include six new worker cases and three new v5 packet cases. A freshly
retrieved authentic H21 v4 replay artifact (ID 12535070907, original ZIP SHA256
`59a2c1930a50ddd8a046ac60c41cab5d06097a6700e0b68bdd71372f8e059599`)
passes the new reader with its 43 records and old scope, without an H22 claim.
Compatibility result SHA256:
`00fad9dae099cfd957964b30507a765e1f56072622031c092c9aa9aba9acd8ae`.

Final full local regression: **622/622 unique tests pass**, with zero failures,
errors, skips or expected failures (399.422 seconds). Nine cases are new in this
continuation, 33 over H21. Full result SHA256:
`f0d591cae84b7d4256deb57476b031405187ecc1c85d716810e3eaefa3a2b367`.
Final isolation passes with the same 164/531/106 file counts and unchanged
workflow; its result SHA256 remains
`315faaa32eff0ed6b3db2a31b7fd1c5a8bb099f77051a748ad33f488bd5076ab`.
Original Git objects remain unchecked locally and must be checked in the remote
jobs. Remote exact-producer execution is pending at this pre-publication
checkpoint. No workflow, permissions, provider, Rust or Solidity source is changed.
The older source digests above identify the initial fee-reader checkpoint, not
these subsequently extended reader/test files.

Additional read-only research could not retrieve the exact historical transaction
through the public Etherscan page or either web search engine. No trace or payment
observation was added. Titan's official Sponsored Bundles documentation was
rechecked; its conditional sponsorship is not execution-specific coverage.
