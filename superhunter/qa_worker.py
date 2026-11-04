"""Run only this package's regression suite, recording every real test outcome.

This is a trusted-code CI worker, not a sandbox for hostile tests or plug-ins.
No test command, module name, target or network endpoint is accepted as input.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import sys
import unittest


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}

    def startTest(self, test):
        super().startTest(test)
        if test.id() in self.records:
            raise ValueError("duplicate test identity")
        self.records[test.id()] = "INCOMPLETE"

    def addSuccess(self, test):
        super().addSuccess(test)
        if self.records[test.id()] == "INCOMPLETE":
            self.records[test.id()] = "PASS"

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records[test.id()] = "FAIL"

    def addError(self, test, err):
        super().addError(test, err)
        self.records[test.id()] = "ERROR"

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records[test.id()] = "SKIP"

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.records[test.id()] = "EXPECTED_FAILURE"

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.records[test.id()] = "UNEXPECTED_SUCCESS"

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.records[test.id()] = "FAIL"


def test_ids(suite):
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            yield from test_ids(child)
        else:
            yield child.id()


def summarize(result, expected):
    rows = [{"id": name, "outcome": result.records.get(name, "INCOMPLETE")} for name in expected]
    passed = (bool(rows) and len(set(expected)) == len(expected) and result.testsRun == len(expected)
              and set(result.records) == set(expected) and all(r["outcome"] == "PASS" for r in rows))
    return {"schema_version": 1, "status": "PASS" if passed else "FAIL",
            "tests_run": result.testsRun, "expected_count": len(expected), "records": rows,
            "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
            "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses)}


def main():
    parser = argparse.ArgumentParser(description="Fixed SUPERHUNTER regression suite")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from superhunter.safe_io import canonical, write_new_bundle
    suite = unittest.TestLoader().discover(str(root / "superhunter/tests"), pattern="test_*.py")
    expected = list(test_ids(suite))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    receipt = summarize(result, expected)
    write_new_bundle(args.out, {"test-results.json": canonical(receipt), "tests.log": stream.getvalue().encode()})
    print(receipt["status"])
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
