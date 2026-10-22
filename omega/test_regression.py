"""Negative checks for the regression evidence recorder, not market evidence."""
import copy
import io
import unittest

from regression import RecordedResult, compare_outcomes, summarize, test_ids
from historical_regression import check_outcome


def record(case):
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
    names = test_ids(suite)
    result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordedResult).run(suite)
    return summarize(result, names)


class RegressionTests(unittest.TestCase):
    def test_success_is_counted_directly(self):
        class Cases(unittest.TestCase):
            def test_ok(self):
                pass
        report = record(Cases)
        self.assertTrue(report["strict_pass"])
        self.assertEqual(len(report["successes"]), 1)
        self.assertFalse(report["canonical_recertification"])

    def test_setup_error_does_not_create_negative_success_count(self):
        class Cases(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise ValueError("source artifact missing")
            def test_unrun(self):
                pass
        report = record(Cases)
        self.assertEqual(report["tests_run"], 0)
        self.assertEqual(report["successes"], [])
        self.assertEqual(len(report["discovered"]), 1)
        self.assertEqual(len(report["issues"]), 1)
        self.assertFalse(report["strict_pass"])

    def test_skip_is_incomplete_even_if_unittest_is_successful(self):
        class Cases(unittest.TestCase):
            @unittest.skip("real source missing")
            def test_unrun(self):
                pass
        report = record(Cases)
        self.assertTrue(report["unittest_successful"])
        self.assertFalse(report["strict_pass"])

    def test_expected_failure_is_not_a_strict_pass(self):
        class Cases(unittest.TestCase):
            @unittest.expectedFailure
            def test_expected(self):
                self.fail("legacy error")
        report = record(Cases)
        self.assertTrue(report["unittest_successful"])
        self.assertFalse(report["strict_pass"])

    def test_subtest_failure_is_recorded(self):
        class Cases(unittest.TestCase):
            def test_values(self):
                with self.subTest(value=1):
                    self.fail("mismatch")
        report = record(Cases)
        self.assertEqual(len(report["issues"]), 1)
        self.assertEqual(report["issues"][0]["kind"], "failure")
        self.assertFalse(report["strict_pass"])

    def test_subtest_error_is_recorded(self):
        class Cases(unittest.TestCase):
            def test_values(self):
                with self.subTest(value=1):
                    raise ValueError("mismatch")
        report = record(Cases)
        self.assertEqual(report["issues"][0]["kind"], "error")
        self.assertFalse(report["strict_pass"])

    def test_matching_broken_baseline_stays_failed(self):
        class Cases(unittest.TestCase):
            def test_error(self):
                raise ValueError("original error")
        comparison = compare_outcomes(record(Cases), record(Cases))
        self.assertTrue(comparison["same_outcomes"])
        self.assertFalse(comparison["current_strict_pass"])
        self.assertFalse(comparison["phase_advance_authorized"])

    def test_added_skip_is_detected(self):
        class Cases(unittest.TestCase):
            def test_ok(self):
                pass
        before = record(Cases)
        Cases.test_ok = unittest.skip("new skip")(Cases.test_ok)
        comparison = compare_outcomes(before, record(Cases))
        self.assertFalse(comparison["same_outcomes"])
        self.assertFalse(comparison["current_strict_pass"])

    def test_tampered_summary_is_rejected(self):
        class Cases(unittest.TestCase):
            def test_ok(self):
                pass
        before = record(Cases)
        after = copy.deepcopy(before)
        after["strict_pass"] = False
        with self.assertRaisesRegex(ValueError, "commitment_mismatch"):
            compare_outcomes(before, after)

    def test_empty_discovery_cannot_pass(self):
        class Cases(unittest.TestCase):
            pass
        self.assertFalse(record(Cases)["strict_pass"])

    def test_historical_log_requires_expected_count_and_exit(self):
        log = "Ran 20 tests in 0.1s\n\nOK\n"
        self.assertTrue(check_outcome(0, log, 20))
        self.assertFalse(check_outcome(1, log, 20))
        self.assertFalse(check_outcome(0, log, 21))

    def test_historical_skips_and_partial_logs_never_pass(self):
        self.assertFalse(check_outcome(0, "Ran 20 tests in 0.1s\n\nOK (skipped=1)\n", 20))
        self.assertFalse(check_outcome(0, "Ran 20 tests in 0.1s\n", 20))
        self.assertFalse(check_outcome(0, "OK\n", 20))


if __name__ == "__main__":
    unittest.main()
