"""Offline tests of a paired Slither contract. All scanner outputs are synthetic.

These tests DO NOT run Slither or solc and do NOT prove scanner accuracy.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import slither_control_pair as pair
from superhunter import slither_owned_runner as scanner
from superhunter import slither_owned_worker as worker
from superhunter.safe_io import canonical, strict_json


def synthetic_result(mode: str) -> dict:
    if mode not in ("positive", "clean", "comparison"):
        raise ValueError("UNKNOWN_MODE")
    source = {"positive": scanner.OWNED_SOURCE, "clean": pair.CLEAN_SOURCE,
              "comparison": pair.COMPARISON_SOURCE}[mode]
    alerts = [{"check": scanner.DETECTOR, "source_bound": True}] if mode == "positive" else []
    return {"normalization_complete": True, "vulnerability_confirmed": False,
            "raw_alert_count": 1 if mode == "positive" else 0, "unique_alert_count": len(alerts),
            "source_bound_alerts": len(alerts),
            "source_sha256": {"Owned.sol": pair.sha(source)},
            "alerts": alerts, "input_kind": "external-report",
            "repository_declared": {"repo": "superhunter-owned/fixture", "commit": "a" * 40},
            "scope_id_declared": ("owned-fixed-local-fixture" if mode == "positive"
                                  else "owned-fixed-local-fixture-" + mode),
            "tool_declared": {"name": "slither", "version": scanner.SCANNER_VERSION},
            "detectors_declared": [scanner.DETECTOR],
            "scanner_execution_verified": False,
            "repository_commit_verified": False}


class SlitherPairTests(unittest.TestCase):
    def test_fixed_clean_source_differs_only_in_authorization(self):
        self.assertEqual(pair.CLEAN_SOURCE, scanner.OWNED_SOURCE.replace(b"tx.origin", b"msg.sender"))
        self.assertEqual(len(pair.CLEAN_SOURCE), 289)
        self.assertEqual(pair.sha(pair.CLEAN_SOURCE), pair.CLEAN_SHA256)

    def test_detector_specific_comparison_is_fixed_and_keeps_tx_origin(self):
        self.assertIn(b"tx.origin == msg.sender", pair.COMPARISON_SOURCE)
        self.assertEqual(len(pair.COMPARISON_SOURCE), 301)
        self.assertEqual(pair.sha(pair.COMPARISON_SOURCE), pair.COMPARISON_SHA256)
        pair.accept(synthetic_result("comparison"), False,
                    expected_source=pair.COMPARISON_SOURCE)
        wrong = synthetic_result("comparison")
        wrong["alerts"] = [{"check": scanner.DETECTOR, "source_bound": True}]
        wrong["raw_alert_count"] = 1
        wrong["unique_alert_count"] = 1
        wrong["source_bound_alerts"] = 1
        with self.assertRaisesRegex(ValueError, "SLITHER_CONTROL_MISMATCH"):
            pair.accept(wrong, False, expected_source=pair.COMPARISON_SOURCE)


    def test_positive_detector_must_report_source_bound_finding(self):
        pair.accept(synthetic_result("positive"), True)
        wrong = synthetic_result("positive")
        wrong["alerts"][0]["source_bound"] = False
        with self.assertRaises(ValueError):
            pair.accept(wrong, True)

    def test_clean_control_must_have_no_false_positive(self):
        pair.accept(synthetic_result("clean"), False)
        wrong = synthetic_result("clean")
        wrong["raw_alert_count"] = 1
        with self.assertRaises(ValueError):
            pair.accept(wrong, False)

    def test_cross_source_and_boolean_counts_fail_closed(self):
        wrong = synthetic_result("clean")
        wrong["source_sha256"] = {"Owned.sol": pair.sha(scanner.OWNED_SOURCE)}
        with self.assertRaises(ValueError):
            pair.accept(wrong, False)
        for key in ("raw_alert_count", "unique_alert_count", "source_bound_alerts"):
            wrong = synthetic_result("clean")
            wrong[key] = False
            with self.assertRaises(ValueError):
                pair.accept(wrong, False)

    def test_missing_tool_blocks_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "bundle"
            with patch.object(scanner, "doctor", return_value={"status": "OWNED_SLITHER_BLOCKED"}):
                with self.assertRaisesRegex(ValueError, "SLITHER_UNAVAILABLE"):
                    pair.run_pair(Path(temp) / "solc", out, "a" * 40)
            self.assertFalse(out.exists())

    def test_bad_commit_blocks_before_doctor(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(scanner, "doctor", side_effect=AssertionError("DOCTOR_CALLED")):
                with self.assertRaisesRegex(ValueError, "COMMIT_REQUIRED"):
                    pair.run_pair(Path(temp) / "solc", Path(temp) / "out", "bad")

    def test_worker_rejects_unknown_mode_and_missing_clean_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(worker.main([temp, "not-allowed"]), 2)
            self.assertEqual(worker.main([temp, "clean"]), 2)
            self.assertEqual(worker.main([temp, "comparison"]), 2)

    def _bundle(self, root: Path) -> dict:
        root.mkdir(mode=0o700)
        for child in ("positive", "clean", "comparison"):
            (root / child).mkdir(mode=0o700)
            (root / child / "COMPLETE.json").write_bytes(canonical({"schema_version": 1}))
        summary = {"schema_version": 1, "status": "OWNED_SLITHER_PAIR_UNVERIFIED",
                   "positive_sha256": pair.sha(scanner.OWNED_SOURCE),
                   "clean_sha256": pair.sha(pair.CLEAN_SOURCE),
                   "comparison_sha256": pair.sha(pair.COMPARISON_SOURCE),
                   "scanner": "slither", "scanner_version": scanner.SCANNER_VERSION,
                   "detector": scanner.DETECTOR, "positive_count": 1,
                   "clean_count": 0, "comparison_count": 0, "declared_commit": "a" * 40,
                   "scanner_executed_in_local_worker": True,
                   "network_isolation_proven": False,
                   "independent_execution_replay": False,
                   "vulnerability_confirmed": False}
        (root / "summary.json").write_bytes(canonical(summary))
        hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                  for name in ("summary.json", "positive/COMPLETE.json", "clean/COMPLETE.json",
                               "comparison/COMPLETE.json")}
        (root / "COMPLETE.json").write_bytes(
            canonical({"schema_version": 1, "sha256": hashes}))
        return summary

    def test_pair_verification_requires_both_independent_import_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            summary = self._bundle(root)
            def fake_verify(path):
                return synthetic_result(path.name)
            with patch.object(pair.static_review, "verify_report", side_effect=fake_verify) as verify:
                self.assertEqual(pair.verify_pair(root), summary)
                self.assertEqual(verify.call_count, 3)

    def test_pair_rejects_reports_with_different_declared_commits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            def mismatched(path):
                result = synthetic_result(path.name)
                if path.name == "clean":
                    result["repository_declared"]["commit"] = "b" * 40
                return result
            with patch.object(pair.static_review, "verify_report", side_effect=mismatched):
                with self.assertRaisesRegex(ValueError, "PAIR_SOURCE_CONTEXT_MISMATCH"):
                    pair.verify_pair(root)

    def test_comparison_wrong_declared_scope_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            def mismatched(path):
                result = synthetic_result(path.name)
                if path.name == "comparison":
                    result["scope_id_declared"] = "owned-fixed-local-fixture-clean"
                return result
            with patch.object(pair.static_review, "verify_report", side_effect=mismatched):
                with self.assertRaisesRegex(ValueError, "PAIR_SOURCE_CONTEXT_MISMATCH"):
                    pair.verify_pair(root)

    def test_comparison_false_positive_rejected_even_if_resealed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            def wrong(path):
                result = synthetic_result(path.name)
                if path.name == "comparison":
                    result["raw_alert_count"] = 1
                    result["unique_alert_count"] = 1
                    result["source_bound_alerts"] = 1
                    result["alerts"] = [{"check": scanner.DETECTOR, "source_bound": True}]
                return result
            with patch.object(pair.static_review, "verify_report", side_effect=wrong):
                with self.assertRaisesRegex(ValueError, "SLITHER_CONTROL_MISMATCH"):
                    pair.verify_pair(root)

    def test_pair_verification_rejects_resealed_false_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            summary = strict_json((root / "summary.json").read_bytes())
            summary["clean_count"] = 1
            (root / "summary.json").write_bytes(canonical(summary))
            marker = strict_json((root / "COMPLETE.json").read_bytes())
            marker["sha256"]["summary.json"] = pair.sha((root / "summary.json").read_bytes())
            (root / "COMPLETE.json").write_bytes(canonical(marker))
            with self.assertRaisesRegex(ValueError, "PAIR_SUMMARY"):
                pair.verify_pair(root)

    def test_pair_verification_rejects_extra_file_even_if_hashes_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            (root / "untracked").write_bytes(b"secret")
            with self.assertRaisesRegex(ValueError, "PAIR_FILE_SET"):
                pair.verify_pair(root)

    def test_missing_third_control_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            (root / "comparison" / "COMPLETE.json").unlink()
            with self.assertRaises((OSError, ValueError)):
                pair.verify_pair(root)

    def test_pair_verification_rejects_missing_child_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "pair"
            self._bundle(root)
            (root / "clean" / "COMPLETE.json").unlink()
            with self.assertRaises((OSError, ValueError)):
                pair.verify_pair(root)


if __name__ == "__main__":
    unittest.main()
