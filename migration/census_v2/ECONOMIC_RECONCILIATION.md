# Historical winner economics: recovered observations and unresolved costs

**Census remains open. All 127 historical competitors remain insufficient
evidence for an executable NQC opportunity.** This population is separate from
the 474 D09/D12 candidate pairs; their counts must not be added or substituted.

The offline consumer now produces an economic ledger for every archived winner
in Ethereum blocks 25,880,316–26,095,351. It authenticates the five recovered
ZIPs, API run/commit/tree bindings, original receipt checkpoint, and the exact
raw RPC manifests already recovered on October 9. It independently recalculates
same-token arithmetic and checks it against the unchanged historical consumer.
This is a source-bound read-back, not an independent certification authority.

## What the available evidence establishes

| Observation | Result | Limit |
| --- | --- | --- |
| Winner population | 139 liquidation events in 127 transactions | Historical successful competitors; failed/censored population incomplete |
| Gas | 448369976498898050 wei, charged once per transaction | Competitor gas only; not NQC spending, net profit or complete costs |
| Raw receipts | 123 BlockPI receipts; 87 also observed by dRPC | Four raw receipts missing; hash-ordered prefixes, not representative samples |
| Full log agreement | All logs and normalized gas/actors agree for the shared 87 | Two operators do not prove independent underlying nodes or complete chain coverage |
| Flash events | 20 recognized events in 19 transactions | Only pinned Aave/Balancer emitters and supported ABIs; absence is not zero financing cost |
| Balancer fee events | 19 events report zero raw fee | Historical event amounts, not a current quote or NQC funding admission |
| Aave fee event | Principal 12412 and fee 7, in raw units of asset `0x2260fac5e5542a773aa44fbcfedf7c193bc2c599` | Do not assume token decimals, convert to USD or infer an observed premium rate |
| Flash event corroboration | 12 events have both operators; eight have one | Each record retains its own witness count, hashes and receipt time |
| Token flow observations | 1,648 ERC20-shaped Transfer logs; 327 selected actor/token net-log rows | Logs are not balance proofs, beneficial ownership, native transfers or realized profit |
| WETH/WETH population | All nine historical cases retained | Retrospective diagnostic, not out-of-sample discovery |
| Conditional WETH arithmetic | Nine positive after competitor gas; eight after an illustrative 5 bps fee | Other costs unresolved; the 5 bps input is not an authenticated quote |
| Available WETH/USD references | Two samples: retrospective ranks 1 and 3 | Rank 2 has no locally recovered price evidence; previous-block prices are not transaction pre-state |

The ninth WETH case has only 103299 wei remaining after observed competitor gas.
Subtracting the illustrative rounded-up 5 bps fee makes that reference negative
by 2049022153595 wei. All nine retain their signs and denominator. Neither a
positive conditional remainder nor an observed competitor flash loan promotes
a case into NQC's executable set.

## Cost and decision-time treatment

Every transaction has an explicit conflict identity, liquidation log indices,
asset-specific repayment/collateral quantities, whole-transaction gas, witness
hashes, classification and material-gap references. Token quantities with
different assets are never added as money. Receipt gas is never multiplied by
the number of liquidation events. Base/priority fee decomposition remains null;
it is included in the known aggregate, not charged again.

Protocol liquidation fees, complete flash fees, swap fees, slippage, builder
payments, financier costs, inventory/conversions, attributed failed attempts,
infrastructure and other liabilities remain null unless fully reconciled.
Each has an explicit evidence requirement in `unknown_cost_treatments`.
Protocol fees and swap effects must be reconciled against actual output before
subtraction, to avoid charging costs already included in an observed cashflow.
Estimated opportunity cost is separate from paid costs and pending obligations.

`selected-actor-token-flows.jsonl` records signed Transfer-log changes for the
transaction sender, recipient, liquidation callers and observed flash receivers.
Addresses are not merged into an assumed owner. WETH wrapping, native internal
transfers, nonstandard token behavior, rebases, actual balances and unobserved
payments are not reconstructed. A positive token-log delta is not profit.

Flash decoders check emitter, full ABI shape, padding, integer domains and exact
log identity. Every receipt log is tied to transaction/block/hash/index and
reorg status before interpretation. Official interface source bytes and their
commit/tree/blob/SHA identities are pinned under `evidence/economics/abi/`.
Those interface references establish decoding layout; they do not establish
historical deployed-bytecode parity. Original license notices are preserved.

October 9 acquisition times cannot establish what NQC knew before these
September/October 1 transactions. No capture probability is assigned. The
MXN 2,000 gas-only amendment remains authoritative for future authorized work,
with zero own principal/collateral/guarantees. It is not applied retroactively;
no gas was spent by this reconciliation.

## Reproduction

The raw receipt files are in the already preserved
`NQC_Census_Winner_RPC_Evidence_20261009.zip` (SHA-256
`fdffde6d1dc14ab648f42033661a3667dc7b2a93e761c83f918f36d8c0849195`).
Use its original directories and five original ZIPs. The script has no network
acquisition, signing or broadcasting path. Missing input fails; it is not
replaced by synthetic data.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/check_winner_economics.py \
  --archive-root /absolute/path/recovered \
  --rpc-root /absolute/path/recovered -v
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/reconcile_winner_economics.py \
  --archive-root /absolute/path/recovered \
  --rpc-root /absolute/path/recovered \
  --output /absolute/path/fresh-output
```

The output ledger hashes, raw manifest pins, original archive identities,
capital-policy hash and verifier source hash are in `reconciliation.json`.
The enclosing Git commit/tree identifies this new producer; historical source
identities are preserved. Eight real-source/adversarial checks cover arithmetic,
double counting, log identity, malformed ABI, wrong emitters, price lookahead,
duplicate prices, missing input and deterministic reproduction.

## Recovery limits

GitHub metadata identifies 13 additional historical economic/receipt archives.
Their connector downloads returned file references, but local materialization
was blocked with HTTP 403 (`error code: 1010`). The same-URL diagnostic confirmed
the denial; no alternate access route was attempted. Their bytes are not
recovered, verified or included as economic inputs. The metadata-only inventory
and failure are retained in `evidence/economics/additional-acquisition.json`.

The separate RPC transport denial remains unresolved. The source device
`codex-nqc-rmc-328dd6` was checked again and was offline, last seen 48 hours ago.
The original episode, censored-opportunity and complete economic ledgers remain
unavailable. Authentic gas funding, external principal admission, routes, full
costs, capture evidence and independent producer review are still required for
Census closure. This work issues no terminal or commercial certification.
