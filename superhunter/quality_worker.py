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



def partition_ids(identities: list[str], count: int) -> list[list[str]]:
    """Deterministic, disjoint groups, keeping each test module together."""
    if type(count) is not int or not 1 <= count <= 8:
        raise ValueError('invalid partition count')
    if (type(identities) is not list or not identities or
            any(type(i) is not str or not i or '.' not in i for i in identities) or
            len(set(identities)) != len(identities)):
        raise ValueError('invalid test inventory')
    modules = {}
    for identity in sorted(identities):
        modules.setdefault(identity.split('.')[0], []).append(identity)
    # Keep the previously measured 1,969-test partitions stable when adding
    # the offline holdout suite. The former slowest partition used 167.5 s of
    # its 180-s wall budget; rebalancing solely by test COUNT placed another
    # 33-test EVM suite there and caused a real timeout. Schedule the new
    # non-EVM holdout suite with the previously lightest partition instead.
    # Every test still runs, with the SAME limits and complete inventories.
    holdout = modules.pop('test_holdout_protocol', []) if count == 8 else []
    # Protect the previously verified 2041-test partition layout. Adding a
    # module before greedy balancing reassigns expensive EVM suites and can
    # exhaust unchanged worker time budgets. Keep the new module whole in the
    # measured ~36s partition instead; no tests or limits are suppressed.
    cross_journal = modules.pop('test_journal_correlation', []) if count == 8 else []
    groups = [[] for _ in range(count)]
    for name in sorted(modules, key=lambda n: (-len(modules[n]), n)):
        index = min(range(count), key=lambda i: (len(groups[i]), i))
        groups[index].extend(modules[name])
    if count == 8:
        # The historical platform suite was the slowest worker (167.5 s wall).
        # A retry on this host exhausted the worker CPU limit; move the entire
        # module to the previously ~5-s partition, preserving every test and
        # leaving per-process CPU, memory and wall budgets unchanged.
        platform = [x for g in groups for x in g if x.split('.')[0] == 'test_platform']
        groups = [[x for x in g if x.split('.')[0] != 'test_platform'] for g in groups]
        groups[6].extend(platform)
    if holdout:
        groups[0].extend(holdout)
    if cross_journal:
        groups[0].extend(cross_journal)
    return [sorted(group) for group in groups]


def test_cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_cases(test)
        else:
            yield test


def batch_succeeded(receipt: dict) -> bool:
    counters = ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes')
    return (receipt['sources_before'] == receipt['sources_after'] and
            type(receipt['tests_run']) is int and receipt['tests_run'] == len(receipt['discovered']) and
            len(receipt['tests']) == len(receipt['discovered']) and
            sorted(row['id'] for row in receipt['tests']) == sorted(receipt['discovered']) and
            all(row['outcome'] == 'PASS' for row in receipt['tests']) and
            all(type(receipt[k]) is int and receipt[k] == 0 for k in counters))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--partition-count', type=int, default=1)
    parser.add_argument('--partition-index', type=int, default=0)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(20*1024**2,20*1024**2))
    sys.dont_write_bytecode = True
    root = Path(__file__).resolve().parent
    sys.path.insert(0,str(root.parent))
    from superhunter.quality import assess, source_snapshot
    from superhunter.safe_io import canonical, write_new_bundle
    from superhunter.privacy import redact_text
    before = source_snapshot()
    suite = unittest.TestLoader().discover(str(root/'tests'),pattern='test*.py')
    global_discovered = sorted(test_ids(suite))
    groups = partition_ids(global_discovered, args.partition_count)
    if not 0 <= args.partition_index < args.partition_count:
        raise ValueError('invalid partition index')
    discovered = groups[args.partition_index]
    if not discovered:
        raise ValueError('empty worker partition')
    selected = set(discovered)
    suite = unittest.TestSuite(test for test in test_cases(suite) if test.id() in selected)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordedResult).run(suite)
    receipt = {'schema_version':1, 'sources_before':before, 'sources_after':source_snapshot(),
               'discovered':discovered, 'tests':result.rows, 'tests_run':result.testsRun,
               'failures':len(result.failures), 'errors':len(result.errors), 'skipped':len(result.skipped),
               'expected_failures':len(result.expectedFailures), 'unexpected_successes':len(result.unexpectedSuccesses),
               'python':sys.version.split()[0]}
    log = redact_text(stream.getvalue())
    receipt["log_privacy"] = log.summary()
    if args.partition_count > 1:
        receipt.update(global_discovered=global_discovered,
                       partition_count=args.partition_count, partition_index=args.partition_index)
        passed = batch_succeeded(receipt)
    else:
        passed = assess(receipt,before)['status'] == 'LOCAL_QA_PASS'
    write_new_bundle(args.directory,{'receipt.json':canonical(receipt),'tests.log':log.text.encode()})
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
