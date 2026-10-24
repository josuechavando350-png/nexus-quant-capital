import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import smoke_collector
finally:
    sys.path.pop(0)


def fixture():
    config = {"run_id": "collector", "scopes": [{"from_block": 100, "to_block": 102}]}
    checks = [{"name": name, "exit_code": 0} for name in
              ("about-before", "validate", "follow-initial", "verify-initial",
               "follow-resumed", "verify-final", "about-after")]
    reports = []
    for count in (2, 3):
        reports.append({"schema": "nqc-miner-collector-status-v1", "run_id": "collector",
                        "plan_sha256": "a" * 64, "completed_windows": count, "incomplete_window": False,
                        "next_from_block": 100 + 3 * count, "integrity_verified": True,
                        "data_class": "historical", "observer_bridge_enabled": False,
                        "signing_enabled": False, "economic_certification": False,
                        "chain_authenticity_verified": False})
    polls = [{"status": "completed", "window_index": i, "from_block": 100 + 3 * i,
              "to_block": 102 + 3 * i} for i in range(3)]
    return [config, checks, *reports, polls, True, True, "a" * 64]


class CollectorSmokeTests(unittest.TestCase):
    def test_verified_restart_is_only_a_finite_smoke_test(self):
        self.assertEqual(smoke_collector.classify(*fixture()), "complete_bounded_restart_smoke")

    def test_missing_or_failed_subprocess_is_incomplete(self):
        for index in range(7):
            args = fixture()
            args[1][index]["exit_code"] = 1
            self.assertEqual(smoke_collector.classify(*args), "incomplete_or_rejected")

    def test_wrong_owner_cursor_class_and_integrity_are_rejected(self):
        for key, value in (("run_id", "foreign"), ("plan_sha256", "foreign"), ("next_from_block", 110),
                           ("completed_windows", 4), ("incomplete_window", True), ("data_class", "shadow"),
                           ("integrity_verified", False), ("economic_certification", True)):
            args = fixture()
            args[3][key] = value
            with self.subTest(key=key):
                self.assertEqual(smoke_collector.classify(*args), "incomplete_or_rejected")

    def test_waiting_duplicate_or_missing_poll_is_not_completion(self):
        for outcome in ([], [{"status": "waiting"}], [fixture()[4][0]] * 3):
            args = fixture()
            args[4] = copy.deepcopy(outcome)
            self.assertEqual(smoke_collector.classify(*args), "incomplete_or_rejected")

    def test_modified_binary_or_old_window_rejects_capture(self):
        for index in (5, 6):
            args = fixture()
            args[index] = False
            self.assertEqual(smoke_collector.classify(*args), "incomplete_or_rejected")
