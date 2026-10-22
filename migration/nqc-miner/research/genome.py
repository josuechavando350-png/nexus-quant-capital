#!/usr/bin/env python3
"""Isolated LightGBM / native TreeSHAP research pipeline for NQC Miner.

No network, observer connection, wallet, model deployment, or critical-path use.
Source hashes establish integrity, not authenticity of claimed realized cashflows.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any

SCHEMA = "nqc-miner-genome-v1"
SOURCE_SCHEMA = "nqc-miner-genome-source-v1"
FEATURE_CATALOG = "nqc-miner-genome-features-v1"
DAY = 86_400
LABEL_HORIZON = 30 * DAY
MAX_ROWS = 10_000
MAX_FILE_BYTES = 64 * 1024 * 1024
PINNED = {"lightgbm": "4.6.0", "polars": "1.34.0", "polars-runtime-32": "1.34.0", "numpy": "2.3.5", "scipy": "1.17.0"}

# name: (minimum, maximum, nullable, integer-valued)
FEATURES: dict[str, tuple[float, float, bool, bool]] = {
    "market_age_days": (0.0, 36_500.0, False, False),
    "borrow_usd": (0.0, 1e15, False, False),
    "utilization_ratio": (0.0, 1.0, False, False),
    "liquidation_bonus_bps": (0.0, 10_000.0, False, False),
    "eligible_positions_count": (0.0, 1e9, False, True),
    "liquidators_30d_count": (0.0, 1e9, False, True),
    "median_liquidation_delay_blocks": (0.0, 1e9, True, False),
    "mean_builder_tip_share": (0.0, 10.0, True, False),
    "collateral_liquidity_usd": (0.0, 1e15, False, False),
    "oracle_staleness_seconds": (0.0, 365.0 * DAY, True, False),
    "days_until_incentive_end": (0.0, 36_500.0, True, False),
    "debt_growth_daily_bps": (0.0, 100_000.0, True, False),
}
MONEY_FIELDS = (
    "gross_realized_microusd", "successful_gas_microusd", "failed_gas_microusd",
    "direct_builder_microusd", "financing_slippage_microusd", "operations_microusd",
    "net_realized_microusd",
)
TIME_FIELDS = (
    "snapshot_unix", "feature_last_event_unix", "feature_available_unix",
    "label_window_start_unix", "label_window_end_unix", "label_finalized_at_unix",
)
METADATA_FIELDS = {
    "mine_id", "chain_id", "evidence_class", "features_source_sha256", "labels_source_sha256",
    "canonical", "finalized", "settlement_count", *TIME_FIELDS, *MONEY_FIELDS,
}
MANIFEST_FIELDS = {
    "schema", "producer", "feature_catalog", "evidence_class", "dataset_sha256",
    "declared_upstream_commit", "as_of_unix", "source_artifacts",
}
SOURCE_FIELDS = {"schema", "producer", "kind", "evidence_class", "declared_upstream_commit", "rows"}


class GenomeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise GenomeError(code, message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _commit(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None and value != "0" * 40


def _integer(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _regular_local_file(path: Path) -> Path:
    require(not path.is_symlink() and path.is_file(), "invalid_file", "a regular local file is required")
    for parent in path.absolute().parents:
        require(not parent.is_symlink(), "symlink_path", "source paths cannot traverse symbolic links")
    require(path.stat().st_size <= MAX_FILE_BYTES, "file_too_large", "file exceeds the bounded research input size")
    return path.resolve()


def _strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key", "duplicate JSON keys are forbidden")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise GenomeError("nonfinite_json", "nonfinite JSON numbers are forbidden")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GenomeError("invalid_json", "malformed JSON evidence") from error


def dependencies() -> tuple[Any, Any, Any, dict[str, str]]:
    """Fail explicitly; there is no substitute estimator if optional modules are absent."""
    versions: dict[str, str] = {}
    try:
        for package, expected in PINNED.items():
            installed = importlib.metadata.version(package)
            require(installed == expected, "dependency_version", f"{package} must be {expected}; found {installed}")
            versions[package] = installed
        os.environ.setdefault("POLARS_MAX_THREADS", "1")
        pl = importlib.import_module("polars")
        np = importlib.import_module("numpy")
        lgb = importlib.import_module("lightgbm")
    except (ModuleNotFoundError, importlib.metadata.PackageNotFoundError, OSError) as error:
        raise GenomeError("missing_dependency", "install research/requirements.txt into a Miner-only environment") from error
    return pl, np, lgb, versions


@dataclass(frozen=True)
class TrainingPolicy:
    mode: str
    minimum_training: int
    minimum_holdout: int
    minimum_training_per_class: int
    minimum_holdout_per_class: int
    minimum_snapshot_span_seconds: int
    embargo_seconds: int = DAY


def policy_for(mode: str) -> TrainingPolicy:
    require(mode in {"fixture", "realized"}, "invalid_mode", "explicit fixture or realized mode is required")
    if mode == "realized":
        return TrainingPolicy(mode, 80, 40, 15, 10, 90 * DAY)
    return TrainingPolicy(mode, 20, 10, 3, 3, 0)


@dataclass
class PreparedData:
    frame: Any
    training: Any
    holdout: Any
    purged_mine_ids: list[str]
    manifest: dict[str, Any]
    dataset_sha256: str
    manifest_sha256: str
    source_hashes: list[str]
    policy: TrainingPolicy


def _source_rows(base: Path, manifest: dict[str, Any]) -> dict[tuple[str, str, int, str], dict[str, Any]]:
    artifacts = manifest["source_artifacts"]
    require(isinstance(artifacts, list) and 2 <= len(artifacts) <= 1_000,
            "invalid_sources", "feature and outcome source artifacts are required")
    result: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    seen_digests: set[str] = set()
    total_source_bytes = 0
    total_source_rows = 0
    for ref in artifacts:
        require(isinstance(ref, dict) and set(ref) == {"path", "sha256", "kind"},
                "invalid_source_reference", "unexpected source reference fields")
        require(ref["kind"] in {"features", "outcomes"} and _digest(ref["sha256"]),
                "invalid_source_reference", "invalid source kind or digest")
        require(isinstance(ref["path"], str) and bool(ref["path"]), "invalid_source_path", "missing source path")
        relative = Path(ref["path"])
        require(not relative.is_absolute() and ".." not in relative.parts,
                "invalid_source_path", "source artifacts must remain inside the manifest directory")
        source_path = _regular_local_file(base / relative)
        require(source_path.is_relative_to(base.resolve()), "invalid_source_path", "source artifact escaped its root")
        data = source_path.read_bytes()
        total_source_bytes += len(data)
        require(total_source_bytes <= 2 * MAX_FILE_BYTES, "sources_too_large", "combined source evidence exceeds the bounded input size")
        require(sha256(data) == ref["sha256"], "source_hash_mismatch", "source artifact bytes do not match the manifest")
        require(ref["sha256"] not in seen_digests, "duplicate_source", "duplicate source artifacts")
        seen_digests.add(ref["sha256"])
        source = _strict_json(data)
        require(isinstance(source, dict) and set(source) == SOURCE_FIELDS,
                "invalid_source_schema", "source artifact fields do not match the versioned schema")
        require(source["schema"] == SOURCE_SCHEMA and source["producer"] == "nqc-miner"
                and source["kind"] == ref["kind"] and source["evidence_class"] == manifest["evidence_class"]
                and source["declared_upstream_commit"] == manifest["declared_upstream_commit"],
                "source_lineage_mismatch", "source producer, class, kind or declared commit differs")
        require(isinstance(source["rows"], list) and 1 <= len(source["rows"]) <= MAX_ROWS,
                "invalid_source_rows", "source rows are missing or unbounded")
        total_source_rows += len(source["rows"])
        require(total_source_rows <= 2 * MAX_ROWS, "sources_too_large", "combined source rows exceed the bounded input size")
        for row in source["rows"]:
            require(isinstance(row, dict), "invalid_source_row", "source row must be an object")
            mine = row.get("mine_id")
            chain = row.get("chain_id")
            require(isinstance(mine, str) and re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,127}", mine) is not None
                    and _integer(chain, 1), "invalid_source_row", "invalid source mine identity")
            key = (ref["sha256"], mine, chain, ref["kind"])
            require(key not in result, "duplicate_source_row", "one source cannot contain two rows for the same mine")
            result[key] = row
    return result


def _same_evidence(left: Any, right: Any) -> bool:
    """Numeric int/float equality is allowed; booleans must never equal amounts."""
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(_same_evidence(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same_evidence(a, b) for a, b in zip(left, right))
    if type(left) in {int, float} and type(right) in {int, float}:
        return left == right
    return type(left) is type(right) and left == right


def _validate_row(row: dict[str, Any], manifest: dict[str, Any], sources: dict[Any, Any]) -> None:
    mine = row["mine_id"]
    require(isinstance(mine, str) and re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,127}", mine) is not None,
            "invalid_mine", "mine IDs must be canonical and bounded")
    require(_integer(row["chain_id"], 1), "invalid_chain", "chain ID must be a positive integer")
    require(row["evidence_class"] == manifest["evidence_class"], "mixed_evidence", "dataset mixes evidence classes")
    require(row["canonical"] is True and row["finalized"] is True,
            "unfinalized_label", "labels must represent canonical, finalized cashflows")
    require(_integer(row["settlement_count"], 1), "missing_settlements", "a realized label requires settlement observations")
    require(all(_integer(row[field]) for field in TIME_FIELDS), "invalid_timestamp", "timestamps must be nonnegative integer Unix seconds")
    snapshot = row["snapshot_unix"]
    require(row["feature_last_event_unix"] <= row["feature_available_unix"] <= snapshot
            < row["label_window_start_unix"], "future_feature", "features must have been available before the label window")
    require(row["label_window_end_unix"] - row["label_window_start_unix"] == LABEL_HORIZON,
            "inconsistent_horizon", "every label must cover the same thirty-day horizon")
    require(row["label_window_end_unix"] <= row["label_finalized_at_unix"] <= manifest["as_of_unix"],
            "unavailable_label", "labels must finish and finalize by the dataset as-of time")
    for field in MONEY_FIELDS:
        minimum = -(2**63) if field == "net_realized_microusd" else 0
        require(_integer(row[field], minimum), "invalid_cashflow", "cashflows must be integer USD millionths")
    expected_net = row["gross_realized_microusd"] - sum(row[field] for field in MONEY_FIELDS[1:-1])
    require(expected_net == row["net_realized_microusd"], "cashflow_mismatch", "net label does not reconcile all declared costs")
    for feature, (minimum, maximum, nullable, integer) in FEATURES.items():
        value = row[feature]
        if value is None:
            require(nullable, "missing_feature", f"required feature {feature} is missing")
        else:
            require(type(value) in {int, float} and math.isfinite(value) and minimum <= value <= maximum,
                    "invalid_feature", f"invalid feature {feature}")
            require(not integer or float(value).is_integer(), "invalid_feature", f"feature {feature} must be integer-valued")
    for field in ("features_source_sha256", "labels_source_sha256"):
        require(_digest(row[field]), "invalid_source_digest", "each row needs source artifact digests")
    features = sources.get((row["features_source_sha256"], mine, row["chain_id"], "features"))
    outcomes = sources.get((row["labels_source_sha256"], mine, row["chain_id"], "outcomes"))
    require(features is not None and outcomes is not None, "missing_row_evidence", "row evidence is not present in the bound source artifacts")
    feature_record = {field: row[field] for field in ("mine_id", "chain_id", "snapshot_unix", "feature_last_event_unix", "feature_available_unix")}
    feature_record["features"] = {feature: row[feature] for feature in FEATURES}
    outcome_record = {field: row[field] for field in (
        "mine_id", "chain_id", "label_window_start_unix", "label_window_end_unix", "label_finalized_at_unix",
        "canonical", "finalized", "settlement_count", *MONEY_FIELDS,
    )}
    require(_same_evidence(features, feature_record) and _same_evidence(outcomes, outcome_record),
            "row_evidence_mismatch", "dataset row does not match its exact feature and cashflow evidence")


def prepare_data(dataset: Path, manifest_path: Path, mode: str, pl: Any) -> PreparedData:
    policy = policy_for(mode)
    dataset = _regular_local_file(dataset)
    manifest_path = _regular_local_file(manifest_path)
    require(dataset.suffix == ".parquet", "input_format", "the research dataset must be a local Parquet file")
    manifest_bytes = manifest_path.read_bytes()
    manifest = _strict_json(manifest_bytes)
    require(isinstance(manifest, dict) and set(manifest) == MANIFEST_FIELDS,
            "invalid_manifest", "unexpected manifest fields")
    require(manifest["schema"] == SCHEMA and manifest["producer"] == "nqc-miner"
            and manifest["feature_catalog"] == FEATURE_CATALOG,
            "wrong_producer", "only the isolated Miner source schema is accepted")
    require(manifest["evidence_class"] == mode, "mixed_evidence", "mode and manifest evidence class differ")
    require(_commit(manifest["declared_upstream_commit"]) and _integer(manifest["as_of_unix"])
            and _digest(manifest["dataset_sha256"]), "invalid_manifest", "missing upstream commit, as-of time or data hash")
    dataset_bytes = dataset.read_bytes()
    dataset_hash = sha256(dataset_bytes)
    require(dataset_hash == manifest["dataset_sha256"], "dataset_hash_mismatch", "dataset bytes do not match their manifest")
    try:
        schema = pl.read_parquet_schema(io.BytesIO(dataset_bytes))
        require(set(schema) == METADATA_FIELDS | set(FEATURES), "column_whitelist", "missing or unapproved dataset columns")
        frame = pl.read_parquet(io.BytesIO(dataset_bytes), n_rows=MAX_ROWS + 1, parallel="none")
    except GenomeError:
        raise
    except Exception as error:
        raise GenomeError("invalid_parquet", "Parquet dataset could not be read") from error
    require(0 < frame.height <= MAX_ROWS, "dataset_size", "dataset is empty or exceeds the row limit")
    require(frame["mine_id"].n_unique() == frame.height, "repeated_mine", "one row per mine is mandatory; repeated windows would leak entity identity")
    sources = _source_rows(manifest_path.parent, manifest)
    for row in frame.iter_rows(named=True):
        _validate_row(row, manifest, sources)
    frame = frame.with_columns([pl.col(feature).cast(pl.Float64, strict=True) for feature in FEATURES])
    frame = frame.sort(["snapshot_unix", "mine_id"])
    require(frame.height >= policy.minimum_training + policy.minimum_holdout,
            "insufficient_dataset", "not enough independent mines for the selected research mode")
    span = int(frame["snapshot_unix"].max()) - int(frame["snapshot_unix"].min())
    require(span >= policy.minimum_snapshot_span_seconds, "insufficient_time_span", "realized data must span at least ninety days of snapshots")
    holdout_count = max(policy.minimum_holdout, math.ceil(frame.height * 0.25))
    candidate_training = frame.head(frame.height - holdout_count)
    holdout = frame.tail(holdout_count)
    cutoff = int(holdout["snapshot_unix"].min())
    # Purging uses label availability, not just feature chronology. No held-out
    # label is passed into fitting, stopping, hyperparameters, or preprocessing.
    training = candidate_training.filter(pl.col("label_finalized_at_unix") < cutoff - policy.embargo_seconds)
    kept = set(training["mine_id"].to_list())
    purged = [mine for mine in candidate_training["mine_id"].to_list() if mine not in kept]
    require(training.height >= policy.minimum_training and holdout.height >= policy.minimum_holdout,
            "insufficient_purged_split", "too few mines remain after chronological label purging and embargo")
    for name, part, minimum in (
        ("training", training, policy.minimum_training_per_class),
        ("holdout", holdout, policy.minimum_holdout_per_class),
    ):
        positives = int(part.filter(pl.col("net_realized_microusd") > 0).height)
        require(min(positives, part.height - positives) >= minimum,
                "insufficient_label_classes", f"{name} needs adequate independent positive and nonpositive labels")
    return PreparedData(frame, training, holdout, purged, manifest, dataset_hash, sha256(manifest_bytes),
                        sorted({ref["sha256"] for ref in manifest["source_artifacts"]}), policy)


def _auc(labels: Any, predictions: Any) -> float:
    ordered = sorted(zip(predictions.tolist(), labels.tolist()), key=lambda item: item[0])
    positives = int(sum(labels))
    negatives = len(labels) - positives
    require(positives > 0 and negatives > 0, "undefined_auc", "AUC requires both label classes")
    rank_sum = 0.0
    first = 0
    while first < len(ordered):
        end = first + 1
        while end < len(ordered) and ordered[end][0] == ordered[first][0]:
            end += 1
        mean_rank = ((first + 1) + end) / 2.0
        rank_sum += mean_rank * sum(label for _, label in ordered[first:end])
        first = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def metrics(labels: Any, predictions: Any, np: Any) -> dict[str, float]:
    require(predictions.shape == labels.shape and bool(np.isfinite(predictions).all())
            and bool(((predictions >= 0.0) & (predictions <= 1.0)).all()),
            "invalid_predictions", "model predictions must be finite binary probabilities")
    clipped = np.clip(predictions, 1e-12, 1.0 - 1e-12)
    return {
        "brier": float(np.mean((predictions - labels) ** 2)),
        "log_loss": float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log1p(-clipped))),
        "auc": _auc(labels, predictions),
        "accuracy_at_0_5": float(np.mean((predictions >= 0.5) == labels)),
    }


def _implementation_identity() -> dict[str, Any]:
    script = Path(__file__).resolve()
    result: dict[str, Any] = {"script_sha256": sha256(script.read_bytes()),
        "requirements_sha256": sha256(script.with_name("requirements.txt").read_bytes()),
        "git_head": None, "worktree_dirty": None}
    try:
        head = subprocess.run(["git", "-C", str(script.parent), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        status = subprocess.run(["git", "-C", str(script.parent), "status", "--porcelain", "--", "genome.py", "requirements.txt"],
            check=True, capture_output=True, text=True, timeout=5).stdout
        result["git_head"] = head
        result["worktree_dirty"] = bool(status)
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def _safe_new_output(path: Path) -> Path:
    require(path.name.startswith("nqc-miner-genome-"), "output_namespace", "output directory must start with nqc-miner-genome-")
    require(not path.exists() and not path.is_symlink(), "output_exists", "output directory must be new; existing work is never overwritten")
    require(path.parent.is_dir(), "output_parent", "output parent directory must already exist")
    for parent in path.absolute().parents:
        require(not parent.is_symlink(), "symlink_path", "output must not traverse symbolic links")
    return path.absolute()


def train(dataset: Path, manifest_path: Path, output: Path, mode: str, seed: int = 1729) -> dict[str, Any]:
    require(_integer(seed, 0, 2**31 - 1), "invalid_seed", "seed must fit a nonnegative signed 32-bit integer")
    output = _safe_new_output(output)
    implementation = _implementation_identity()
    pl, np, lgb, versions = dependencies()
    prepared = prepare_data(dataset, manifest_path, mode, pl)
    names = list(FEATURES)
    x_train = prepared.training.select(names).to_numpy()
    x_test = prepared.holdout.select(names).to_numpy()
    y_train = (prepared.training["net_realized_microusd"].to_numpy() > 0).astype(np.int8)
    y_test = (prepared.holdout["net_realized_microusd"].to_numpy() > 0).astype(np.int8)
    parameters = {
        "objective": "binary", "metric": "binary_logloss", "boosting_type": "gbdt",
        "learning_rate": 0.05, "num_leaves": 7, "max_depth": 3,
        "min_data_in_leaf": 10, "min_sum_hessian_in_leaf": 1.0,
        "lambda_l1": 0.1, "lambda_l2": 1.0, "max_bin": 63,
        "feature_fraction": 1.0, "bagging_fraction": 1.0, "bagging_freq": 0,
        "seed": seed, "data_random_seed": seed, "feature_fraction_seed": seed,
        "bagging_seed": seed, "drop_seed": seed,
        "num_threads": 1, "device_type": "cpu", "deterministic": True,
        "force_col_wise": True, "verbosity": -1,
    }
    dataset_train = lgb.Dataset(x_train, label=y_train, feature_name=names, free_raw_data=False)
    # Fixed iterations and fixed parameters: the only holdout is not reused for
    # early stopping, model selection, calibration or threshold optimization.
    model = lgb.train(parameters, dataset_train, num_boost_round=64)
    probability = np.asarray(model.predict(x_test, num_threads=1), dtype=np.float64)
    raw_score = np.asarray(model.predict(x_test, raw_score=True, num_threads=1), dtype=np.float64)
    contributions = np.asarray(model.predict(x_test, pred_contrib=True, num_threads=1), dtype=np.float64)
    require(contributions.shape == (prepared.holdout.height, len(names) + 1)
            and bool(np.isfinite(contributions).all())
            and bool(np.allclose(contributions.sum(axis=1), raw_score, rtol=1e-8, atol=1e-8)),
            "shap_additivity", "native feature contributions do not reconstruct raw log-odds")
    baseline_rate = float(np.mean(y_train))
    baseline = np.full(y_test.shape, baseline_rate, dtype=np.float64)
    measured = metrics(y_test, probability, np)
    constant = metrics(y_test, baseline, np)
    improved = measured["brier"] < constant["brier"] and measured["log_loss"] < constant["log_loss"]
    explanations = []
    for index, row in enumerate(prepared.holdout.iter_rows(named=True)):
        explanations.append({
            "mine_id": row["mine_id"], "chain_id": row["chain_id"], "snapshot_unix": row["snapshot_unix"],
            "positive_net_probability": float(probability[index]), "realized_label_positive": bool(y_test[index]),
            "raw_log_odds": float(raw_score[index]), "base_log_odds": float(contributions[index, -1]),
            "feature_contributions_log_odds": {name: float(contributions[index, i]) for i, name in enumerate(names)},
        })
    importance = [{"feature": name, "mean_absolute_contribution_log_odds": float(np.mean(np.abs(contributions[:, i])))}
                  for i, name in enumerate(names)]
    importance.sort(key=lambda item: (-item["mean_absolute_contribution_log_odds"], item["feature"]))
    model_bytes = model.model_to_string(num_iteration=model.current_iteration()).encode("utf-8")
    # The serialized model must preserve predictions before an artifact is emitted.
    reloaded = lgb.Booster(model_str=model_bytes.decode("utf-8"))
    require(bool(np.array_equal(probability, reloaded.predict(x_test, num_threads=1))),
            "model_roundtrip", "serialized model predictions changed")
    current_implementation = _implementation_identity()
    require(implementation["script_sha256"] == current_implementation["script_sha256"]
            and implementation["requirements_sha256"] == current_implementation["requirements_sha256"],
            "implementation_changed", "implementation changed while the model was being fitted")
    require(sha256(_regular_local_file(dataset).read_bytes()) == prepared.dataset_sha256
            and sha256(_regular_local_file(manifest_path).read_bytes()) == prepared.manifest_sha256,
            "input_changed_during_training", "input bytes changed while the model was being fitted")
    for ref in prepared.manifest["source_artifacts"]:
        require(sha256(_regular_local_file(manifest_path.parent / ref["path"]).read_bytes()) == ref["sha256"],
                "input_changed_during_training", "source evidence changed while the model was being fitted")
    run_inputs = {"schema": SCHEMA, "dataset_sha256": prepared.dataset_sha256,
        "manifest_sha256": prepared.manifest_sha256, "implementation": implementation,
        "parameters": parameters, "rounds": 64, "mode": mode}
    status = "fixture_pipeline_verified_no_predictive_claim" if mode == "fixture" else (
        "research_candidate_baseline_improved" if improved else "research_candidate_baseline_not_improved")
    report = {
        "schema": SCHEMA, "producer": "nqc-miner", "component": 9, "status": status,
        "run_id": sha256(canonical_json(run_inputs)), "evidence_class": mode,
        "feature_catalog": FEATURE_CATALOG, "features": names,
        "feature_catalog_sha256": sha256(canonical_json(FEATURES)),
        "input_provenance": {"dataset_sha256": prepared.dataset_sha256, "manifest_sha256": prepared.manifest_sha256,
            "source_sha256": prepared.source_hashes, "declared_upstream_commit": prepared.manifest["declared_upstream_commit"],
            "as_of_unix": prepared.manifest["as_of_unix"], "verification": "sha256_and_internal_consistency_only"},
        "implementation": implementation,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(), "dependencies": versions,
            "lightgbm_threads": 1, "polars_threads": pl.thread_pool_size()},
        "model": {"file": "model.txt", "sha256": sha256(model_bytes), "parameters": parameters,
            "requested_boosting_rounds": 64, "trained_iterations": model.current_iteration()},
        "split": {"strategy": "one_mine_one_row_purged_chronological_holdout_v1", "total_mines": prepared.frame.height,
            "training_mines": prepared.training["mine_id"].to_list(), "holdout_mines": prepared.holdout["mine_id"].to_list(),
            "purged_mines": prepared.purged_mine_ids, "embargo_seconds": prepared.policy.embargo_seconds,
            "latest_training_label_finalized_at": int(prepared.training["label_finalized_at_unix"].max()),
            "first_holdout_snapshot_at": int(prepared.holdout["snapshot_unix"].min()),
            "label_horizon_seconds": LABEL_HORIZON, "holdout_used_for_tuning": False},
        "validation": {"model": measured, "constant_training_prevalence": constant,
            "baseline_probability": baseline_rate, "both_brier_and_log_loss_improved": improved,
            "statistical_significance_established": False, "economic_predictive_claim": False},
        "tree_shap": {"method": "lightgbm_native_pred_contrib", "units": "raw_log_odds",
            "additivity_verified": True, "causal_interpretation": False,
            "mean_absolute_contributions": importance, "holdout_explanations": explanations},
        "admission": {"production_model_enabled": False, "observer_bridge_enabled": False,
            "authorizes_spending": False, "automated_search_updates_enabled": False},
    }
    report_bytes = canonical_json(report)
    owner_bytes = canonical_json({"producer": "nqc-miner", "purpose": "genome_research_only", "evidence_class": mode,
        "run_id": report["run_id"], "report_sha256": sha256(report_bytes), "model_sha256": sha256(model_bytes)})
    # Exclusive creation avoids overwriting an observer directory or prior run.
    try:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name, data in (("model.txt", model_bytes), ("report.json", report_bytes), ("owner.json", owner_bytes)):
            with (output / name).open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
    except OSError as error:
        raise GenomeError("output_write_failed", "output could not be completed; do not consume it without the owner manifest") from error
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("fixture", "realized"))
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args(argv)
    try:
        report = train(args.dataset, args.manifest, args.output, args.mode, args.seed)
        print(json.dumps({"status": report["status"], "run_id": report["run_id"],
            "output": str(args.output.absolute()), "production_model_enabled": False}, sort_keys=True))
        return 0
    except (GenomeError, OSError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
