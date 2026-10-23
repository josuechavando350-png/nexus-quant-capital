# Combined Aave debt execution evidence

Source commit: `60dd3ebee9c117a3e35c7d4ba1545e2032649232`.
Bundle prerequisite: `3d47c20299657af4cbbd04dce19a4b42cd3c3e5a`.

`compiler/` retains the pinned solc 0.8.27 compilation of the synthetic Pool
entrypoint, forwarding proxy and rewards probe. The original pool sources are
unchanged. The token/strategy runtimes are imported from the preceding audited
compiler outputs and checked against the historical dependency evidence by the
builder, rather than recompiled under a different joint compiler configuration.
The resulting fixture is `../../fixtures/aave_debt_execution.json`.

`synthetic/input.json` is a complete closed-state input accepted by the real
`nqc-miner simulate` CLI. `synthetic/output.json` records the matching output,
ordered logs, storage changes and explicitly unauthenticated state. Python
regression tests execute this input again and compare the entire output.

`targeted-final.txt` retains eight passing Rust tests: 600 seeded successes and
32 directed attempts. Of those directed attempts, eleven succeed, fourteen
complete with the expected revert and seven stop on missing witnesses. All
successes compare ten result words, complete logs and all changed contract slots;
all completed reverts have no logs or contract-storage changes. This is 632
attempts within eight tests, not 632 independent tests or liquidations.

`python-targeted.txt` retains four passing provenance/CLI tests. `offline/`
retains the complete final suite and exact source/build/input identities.
`verification.json` binds all logs, artifacts, source bundle and final docs.

Earlier failures are preserved: test-only numeric conversion/shift inference,
selector-prefix assertion and Clippy style failures, plus the passing seven-test
run before the directed kink/max-balance test. `preflight-notes.json` describes
the initial Solidity address-literal checksum correction. No dependency upgrade,
original-source edit or lint suppression was used to resolve those issues.

All state, the Pool entrypoint, forwarding proxy and rewards behavior are
synthetic. Token burn and rate responses are computed by the real audited
runtimes. This does not certify the deployed proxy, rewards controller,
historical transaction state, a complete liquidation or economics. The example's
gas number measures only this synthetic harness. No new network reads/events,
activation, Observer changes, signing, deployment or spending occurred.
