"""Failure preservation tests; synthetic receipts never stand in for real QA."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from superhunter import qa_failure as failure, quality
from superhunter.quality_worker import RecordedResult
from superhunter.safe_io import canonical, write_new_bundle


class FailureEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.snapshot = {'own.py':'a'*64}
        self.digest = failure.sha(canonical(self.snapshot))
        self.ids = ['test_own.Example.test_one','test_own.Example.test_two']

    def receipt(self):
        return {'schema_version':1,'partition_index':0,'partition_count':8,
            'sources_before':self.snapshot,'sources_after':self.snapshot,
            'global_discovered':self.ids,'discovered':self.ids,'tests':[],
            'tests_run':0,'errors':1,'failures':0,'skipped':0,
            'expected_failures':0,'unexpected_successes':0,'python':'unit fixture',
            'log_privacy':{'unit_fixture':True}}

    def capture(self, receipt=None):
        worker = self.root/'worker'; write_new_bundle(worker,{
            'receipt.json':canonical(self.receipt() if receipt is None else receipt),
            'tests.log':b'explicit unit fixture\n'})
        c = failure.FailureCapture(self.root/'qa',self.snapshot)
        c.record(0,1,worker)
        report = c.save('aggregate',ValueError('private-error-must-not-appear'))
        return c.output,report

    def test_setup_class_failure_keeps_unobserved_test_ids(self):
        class Example(unittest.TestCase):
            @classmethod
            def setUpClass(cls): raise RuntimeError('owned preparation failure')
            def test_one(self): self.fail('must not run')
            def test_two(self): self.fail('must not run')
        result = unittest.TextTestRunner(stream=io.StringIO(),resultclass=RecordedResult).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Example))
        self.assertEqual((result.testsRun,len(result.errors),result.rows),(0,1,[]))
        data=self.receipt();data['tests']=result.rows;data['tests_run']=result.testsRun
        out,report=self.capture(data)
        self.assertEqual(report['not_observed_test_ids'],self.ids)
        self.assertEqual(report['recorded_unique_declared_tests'],0)
        self.assertFalse(report['qa_passed'])
        self.assertEqual(failure.verify(out,self.digest)['not_observed_tests'],2)

    def test_exact_original_receipt_log_and_marker_are_retained(self):
        out,report=self.capture()
        for name in failure.ARTIFACTS:
            self.assertEqual((out/('worker-0-'+name)).read_bytes(),(self.root/'worker'/name).read_bytes())
        self.assertNotIn('private-error',canonical(report).decode())

    def test_worker_directory_symlink_is_not_followed(self):
        real=self.root/'real';write_new_bundle(real,{'receipt.json':canonical(self.receipt()),
                                                   'tests.log':b'not this worker'})
        linked=self.root/'linked';linked.symlink_to(real,target_is_directory=True)
        c=failure.FailureCapture(self.root/'qa',self.snapshot);c.record(0,1,linked)
        report=c.save('worker_validation',ValueError())
        self.assertEqual(report['workers'][0]['available'],[])
        self.assertEqual(set(p.name for p in c.output.iterdir()),
                         {'COMPLETE.json','failure.json','source-snapshot.json'})

    def test_source_snapshot_is_frozen_before_caller_mutation(self):
        c=failure.FailureCapture(self.root/'qa',self.snapshot)
        self.snapshot['own.py']='b'*64
        c.record(0,None,self.root/'absent')
        report=c.save('worker_execution',RuntimeError())
        self.assertEqual(report['source_digest'],self.digest)
        self.assertEqual(failure.verify(c.output,self.digest)['source_digest'],self.digest)

    def test_separate_process_verifier_stays_non_successful_qa(self):
        import sys
        out,_=self.capture()
        r=subprocess.run([sys.executable,'-m','superhunter','verify-failed-check',
            '--bundle',str(out),'--source-digest',self.digest],cwd=quality.ROOT.parent,
            capture_output=True,timeout=10)
        self.assertEqual(r.returncode,1,r.stderr.decode())
        value=json.loads(r.stdout);self.assertEqual(value['status'],'QA_FAILURE_EVIDENCE_VERIFIED')
        self.assertFalse(value['qa_passed']);self.assertFalse(value['tests_rerun'])

    def test_timeout_without_receipt_keeps_inventory_unknown(self):
        c=failure.FailureCapture(self.root/'qa',self.snapshot)
        c.record(0,None,self.root/'absent')
        report=c.save('worker_execution',subprocess.TimeoutExpired('private-command',180))
        self.assertFalse(report['inventory_known']);self.assertIsNone(report['declared_total'])
        self.assertIsNone(failure.verify(c.output,self.digest)['not_observed_tests'])
        self.assertNotIn('private-command',canonical(report).decode())

    def test_real_orchestrator_preserves_timeout_without_success(self):
        out=self.root/'qa'
        with patch.object(quality.subprocess,'run',side_effect=subprocess.TimeoutExpired('private',180)):
            with self.assertRaises(subprocess.TimeoutExpired):quality.run_check(out)
        self.assertFalse(out.exists())
        result=failure.verify(self.root/'qa.failure',quality.sha(canonical(quality.source_snapshot())))
        self.assertFalse(result['qa_passed']);self.assertEqual(result['workers_captured'],1)

    def test_real_orchestrator_preserves_bad_exit_without_success(self):
        with patch.object(quality.subprocess,'run',return_value=subprocess.CompletedProcess(['fixed'],7)):
            with self.assertRaises(RuntimeError):quality.run_check(self.root/'qa')
        report=json.loads((self.root/'qa.failure/failure.json').read_text())
        self.assertEqual(report['workers'][0]['returncode'],7)
        self.assertEqual(report['stage'],'worker_validation')

    def test_resealed_pass_or_fewer_missing_tests_rejected(self):
        out,_=self.capture()
        original={p.name:p.read_bytes() for p in out.iterdir() if p.name!='COMPLETE.json'}
        for key,value in [('qa_passed',True),('not_observed_test_ids',[]),('declared_total',True)]:
            files=deepcopy(original);r=json.loads(files['failure.json']);r[key]=value
            files['failure.json']=canonical(r);other=self.root/key;write_new_bundle(other,files)
            with self.assertRaisesRegex(ValueError,'FAILURE_REPORT_MISMATCH'):failure.verify(other,self.digest)

    def test_wrong_external_source_and_raw_tamper_rejected(self):
        out,_=self.capture()
        with self.assertRaises(ValueError):failure.verify(out,'b'*64)
        (out/'worker-0-tests.log').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'FAILURE_ARTIFACT_HASH'):failure.verify(out,self.digest)

    def test_extra_file_symlink_and_existing_failure_never_accepted(self):
        out,_=self.capture()
        with self.assertRaises(FileExistsError):failure.FailureCapture(self.root/'qa',self.snapshot)
        extra=out/'extra';extra.write_bytes(b'no')
        with self.assertRaises(ValueError):failure.verify(out,self.digest)
        extra.unlink();link=self.root/'link';link.symlink_to(out,target_is_directory=True)
        with self.assertRaises(ValueError):failure.verify(link,self.digest)

    def test_malformed_receipt_is_preserved_without_invented_counts(self):
        worker=self.root/'worker';write_new_bundle(worker,{'receipt.json':b'{not json', 'tests.log':b'unit'})
        c=failure.FailureCapture(self.root/'qa',self.snapshot);c.record(0,1,worker)
        report=c.save('worker_validation',ValueError())
        self.assertEqual(report['workers'][0]['receipt_status'],'MALFORMED')
        self.assertFalse(report['inventory_known'])
        self.assertFalse(failure.verify(c.output,self.digest)['qa_passed'])

    def test_unbound_source_cannot_establish_inventory(self):
        data=self.receipt();data['sources_after']={'changed.py':'b'*64}
        out,report=self.capture(data)
        self.assertFalse(report['inventory_known']);self.assertFalse(report['workers'][0]['source_matches'])

    def test_incomplete_worker_marker_keeps_inventory_unknown(self):
        worker=self.root/'worker';worker.mkdir()
        (worker/'receipt.json').write_bytes(canonical(self.receipt()))
        c=failure.FailureCapture(self.root/'qa',self.snapshot);c.record(0,1,worker)
        report=c.save('worker_validation',ValueError())
        self.assertFalse(report['workers'][0]['worker_manifest_matches'])
        self.assertFalse(report['inventory_known'])
        self.assertFalse(failure.verify(c.output,self.digest)['qa_passed'])

    def test_conflicting_worker_inventories_are_not_combined(self):
        c=failure.FailureCapture(self.root/'qa',self.snapshot)
        for index in range(2):
            data=self.receipt();data['partition_index']=index
            if index:
                data['global_discovered']=data['discovered']=['test_other.Case.test_one']
            worker=self.root/str(index);write_new_bundle(worker,{
                'receipt.json':canonical(data),'tests.log':b'unit'})
            c.record(index,1,worker)
        report=c.save('aggregate',ValueError())
        self.assertTrue(report['inventory_conflict']);self.assertFalse(report['inventory_known'])
        self.assertIsNone(report['not_observed_test_ids'])

    def test_duplicate_or_unexpected_records_remain_visible(self):
        data=self.receipt();data['tests']=[{'id':self.ids[0],'outcome':'PASS'}]*2+[
            {'id':'other.Class.test_unknown','outcome':'ERROR'}];data['tests_run']=3
        out,report=self.capture(data);row=report['workers'][0]
        self.assertEqual(row['duplicate_test_records'],1)
        self.assertEqual(row['unexpected_test_ids'],['other.Class.test_unknown'])
        self.assertEqual(row['missing_declared_test_ids'],[self.ids[1]])

    def test_boolean_counter_is_not_a_numeric_count(self):
        data=self.receipt();data['errors']=True
        _,report=self.capture(data)
        self.assertEqual(report['workers'][0]['receipt_status'],'MALFORMED')

    def test_positive_verifier_cannot_accept_failure_bundle(self):
        out,_=self.capture()
        with self.assertRaises((ValueError,OSError)):quality.verify_bundle(out)

    def test_cli_does_not_echo_paths_on_invalid_evidence(self):
        output=io.StringIO()
        with redirect_stdout(output):
            code=failure.main(['--bundle','/private-evidence','--source-digest',self.digest])
        self.assertEqual(code,2);self.assertNotIn('private',output.getvalue())


if __name__=='__main__':unittest.main()
