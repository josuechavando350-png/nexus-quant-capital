"""Offline triple-control replay verification tests with synthetic normalized records.

The real source-bound importer is mocked in these unit tests. No Slither,
Solidity compiler, network request, or external vulnerability is exercised.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import slither_pair_replay as replay
from superhunter.safe_io import canonical, strict_json


SUMMARY = {
    "status": "OWNED_SLITHER_PAIR_UNVERIFIED", "declared_commit": "a" * 40,
    "scanner_version": "0.11.6", "positive_count": 1, "clean_count": 0,
    "comparison_count": 0, "comparison_sha256": replay.pair.COMPARISON_SHA256,
    "vulnerability_confirmed": False, "separate_host_proven": False,
}


def normalized(mode: str) -> dict:
    if mode not in ("positive", "clean", "comparison"):
        raise ValueError("INVALID_TEST_FIXTURE_MODE")
    clean = mode != "positive"
    fixture = {"positive": replay.pair.positive.OWNED_SOURCE,
               "clean": replay.pair.CLEAN_SOURCE,
               "comparison": replay.pair.COMPARISON_SOURCE}[mode]
    result = {
        "adapter_sha256": "9" * 64, "ignored_result_sections": [],
        "status": "NO_ALERTS_IN_SUPPLIED_REPORT" if clean else "STATIC_REVIEW_REQUIRED",
        "raw_alert_count": 0 if clean else 1,
        "unique_alert_count": 0 if clean else 1,
        "duplicate_count": 0, "source_bound_alerts": 0 if clean else 1,
        "unbound_alerts": 0, "tool_impact_counts": {} if clean else {"Medium": 1},
        "alerts": [] if clean else [{
            "fingerprint": "b" * 64, "check": "tx-origin",
            "tool_impact": "Medium", "tool_confidence": "High",
            "source_bound": True, "locations": [{"file": "Owned.sol", "start_byte": 140}],
        }],
        "source_sha256": {"Owned.sol": replay.digest(fixture)},
        "repository_declared": {"repo": "superhunter-owned/fixture", "commit": "a" * 40},
        "scope_id_declared": ("owned-fixed-local-fixture" if mode == "positive"
                               else "owned-fixed-local-fixture-" + mode),
        "tool_declared": {"name": "slither", "version": "0.11.6"},
        "detectors_declared": ["tx-origin"],
        "normalization_complete": True, "input_kind": "external-report",
        "scanner_execution_verified": False, "producer_authenticated": False,
        "repository_commit_verified": False, "scope_authorization_verified": False,
        "vulnerability_confirmed": False,
    }
    return result


class SlitherReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.first, self.second = self.root / "first", self.root / "second"
        self.out = self.root / "comparison"
        for name, path in (("first", self.first), ("second", self.second)):
            path.mkdir()
            (path / "COMPLETE.json").write_bytes(canonical({"case": name}))
            (path / "positive").mkdir()
            (path / "clean").mkdir()
            (path / "comparison").mkdir()
        self.a = replay.digest((self.first / "COMPLETE.json").read_bytes())
        self.b = replay.digest((self.second / "COMPLETE.json").read_bytes())
        self.observations = {
            "first": {name: normalized(name) for name in ("positive", "clean", "comparison")},
            "second": {name: normalized(name) for name in ("positive", "clean", "comparison")},
        }

    def mocks(self):
        self.enterContext(patch.object(replay.pair, "verify_pair", return_value=deepcopy(SUMMARY)))
        # Use REAL pair.accept/check_context, not stubs: this rechecks scopes,
        # source hashes and detector polarities against the three fixed sources.
        def verify(path):
            return deepcopy(self.observations[path.parent.name][path.name])

        self.enterContext(patch.object(replay.static_review, "verify_report", side_effect=verify))

    def test_two_distinct_anchored_pairs_agree_offline(self):
        self.mocks()
        result = replay.create(self.first, self.second, self.a, self.b, self.out)
        self.assertEqual(result["status"], "TWO_SLITHER_THREE_CONTROL_RUNS_AGREE_UNAUTHENTICATED")
        self.assertEqual(result["original_complete_sha256"], self.a)
        self.assertEqual(result["repeat_complete_sha256"], self.b)
        self.assertEqual(result["report_pairs_reevaluated"], 2)
        self.assertEqual(result["control_reports_reevaluated"], 6)
        self.assertEqual(result["comparison_cases"], 1)
        self.assertFalse(result["independent_execution_proven"])
        self.assertFalse(result["producer_authenticated"])
        self.assertFalse(result["scanner_executed_here"])
        self.assertEqual(replay.verify(self.out, self.first, self.second, self.a, self.b), result)

    def test_missing_or_forged_external_anchor_rejected(self):
        self.mocks()
        for a, b in (("A" * 64, self.b), ("0" * 64, self.b),
                     (self.a, self.a), ("", self.b)):
            with self.subTest(first=a):
                with self.assertRaisesRegex(ValueError, "ANCHOR"):
                    replay.compare(self.first, self.second, a, b)
        self.assertFalse(self.out.exists())

    def test_duplicate_and_nested_pair_rejected(self):
        self.mocks()
        with self.assertRaisesRegex(ValueError, "DISTINCT"):
            replay.compare(self.first, self.first, self.a, self.a)
        nested = self.first / "nested"
        nested.mkdir()
        (nested / "COMPLETE.json").write_bytes(b"anything")
        with self.assertRaisesRegex(ValueError, "DISTINCT"):
            replay.compare(self.first, nested, self.a, replay.digest(b"anything"))

    def test_symlink_pair_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.first, target_is_directory=True)
        self.mocks()
        with self.assertRaisesRegex(ValueError, "DISTINCT"):
            replay.compare(alias, self.second, self.a, self.b)

    def test_difference_in_alert_fingerprint_rejected(self):
        self.mocks()
        self.observations["second"]["positive"]["alerts"][0]["fingerprint"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "OBSERVATION_DIVERGENCE"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_difference_in_severity_rejected(self):
        self.mocks()
        self.observations["second"]["positive"]["alerts"][0]["tool_impact"] = "High"
        with self.assertRaisesRegex(ValueError, "OBSERVATION_DIVERGENCE"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_difference_in_source_identity_rejected(self):
        self.mocks()
        self.observations["second"]["clean"]["source_sha256"] = {"Owned.sol": "f" * 64}
        with self.assertRaisesRegex(ValueError, "SLITHER_CONTROL_MISMATCH|OBSERVATION_DIVERGENCE"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_difference_in_declared_commit_rejected(self):
        self.mocks()
        self.observations["second"]["positive"]["repository_declared"]["commit"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "PAIR_SOURCE_CONTEXT_MISMATCH"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_third_control_semantic_divergence_is_detected(self):
        self.mocks()
        self.observations["second"]["comparison"]["status"] = "STATIC_REVIEW_REQUIRED"
        with self.assertRaisesRegex(ValueError, "OBSERVATION_DIVERGENCE"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_third_control_false_positive_blocks_before_comparison(self):
        self.mocks()
        row = self.observations["second"]["comparison"]
        row["raw_alert_count"] = 1
        row["unique_alert_count"] = 1
        row["source_bound_alerts"] = 1
        row["alerts"] = [{"check": "tx-origin", "source_bound": True}]
        with self.assertRaisesRegex(ValueError, "SLITHER_CONTROL_MISMATCH"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_missing_third_control_blocks_replay(self):
        self.mocks()
        del self.observations["second"]["comparison"]
        with self.assertRaises(KeyError):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_difference_in_summary_rejected(self):
        self.mocks()
        def summary(path):
            result = deepcopy(SUMMARY)
            if path.name == "second":
                result["positive_count"] = 0
            return result
        with patch.object(replay.pair, "verify_pair", side_effect=summary):
            with self.assertRaisesRegex(ValueError, "SUMMARY_DIVERGENCE"):
                replay.compare(self.first, self.second, self.a, self.b)

    def test_missing_semantic_field_is_error(self):
        self.mocks()
        del self.observations["first"]["positive"]["tool_impact_counts"]
        with self.assertRaisesRegex(ValueError, "MISSING_RECOMPUTED"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_altered_original_fails_external_anchor(self):
        self.mocks()
        (self.first / "COMPLETE.json").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ANCHOR_MISMATCH"):
            replay.compare(self.first, self.second, self.a, self.b)

    def test_report_tampering_rejected_after_manifest_reseal(self):
        self.mocks()
        replay.create(self.first, self.second, self.a, self.b, self.out)
        artifact = self.out / "comparison.json"
        report = strict_json(artifact.read_bytes())
        report["producer_authenticated"] = True
        artifact.write_bytes(canonical(report))
        marker = self.out / "COMPLETE.json"
        manifest = strict_json(marker.read_bytes())
        manifest["sha256"]["comparison.json"] = replay.digest(artifact.read_bytes())
        marker.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(ValueError, "CONTENT_DIVERGENCE"):
            replay.verify(self.out, self.first, self.second, self.a, self.b)

    def test_missing_private_receipt_blocks(self):
        self.mocks()
        replay.create(self.first, self.second, self.a, self.b, self.out)
        (self.out / "REVIEW.md").unlink()
        with self.assertRaisesRegex(ValueError, "INVALID_COMPARISON_MANIFEST"):
            replay.verify(self.out, self.first, self.second, self.a, self.b)

    def test_existing_output_or_in_repository_blocks(self):
        self.mocks()
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, "UNSAFE_OUTPUT"):
            replay.create(self.first, self.second, self.a, self.b, self.out)
        with self.assertRaisesRegex(ValueError, "UNSAFE_OUTPUT"):
            replay.create(self.first, self.second, self.a, self.b,
                          replay.ROOT / "should-not-create-replay")

    def test_cli_never_echoes_private_path(self):
        self.mocks()
        with redirect_stdout(io.StringIO()) as buf:
            code = replay.main([
                "compare-owned-slither-pairs", "--first", str(self.first),
                "--second", str(self.second), "--expected-first-sha256", "BADSECRET",
                "--expected-second-sha256", self.b, "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertNotIn(str(self.first), buf.getvalue())
        self.assertNotIn("BADSECRET", buf.getvalue())
        self.assertIn("SLITHER_COMPARISON_BLOCKED", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
