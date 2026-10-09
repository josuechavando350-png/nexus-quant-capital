# Physical evidence recovered from original job logs

Four original GitHub Actions job logs record 16 successful physical test
executions. This change preserves their decoded bytes, reconciles their
provenance and measured outputs, and binds ten original source files. It does
not rerun a fork or issue an independent certification. Census remains open.

## Original scope and identity

All runs belong to `josuechavando350-png/nexus-engine`, with event
`pull_request` and conclusion `success`. The original repository was read only.
Full commit/tree, artifact metadata, log SHA-256 and source Git blob/SHA-256
identities are in `evidence/physical-logs/pins.json`, `api-snapshot.json` and
`source-origins.json`. Actual checkout output agrees with the pinned run head.
Historical workflows are preserved as `.txt` evidence; none was enabled.

| Original run / job | Observed tests | Narrow result |
| --- | ---: | --- |
| 37737680174 / 113180865275 | 9 | WETH deposit, withdrawal, transfers, allowances, runtime and metadata behavior at Ethereum block 26,095,351. |
| 37740704145 / 113190514122 | 3 | Three previously selected winners examined by advancing block/time from each preceding block. Only rank one crosses health factor below one. |
| 37741109591 / 113191790079 | 2 | Rank-one fork liquidation repays principal and premium without test WETH top-up; impossible profit requirement reverts atomically. |
| 37742063251 / 113194816303 | 2 | Same positive/rollback cases, including measured execute-call gas. |

The logs are the exact UTF-8 decoded text returned by the job-log connector,
stored with deterministic gzip compression. They are not claimed to be raw
HTTP response bytes. API snapshots preserve run/job/artifact metadata, but
offline copies cannot authenticate their own remote provenance. Precise
per-call acquisition receipt times were not retained; historical runner
timestamps are preserved separately. All four artifact ZIPs are still missing.
Job logs are a separate supported resource, not a substitute download of the
previously denied archives. No new RPC call or fork execution was made.

## Measured facts and economic limits

For historical reference transaction
`0x6313fb267755f3cfa48214bf74309505984306129ee09a558efe4801006dcbba`,
the test forks the preceding block, 25,938,047, then advances block/time to
25,938,048. It does not replay the intervening original transactions.

| Quantity | Original source/log result |
| --- | ---: |
| Principal, from pinned test source | 10,684,013,854,557,827,871 WETH wei |
| Flash fee, logged | 5,342,006,927,278,914 WETH wei |
| Fork surplus after repayment, before gas | 90,814,117,763,741,536 WETH wei |
| Execute-call gas, logged | 562,357 gas units |
| Production gas sponsored, logged flag | 0 |

The surplus equals separately recovered liquidation collateral minus debt
minus the logged fork fee, using integer arithmetic. The oracle reference is
bound to the already recovered `winner-weth-prices-original.zip`, its API
transport pin and inner report hash: preceding-block price 250,480,170,000 in
USD units of 1e-8. This is a historical reference valuation, not an executable
conversion price or realized income.

Five gas sensitivities are reproduced from the logged call-gas value and the
job-reported base fee of 59,451,728 wei/gas. They assume 21,000 intrinsic gas,
additional overhead of 0/50,000/100,000/200,000/300,000 units and tips of
0/1/2/5/10 gwei. All five retain positive conditional surplus. These are
gas-only scenarios: calldata, actual transaction overhead, builder payments,
failure costs, competition, native-gas funding and capture are not established.
The job's underlying header/RPC bytes were not recovered here. WETH/ETH par
accounting does not prove that native ETH was available to pay upfront gas.

The three logged health-factor pairs, in WAD, are:

| Retrospective rank | Previous block | After time-only advance |
| --- | ---: | ---: |
| 1 | 1000000001993818630 | 999999999704293538 |
| 2 | 1000701093031081909 | 1000701096098308225 |
| 3 | 1000489719586999148 | 1000489713637144623 |

Selection uses later-known winners. These observations do not demonstrate
prediction, decision-time knowledge, exact intrablock execution, inclusion or
that Nexus would have beaten competitors. Test-plan placeholder hashes are
not authenticated financing quotes. Scoped WETH behavior does not resolve
all 43 underlying-asset blockers in the separate D12 candidate population.

## Fee-rounding review

The imported capital adapter already uses `RoundingMode::Ceil` and has the
PFT-linked regression
`aave_v3_adapter_matches_pft_compat_009_flash_premium_ceiling`. That existing
test passed here (one passed, 19 filtered); no original Rust source changed.
Some historical research helpers use half-up arithmetic. Their immutability
is preserved and they must not be promoted to executable fee quotes without
version/deployment/state proof. The selected WETH fork amount gives the same
result under both modes, so its success cannot distinguish rounding modes.
The separate WBTC receipt's amount 12,412 and fee 7 would distinguish ceil
from half-up *at an assumed 5 bps*, but the receipt alone does not prove that
historical rate. No deployment claim is inferred from current upstream code.

## Reproduction and checks

Run from the repository root with the actual previously recovered oracle
archive in `--archive-root`; output paths must be new:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/verify_physical_recovery.py \
  --archive-root /absolute/path/archives --output /absolute/path/new-report.json
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_physical_recovery.py \
  --archive-root /absolute/path/archives -v
PYTHONDONTWRITEBYTECODE=1 python3 migration/verify_isolation.py \
  --source-git /absolute/path/nqc-original-objects
```

The consumer distinguishes actual runner output from displayed shell commands.
It rejects missing/duplicate suites or measurements, actual failures, altered
log/source bytes and mismatched run/checkout/tree/artifact identities. Eight
offline tests exercise these boundaries and the integer reconciliation; their
results are distinct from the 16 historical executions merely observed above.
`reconciliation.json` binds the consumer hash. `validation.json` and its logs
record the current commands and results. The enclosing commit/tree binds the
new consumer; original producer identities never become this producer's
certification. Historical broad-suite setup errors/skips remain unresolved as
recorded in the main README; they are not relabeled by these passing checks.

## Closure implications

The missing physical ZIPs and full input chains still need independent
recovery/replay. Complete declared market coverage, authentic decision-time
and censored ledgers, admissible capital, complete costs/routes, competition
and independent authority remain necessary for final Census closure. Every
material unknown keeps its treatment in the existing candidate/economic
ledgers; these logs do not change any executable classification.

The user's MXN 2,000 gas-only amendment remains recorded, with no retroactive
application to these historical tests. No principal, collateral or additional
liability is authorized by these results. No transaction was signed or sent,
and no gas or infrastructure was purchased.
