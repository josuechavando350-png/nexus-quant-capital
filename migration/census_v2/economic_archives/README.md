# Recovered economic archives and complete decoded receipt logs

Thirteen original economic archives previously available only as metadata are
now recovered, SHA-256 verified and bound to fresh GitHub run/commit/tree/artifact
snapshots. The earlier signed-download HTTP 403 remains in the original record.
This recovery uses the normal artifact-download connector. The offline consumer
makes no RPC or other network requests.

| Check | Result |
| --- | --- |
| Original gas and transaction identities | All 127 match; gas stays counted once per transaction. |
| Earlier full receipt/log witnesses | All 210 match: 123 BlockPI and 87 dRPC observations, covering 123 distinct transactions. |
| Previously missing full receipts | Four now have decoded logs. The historical ledger stays unchanged. |
| Liquidation event amounts | All 139 decoded records are byte-identical to the authenticated legs archive. |
| Receipt logs | 3,720 validated logs, including 1,696 ERC20-shaped transfers. |
| Recognized flash events | 22 events in 21 transactions: two Aave and 20 Balancer. All prior 20 events are preserved. |
| Additional flash observations | One Aave UNI principal/fee event and one zero-fee Balancer UNI event in two formerly missing receipts. |
| Historical WETH cost calculation | Nine-case producer rerun: byte-identical to both push/PR payloads. Those duplicates are not new market observations. |
| Historical fee reference | Three retained preblock observations reconcile, including exact half-up rounding. No new fee quote or RPC observation. |

Receipt records are decoded JSON results, not original HTTP bytes; per-request
acquisition timestamps are missing. All 127 have normalized parity with the
original dRPC checkpoint, but full log comparison to earlier operators covers
only 123 transactions. Operator labels do not prove distinct underlying nodes.
The failed dRPC parent run remains failed.

Historical pool fees are not authenticated available principal or proof of a
competitor's actual financing route. Eight of nine WETH cases are positive only
under the old illustrative five-basis-point calculation, before omitted costs;
this is not NQC profit or capture. Transfer logs do not prove balances, complete
native transfers, off-chain payments, full liabilities, unexecuted opportunities
or decision-time availability.

Original reports keep their historical `own_capital_usd: "0"` and external-gas
assumptions. These are **not the active NQC policy**. The consumer separately
binds the unchanged **MXN 2,000 cumulative gas-only policy**, without retroactive
application. Original economic classifications remain insufficient evidence.

## Reproduction

The 13 recovered archives and three small upstream archives are under `inputs/`.
Metadata, inner manifests, report commitments and membership are checked before
arithmetic or receipt interpretation. Choose a new output path:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/economic_archives/reconcile.py \
  --out /absolute/path/new-economic-replay
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s migration/census_v2/economic_archives -p test_reconcile.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ci/nqc-census \
  python3 ci/nqc-census/test_rmc016_weth_cashflow_audit.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ci/nqc-census \
  python3 ci/nqc-census/test_rmc016_historical_aave_flash_premium.py -v
```

Eight new real-input/adversarial checks, 18 original WETH tests and 14 original
premium tests pass: **40 tests, zero skips**. Original unit suites use synthetic
adversarial fixtures; the integration uses authenticated archives. Two complete
runs produce byte-identical reports and flash-observation ledgers. Logs, exact
commands, report and isolation output are under `evidence/`. Rust code is
unchanged and Rust suites were not rerun.

No imported source was edited, no workflow enabled and no gas spent. This closes
the missing economic-archive transport and four-receipt log gaps. Full historical
coverage, executable token compatibility, complete execution costs, financing,
inclusion/capture and independent Census review remain open.
