# Original collateral burn and observed WETH evidence

Tested source: `4bfae245e78ce99d37131198275867d5a3f04302`.
Source bundle prerequisite: `2955dbbce58d7d74df4a6c4eaa79188e3285cb04`.

`public/` retains a complete 66-request, two-provider capture at the three earlier
blocks. Canonical hash-pinned WETH code and aWETH underlying-slot reads agree;
chain/finality/block/event header checks and request sequencing replay exactly.
No new liquidation events or balances are captured. Provider agreement is not an
authenticated state-root proof.

`weth-source.json.gz` is the unchanged source-service reply, including the original
CRLF/license. `compiler-retrieval.json` binds the official solc-bin binary download
to the previously retained official compiler index. `compiler/` and `preflight/`
retain original inputs and outputs for solc 0.4.19 (WETH) and 0.8.27 (harness).
`recompilation.json` records three identical executions per profile.

`runtime-audit.json` explicitly retains the source gap: WETH's executable prefix
of 3081 bytes matches, but 32 bytes of the bzzr0 metadata hash differ. Full runtime
recompilation parity is false. The deployed metadata is never patched into compiler
output. Execution uses the entire 3124-byte observed runtime, including its original
footer; all six provider code replies agree on these complete bytes.

`synthetic/` is a complete real CLI input/output with actual aToken burn, WETH
transfer, rate/rewards updates and capped fee. Twenty-four words, fourteen events
and twenty-one changed slots match independent expectations. All execution state
is synthetic. `targeted-initial.txt` has eight passing new Rust tests with 240
seeded cases and 32 intentionally filtered existing tests. `python-targeted.txt`
has twelve passing tests. There were no targeted compilation or assertion failures.

`offline/` retains the independent final full verification. `verification.json`
binds source inputs, logs, fixture, compiler/source/capture bytes, source bundle and
final documents. Earlier evidence and Observer are unchanged. Debt payment,
complete Pool validation/state updates, same-asset/multireserve handling and
authenticated historical execution remain pending. No economic certification,
activation, signing, broadcast, deployment or spending occurred.
