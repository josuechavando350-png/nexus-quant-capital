import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    SPEC = importlib.util.spec_from_file_location("capture_run", SCRIPTS / "capture_run.py")
    capture_run = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(capture_run)
finally:
    sys.path.pop(0)


def fixture():
    config = {"namespace": "nqc_miner_v1", "producer": "nqc-miner", "run_id": "fixture",
              "data_class": "historical", "code_commit": "a" * 40, "cargo_lock_sha256": "b" * 64,
              "scopes": [{"id": "aave", "chain_id": 1, "from_block": 10, "to_block": 20}]}
    owner = {k: v for k, v in config.items() if k != "scopes"}
    verified = {"owner": owner, "integrity_verified": True, "provisional_events": 0,
                "invalidated_from": {}, "completed_scopes": 1}
    report = {"owner": owner, "scope_completion": [{"scope_id": "aave", "chain_id": 1,
               "from_block": 10, "to_block": 20, "complete": True}],
              "activation_permitted": False, "measured_realized_profit": None}
    checks = [{"name": name, "exit_code": 0} for name in
              ("about-before", "validate", "scan", "verify", "report", "about-after")]
    return config, checks, verified, report


class CaptureTests(unittest.TestCase):
    def test_full_evidence_is_a_bounded_sample(self):
        self.assertEqual(capture_run.classify(*fixture(), True), "complete_read_only_sample")

    def test_successful_process_cannot_hide_incomplete_scope(self):
        config, checks, verified, report = fixture()
        report["scope_completion"][0]["complete"] = False
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")

    def test_wrong_range_chain_or_duplicate_scope_rejected(self):
        for field, value in (("to_block", 19), ("chain_id", 8453), ("scope_id", "foreign")):
            config, checks, verified, report = fixture()
            report["scope_completion"][0][field] = value
            with self.subTest(field=field):
                self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")
        config, checks, verified, report = fixture()
        report["scope_completion"] *= 2
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")

    def test_changed_binary_foreign_owner_reorg_and_provisional_fail(self):
        config, checks, verified, report = fixture()
        self.assertEqual(capture_run.classify(config, checks, verified, report, False), "incomplete_or_rejected")
        for field, value in (("owner", {}), ("provisional_events", 1),
                             ("invalidated_from", {"1": 15}), ("integrity_verified", False)):
            candidate = copy.deepcopy(verified)
            candidate[field] = value
            with self.subTest(field=field):
                self.assertEqual(capture_run.classify(config, checks, candidate, report, True), "incomplete_or_rejected")

    def test_failed_scan_not_promoted_by_valid_partial_report(self):
        config, checks, verified, report = fixture()
        checks[2]["exit_code"] = 1
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")

    def test_v2_wrong_build_or_downgraded_owner_rejected(self):
        config, checks, verified, report = fixture()
        config.update(schema_version=2, build_identity_sha256="c" * 64)
        for value in (verified, report):
            value["owner"] = dict(value["owner"], schema="nqc-miner-owner-v2", build_identity_sha256="c" * 64)
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "complete_read_only_sample")
        report["owner"]["build_identity_sha256"] = "d" * 64
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")
        report["owner"]["build_identity_sha256"] = "c" * 64
        report["owner"]["schema"] = "nqc-miner-owner-v1"
        self.assertEqual(capture_run.classify(config, checks, verified, report, True), "incomplete_or_rejected")

    def test_timeout_retains_partial_stdout_and_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = capture_run.step(out, "timeout", [sys.executable, "-c",
                "import time; print('partial',flush=True); time.sleep(10)"], 0.25)
            self.assertEqual(result["exit_code"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual((out / "timeout.stdout").read_text(), "partial\n")

    def test_safe_paths_reject_observer_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "foreign").mkdir()
            (root / "link").symlink_to(root / "foreign", target_is_directory=True)
            with self.assertRaises(capture_run.BindError):
                capture_run.safe_path(root / "link" / "run")

    def test_real_binary_rejects_config_and_captures_failure_without_network(self):
        binary = Path(os.environ["NQC_MINER_TEST_BINARY"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = json.loads((SCRIPTS.parent / "evidence/public-retry-20261022/config.template.json").read_text())
            template["scopes"] = []
            (root / "template.json").write_text(json.dumps(template))
            summary = capture_run.capture(binary, root / "template.json", root / "capture", 1, "synthetic_fixture")
            self.assertEqual(summary["status"], "incomplete_or_rejected")
            self.assertFalse(any(c["name"] == "scan" for c in summary["checks"]))
            self.assertFalse((root / "capture/state").exists())
            for name, expected in summary["files"].items():
                self.assertEqual(capture_run.digest(root / "capture" / name), expected)
            self.assertEqual(json.loads((root / "capture/capture.json").read_text()), summary)
            with self.assertRaises(FileExistsError):
                capture_run.capture(binary, root / "template.json", root / "capture", 1, "synthetic_fixture")


if __name__ == "__main__":
    unittest.main()
