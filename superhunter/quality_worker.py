"""Bounded worker for this repository's own tests. No arbitrary test/target path."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import resource
import sys
import unittest


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.active = {}

    def startTest(self, test):
        super().startTest(test)
        row = {'id':test.id(), 'outcome':'INCOMPLETE'}
        self.rows.append(row)
        self.active[test.id()] = row

    def _record(self, test, outcome):
        if test.id() in self.active:
            self.active[test.id()]['outcome'] = outcome

    def addSuccess(self, test):
        super().addSuccess(test); self._record(test,'PASS')

    def addFailure(self, test, err):
        super().addFailure(test,err); self._record(test,'FAIL')

    def addError(self, test, err):
        super().addError(test,err); self._record(test,'ERROR')

    def addSkip(self, test, reason):
        super().addSkip(test,reason); self._record(test,'SKIP')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test,err); self._record(test,'EXPECTED_FAILURE')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self._record(test,'UNEXPECTED_SUCCESS')

    def addSubTest(self, test, subtest, outcome):
        super().addSubTest(test,subtest,outcome)
        if outcome is not None:
            self._record(test,'FAIL')


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parent
    sys.path.insert(0,str(root.parent))
    from superhunter.quality import assess, source_snapshot
    from superhunter.safe_io import canonical, write_new_bundle
    before = source_snapshot()
    suite = unittest.TestLoader().discover(str(root/'tests'),pattern='test*.py')
    discovered = list(test_ids(suite))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordedResult).run(suite)
    receipt = {'schema_version':1, 'sources_before':before, 'sources_after':source_snapshot(),
               'discovered':discovered, 'tests':result.rows, 'tests_run':result.testsRun,
               'failures':len(result.failures), 'errors':len(result.errors), 'skipped':len(result.skipped),
               'expected_failures':len(result.expectedFailures), 'unexpected_successes':len(result.unexpectedSuccesses),
               'python':sys.version.split()[0]}
    verdict = assess(receipt,before)
    write_new_bundle(args.directory,{'receipt.json':canonical(receipt),'tests.log':stream.getvalue().encode()})
    return 0 if verdict['status']=='LOCAL_QA_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
