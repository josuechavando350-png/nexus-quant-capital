"""Synthetic receipts test validator decisions, never masquerade as executions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import quality
from superhunter.regression import compare, load_run, run_comparison, verify_comparison
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class RegressionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.snapshot = quality.source_snapshot()
        self.ids = list(quality.REQUIRED_TESTS)
        self.subject = self.ids[0]
        self.old_snapshot = {**self.snapshot, '__main__.py': '1' * 64}
        self.before = self.root/'before'
        self.after = self.root/'after'

    def bundle(self, path, snapshot=None, outcomes=None, ids=None):
        snapshot = deepcopy(self.snapshot if snapshot is None else snapshot)
        outcomes = outcomes or {}
        ids = list(self.ids if ids is None else ids)
        rows = [{'id': key, 'outcome': outcomes.get(key, 'PASS')} for key in ids]
        receipt = {'schema_version': 1, 'sources_before': snapshot, 'sources_after': deepcopy(snapshot),
                   'discovered': ids, 'tests': rows, 'tests_run': len(rows), 'python': sys.version.split()[0],
                   'failures': sum(r['outcome'] == 'FAIL' for r in rows),
                   'errors': sum(r['outcome'] == 'ERROR' for r in rows),
                   'skipped': sum(r['outcome'] == 'SKIP' for r in rows),
                   'expected_failures': sum(r['outcome'] == 'EXPECTED_FAILURE' for r in rows),
                   'unexpected_successes': sum(r['outcome'] == 'UNEXPECTED_SUCCESS' for r in rows)}
        result = quality.assess(receipt, snapshot)
        write_new_bundle(path, {'receipt.json': canonical(receipt), 'quality.json': canonical(result),
                               'source-snapshot.json': canonical(snapshot),
                               'CHECKLIST.md': quality.checklist(quality.catalog(), result).encode(),
                               'tests.log': b'SYNTHETIC TEST FIXTURE - NOT AN EXECUTION\n'})
        return hashlib.sha256(canonical(snapshot)).hexdigest()

    def pair(self, *, old=None, new=None, old_snapshot=None, new_snapshot=None, new_ids=None):
        self.bp = self.bundle(self.before, self.old_snapshot if old_snapshot is None else old_snapshot,
                              {self.subject:'FAIL'} if old is None else old)
        self.ap = self.bundle(self.after, new_snapshot, new, new_ids)

    def compare(self):
        return compare(self.before, self.after, self.bp, self.ap)

    def alter(self, directory, name, change, raw=False):
        file = directory/name
        if raw:
            data = change(file.read_bytes())
        else:
            value = strict_json(file.read_bytes());change(value);data = canonical(value)
        file.write_bytes(data)
        marker = strict_json((directory/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(data).hexdigest()
        (directory/'COMPLETE.json').write_bytes(canonical(marker))

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', '-m', 'superhunter', *map(str,args)],
                              cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)

    def test_fixed_failure_same_oracle_observed(self):
        self.pair();result=self.compare()
        self.assertEqual(result['status'], 'LOCAL_FIX_OBSERVED')
        self.assertEqual(result['tests']['fail_to_pass'], [self.subject])
        self.assertTrue(result['fix_observed'])
        self.assertFalse(result['production_certified'])
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertFalse(result['producer_authenticated'])

    def test_pass_to_failure_is_regression(self):
        self.pair(old={}, new={self.subject:'FAIL'})
        self.assertEqual(self.compare()['status'],'REGRESSION_DETECTED')

    def test_pass_to_error_is_regression(self):
        self.pair(old={}, new={self.subject:'ERROR'})
        self.assertEqual(self.compare()['status'],'REGRESSION_DETECTED')

    def test_removed_test_never_counts_as_fix(self):
        self.pair(new_ids=self.ids[1:]);result=self.compare()
        self.assertEqual(result['status'],'COMPARISON_BLOCKED')
        self.assertIn(self.subject,result['tests']['removed'])
        self.assertFalse(result['fix_observed'])

    def test_changed_assertion_is_not_a_fix(self):
        snap={**self.snapshot,'tests/'+self.subject.split('.')[0]+'.py':'2'*64}
        self.pair(new_snapshot=snap)
        self.assertEqual(self.compare()['status'],'COMPARISON_BLOCKED')
        self.assertIn('TEST_ORACLE_CHANGED',self.compare()['blockers'])

    def test_changed_shared_test_helper_blocks(self):
        snap={**self.snapshot,'tests/test_quality.py':'2'*64}
        self.pair(new_snapshot=snap)
        self.assertFalse(self.compare()['fix_observed'])

    def test_skip_never_fixes_failure(self):
        self.pair(new={self.subject:'SKIP'})
        self.assertEqual(self.compare()['status'],'COMPARISON_BLOCKED')

    def test_expected_failure_never_fixes_failure(self):
        self.pair(new={self.subject:'EXPECTED_FAILURE'})
        self.assertEqual(self.compare()['status'],'COMPARISON_BLOCKED')

    def test_incomplete_run_is_not_green(self):
        self.pair(new={self.subject:'INCOMPLETE'})
        self.assertEqual(self.compare()['status'],'COMPARISON_BLOCKED')

    def test_other_remaining_failure_blocks_fix(self):
        self.pair(old={self.subject:'FAIL',self.ids[1]:'FAIL'},new={self.ids[1]:'FAIL'})
        self.assertFalse(self.compare()['fix_observed'])

    def test_new_regression_overrides_fixed_test(self):
        self.pair(new={self.ids[1]:'FAIL'})
        result=self.compare();self.assertEqual(result['status'],'REGRESSION_DETECTED')
        self.assertFalse(result['fix_observed'])
        self.assertIn(self.subject,result['tests']['fail_to_pass'])

    def test_runtime_error_resolved_not_called_bug_fix(self):
        self.pair(old={self.subject:'ERROR'})
        result=self.compare();self.assertEqual(result['status'],'NO_REGRESSION_OBSERVED')
        self.assertFalse(result['fix_observed'])
        self.assertEqual(result['tests']['error_to_pass'],[self.subject])

    def test_outcome_change_without_code_blocks(self):
        self.pair(old_snapshot=self.snapshot)
        self.assertIn('OUTCOME_CHANGED_WITHOUT_CODE_CHANGE',self.compare()['blockers'])

    def test_same_code_green_is_not_a_new_fix(self):
        self.pair(old={},old_snapshot=self.snapshot)
        self.assertEqual(self.compare()['status'],'NO_REGRESSION_OBSERVED')
        self.assertEqual(self.compare()['source_changes'],[])

    def test_added_pass_test_does_not_displace_old_failure(self):
        added='test_regression.RegressionTests.test_additional_fixture'
        self.pair(new={self.subject:'FAIL'},new_ids=self.ids+[added])
        self.assertEqual(self.compare()['tests']['added'],[added])
        self.assertEqual(self.compare()['status'],'COMPARISON_BLOCKED')

    def test_wrong_expected_identity_rejected(self):
        self.pair()
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_SOURCE_DIGEST'):
            compare(self.before,self.after,'0'*64,self.ap)

    def test_noncanonical_pin_rejected(self):
        self.pair()
        with self.assertRaisesRegex(ValueError,'INVALID_SHA256'):
            compare(self.before,self.after,'fake',self.ap)

    def test_changed_harness_rejected(self):
        self.pair(old_snapshot={**self.old_snapshot,'quality_worker.py':'0'*64})
        with self.assertRaisesRegex(ValueError,'HARNESS_NOT_COMPARABLE'):self.compare()

    def test_changed_sources_during_run_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v['sources_after'].update({'bridge.py':'0'*64}))
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.compare()

    def test_different_python_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v.update(python='0.0.0'))
        with self.assertRaisesRegex(ValueError,'PYTHON_VERSION'):self.compare()

    def test_duplicate_test_identity_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v['tests'][1].update(id=self.subject))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_TEST'):self.compare()

    def test_discovered_results_mismatch_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v['discovered'].pop())
        with self.assertRaisesRegex(ValueError,'DISCOVERY_RESULT'):self.compare()

    def test_boolean_counts_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v.update(failures=False))
        with self.assertRaisesRegex(ValueError,'INVALID_OUTCOME_COUNTER'):self.compare()

    def test_wrong_test_count_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v.update(tests_run=1))
        with self.assertRaisesRegex(ValueError,'INVALID_TEST_COUNT'):self.compare()

    def test_unknown_outcome_rejected(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v['tests'][0].update(outcome='PROVED'))
        with self.assertRaisesRegex(ValueError,'UNKNOWN_TEST_OUTCOME'):self.compare()

    def test_all_pass_cannot_hide_failure_counter(self):
        self.pair();self.alter(self.after,'receipt.json',lambda v:v.update(failures=1))
        with self.assertRaisesRegex(ValueError,'COUNTERS_CONTRADICT_PASS'):self.compare()

    def test_forged_qa_pass_recomputed(self):
        self.pair(new={self.subject:'FAIL'})
        self.alter(self.after,'quality.json',lambda v:v.update(status='LOCAL_QA_PASS'))
        with self.assertRaisesRegex(ValueError,'QA_VERDICT_NOT_REPRODUCIBLE'):self.compare()

    def test_duplicate_json_keys_rejected_even_with_new_hash(self):
        self.pair();self.alter(self.after,'receipt.json',lambda raw:raw.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1'),raw=True)
        with self.assertRaisesRegex(ValueError,'duplicate'):self.compare()

    def test_symlink_artifact_rejected(self):
        self.pair();p=self.after/'tests.log';data=p.read_bytes();p.unlink()
        (self.root/'other.log').write_bytes(data);p.symlink_to(self.root/'other.log')
        with self.assertRaises((ValueError,OSError)):self.compare()

    def test_unmodified_source_evidence_retained(self):
        self.pair();old={p:p.read_bytes() for root in (self.before,self.after) for p in root.iterdir()}
        self.compare()
        self.assertTrue(all(p.read_bytes()==raw for p,raw in old.items()))

    def test_no_network_or_code_execution(self):
        self.pair()
        with patch.object(socket,'socket',side_effect=AssertionError),patch.object(subprocess,'run',side_effect=AssertionError):
            self.assertTrue(self.compare()['fix_observed'])

    def test_written_comparison_reverified(self):
        self.pair();out=self.root/'comparison'
        result=run_comparison(self.before,self.after,self.bp,self.ap,out)
        self.assertEqual(verify_comparison(out,self.before,self.after,self.bp,self.ap),result)

    def test_resealed_comparison_must_recompute(self):
        self.pair(new={self.subject:'FAIL'});out=self.root/'comparison'
        run_comparison(self.before,self.after,self.bp,self.ap,out)
        self.alter(out,'comparison.json',lambda v:v.update(status='LOCAL_FIX_OBSERVED',fix_observed=True))
        with self.assertRaisesRegex(ValueError,'COMPARISON_NOT_REPRODUCIBLE'):
            verify_comparison(out,self.before,self.after,self.bp,self.ap)

    def test_existing_output_not_overwritten(self):
        self.pair();out=self.root/'comparison'
        run_comparison(self.before,self.after,self.bp,self.ap,out)
        with self.assertRaises(FileExistsError):run_comparison(self.before,self.after,self.bp,self.ap,out)

    def test_cli_comparison_and_reverification(self):
        self.pair();out=self.root/'comparison'
        args=['--before',self.before,'--after',self.after,'--expect-before',self.bp,'--expect-after',self.ap]
        a=self.cli('compare-checks',*args,'--out',out)
        self.assertEqual(a.returncode,0,a.stderr+a.stdout)
        b=self.cli('verify-comparison',*args,'--bundle',out)
        self.assertEqual(b.returncode,0,b.stderr+b.stdout)
        self.assertFalse(json.loads(b.stdout)['vulnerability_confirmed'])

    def test_cli_regression_returns_nonzero(self):
        self.pair(old={},new={self.subject:'FAIL'})
        a=self.cli('compare-checks','--before',self.before,'--after',self.after,'--expect-before',self.bp,
                   '--expect-after',self.ap,'--out',self.root/'comparison')
        self.assertEqual(a.returncode,1,a.stderr+a.stdout)

    def test_cli_does_not_echo_sensitive_arguments(self):
        marker='private_key=LOCAL_TEST_MARKER_NOT_REAL'
        a=self.cli('compare-checks','--unknown',marker)
        self.assertEqual(a.returncode,2)
        self.assertNotIn(marker,a.stdout+a.stderr)

    def test_cli_bad_pin_reports_error_not_fix(self):
        self.pair()
        a=self.cli('compare-checks','--before',self.before,'--after',self.after,'--expect-before','bad',
                   '--expect-after',self.ap,'--out',self.root/'comparison')
        self.assertEqual(a.returncode,2)
        self.assertEqual(json.loads(a.stdout)['status'],'COMPARISON_ERROR')


if __name__ == '__main__':
    unittest.main()
