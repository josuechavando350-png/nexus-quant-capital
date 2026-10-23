# Aave rewards accrual and the second proxy family

The combined debt experiment now executes both the real rewards proxy and the
18,645-byte `RewardsController` implementation. The earlier rewards probe remains
in the preceding fixtures as an explicit test double. The new fixture is
`fixtures/aave_rewards_execution.json`; it contains actual callback code and
explicitly synthetic reward distributions and balances.

## Historical code identity

A fresh 72-request capture checks the rewards proxy's ERC-1967 implementation
word and both runtimes in blocks 26248075, 26248113 and 26248378. Blast and dRPC
agree, using canonical block-hash pins surrounded by chain, header, finality and
post-read header checks. The implementation is
`0xe7b67f44ea304dd7f6d215b13686637ff64cd2b2` in all three samples. These checks do
not authenticate an Ethereum state root or reconstruct transaction prestate.

The initial capture stopped because PublicNode had pruned the oldest requested
state: its error reported earliest block 26248138. The failed attempt is retained
separately. A diagnostic at dRPC succeeded; Llama returned HTTP 405; the new complete
capture restarts from request one using Blast and dRPC, without mixing attempts.
The original three events and 48 position/oracle observations are unchanged.

Unmodified Sourcify source responses for the rewards proxy and implementation
compile with checksum-pinned solc 0.8.10. The proxy has immutable admin
`0x2f39d218133afab8f2b819b1066c7e434ad94e9e`; the controller has immutable emission
manager `0x223d844fc4b006d67c0cdbd39371a9f73f69d974`. Only compiler-declared immutable
positions are populated. Both complete runtimes, including metadata, match all
six provider observations each. Claiming source-text uniqueness is out of scope.

The missing 1,853-byte token-proxy family was recovered from Etherscan's embedded
standard JSON input after Sourcify returned 404 and Blockscout returned 403. The
parser decodes one JavaScript string as data; it never executes page scripts.
Original sources/settings compile with pinned solc 0.8.22, Shanghai, 200 optimizer
runs, no IR and the original metadata policy. Full bytes match the two remaining
proxies in both retained provider replies. All **eight distinct token proxies in
twelve observations** now have compiled runtime coverage across both families.
Two fresh compiler runs per profile produce identical complete outputs.

## Execution

The existing synthetic Pool entrypoint calls the unchanged original debt function,
which burns through the actual USDC debt proxy and variable-debt implementation.
The token invokes the real rewards proxy/controller with the pre-burn scaled
balance and total supply. The controller loads nested asset/reward/user storage,
computes its index and accrued rewards, emits `Accrued`, and returns to the burn
and actual rate strategy. No rewards result is supplied to that execution.

The default retained example has pre-burn balance 100 and supply 1000. A reward
index of 1,000,000, user index 900,000, emission 100 per second, 100 elapsed seconds
and six asset decimals produce index 11,000,000 and newly accrued rewards 1010.
The stored accrued amount increases from 7 to 1017. All four ordered events and
all changed contract slots match: five Pool, two token and two rewards slots.
The token still ends at scaled balance 74 and supply 974, and rates match the
previous independently checked debt/token/rate calculation.

Eight new Rust tests include 400 seeded combined cases, each paired with the
preceding debt reference execution (which itself checks independent arithmetic).
Rewards are predicted by separate integer arithmetic; complete output, event
order and all contract-storage changes are compared. Cases cover empty/multiple
rewards, expiry, emission zero, timestamp equality and range, rounding, uint104
index and uint128 accrual bounds, future user indices and missing nested witnesses.
Standalone controller calls additionally cover zero supply and user balance with
an explicitly synthetic asset caller. Failures after a first reward update or
later Pool/rate updates must roll back all controller/token/Pool writes and logs.

The two newly covered token proxies separately execute actual aToken/debt getters
at their observed addresses, plus admin/fallback checks. This does not establish a
complete liquidation involving their underlying assets. Administrative controller
configuration, claiming rewards and transfer-strategy execution are not tested.

Fourteen Python tests verify replay and source/compiler identity, mutation rejection
including rehashed captures, immutable bounds, full runtime/metadata matching,
packed layouts, complete fixture regeneration and real CLI reproduction. Missing
controller/slot witnesses and inconsistent code hashes fail closed.

## Reproduction and limits

From `migration/nqc-miner`:

```sh
python3 research/build_aave_rewards.py --compiler-directory /absolute/compiler-directory --output /fresh/compiler-output
cargo test --locked --offline --test aave_debt_execution_tests rewards_execution
NQC_MINER_TEST_BINARY=/absolute/path/nqc-miner python3 -m unittest discover -s research -p test_aave_rewards.py -v
nqc-miner simulate --input evidence/aave-rewards-20261023/synthetic/input.json
```

The builder recompiles sources and refreshes output hashes in the new profiles;
`build_aave_rewards.fixture()` independently rebuilds the fixture from retained
compiler outputs and fully replayed captures. It does not mutate older evidence.
The retained example can be exported to a fresh directory with
`NQC_MINER_REWARDS_EVIDENCE_DIR` during the named Rust example test.

The execution state, reward parameters and Pool entrypoint remain synthetic.
Historical rewards configuration, balances, transaction boundaries and the actual
fork are not authenticated. The sandbox uses Cancun; historical fork certification
is pending. No real claim, transfer, upgrade, signing or broadcasting occurs.

The example's 209080 gas measures this harness only. The remaining work includes
aToken/underlying transfers, full health/eMode and multireserve liquidation,
authenticated transaction state, Foundry certification, hermetic integration and
prospective economic measurements. No complete liquidation or profitability is
claimed. Progress remains 43/100 and Observer stays unchanged.
