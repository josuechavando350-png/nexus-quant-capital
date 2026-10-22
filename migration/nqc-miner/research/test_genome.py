"""Adversarial data gates and real LightGBM/TreeSHAP integration on fixtures only."""
from __future__ import annotations

import contextlib
import copy
import importlib.metadata
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import genome


def fixture_rows(count: int = 80) -> list[dict]:
    """Artificial separable data; never an assertion about an economic mine."""
    rows = []
    for i in range(count):
        snapshot = 1_500_000_000 + i * 7 * genome.DAY
        positive = i % 2 == 0
        gross = 200_000_000 if positive else 1_000_000
        rows.append({
            "mine_id": f"fixture-mine-{i:04d}", "chain_id": 1, "evidence_class": "fixture",
            "snapshot_unix": snapshot, "feature_last_event_unix": snapshot - 120,
            "feature_available_unix": snapshot - 60, "label_window_start_unix": snapshot + 1,
            "label_window_end_unix": snapshot + 1 + genome.LABEL_HORIZON,
            "label_finalized_at_unix": snapshot + 1 + genome.LABEL_HORIZON + 3_600,
            "canonical": True, "finalized": True, "settlement_count": 2,
            "gross_realized_microusd": gross, "successful_gas_microusd": 3_000_000,
            "failed_gas_microusd": 2_000_000, "direct_builder_microusd": 2_000_000,
            "financing_slippage_microusd": 1_000_000, "operations_microusd": 1_000_000,
            "net_realized_microusd": gross - 9_000_000,
            "market_age_days": 300.0 if positive else 3.0,
            "borrow_usd": 1_000_000.0 + i * 100.0, "utilization_ratio": 0.7,
            "liquidation_bonus_bps": 500.0, "eligible_positions_count": 15,
            "liquidators_30d_count": 1 if positive else 20,
            "median_liquidation_delay_blocks": 10.0 if positive else 0.0,
            "mean_builder_tip_share": 0.02 if positive else 0.9,
            "collateral_liquidity_usd": 1_000_000.0, "oracle_staleness_seconds": 30.0,
            "days_until_incentive_end": None, "debt_growth_daily_bps": 1.0,
        })
    return rows


def write_bundle(root: Path, rows: list[dict] | None = None, mode: str = "fixture") -> tuple[Path, Path]:
    pl, _, _, _ = genome.dependencies()
    rows = copy.deepcopy(fixture_rows() if rows is None else rows)
    root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        row["evidence_class"] = mode
    shared = {"schema": genome.SOURCE_SCHEMA, "producer": "nqc-miner", "evidence_class": mode,
              "declared_upstream_commit": "a" * 40}
    feature_rows = []
    outcome_rows = []
    for row in rows:
        features = {field: row[field] for field in ("mine_id", "chain_id", "snapshot_unix", "feature_last_event_unix", "feature_available_unix")}
        features["features"] = {name: row[name] for name in genome.FEATURES}
        feature_rows.append(features)
        outcome_rows.append({field: row[field] for field in (
            "mine_id", "chain_id", "label_window_start_unix", "label_window_end_unix", "label_finalized_at_unix",
            "canonical", "finalized", "settlement_count", *genome.MONEY_FIELDS,
        )})
    features_bytes = genome.canonical_json({**shared, "kind": "features", "rows": feature_rows})
    outcomes_bytes = genome.canonical_json({**shared, "kind": "outcomes", "rows": outcome_rows})
    (root / "features.json").write_bytes(features_bytes)
    (root / "outcomes.json").write_bytes(outcomes_bytes)
    for row in rows:
        row["features_source_sha256"] = genome.sha256(features_bytes)
        row["labels_source_sha256"] = genome.sha256(outcomes_bytes)
    dataset = root / "dataset.parquet"
    pl.DataFrame(rows).write_parquet(dataset)
    manifest = root / "manifest.json"
    manifest.write_bytes(genome.canonical_json({
        "schema": genome.SCHEMA, "producer": "nqc-miner", "feature_catalog": genome.FEATURE_CATALOG,
        "evidence_class": mode, "dataset_sha256": genome.sha256(dataset.read_bytes()),
        "declared_upstream_commit": "a" * 40,
        "as_of_unix": max(row["label_finalized_at_unix"] for row in rows) + 1,
        "source_artifacts": [
            {"path": "features.json", "sha256": genome.sha256(features_bytes), "kind": "features"},
            {"path": "outcomes.json", "sha256": genome.sha256(outcomes_bytes), "kind": "outcomes"},
        ],
    }))
    return dataset, manifest


class GenomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl, cls.np, cls.lgb, cls.versions = genome.dependencies()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nqc-miner-genome-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, dataset: Path, manifest: Path, mode: str = "fixture"):
        return genome.prepare_data(dataset, manifest, mode, self.pl)

    def assert_code(self, code: str, callback):
        with self.assertRaises(genome.GenomeError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def rewrite_dataset(self, dataset: Path, manifest: Path, frame):
        frame.write_parquet(dataset)
        value = json.loads(manifest.read_text())
        value["dataset_sha256"] = genome.sha256(dataset.read_bytes())
        manifest.write_bytes(genome.canonical_json(value))

    def test_actual_lightgbm_and_native_treeshap_roundtrip(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        output = self.root / "nqc-miner-genome-fixture"
        report = genome.train(dataset, manifest, output, "fixture")
        self.assertEqual(report["status"], "fixture_pipeline_verified_no_predictive_claim")
        self.assertEqual(report["runtime"]["dependencies"]["lightgbm"], "4.6.0")
        self.assertEqual(report["runtime"]["lightgbm_threads"], 1)
        self.assertTrue(report["tree_shap"]["additivity_verified"])
        self.assertFalse(report["validation"]["economic_predictive_claim"])
        self.assertTrue(report["validation"]["both_brier_and_log_loss_improved"])
        self.assertTrue(all(value is False for value in report["admission"].values()))
        self.assertEqual(set(report["features"]), set(genome.FEATURES))
        for item in report["tree_shap"]["holdout_explanations"]:
            total = item["base_log_odds"] + sum(item["feature_contributions_log_odds"].values())
            self.assertAlmostEqual(total, item["raw_log_odds"], places=8)
        owner = json.loads((output / "owner.json").read_text())
        self.assertEqual(owner["model_sha256"], genome.sha256((output / "model.txt").read_bytes()))
        self.assertEqual(owner["report_sha256"], genome.sha256((output / "report.json").read_bytes()))
        self.assertEqual(set(path.name for path in output.iterdir()), {"model.txt", "report.json", "owner.json"})

    def test_same_seed_and_data_produce_identical_model_and_explanations(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        a = genome.train(dataset, manifest, self.root / "nqc-miner-genome-one", "fixture", seed=10)
        b = genome.train(dataset, manifest, self.root / "nqc-miner-genome-two", "fixture", seed=10)
        self.assertEqual(a["model"]["sha256"], b["model"]["sha256"])
        self.assertEqual(a["tree_shap"], b["tree_shap"])
        self.assertEqual(a["validation"], b["validation"])

    def test_chronology_purges_unavailable_training_labels(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        data = self.prepare(dataset, manifest)
        self.assertGreater(len(data.purged_mine_ids), 0)
        self.assertLess(int(data.training["label_finalized_at_unix"].max()) + data.policy.embargo_seconds,
                        int(data.holdout["snapshot_unix"].min()))
        self.assertTrue(set(data.training["mine_id"].to_list()).isdisjoint(data.holdout["mine_id"].to_list()))

    def test_concurrent_input_change_aborts_before_any_output(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        output = self.root / "nqc-miner-genome-concurrent"
        original_train = self.lgb.train

        def mutating_train(*args, **kwargs):
            dataset.write_bytes(dataset.read_bytes() + b"changed-during-training")
            return original_train(*args, **kwargs)

        with patch.object(self.lgb, "train", side_effect=mutating_train):
            self.assert_code("input_changed_during_training", lambda: genome.train(dataset, manifest, output, "fixture"))
        self.assertFalse(output.exists())

    def test_concurrent_implementation_change_aborts_before_any_output(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        output = self.root / "nqc-miner-genome-concurrent-code"
        before = {"script_sha256": "a" * 64, "requirements_sha256": "c" * 64, "git_head": "d" * 40, "worktree_dirty": True}
        after = {**before, "script_sha256": "b" * 64}
        with patch("genome._implementation_identity", side_effect=[before, after]):
            self.assert_code("implementation_changed", lambda: genome.train(dataset, manifest, output, "fixture"))
        self.assertFalse(output.exists())

    def test_repeated_mine_cannot_leak_into_two_splits(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        frame = self.pl.read_parquet(dataset)
        frame = self.pl.concat([frame, frame.head(1)])
        self.rewrite_dataset(dataset, manifest, frame)
        self.assert_code("repeated_mine", lambda: self.prepare(dataset, manifest))

    def test_feature_observed_after_snapshot_is_rejected(self):
        rows = fixture_rows(); rows[0]["feature_last_event_unix"] = rows[0]["snapshot_unix"] + 1
        rows[0]["feature_available_unix"] = rows[0]["snapshot_unix"] + 1
        dataset, manifest = write_bundle(self.root / "inputs", rows)
        self.assert_code("future_feature", lambda: self.prepare(dataset, manifest))

    def test_historical_feature_learned_only_later_is_also_rejected(self):
        rows = fixture_rows(); rows[0]["feature_available_unix"] = rows[0]["label_window_start_unix"] + 1
        dataset, manifest = write_bundle(self.root / "inputs", rows)
        self.assert_code("future_feature", lambda: self.prepare(dataset, manifest))

    def test_unequal_label_horizons_cannot_be_compared(self):
        rows = fixture_rows(); rows[0]["label_window_end_unix"] -= 1
        dataset, manifest = write_bundle(self.root / "inputs", rows)
        self.assert_code("inconsistent_horizon", lambda: self.prepare(dataset, manifest))

    def test_fixture_cannot_be_used_in_realized_mode(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        self.assert_code("mixed_evidence", lambda: self.prepare(dataset, manifest, "realized"))

    def test_synthetic_rows_claiming_realized_still_fail_minimum_dataset_gate(self):
        # Adversarial claimed class only. No model is fitted and no real data exists.
        dataset, manifest = write_bundle(self.root / "inputs", fixture_rows(40), mode="realized")
        self.assert_code("insufficient_dataset", lambda: self.prepare(dataset, manifest, "realized"))

    def test_no_training_with_only_positive_labels(self):
        rows = fixture_rows()
        for row in rows:
            row["gross_realized_microusd"] = 100_000_000
            row["net_realized_microusd"] = 91_000_000
        dataset, manifest = write_bundle(self.root / "inputs", rows)
        self.assert_code("insufficient_label_classes", lambda: self.prepare(dataset, manifest))

    def test_unapproved_feature_column_is_rejected_even_if_harmless_looking(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        frame = self.pl.read_parquet(dataset).with_columns(self.pl.lit(1.0).alias("future_profit_hint"))
        self.rewrite_dataset(dataset, manifest, frame)
        self.assert_code("column_whitelist", lambda: self.prepare(dataset, manifest))

    def test_labels_must_reconcile_failed_gas_and_all_other_costs(self):
        rows = fixture_rows(); rows[0]["failed_gas_microusd"] += 1
        dataset, manifest = write_bundle(self.root / "inputs", rows)
        self.assert_code("cashflow_mismatch", lambda: self.prepare(dataset, manifest))

    def test_missing_cost_is_not_imputed_as_zero(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        frame = self.pl.read_parquet(dataset).drop("failed_gas_microusd")
        self.rewrite_dataset(dataset, manifest, frame)
        self.assert_code("column_whitelist", lambda: self.prepare(dataset, manifest))

    def test_dataset_hash_and_source_hash_are_checked(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        original = dataset.read_bytes()
        dataset.write_bytes(original + b"tampered")
        self.assert_code("dataset_hash_mismatch", lambda: self.prepare(dataset, manifest))
        dataset.write_bytes(original)
        source = self.root / "inputs" / "outcomes.json"
        source.write_bytes(source.read_bytes() + b" ")
        self.assert_code("source_hash_mismatch", lambda: self.prepare(dataset, manifest))

    def test_rehashing_modified_parquet_does_not_bypass_source_evidence(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        frame = self.pl.read_parquet(dataset).with_columns((self.pl.col("borrow_usd") + 1.0).alias("borrow_usd"))
        self.rewrite_dataset(dataset, manifest, frame)
        self.assert_code("row_evidence_mismatch", lambda: self.prepare(dataset, manifest))

    def test_source_producer_and_mode_are_isolated(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        value = json.loads(manifest.read_text()); value["producer"] = "sovereign-radar-omega"
        manifest.write_bytes(genome.canonical_json(value))
        self.assert_code("wrong_producer", lambda: self.prepare(dataset, manifest))

    def test_sources_cannot_escape_input_directory(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        value = json.loads(manifest.read_text()); value["source_artifacts"][0]["path"] = "../outside.json"
        manifest.write_bytes(genome.canonical_json(value))
        self.assert_code("invalid_source_path", lambda: self.prepare(dataset, manifest))

    def test_unfinalized_or_noncanonical_outcomes_are_not_training_labels(self):
        for field in ("canonical", "finalized"):
            with self.subTest(field=field):
                rows = fixture_rows(); rows[0][field] = False
                dataset, manifest = write_bundle(self.root / field, rows)
                self.assert_code("unfinalized_label", lambda: self.prepare(dataset, manifest))

    def test_dependency_missing_is_explicit_and_no_fallback_model_runs(self):
        with patch("genome.importlib.metadata.version", side_effect=importlib.metadata.PackageNotFoundError("lightgbm")):
            self.assert_code("missing_dependency", genome.dependencies)

    def test_dependency_version_drift_is_rejected(self):
        with patch("genome.importlib.metadata.version", return_value="0.0.0"):
            self.assert_code("dependency_version", genome.dependencies)

    def test_output_is_namespaced_and_existing_results_are_never_overwritten(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        self.assert_code("output_namespace", lambda: genome.train(dataset, manifest, self.root / "observer", "fixture"))
        output = self.root / "nqc-miner-genome-existing"; output.mkdir()
        (output / "keep.txt").write_text("unchanged")
        self.assert_code("output_exists", lambda: genome.train(dataset, manifest, output, "fixture"))
        self.assertEqual((output / "keep.txt").read_text(), "unchanged")

    def test_native_missing_features_are_not_replaced_by_future_information(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        prepared = self.prepare(dataset, manifest)
        self.assertEqual(prepared.frame["days_until_incentive_end"].null_count(), prepared.frame.height)

    def test_brier_log_loss_and_tied_auc_match_hand_calculation(self):
        labels = self.np.array([0, 1, 0, 1])
        p = self.np.full(4, 0.5)
        result = genome.metrics(labels, p, self.np)
        self.assertEqual(result["brier"], 0.25)
        self.assertAlmostEqual(result["log_loss"], 0.6931471805599453)
        self.assertEqual(result["auc"], 0.5)
        perfect = genome.metrics(labels, self.np.array([0.1, 0.9, 0.1, 0.9]), self.np)
        self.assertEqual(perfect["auc"], 1.0)

    def test_unknown_json_fields_and_duplicate_keys_fail(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        value = json.loads(manifest.read_text()); value["approved"] = True
        manifest.write_bytes(genome.canonical_json(value))
        self.assert_code("invalid_manifest", lambda: self.prepare(dataset, manifest))
        self.assert_code("duplicate_json_key", lambda: genome._strict_json(b'{"a":1,"a":2}'))

    def test_boolean_cannot_impersonate_numeric_evidence(self):
        self.assertFalse(genome._same_evidence({"amount": True}, {"amount": 1}))
        self.assertTrue(genome._same_evidence({"amount": 1.0}, {"amount": 1}))

    def test_cli_failure_is_structured_and_does_not_create_output(self):
        dataset, manifest = write_bundle(self.root / "inputs")
        output = self.root / "nqc-miner-genome-blocked"
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            status = genome.main(["--dataset", str(dataset), "--manifest", str(manifest),
                                  "--output", str(output), "--mode", "realized"])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(stream.getvalue())["status"], "blocked")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
