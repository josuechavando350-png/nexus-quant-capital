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
        self.assertEqual({i['id'] for i in data['items'] if i['status']=='PARTIAL'}, {3,14,24,29,34,37,45,47,48})
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


    def partition_receipts(self):
        from superhunter.quality_worker import partition_ids
        ids = sorted(self.receipt['discovered'])
        groups = partition_ids(ids, quality.PARTITION_COUNT)
        return [{**deepcopy(self.receipt), 'global_discovered':ids,
                 'discovered':group,'tests':[{'id':i,'outcome':'PASS'} for i in group],
                 'tests_run':len(group),'partition_count':quality.PARTITION_COUNT,
                 'partition_index':index,'python':'synthetic-unit-fixture',
                 'log_privacy':{'fixture_only':True}} for index,group in enumerate(groups)]

    def test_partition_is_complete_disjoint_and_module_preserving(self):
        from superhunter.quality_worker import partition_ids
        names=[f'test_m{i}.Case.test_{j}' for i in range(8) for j in range(i+1)]
        groups=partition_ids(names,4)
        self.assertEqual(sorted(i for g in groups for i in g),sorted(names))
        owner={}
        for index,group in enumerate(groups):
            for name in group:
                module=name.split('.')[0]
                self.assertEqual(owner.setdefault(module,index),index)

    def test_partition_order_does_not_change_membership(self):
        from superhunter.quality_worker import partition_ids
        names=[f'test_m{i}.Case.test_{j}' for i in range(8) for j in range(i+1)]
        self.assertEqual(partition_ids(names,4),partition_ids(list(reversed(names)),4))
        for invalid in (True,0,9):
            with self.subTest(value=invalid),self.assertRaises(ValueError):partition_ids(names,invalid)

    def test_aggregate_requires_all_worker_partitions(self):
        receipts=self.partition_receipts();receipts.pop()
        with self.assertRaisesRegex(ValueError,'missing worker'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_rejects_duplicate_worker_index(self):
        receipts=self.partition_receipts();receipts[-1]['partition_index']=0
        with self.assertRaisesRegex(ValueError,'invalid worker'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_rejects_omitted_test_even_if_count_adjusted(self):
        receipts=self.partition_receipts();r=receipts[0]
        r['tests'].pop();r['tests_run']-=1
        with self.assertRaisesRegex(ValueError,'omitted or duplicated'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_rejects_mixed_source_versions(self):
        receipts=self.partition_receipts();receipts[1]['sources_after']={}
        with self.assertRaisesRegex(ValueError,'source identity'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_rejects_different_global_inventory(self):
        receipts=self.partition_receipts();receipts[1]['global_discovered']=[]
        with self.assertRaisesRegex(ValueError,'inventory/runtime'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_keeps_failure_in_combined_gate(self):
        receipts=self.partition_receipts();receipts[0]['tests'][0]['outcome']='FAIL';receipts[0]['failures']=1
        combined=quality.aggregate_receipts(receipts,self.snapshot)
        self.assertEqual(combined['failures'],1)
        self.assertEqual(quality.assess(combined,self.snapshot)['status'],'LOCAL_QA_BLOCKED')

    def test_aggregate_boolean_counter_rejected(self):
        receipts=self.partition_receipts();receipts[0]['errors']=False
        with self.assertRaisesRegex(ValueError,'integer'):
            quality.aggregate_receipts(receipts,self.snapshot)

    def test_aggregate_cannot_replace_failed_result_with_pass(self):
        receipts=self.partition_receipts()
        combined=quality.aggregate_receipts(receipts,self.snapshot)
        self.assertEqual(quality.assess(combined,self.snapshot)['status'],'LOCAL_QA_PASS')
        combined['partition_receipts'][0]['tests'][0]['outcome']='FAIL'
        combined['partition_receipts'][0]['failures']=1
        result=quality.assess(combined,self.snapshot)
        self.assertEqual(result['status'],'LOCAL_QA_BLOCKED')
        self.assertIn('aggregate differs from worker receipts',result['reasons'])



# Compact QA receipts keep every worker outcome and their source commitments.
# Existing unit fake receipts above remain unchanged and test old compatibility.
class CompactReceiptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = QualityTests()
        self.fixture.setUp()
        self.snapshot = self.fixture.snapshot
        self.workers = self.fixture.partition_receipts()
        self.full = quality.aggregate_receipts(self.workers, self.snapshot)

    def test_roundtrip_preserves_full_worker_evidence(self):
        compact = quality.compact_partition_receipt(self.full)
        self.assertEqual(quality.expand_partition_receipt(compact,self.snapshot),self.full)
        self.assertNotIn('sources_before',compact['partition_receipts'][0])
        self.assertEqual(quality.assess(compact,self.snapshot),quality.assess(self.full,self.snapshot))

    def test_worker_outcome_tamper_is_rejected_even_when_outer_report_rehashed(self):
        compact = quality.compact_partition_receipt(self.full)
        compact['partition_receipts'][0]['tests'][0]['outcome']='PASS_FAKE'
        with self.assertRaisesRegex(ValueError,'worker receipt commitment mismatch'):
            quality.expand_partition_receipt(compact,self.snapshot)

    def test_worker_source_identity_cannot_be_overridden(self):
        compact = quality.compact_partition_receipt(self.full)
        compact['partition_receipts'][0]['sources_after']={}
        with self.assertRaisesRegex(ValueError,'invalid compact worker fields'):
            quality.expand_partition_receipt(compact,self.snapshot)

    def test_source_change_invalidates_every_worker_commitment(self):
        compact = quality.compact_partition_receipt(self.full)
        snapshot = dict(self.snapshot)
        snapshot['quality.py']='0'*64
        with self.assertRaisesRegex(ValueError,'worker receipt commitment mismatch'):
            quality.expand_partition_receipt(compact,snapshot)

    def test_truncated_compact_receipt_never_passes(self):
        compact = quality.compact_partition_receipt(self.full)
        compact['partition_receipts'].pop()
        with self.assertRaisesRegex(ValueError,'invalid compact QA receipt'):
            quality.expand_partition_receipt(compact,self.snapshot)

    def test_older_uncompressed_receipt_is_supported(self):
        self.assertIs(quality.expand_partition_receipt(self.full,self.snapshot),self.full)

    def test_compact_receipt_smaller_without_dropping_tests(self):
        compact = quality.compact_partition_receipt(self.full)
        self.assertLess(len(canonical(compact)),len(canonical(self.full)))
        self.assertEqual(compact['tests'],self.full['tests'])
        self.assertEqual(compact['tests_run'],self.full['tests_run'])


if __name__=='__main__':unittest.main()
