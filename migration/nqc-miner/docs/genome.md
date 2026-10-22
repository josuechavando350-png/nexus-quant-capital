# Mine genome: isolated research implementation

Component 9 now has a real optional LightGBM training pipeline, Polars Parquet input,
and native TreeSHAP explanations. It is **research code**, outside Rust ingestion,
simulation, lifecycle gates and the observer. It has no network client, transaction
sender, signing key, deployment operation or automatic search update.

No dataset of verified realized mine results was available for this implementation.
The integration tests train only artificial fixture models. Their predictive
metrics have no economic interpretation, even if the deliberately separable
fixtures score well.

## Reproducible optional environment

Create a separate Miner research environment and install
`research/requirements.txt`. The pinned packages are LightGBM 4.6.0, Polars 1.34.0,
the matching Polars runtime, NumPy 2.3.5 and SciPy 1.17.0. The pipeline checks these
versions explicitly and fails if a dependency is absent or changed. It never
silently substitutes a heuristic or a different estimator.

The executed verification environment used Python 3.12.14 on Linux x86-64. A fresh
environment can be prepared with:

```bash
python3 -m venv /tmp/nqc-miner-research-venv
/tmp/nqc-miner-research-venv/bin/python -m pip install -r research/requirements.txt
PYTHONDONTWRITEBYTECODE=1 POLARS_MAX_THREADS=1 /tmp/nqc-miner-research-venv/bin/python -m unittest discover -s research -p test_genome.py -v
```

LightGBM runs on CPU with one thread, fixed seeds, fixed parameters and
`deterministic=true, force_col_wise=true`. These settings follow the
[LightGBM 4.6.0 parameter documentation](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html#deterministic).
The report records dependency versions, Python/platform identity, the script hash,
requirements hash, observed Git HEAD and whether the implementation files were
dirty. Dependency version pins are not a claim of cross-platform bit identity;
the tests establish repeatability in the verified environment.

## Input contract

The CLI accepts a local `.parquet` dataset, a JSON manifest, an explicit mode
(`fixture` or `realized`), an integer seed, and a **new** output directory whose name
starts with `nqc-miner-genome-`. The parent directory must exist. Symlink paths,
existing output directories, unknown JSON fields, duplicate JSON keys, unsupported
producers and unexpected dataset columns are rejected.

Example invocation, after obtaining an independently verified realized dataset:

```bash
PYTHONDONTWRITEBYTECODE=1 POLARS_MAX_THREADS=1 /tmp/nqc-miner-research-venv/bin/python research/genome.py \
  --dataset /tmp/nqc-miner-input/dataset.parquet \
  --manifest /tmp/nqc-miner-input/manifest.json \
  --output /tmp/nqc-miner-genome-review-001 \
  --mode realized \
  --seed 1729
```

That command is an example, not a record of real-data training. Fixture data must
use `--mode fixture`. There is no automatic promotion from fixture to realized.

### Manifest

The manifest has exactly these fields:

| Field | Requirement |
|---|---|
| `schema` | `nqc-miner-genome-v1` |
| `producer` | `nqc-miner` |
| `feature_catalog` | `nqc-miner-genome-features-v1` |
| `evidence_class` | Matches the explicit CLI mode. |
| `dataset_sha256` | Lowercase SHA-256 of the exact Parquet bytes. |
| `declared_upstream_commit` | Nonzero, 40-character lowercase Git identity supplied by the upstream producer. |
| `as_of_unix` | Latest time at which all included labels were already finalized. |
| `source_artifacts` | Local feature and outcome evidence references, each with `path`, `sha256` and `kind`. |

Source artifact paths remain beneath the manifest directory. Their bytes must
match their hashes. Each artifact identifies `nqc-miner` as producer, uses schema
`nqc-miner-genome-source-v1`, preserves the manifest's evidence class and declared
upstream commit, and contains rows of either `features` or `outcomes`.

Every Parquet row references its feature artifact and outcome artifact by hash.
The pipeline reconstructs the row's feature and outcome records and compares them
against those exact source records. Rehashing a modified Parquet file therefore
does not bypass the separately bound evidence. Numeric values cannot be
impersonated by JSON booleans.

This is **integrity and internal consistency verification**. It does not establish
that a declared upstream commit actually produced the file, that cashflows occurred
on-chain, that the producer is authenticated, or that a source omitted nothing.
Canonical receipt reconciliation, price provenance and complete cost attribution
must be independently verified upstream. Those trust boundaries remain explicit in
the report. Parquet parsing uses the exact in-memory bytes that were hashed. Before
writing a model, the pipeline checks that its code, requirements and all input
evidence still match the original hashes; a concurrent change aborts the output.

The compact schema rejects files larger than 64 MiB, more than 10,000 mines, more
than 20,000 combined source rows or more than 128 MiB of combined source evidence.
These are engineering resource bounds for the research tool.

### One row per mine

Each row requires a unique, canonical `mine_id`, a positive `chain_id`, the same
evidence class as its manifest and all specified timestamps. Repeated windows for
the same mine are rejected. Mine IDs should include the chain in their upstream
identity to avoid accidental aliasing.

Temporal ordering must satisfy:

```
latest_feature_event <= feature_available <= snapshot < label_window_start
label_window_end = label_window_start + 30 days
label_window_end <= label_finalized_at <= dataset_as_of
```

The feature availability timestamp is distinct from the underlying event's time:
a historical fact learned only after prediction time is forbidden. A scheduled
future event may contribute a feature only if its schedule was already known at
the snapshot. The pipeline validates the asserted timestamps and their evidence
binding; upstream extraction must establish their truth.

### Fixed feature whitelist

Only these twelve fields reach the model:

| Feature | Missing values |
|---|---|
| `market_age_days` | Rejected |
| `borrow_usd` | Rejected |
| `utilization_ratio` | Rejected; must be between 0 and 1 |
| `liquidation_bonus_bps` | Rejected |
| `eligible_positions_count` | Rejected; integer-valued |
| `liquidators_30d_count` | Rejected; integer-valued |
| `median_liquidation_delay_blocks` | Allowed and retained |
| `mean_builder_tip_share` | Allowed and retained |
| `collateral_liquidity_usd` | Rejected |
| `oracle_staleness_seconds` | Allowed and retained |
| `days_until_incentive_end` | Allowed and retained |
| `debt_growth_daily_bps` | Allowed and retained |

Numeric values must be finite and within the versioned engineering bounds in
`FEATURES`. Optional nulls remain missing for LightGBM; they are not imputed using
the holdout or replaced with future observations. Mine IDs, chain IDs, outcomes,
source hashes and times are metadata and never enter the feature matrix.
Polars uses its [native Parquet reader](https://docs.pola.rs/api/python/stable/reference/api/polars.read_parquet.html)
and an explicit ordered column selection; PyArrow is not required.

### Labels and cost reconciliation

Every label covers exactly thirty days and requires canonical/finalized outcome
flags and at least one settlement observation. The target is the sign of integer
net **USD millionths**:

```
net_realized = gross_realized
               - successful_gas - failed_gas - direct_builder_payments
               - financing_and_slippage - operations
positive_label = net_realized > 0
```

Every cost field is mandatory and nonnegative. Missing costs are not replaced by
zero. The declared net must match the exact integer reconciliation. Direct builder
payments exclude expenses already counted in gas. Currency conversion and economic
completeness require upstream evidence.

`fixture`, `historical`, or `shadow` outcomes cannot be included in a `realized`
training bundle. Fixture bundles retain synthetic labels solely to exercise the
pipeline; their reports never make an economic predictive claim.

## Purged chronological validation

Rows are sorted by snapshot time and mine ID. The latest quarter is reserved as
holdout, with at least the mode's minimum holdout size. Candidate training rows are
then purged unless their complete label was finalized **more than one day before
the earliest holdout snapshot**. This prevents training on outcomes that were
unknown at the start of the validation period, including outcomes of earlier
feature snapshots whose label windows overlap the holdout.

The tool imposes the following fixed minimums after purging:

| Mode | Training mines | Holdout mines | Minimum per class in training | Minimum per class in holdout | Snapshot span |
|---|---:|---:|---:|---:|---|
| Fixture | 20 | 10 | 3 | 3 | No economic requirement |
| Realized | 80 | 40 | 15 | 10 | At least 90 days |

These are conservative **engineering gates**, not a statistical guarantee that
those sample counts are sufficient for every market. Correlated mines and changing
market regimes may require substantially more independent evidence.

The booster has fixed hyperparameters and at most 64 boosting rounds. No holdout
label enters fitting, early stopping, feature selection, preprocessing, calibration,
or decision-threshold optimization. The implementation calls the official
[`lightgbm.train`](https://lightgbm.readthedocs.io/en/v4.6.0/pythonapi/lightgbm.train.html)
API without passing the holdout as a training validation set.

The report compares Brier score and log loss against a constant predictor equal to
the training positive-label prevalence. It also reports ROC AUC, including tied
scores correctly, and accuracy at a fixed 0.5 threshold. A candidate is marked as
improving the baseline only when both Brier score and log loss improve. No
statistical significance, calibration, return forecast or causal edge is claimed.
Repeated manual tuning against this holdout would invalidate it; a later final
assessment needs untouched data.

## Native TreeSHAP and outputs

The pipeline calls `Booster.predict(..., pred_contrib=True)`. LightGBM returns one
contribution per feature plus the bias column; the pipeline checks that their sum
reconstructs `predict(..., raw_score=True)` for every held-out mine. These are
contributions in **raw log-odds**, not percentages of profit. See the official
[`Booster.predict` documentation](https://lightgbm.readthedocs.io/en/v4.6.0/pythonapi/lightgbm.Booster.html#lightgbm.Booster.predict).

Explanations describe this model's output. They do not establish causal drivers,
entity identity, reliability outside the measured scope, or a profitable action.
Mean absolute contributions are included as advisory research information; they
are not automatically written into Miner discovery rules or observer state.

The new output directory contains:

- `model.txt`: an actual serialized LightGBM model, reloaded and checked for
  identical held-out predictions before writing.
- `report.json`: exact provenance, environment, fixed parameters, split membership,
  purged mines, validation metrics, per-mine native TreeSHAP explanations and gates.
- `owner.json`: Miner ownership marker and hashes of the completed model and report.

All files are created exclusively; a previous run is never overwritten. The owner
manifest is written last. An output without a complete, matching owner manifest
must not be consumed. Every report keeps production admission, observer bridge,
automatic search updates and spending authorization **disabled**.

## What remains before a production genome

This completes a tested research pipeline, not the autonomous learning phase exit.
Remaining work includes authenticated realized datasets, complete source and price
reconciliation, real-data temporal validation, drift monitoring, model registry and
rollback, independently reviewed search feedback, and demonstrated improvement in
prospective decisions. No real-data model was trained as part of this delivery.
