# Actual aToken transfer composition evidence

Tested source: `424775f2b17fdc2581fcd8cd70f50abe6c126e06`.
Source bundle prerequisite: `4cceb0975d80e4c9c72b297b7c02b07f4bbd0699`.

`compiler/` retains the original-source-plus-generated-wrapper input and exact
output bytes from checksum-pinned solc 0.8.27. `recompilation.json` records a
second identical compiler run and four byte-exact extracted segment hashes.
Inherited token/proxy/rate/rewards runtimes are unchanged from their previous
historical-code evidence. This block makes no new RPC request or source capture.

`synthetic/` retains the real CLI input/output for the composed receive-aToken
branch. All balances/indices/distributions/aggregate values are synthetic; amounts
are supplied and initial health validation is not executed. Actual token balances
determine fee capping. The default example has nineteen output words, seventeen
ordered events and seventeen changed contract storage slots.

`targeted-final.txt` has eight passing Rust tests, including 320 seeded cases;
24 existing tests are intentionally filtered only in that targeted invocation.
`python-targeted-final.txt` has eight passing Python tests. Earlier extraction,
compilation and independent-model failures are retained with their explanations
in `execution-notes.json`. The interrupted fourth targeted invocation has no
completion summary and is not counted as a successful full run.

`offline/` is the separate full verification. `verification.json` binds its logs,
input hashes, exact fixture, compiler artifacts, source bundle and final docs.
No previous evidence or Observer files are changed. Underlying asset transfers,
debt payment, complete Pool validation and historical authenticated execution
remain open. This is neither a historical liquidation nor economic certification.
