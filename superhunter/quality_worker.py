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



# Reviewed eight-worker schedule. Preserve historical module ownership as the
# inventory grows. Platform replay moves from the busy EVM-study worker (6)
# into worker 5, previously measured at ~2 seconds on this host. The M10 module
# is named here so the same schedule can be reconciled into the successor PR.
QA_MODULE_GROUPS = (
    (
        'test_audit_links',
        'test_chain_path_audit',
        'test_compiler_layout',
        'test_critical_chain',
        'test_evidence_ablation',
        'test_evidence_common_mode',
        'test_evidence_cut_sets',
        'test_evidence_joint_failure',
        'test_evm_accounting',
        'test_evm_bounded_replay',
        'test_evm_guidance_benchmark',
        'test_holdout_protocol',
        'test_journal_correlation',
        'test_native_compile',
        'test_permission_domain',
        'test_solidity_stateful',
    ),
    (
        'test_benchmark',
        'test_evm_coverage_guidance',
        'test_evm_forensic_binding',
        'test_ledger_sequence',
        'test_local_lab',
        'test_ordered_case',
        'test_reconciliation',
    ),
    (
        'test_case_review',
        'test_forensic_timeline',
        'test_native_platform',
        'test_owned_mutation_evaluation',
        'test_rate_control',
        'test_regression',
        'test_storage_layout',
    ),
    (
        'test_evm_access_family',
        'test_evm_execution',
        'test_permission_smt',
        'test_quality',
        'test_research_plan',
        'test_review',
        'test_storage_placement',
    ),
    (
        'test_bytecode_controls',
        'test_compiler_variants',
        'test_evm_feedback',
        'test_fuzz_lab',
        'test_owned_platform',
        'test_proof_graph',
        'test_source_types',
        'test_static_review',
    ),
    (
        'test_balance_reconciliation',
        'test_custody',
        'test_evm_opcode_trace',
        'test_fuzz_evidence',
        'test_integration',
        'test_internal_units',
        'test_platform',
        'test_program_registry',
    ),
    (
        'test_evm_seed_study',
        'test_evm_sequence_fuzz',
        'test_journal_ingest',
        'test_native_layout',
        'test_owned_cross_evm',
        'test_owned_spec_evm',
        'test_owned_quota_review',
        'test_owned_quota_cross_evm',
        'test_qa_failure',
        'test_quality_cache',
        'test_quality_process',
        'test_native_doctor',
        'test_repository_boundary',
        'test_permissions',
        'test_solidity_formal',
        'test_source_graph',
    ),
    (
        'test_bridge',
        'test_evm_pause_family',
        'test_privacy',
        'test_sharing',
        'test_smt_backend',
        'test_solidity_inventory',
    ),
)


def partition_ids(identities: list[str], count: int) -> list[list[str]]:
    """Stable known-module placement; complete deterministic fallback for new ones.

    Eight-worker QA uses a reviewed layout so adding tests to a module cannot
    silently move expensive historical suites. New modules stay whole and use
    the least populated group. Counts are only a fallback, not a runtime claim;
    the existing wall, CPU, memory and output limits remain authoritative.
    """
    if type(count) is not int or not 1 <= count <= 8:
        raise ValueError('invalid partition count')
    if (type(identities) is not list or not identities or
            any(type(i) is not str or not i or '.' not in i for i in identities) or
            len(set(identities)) != len(identities)):
        raise ValueError('invalid test inventory')
    modules = {}
    for identity in sorted(identities):
        modules.setdefault(identity.split('.')[0], []).append(identity)
    groups = [[] for _ in range(count)]
    if count == 8:
        for index, names in enumerate(QA_MODULE_GROUPS):
            for name in names:
                groups[index].extend(modules.pop(name, ()))
    for name in sorted(modules, key=lambda n: (-len(modules[n]), n)):
        index = min(range(count), key=lambda i: (len(groups[i]), i))
        groups[index].extend(modules[name])
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
