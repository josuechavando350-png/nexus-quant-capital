"""QA gate negative tests; fake receipts here are unit inputs, never evidence."""
from __future__ import annotations

from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import quality
from superhunter.quality_worker import RecordedResult
from superhunter.safe_io import canonical, write_new_bundle


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = quality.source_snapshot()
        ids = list(quality.REQUIRED_TESTS)
        self.receipt = {'schema_version':1,'sources_before':self.snapshot,'sources_after':self.snapshot,
                        'discovered':ids,'tests':[{'id':i,'outcome':'PASS'} for i in ids],
                        'tests_run':len(ids),'failures':0,'errors':0,'skipped':0,
                        'expected_failures':0,'unexpected_successes':0}

    def assess(self):
        return quality.assess(self.receipt,self.snapshot)

    def blocked(self):
        self.assertEqual(self.assess()['status'],'LOCAL_QA_BLOCKED')
        self.assertFalse(self.assess()['vulnerability_confirmed'])

    def test_consistent_unit_receipt_can_be_assessed_not_authenticated(self):
        self.assertEqual(self.assess()['status'],'LOCAL_QA_PASS')
        self.assertFalse(self.assess()['production_certified'])

    def test_skip_never_counts_as_pass(self):
        self.receipt['tests'][0]['outcome']='SKIP'
        self.receipt['skipped']=1
        self.blocked()

    def test_expected_failure_blocks_gate(self):
        self.receipt['expected_failures']=1
        self.blocked()

    def test_error_counter_blocks_gate(self):
        self.receipt['errors']=1
        self.blocked()

    def test_unexpected_success_blocks_gate(self):
        self.receipt['unexpected_successes']=1
        self.blocked()

    def test_incomplete_record_blocks_gate(self):
        self.receipt['tests'][0]['outcome']='INCOMPLETE'
        self.blocked()

    def test_unknown_outcome_is_not_pass(self):
        self.receipt['tests'][0]['outcome']='ALMOST_PASS'
        self.blocked()

    def test_source_change_blocks_success(self):
        self.receipt['sources_after']={**self.snapshot,'bridge.py':'0'*64}
        self.blocked()

    def test_source_before_must_match(self):
        self.receipt['sources_before']={}
        self.blocked()

    def test_duplicated_test_ids_block(self):
        self.receipt['tests'].append(deepcopy(self.receipt['tests'][0]))
        self.receipt['tests_run']+=1
        self.blocked()

    def test_missing_mandatory_test_blocks(self):
        self.receipt['tests'].pop()
        self.receipt['discovered']=self.receipt['discovered'][:-1]
        self.receipt['tests_run']-=1
        self.blocked()

    def test_declared_count_is_not_evidence(self):
        self.receipt['tests_run']=9999
        self.blocked()

    def test_boolean_count_rejected(self):
        self.receipt['failures']=False
        self.blocked()

    def test_empty_suite_never_passes(self):
        self.receipt['tests']=[]
        with self.assertRaises(ValueError):self.assess()

    def test_malformed_result_rejected(self):
        self.receipt['tests']=[{'id':'x'}]
        with self.assertRaises(ValueError):self.assess()

    def test_unmapped_runtime_file_detected(self):
        snap={**self.snapshot,'orphan.py':'a'*64}
        self.assertTrue(any('unmapped' in e for e in quality.validate_components(snap)))

    def test_missing_runtime_file_detected(self):
        snap={k:v for k,v in self.snapshot.items() if k!='integration.py'}
        self.assertTrue(any('missing source' in e for e in quality.validate_components(snap)))

    def test_unknown_dependency_detected(self):
        groups=deepcopy(quality.COMPONENTS);groups['io']['depends']=['nonexistent']
        self.assertTrue(any('unknown dependency' in e for e in quality.validate_components(self.snapshot,groups)))

    def test_cycle_detected(self):
        groups=deepcopy(quality.COMPONENTS);groups['io']['depends']=['quality']
        self.assertTrue(any('cycle' in e for e in quality.validate_components(self.snapshot,groups)))

    def test_duplicate_file_owner_rejected(self):
        groups=deepcopy(quality.COMPONENTS);groups['io']['files'].append('bridge.py')
        self.assertTrue(any('assigned twice' in e for e in quality.validate_components(self.snapshot,groups)))

    def test_all_50_ids_preserved_and_none_complete(self):
        data=quality.catalog()
        self.assertEqual([i['id'] for i in data['items']],list(range(1,51)))
        self.assertEqual(sum(i['status']=='PARTIAL' for i in data['items']),4)
        self.assertFalse(any(i['status']=='IMPLEMENTED' for i in data['items']))

    def test_catalog_rejects_unearned_complete(self):
        data=quality.catalog();data['items'][0]['status']='IMPLEMENTED'
        with patch('superhunter.quality.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            quality.catalog()

    def test_catalog_rejects_deleted_capability(self):
        data=quality.catalog();data['items'].pop()
        with patch('superhunter.quality.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            quality.catalog()

    def test_partial_requires_implemented_components(self):
        data=quality.catalog();data['items'][44]['components']=[]
        with patch('superhunter.quality.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            quality.catalog()

    def test_pending_cannot_borrow_proof(self):
        data=quality.catalog();data['items'][0]['components']=['lab']
        with patch('superhunter.quality.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            quality.catalog()

    def test_checklist_does_not_claim_perfection(self):
        text=quality.checklist(quality.catalog(),self.assess())
        self.assertIn('Ninguna está certificada completa',text)
        self.assertIn('50.',text)

    def test_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'real.py').write_text('x=1\n');(root/'alias.py').symlink_to(root/'real.py')
            with self.assertRaises((OSError,ValueError)):quality.source_snapshot(root)

    def test_directory_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'loop').symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError):quality.source_snapshot(root)

    def test_receipt_bundle_cannot_claim_another_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'bundle'
            result=self.assess();wrong={**result,'status':'PRODUCTION_CERTIFIED'}
            write_new_bundle(out,{'receipt.json':canonical(self.receipt),'quality.json':canonical(wrong),
                'source-snapshot.json':canonical(self.snapshot),'CHECKLIST.md':quality.checklist(quality.catalog(),result).encode(),
                'tests.log':b'unit fixture, not an execution record'})
            with self.assertRaisesRegex(ValueError,'claimed verdict'):quality.verify_bundle(out)

    def test_verifier_rejects_old_source_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'bundle';result=self.assess()
            write_new_bundle(out,{'receipt.json':canonical(self.receipt),'quality.json':canonical(result),
                'source-snapshot.json':canonical({'old':'a'*64}),'CHECKLIST.md':b'old','tests.log':b'unit fixture'})
            with self.assertRaisesRegex(ValueError,'current package'):quality.verify_bundle(out)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(FileExistsError):
            quality.run_check(Path(d))

    def test_missing_bundle_not_success(self):
        with tempfile.TemporaryDirectory() as d,self.assertRaises(OSError):
            quality.verify_bundle(Path(d))

    def test_unittest_subtest_failure_recorded(self):
        class Example(unittest.TestCase):
            def runTest(self):
                with self.subTest(i=1):self.assertEqual(1,2)
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(unittest.TestSuite([Example()]))
        self.assertEqual(result.rows[0]['outcome'],'FAIL')
        self.assertEqual(len(result.failures),1)

    def test_unittest_expected_failure_recorded(self):
        class Example(unittest.TestCase):
            @unittest.expectedFailure
            def runTest(self):self.fail('intentional fixture')
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(unittest.TestSuite([Example()]))
        self.assertEqual(result.rows[0]['outcome'],'EXPECTED_FAILURE')

    def test_unittest_skip_recorded(self):
        class Example(unittest.TestCase):
            @unittest.skip('intentional fixture')
            def runTest(self):pass
        result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(unittest.TestSuite([Example()]))
        self.assertEqual(result.rows[0]['outcome'],'SKIP')


if __name__=='__main__':unittest.main()
