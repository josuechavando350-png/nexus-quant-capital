"""Record unittest outcomes without turning inherited errors or skips into PASS.

Run each source tree in a fresh process. Reports are local test evidence only;
they cannot authorize Census, certification, signing or spending.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import unittest

from integrity import canonical, digest


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.successes = []
        self.issues = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test.id())

    def _issue(self, kind, test, error):
        self.issues.append({"kind": kind, "test": test.id(),
                            "exception": error[0].__name__, "message": str(error[1])})

    def addError(self, test, err):
        super().addError(test, err)
        self._issue("error", test, err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._issue("failure", test, err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            kind = "failure" if issubclass(err[0], test.failureException) else "error"
            self._issue(kind, subtest, err)


def test_ids(suite):
    if isinstance(suite, unittest.TestSuite):
        return [name for child in suite for name in test_ids(child)]
    return [suite.id()]


def summarize(result, discovered):
    skipped = [{"test": test.id(), "reason": reason} for test, reason in result.skipped]
    expected = [test.id() for test, _ in result.expectedFailures]
    unexpected = [test.id() for test in result.unexpectedSuccesses]
    passed = (bool(discovered) and result.wasSuccessful() and not skipped
              and not expected and not unexpected
              and sorted(result.successes) == sorted(discovered))
    report = {
        "schema": "nqc.omega.python-regression.v1",
        "status": "TESTS_PASS" if passed else "TESTS_INCOMPLETE_OR_FAILED",
        "strict_pass": passed,
        "unittest_successful": result.wasSuccessful(),
        "discovered": sorted(discovered), "tests_run": result.testsRun,
        # setUpClass failures are NOT counted in testsRun. Never subtract them.
        "successes": sorted(result.successes),
        "issues": sorted(result.issues, key=lambda item: canonical(item)),
        "skipped": sorted(skipped, key=lambda item: canonical(item)),
        "expected_failures": sorted(expected), "unexpected_successes": sorted(unexpected),
        "canonical_recertification": False, "census_closed": False,
        "phase_advance_authorized": False,
    }
    report["report_commitment_sha256"] = digest(canonical(report))
    return report


def compare_outcomes(baseline, current):
    """A matching broken baseline is still broken, never a strict pass."""
    keys = ("schema", "status", "strict_pass", "unittest_successful", "discovered",
            "tests_run", "successes", "issues", "skipped", "expected_failures",
            "unexpected_successes")
    for report in (baseline, current):
        unsigned = {k: v for k, v in report.items() if k != "report_commitment_sha256"}
        if report.get("report_commitment_sha256") != digest(canonical(unsigned)):
            raise ValueError("regression_report_commitment_mismatch")
        if report.get("schema") != "nqc.omega.python-regression.v1":
            raise ValueError("unsupported_regression_report")
        if not all(key in report for key in keys):
            raise ValueError("incomplete_regression_report")
    differences = [key for key in keys if baseline[key] != current[key]]
    return {"same_outcomes": not differences, "different_fields": differences,
            "current_strict_pass": current["strict_pass"],
            "canonical_recertification": False, "census_closed": False,
            "phase_advance_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-directory", type=Path, required=True)
    parser.add_argument("--pattern", default="test*.py")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("report already exists; preserve previous evidence")
    root = args.start_directory.resolve(strict=True)
    if args.report.resolve().is_relative_to(root):
        parser.error("report must be outside the test source directory")
    # Do not add the directory containing this recorder ahead of source modules.
    sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.discover(str(root), pattern=args.pattern)
    discovered = test_ids(suite)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    report = summarize(result, discovered)
    report["test_source_sha256"] = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob(args.pattern)) if p.is_file()
    }
    report["report_commitment_sha256"] = digest(canonical({
        key: value for key, value in report.items() if key != "report_commitment_sha256"}))
    with args.report.open("xb") as stream:
        stream.write(canonical(report))
    return 0 if report["strict_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
