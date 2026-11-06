"""Joint-acceptance wiring tests, with explicit QA/execute test doubles.

The native fixture came from a prior real execution. Mocked calls below prove
control flow and checks, NOT new compilations or native acceptance. Separate
CLI acceptance with real binaries is required and recorded outside this suite.
"""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from superhunter import native_platform as joint, evm_accounting, evm_execution, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

AT = '2026-11-05T23:00:00+00:00'
FIXTURE = Path(__file__).parent / 'fixtures/evm_accounting_capture.json'


class NativePlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = strict_json(FIXTURE.read_bytes())
        cls.native_files = evm_accounting.documents(cls.capture, AT)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bundle = self.root / 'run'
        self.solc, self.evm = self.root / 'solc', self.root / 'evm'
        self.source = joint.source_digest()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(joint, 'LOCAL_FILES', {'qa/receipt.json', 'qa/UNIT_FIXTURE.txt'}))
        self.stack.enter_context(patch.object(joint, 'preflight', side_effect=lambda *_: evm_accounting.identity()))
        self.native_run = self.stack.enter_context(patch.object(evm_execution, 'execute', return_value=self.capture))
        self.qa_run = self.stack.enter_context(patch.object(joint.local, 'run_platform', side_effect=self.fake_qa))
        self.qa_verify = self.stack.enter_context(patch.object(joint.local, 'verify_platform', side_effect=self.fake_qa_verify))

    def qa_result(self):
        return {'status': 'LOCAL_DEFENSIVE_REVIEW_PASS', 'source_digest': self.source,
                'platform_complete': False, 'vulnerability_confirmed': False,
                'stages': {'qa': {'status': 'LOCAL_QA_PASS', 'tests_run': 2},
                           'lab': {'cases_passed': 5}, 'fuzz': {'cases_verified': 256},
                           'economics': {'cases_checked': 3}, 'benchmark_control': {'cases': 8},
                           'sequence': {'cases_checked': 4}},
                'integration': {'items': [{'id': i} for i in range(1,28)]},
                'capabilities': {'items': [{'id': i} for i in range(1,51)]},
                'research_initiatives': {'items': [{'id': 'unit-fixture-'+str(i)} for i in range(25)]}}

    def fake_qa(self, out):
        (out / 'qa').mkdir(parents=True, mode=0o700)
        (out / 'qa/receipt.json').write_bytes(canonical({'discovered': ['fixture.one', 'fixture.two']}))
        (out / 'qa/UNIT_FIXTURE.txt').write_text('FABRICATED QA TEST INPUT: not an execution receipt.\n')
        return self.qa_result()

    def fake_qa_verify(self, out):
        # This unit double checks that the orchestrator uses this directory.
        self.assertTrue((out / 'qa/UNIT_FIXTURE.txt').is_file())
        return self.qa_result()

    def run_joint(self):
        return joint.create(self.solc, self.evm, self.bundle)

    def verify(self):
        return joint.verify(self.bundle, self.solc, self.evm, self.source)

    def reseal(self, folder, name, fn):
        p = folder / name
        data = strict_json(p.read_bytes()); fn(data); raw = canonical(data); p.write_bytes(raw)
        m = strict_json((folder / 'COMPLETE.json').read_bytes()); m['sha256'][name] = joint.sha(raw)
        (folder / 'COMPLETE.json').write_bytes(canonical(m))

    def test_replay_is_mandatory_even_after_creation(self):
        self.run_joint()
        self.assertEqual(self.qa_run.call_count, 1)
        self.assertEqual(self.native_run.call_count, 2)  # creation + mandatory replay
        self.verify()
        self.assertEqual(self.native_run.call_count, 3)
        self.assertEqual(self.qa_run.call_count, 1)  # verifier revalidates QA, not reruns suite

    def test_actual_native_verifier_called(self):
        with patch.object(evm_accounting, 'replay', wraps=evm_accounting.replay) as replay:
            self.run_joint(); self.verify()
        self.assertEqual(replay.call_count, 2)

    def test_unified_result_preserves_boundaries(self):
        r = self.run_joint()
        self.assertEqual(r['qa']['tests_run'], 2)
        self.assertEqual((r['native_controls']['constructors'], r['native_controls']['calls']), (3,18))
        self.assertEqual((r['native_controls']['applied_transfers'], r['native_controls']['failed_calls_without_transfer']), (5,13))
        for name in ('platform_complete','vulnerability_confirmed','producer_authenticated',
                     'independent_evm_used','network_used','external_targets_executed'):
            self.assertIs(r[name], False)
        self.assertIsNone(r['monetary_valuation_usd'])
        self.assertFalse(r['qa']['tests_reexecuted_by_verifier'])
        self.assertEqual(len(r['plans']['integration_ids']), 27)
        self.assertEqual(len(r['plans']['capability_ids']), 50)
        self.assertEqual(len(r['plans']['initiative_ids']), 25)

    def test_observed_states_not_tentative_states(self):
        r = self.run_joint()
        self.assertEqual(r['native_controls']['cases']['delayed_credit']['final_units'], {'debit':'10','credit':'5'})
        self.assertEqual(r['native_controls']['cases']['delayed_credit']['applied_units'],'5')

    def test_native_failure_cannot_emit_success(self):
        self.native_run.side_effect = ValueError('FIXED_EXECUTION_FAILURE')
        with self.assertRaises(ValueError): self.run_joint()
        self.assertFalse((self.bundle/'review/COMPLETE.json').exists())

    def test_qa_failure_prevents_native_execution(self):
        self.qa_run.side_effect = ValueError('QA_FAILURE')
        with self.assertRaises(ValueError): self.run_joint()
        self.native_run.assert_not_called()
        self.assertFalse((self.bundle/'review').exists())

    def test_preflight_failure_prevents_qa_or_output(self):
        with patch.object(joint,'preflight',side_effect=ValueError('MISSING_BINARY')):
            with self.assertRaises(ValueError): self.run_joint()
        self.qa_run.assert_not_called(); self.native_run.assert_not_called()
        self.assertFalse(self.bundle.exists())

    def test_second_native_execution_must_not_be_skipped(self):
        self.native_run.side_effect = [self.capture, ValueError('REPLAY_FAILURE')]
        with self.assertRaises(ValueError): self.run_joint()
        self.assertEqual(self.native_run.call_count,2)
        self.assertFalse((self.bundle/'review/COMPLETE.json').exists())

    def test_verification_without_binary_does_not_fall_back(self):
        self.run_joint(); before=self.native_run.call_count
        with patch.object(joint,'preflight',side_effect=ValueError('MISSING_BINARY')):
            with self.assertRaises(ValueError): self.verify()
        self.assertEqual(self.native_run.call_count,before)

    def test_wrong_qa_source_rejected_before_native_replay(self):
        self.run_joint(); self.native_run.reset_mock()
        fake=self.qa_result(); fake['source_digest']='0'*64
        self.qa_verify.side_effect=None; self.qa_verify.return_value=fake
        with self.assertRaisesRegex(ValueError,'LOCAL_QA_IDENTITY'): self.verify()
        self.native_run.assert_not_called()

    def test_expected_source_is_external_and_mandatory(self):
        self.run_joint(); self.native_run.reset_mock()
        for bad in ('0'*64, None, True, 'not-a-hash'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                joint.verify(self.bundle,self.solc,self.evm,bad)
        self.native_run.assert_not_called()

    def test_boolean_qa_count_not_integer(self):
        self.run_joint(); fake=self.qa_result(); fake['stages']['qa']['tests_run']=True
        self.qa_verify.side_effect=None; self.qa_verify.return_value=fake
        with self.assertRaisesRegex(ValueError,'QA_COUNT'): self.verify()

    def test_extra_local_file_rejected_before_replay(self):
        self.run_joint(); self.native_run.reset_mock()
        (self.bundle/'local/qa/untracked.txt').write_text('DO_NOT_EXPORT')
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_EVIDENCE_FILE'): self.verify()
        self.native_run.assert_not_called()

    def test_extra_nested_directory_rejected(self):
        self.run_joint(); (self.bundle/'local/qa/extra').mkdir()
        with self.assertRaisesRegex(ValueError,'UNEXPECTED_EVIDENCE_DIRECTORY'): self.verify()

    def test_missing_native_stage_rejected(self):
        self.run_joint(); shutil.rmtree(self.bundle/'native'); self.native_run.reset_mock()
        with self.assertRaisesRegex(ValueError,'JOINT_STAGE_INVENTORY'): self.verify()
        self.native_run.assert_not_called()

    def test_missing_native_artifact_rejected(self):
        self.run_joint(); (self.bundle/'native/evm--execution.json').unlink()
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_EVIDENCE'): self.verify()

    def test_extra_top_level_stage_rejected(self):
        self.run_joint(); (self.bundle/'invented-stage').mkdir()
        with self.assertRaisesRegex(ValueError,'JOINT_STAGE_INVENTORY'): self.verify()

    def test_root_symlink_rejected(self):
        self.run_joint(); alias=self.root/'alias'; alias.symlink_to(self.bundle,target_is_directory=True)
        with self.assertRaises(ValueError): joint.verify(alias,self.solc,self.evm,self.source)

    def test_artifact_symlink_rejected(self):
        self.run_joint(); p=self.bundle/'local/qa/receipt.json'
        external=self.root/'receipt.json';external.write_bytes(p.read_bytes());p.unlink();p.symlink_to(external)
        with self.assertRaises(ValueError):self.verify()

    def test_native_source_map_cannot_disagree_with_qa(self):
        snap=quality.source_snapshot()
        with self.assertRaisesRegex(ValueError,'QA_NATIVE_SOURCE_MISMATCH'):
            joint._check_source_maps({'nested':{'sources_sha256':{'evm_accounting.py':'0'*64}}},snap)

    def test_native_replay_cannot_report_false_or_missing_execution(self):
        self.run_joint()
        with patch.object(evm_accounting,'replay',return_value={'native_execution_performed_here':False}):
            with self.assertRaisesRegex(ValueError,'REPLAY_RECEIPT'):self.verify()

    def test_changed_report_cannot_claim_completion(self):
        self.run_joint()
        self.reseal(self.bundle/'review','acceptance.json',lambda r:r.update(platform_complete=True))
        with self.assertRaisesRegex(ValueError,'DIFFERS_FROM_REPLAY'):self.verify()

    def test_changed_count_cannot_inflate_results(self):
        self.run_joint()
        self.reseal(self.bundle/'review','acceptance.json',lambda r:r['qa'].update(tests_run=999999))
        with self.assertRaisesRegex(ValueError,'DIFFERS_FROM_REPLAY'):self.verify()

    def test_resealed_audit_cannot_claim_other_execution(self):
        self.run_joint()
        self.reseal(self.bundle/'review','audit.json',lambda r:r['events'][1]['data']['native_controls'].update(calls=0))
        with self.assertRaisesRegex(ValueError,'DIFFERS_FROM_REPLAY'):self.verify()

    def test_altered_native_effects_rejected_by_real_artifact_verifier(self):
        self.run_joint()
        self.reseal(self.bundle/'native','effects.json',lambda r:r.update(failed_calls_without_transfer=0))
        with self.assertRaisesRegex(ValueError,'NATIVE_ACCOUNTING_REPLAY_MISMATCH'):self.verify()

    def test_changed_local_bytes_do_not_inherit_joint_receipt(self):
        self.run_joint()
        (self.bundle/'local/qa/UNIT_FIXTURE.txt').write_text('DIFFERENT FIXTURE')
        with self.assertRaisesRegex(ValueError,'DIFFERS_FROM_REPLAY'):self.verify()

    def test_missing_final_marker_is_not_success(self):
        self.run_joint();(self.bundle/'review/COMPLETE.json').unlink();self.native_run.reset_mock()
        with self.assertRaises(ValueError):self.verify()
        self.native_run.assert_not_called()

    def test_new_output_required_and_previous_evidence_unchanged(self):
        self.run_joint();raw=(self.bundle/'review/acceptance.json').read_bytes()
        with self.assertRaises(ValueError):self.run_joint()
        self.assertEqual(raw,(self.bundle/'review/acceptance.json').read_bytes())

    def test_output_cannot_enter_checkout(self):
        with self.assertRaises(ValueError):
            joint.create(self.solc,self.evm,joint.ROOT/'generated-unit-fixture')

    def test_native_and_report_original_bytes_unchanged_by_verify(self):
        self.run_joint();before={str(p.relative_to(self.bundle)):p.read_bytes() for p in self.bundle.rglob('*') if p.is_file()}
        self.verify();after={str(p.relative_to(self.bundle)):p.read_bytes() for p in self.bundle.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_report_private_permissions(self):
        self.run_joint();self.assertEqual(self.bundle.stat().st_mode&0o777,0o700)
        self.assertEqual((self.bundle/'review').stat().st_mode&0o777,0o700)
        for p in (self.bundle/'review').iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_inventory_budget_enforced(self):
        self.run_joint()
        with patch.object(joint,'MAX_TREE_BYTES',1), self.assertRaisesRegex(ValueError,'EVIDENCE_BUDGET'):self.verify()

    def test_cli_rejects_target_rpc_or_source_options(self):
        for option in ('--rpc','--target','--source','--payload'):
            with redirect_stderr(io.StringIO()) as stream,self.assertRaises(SystemExit):
                joint.main(['review-native-platform','--out',str(self.root/'out'),'--solc','x','--evm','x',option,'SECRET'])
            self.assertNotIn('SECRET',stream.getvalue())

    def test_cli_structured_failure_no_private_paths(self):
        with redirect_stdout(io.StringIO()) as stream:
            code=joint.main(['verify-native-platform','--bundle',str(self.root/'PRIVATE'),'--solc','x','--evm','x','--expected-source',self.source])
        self.assertEqual(code,2);self.assertNotIn('PRIVATE',stream.getvalue())
        self.assertFalse(json.loads(stream.getvalue())['platform_complete'])

    def test_cli_connected_to_package_entrypoint(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','review-native-platform','--out',str(self.bundle),'--solc','x','--evm','x']),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(__main__.main(),0)
        self.assertEqual(json.loads(output.getvalue())['native_calls'],18)

    def test_qa_blocked_return_prevents_native_execution(self):
        def blocked(out):
            result=self.fake_qa(out);result['status']='LOCAL_QA_BLOCKED';return result
        self.qa_run.side_effect=blocked
        with self.assertRaisesRegex(ValueError,'QA_STAGE_NOT_APPROVED'):self.run_joint()
        self.native_run.assert_not_called()

    def test_source_change_after_qa_blocks_native_stage(self):
        original=quality.source_snapshot()
        state={'changed':False}
        def snapshot():
            return {**original,'native_platform.py':'0'*64} if state['changed'] else original
        def qa(out):
            r=self.fake_qa(out);state['changed']=True;return r
        self.qa_run.side_effect=qa
        with patch.object(quality,'source_snapshot',side_effect=snapshot),self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_AFTER_QA'):
            self.run_joint()
        self.native_run.assert_not_called()

    def test_creation_cannot_ignore_untracked_root_file(self):
        def native(solc,evm,out):
            write_new_bundle(out,self.native_files)
            (out.parent/'UNTRACKED.txt').write_text('do not ignore')
        with patch.object(evm_accounting,'create',side_effect=native),self.assertRaisesRegex(ValueError,'JOINT_STAGE_INVENTORY'):
            self.run_joint()
        self.assertFalse((self.bundle/'review/COMPLETE.json').exists())

    def test_native_evidence_mutation_during_replay_blocks_report(self):
        self.run_joint()
        original=evm_accounting.replay
        def mutate(root,solc,evm):
            result=original(root,solc,evm)
            with (root/'REVIEW.md').open('ab') as stream:stream.write(b' ')
            return result
        with patch.object(evm_accounting,'replay',side_effect=mutate),self.assertRaisesRegex(ValueError,'SOURCE_OR_EVIDENCE_CHANGED'):
            self.verify()

    def test_quality_graph_no_cycle_and_tests_required(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])
        self.assertIn('native_platform',quality.COMPONENTS['entrypoints']['depends'])
        self.assertIn('test_native_platform.NativePlatformTests.test_native_failure_cannot_emit_success',quality.REQUIRED_TESTS)


if __name__=='__main__':
    unittest.main()
