"""Combined review tests. Synthetic QA receipts are unit fixtures, not run evidence."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import platform, quality, balance_reconciliation as accounting, benchmark_controls, ledger_sequence
from superhunter.fuzz_lab import execute as execute_fuzz
from superhunter.local_lab import execute_local
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab_bytes = execute_local()
        cls.fuzz_bytes = execute_fuzz(20261104, 4)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root/'platform'
        self.bundle.mkdir(mode=0o700)
        write_new_bundle(self.bundle/'lab', self.lab_bytes)
        write_new_bundle(self.bundle/'fuzz', self.fuzz_bytes)
        accounting.run_examples(self.bundle/'economics')
        benchmark_controls.create(self.bundle/'benchmark_control')
        ledger_sequence.run_controls(self.bundle/'sequence')
        self.snapshot = quality.source_snapshot()
        ids = platform._test_inventory()
        self.receipt = {'schema_version':1, 'sources_before':self.snapshot, 'sources_after':self.snapshot,
                        'discovered':ids, 'tests':[{'id':i,'outcome':'PASS'} for i in ids],
                        'tests_run':len(ids), 'failures':0, 'errors':0, 'skipped':0,
                        'expected_failures':0, 'unexpected_successes':0}
        self.make_qa()

    def make_qa(self):
        result = quality.assess(self.receipt, self.snapshot)
        write_new_bundle(self.bundle/'qa', {
            'receipt.json':canonical(self.receipt), 'quality.json':canonical(result),
            'source-snapshot.json':canonical(self.snapshot),
            'CHECKLIST.md':quality.checklist(quality.catalog(), result).encode(),
            'tests.log':b'UNIT FIXTURE ONLY: fabricated receipt for parser checks, not evidence of execution.\n'})

    def reseal(self, subdir, name, edit):
        target = self.bundle/subdir/name
        value = strict_json(target.read_bytes())
        edit(value)
        raw = canonical(value)
        target.write_bytes(raw)
        marker = strict_json((self.bundle/subdir/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (self.bundle/subdir/'COMPLETE.json').write_bytes(canonical(marker))

    def test_all_original_ids_retained(self):
        result = platform.collect(self.bundle)
        self.assertEqual([x['id'] for x in result['integration']['items']], list(range(1,28)))
        self.assertEqual([x['id'] for x in result['capabilities']['items']], list(range(1,51)))
        self.assertEqual(result['integration']['counts'], {'IMPLEMENTED_BOUNDED':12,'PENDING':12,'PARTIAL':3})
        self.assertEqual(result['capabilities']['counts'], {'PLANNED':24,'PARTIAL':9,'REDESIGN_REQUIRED':17})

    def test_complete_local_evidence_does_not_complete_platform(self):
        result = platform.collect(self.bundle)
        self.assertFalse(result['platform_complete'])
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertFalse(result['independently_authenticated'])
        self.assertEqual(result['stages']['fuzz']['cases_verified'], 4)
        self.assertEqual(result['stages']['lab']['cases_passed'], 5)

    def test_every_stage_is_actually_reverified(self):
        with patch.object(platform.quality,'verify_bundle',wraps=quality.verify_bundle) as qa, \
             patch.object(platform,'verify_local_bundle',wraps=platform.verify_local_bundle) as lab, \
             patch.object(platform,'verify_fuzz',wraps=platform.verify_fuzz) as fuzz:
            platform.collect(self.bundle)
        self.assertEqual([qa.call_count,lab.call_count,fuzz.call_count], [1,1,1])

    def test_missing_qa_not_silently_ignored(self):
        shutil.rmtree(self.bundle/'qa')
        with self.assertRaises((OSError,ValueError)):
            platform.collect(self.bundle)

    def test_missing_fuzz_not_silently_ignored(self):
        shutil.rmtree(self.bundle/'fuzz')
        with self.assertRaises((OSError,ValueError)):
            platform.collect(self.bundle)

    def test_failed_qa_blocks_review(self):
        shutil.rmtree(self.bundle/'qa')
        self.receipt['tests'][0]['outcome']='FAIL'
        self.receipt['failures']=1
        self.make_qa()
        with self.assertRaisesRegex(ValueError,'QA is blocked'):
            platform.collect(self.bundle)

    def test_nonmandatory_missing_test_blocks_complete_suite_claim(self):
        required = set(quality.REQUIRED_TESTS)
        selected = next(i for i in self.receipt['discovered'] if i not in required)
        self.receipt['discovered'].remove(selected)
        self.receipt['tests']=[r for r in self.receipt['tests'] if r['id'] != selected]
        self.receipt['tests_run']-=1
        shutil.rmtree(self.bundle/'qa'); self.make_qa()
        with self.assertRaisesRegex(ValueError,'complete current test inventory'):
            platform.collect(self.bundle)

    def test_stale_source_snapshot_rejected(self):
        self.reseal('qa','source-snapshot.json',lambda d:d.update({'old.py':'0'*64}))
        with self.assertRaisesRegex(ValueError,'current package'):
            platform.collect(self.bundle)

    def test_input_change_after_review_rejected(self):
        platform._finish(self.bundle)
        with (self.bundle/'fuzz/fuzz-result.json').open('ab') as stream:
            stream.write(b' ')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            platform.verify_platform(self.bundle)

    def test_resealed_complete_claim_rejected(self):
        platform._finish(self.bundle)
        self.reseal('review','review.json',lambda d:d.update(platform_complete=True))
        with self.assertRaisesRegex(ValueError,'recomputed evidence'):
            platform.verify_platform(self.bundle)

    def test_resealed_test_count_claim_rejected(self):
        platform._finish(self.bundle)
        self.reseal('review','review.json',lambda d:d['stages']['qa'].update(tests_run=99999))
        with self.assertRaisesRegex(ValueError,'recomputed evidence'):
            platform.verify_platform(self.bundle)

    def test_unearned_checkbox_in_report_rejected(self):
        platform._finish(self.bundle)
        path=self.bundle/'review/INTEGRATION.md'
        raw=path.read_bytes()+b'\nAll vulnerabilities found.\n';path.write_bytes(raw)
        marker=strict_json((path.parent/'COMPLETE.json').read_bytes())
        marker['sha256'][path.name]=hashlib.sha256(raw).hexdigest()
        (path.parent/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError,'recomputed evidence'):
            platform.verify_platform(self.bundle)

    def test_full_review_roundtrip(self):
        result=platform._finish(self.bundle)
        self.assertEqual(platform.verify_platform(self.bundle), result)
        self.assertTrue(set(platform.INPUT_FILES)==set(result['evidence_sha256']))
        text=(self.bundle/'review/STATUS.md').read_text()
        self.assertIn('Plataforma completa: NO', text)
        self.assertIn('no certifica ausencia de errores', text)
        self.assertIn('27.', (self.bundle/'review/INTEGRATION.md').read_text())
        self.assertIn('50.', (self.bundle/'review/CAPABILITIES.md').read_text())

    def test_unexpected_extra_stage_rejected(self):
        platform._finish(self.bundle)
        (self.bundle/'undocumented').mkdir()
        with self.assertRaisesRegex(ValueError,'unexpected or missing'):
            platform.verify_platform(self.bundle)

    def test_missing_completion_marker_rejected(self):
        platform._finish(self.bundle)
        (self.bundle/'review/COMPLETE.json').unlink()
        with self.assertRaises(OSError):
            platform.verify_platform(self.bundle)

    def test_report_symlink_rejected(self):
        platform._finish(self.bundle)
        p=self.bundle/'review/STATUS.md'
        raw=p.read_bytes();p.unlink();(self.root/'report').write_bytes(raw);p.symlink_to(self.root/'report')
        with self.assertRaises((OSError,ValueError)):
            platform.verify_platform(self.bundle)

    def test_registry_cannot_delete_original_item(self):
        data=platform.integration_plan();data['items'].pop()
        with patch('superhunter.platform.read_artifact',return_value=canonical(data)), self.assertRaises(ValueError):
            platform.integration_plan()

    def test_registry_cannot_reorder_items(self):
        data=platform.integration_plan();data['items'][0],data['items'][1]=data['items'][1],data['items'][0]
        with patch('superhunter.platform.read_artifact',return_value=canonical(data)), self.assertRaises(ValueError):
            platform.integration_plan()

    def test_registry_boolean_id_rejected(self):
        data=platform.integration_plan();data['items'][0]['id']=True
        with patch('superhunter.platform.read_artifact',return_value=canonical(data)), self.assertRaises(ValueError):
            platform.integration_plan()

    def test_registry_evidence_required_for_checkbox(self):
        data=platform.integration_plan();data['items'][0]['required_tests']=[]
        with patch('superhunter.platform.read_artifact',return_value=canonical(data)), self.assertRaises(ValueError):
            platform.integration_plan()

    def test_registry_unknown_component_rejected(self):
        data=platform.integration_plan();data['items'][0]['components']=['imaginary-engine']
        with patch('superhunter.platform.read_artifact',return_value=canonical(data)), self.assertRaises(ValueError):
            platform.integration_plan()

    def test_registered_but_unexecuted_test_cannot_support_item(self):
        data=platform.integration_plan();data['items'][0]['required_tests']=['test_platform.DoesNotExist.test_nothing']
        with patch.object(platform,'integration_plan',return_value=data), patch.object(platform,'verify_projection'), self.assertRaisesRegex(ValueError,'missing or failed'):
            platform.collect(self.bundle)

    def test_snapshot_covers_both_registries(self):
        self.assertIn('capabilities.json', self.snapshot)
        self.assertIn('integration-checklist.json', self.snapshot)

    def test_source_drift_during_collection_rejected(self):
        original=quality.source_snapshot
        calls=0
        def changed():
            nonlocal calls
            calls+=1
            return original() if calls<=2 else {**original(),'platform.py':'0'*64}
        with patch.object(quality,'source_snapshot',side_effect=changed), self.assertRaisesRegex(ValueError,'changed during review'):
            platform.collect(self.bundle)

    def test_workflow_existing_destination_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            platform.run_platform(self.bundle)

    def test_workflow_outputs_not_in_public_source_checkout(self):
        with self.assertRaisesRegex(ValueError,'outside the source checkout'):
            platform.run_platform(platform.ROOT/'test-generated-output-must-not-exist')

    def test_workflow_runs_only_fixed_stages(self):
        calls=[]
        with patch.object(quality,'run_check',side_effect=lambda p:calls.append(('qa',p)) or {'status':'LOCAL_QA_PASS'}), \
             patch.object(platform,'lab_main',side_effect=lambda a:calls.append(('lab',a)) or 0), \
             patch.object(platform,'fuzz_main',side_effect=lambda a:calls.append(('fuzz',a)) or 0), \
             patch.object(accounting,'run_examples',side_effect=lambda p:calls.append(('economics',p))), \
             patch.object(benchmark_controls,'create',side_effect=lambda p:calls.append(('benchmark_control',p))), \
             patch.object(ledger_sequence,'run_controls',side_effect=lambda p:calls.append(('sequence',p))), \
             patch.object(platform,'_finish',return_value={'unit_fixture':True}):
            self.assertEqual(platform.run_platform(self.root/'orchestrated'), {'unit_fixture':True})
        self.assertEqual([c[0] for c in calls], ['qa','lab','fuzz','economics','benchmark_control','sequence'])
        self.assertEqual(calls[2][1][-4:], ['--seed','20261104','--cases','256'])

    def test_workflow_qa_failure_stops_remaining_stages(self):
        with patch.object(quality,'run_check',return_value={'status':'LOCAL_QA_BLOCKED'}), \
             patch.object(platform,'lab_main') as lab, self.assertRaises(ValueError):
            platform.run_platform(self.root/'blocked')
        lab.assert_not_called()
        self.assertFalse((self.root/'blocked/review/COMPLETE.json').exists())

    def test_workflow_lab_failure_stops_fuzz(self):
        with patch.object(quality,'run_check',return_value={'status':'LOCAL_QA_PASS'}), \
             patch.object(platform,'lab_main',return_value=2), \
             patch.object(platform,'fuzz_main') as fuzz, self.assertRaises(RuntimeError):
            platform.run_platform(self.root/'blocked')
        fuzz.assert_not_called()

    def test_workflow_fuzz_failure_stops_report(self):
        with patch.object(quality,'run_check',return_value={'status':'LOCAL_QA_PASS'}), \
             patch.object(platform,'lab_main',return_value=0), \
             patch.object(platform,'fuzz_main',return_value=2), \
             patch.object(platform,'_finish') as finish, self.assertRaises(RuntimeError):
            platform.run_platform(self.root/'blocked')
        finish.assert_not_called()

    def test_cli_verification(self):
        platform._finish(self.bundle)
        proc=subprocess.run([sys.executable,'-B','-m','superhunter','verify-platform','--bundle',str(self.bundle)],
                            cwd=platform.ROOT.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
        self.assertFalse(json.loads(proc.stdout)['platform_complete'])

    def test_cli_error_is_not_success(self):
        with redirect_stdout(io.StringIO()) as output:
            code=platform.main(['verify-platform','--bundle',str(self.root/'missing')])
        self.assertEqual(code,2)
        self.assertFalse(json.loads(output.getvalue())['platform_complete'])

    def test_timeout_is_structured_error(self):
        with patch.object(platform,'run_platform',side_effect=subprocess.TimeoutExpired('fixed',180)), redirect_stdout(io.StringIO()) as output:
            code=platform.main(['review-platform','--out',str(self.root/'timeout')])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(output.getvalue())['error_type'],'TimeoutExpired')

    def test_verifier_never_starts_a_process_or_network(self):
        platform._finish(self.bundle)
        with patch('subprocess.run',side_effect=AssertionError('process')), patch('socket.socket',side_effect=AssertionError('network')):
            self.assertFalse(platform.verify_platform(self.bundle)['platform_complete'])

    def test_no_poC_or_target_cli_option(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            platform.main(['review-platform','--out',str(self.root/'unused'),'--target','example.invalid'])


    def test_economic_stage_is_required(self):
        shutil.rmtree(self.bundle/'economics')
        with self.assertRaises((ValueError,OSError)):
            platform.collect(self.bundle)

    def test_economic_stage_recomputed_not_only_hashed(self):
        with patch.object(accounting,'verify_examples',wraps=accounting.verify_examples) as verify:
            result=platform.collect(self.bundle)
        self.assertEqual(verify.call_count,1)
        self.assertEqual(result['stages']['economics']['cases_checked'],3)
        self.assertFalse(result['stages']['economics']['vulnerability_confirmed'])

    def test_resealed_economic_result_blocks_platform(self):
        self.reseal('economics/one_unit_gap','analysis.json',lambda v:v.update(status='ACCOUNTING_RECONCILED'))
        with self.assertRaisesRegex(ValueError,'RESULT_MISMATCH'):
            platform.collect(self.bundle)

    def test_economic_error_stops_final_report(self):
        with patch.object(quality,'run_check',return_value={'status':'LOCAL_QA_PASS'}), \
             patch.object(platform,'lab_main',return_value=0), \
             patch.object(platform,'fuzz_main',return_value=0), \
             patch.object(accounting,'run_examples',side_effect=ValueError('control failed')), \
             patch.object(platform,'_finish') as finish, self.assertRaises(ValueError):
            platform.run_platform(self.root/'blocked-economic')
        finish.assert_not_called()

    def test_economic_report_and_evidence_are_bound(self):
        result=platform.collect(self.bundle)
        self.assertIn('Conciliación económica: 3 controles sintéticos',platform.render_status(result))
        expected={'economics/'+p for p in accounting.EXAMPLE_INPUT_FILES}
        self.assertTrue(expected <= set(result['evidence_sha256']))

    def test_missing_benchmark_controls_blocks_review(self):
        shutil.rmtree(self.bundle/'benchmark_control')
        with self.assertRaises((OSError,ValueError)):
            platform.collect(self.bundle)

    def test_benchmark_control_is_reexecuted_and_bound(self):
        with patch.object(benchmark_controls,'verify',wraps=benchmark_controls.verify) as verify:
            result=platform.collect(self.bundle)
        self.assertEqual(verify.call_count,1)
        self.assertEqual(result['stages']['benchmark_control']['cases'],8)
        self.assertFalse(result['stages']['benchmark_control']['generalization_established'])
        expected={'benchmark_control/'+name for name in benchmark_controls.FILES | {'COMPLETE.json'}}
        self.assertTrue(expected <= set(result['evidence_sha256']))

    def test_benchmark_control_resealed_metric_rejected(self):
        self.reseal('benchmark_control','evaluation.json',lambda obj:obj.update(generalization_established=True))
        with self.assertRaisesRegex(ValueError,'CONTROL_SCORE_MISMATCH'):
            platform.collect(self.bundle)

    def test_benchmark_stage_failure_blocks_final_report(self):
        with patch.object(quality,'run_check',return_value={'status':'LOCAL_QA_PASS'}), \
             patch.object(platform,'lab_main',return_value=0), \
             patch.object(platform,'fuzz_main',return_value=0), \
             patch.object(accounting,'run_examples'), \
             patch.object(benchmark_controls,'create',side_effect=ValueError('fixture failed')), \
             patch.object(platform,'_finish') as finish, self.assertRaises(ValueError):
            platform.run_platform(self.root/'blocked-benchmark')
        finish.assert_not_called()

    def test_benchmark_report_never_claims_detection_rate(self):
        result=platform.collect(self.bundle)
        text=platform.render_status(result)
        self.assertIn('no benchmark ciego ni tasa de descubrimiento',text)
        self.assertIn('8 controles conocidos',text)

    def test_missing_sequence_controls_blocks_review(self):
        shutil.rmtree(self.bundle/'sequence')
        with self.assertRaises((OSError, ValueError)):
            platform.collect(self.bundle)

    def test_sequence_control_is_reverified_not_just_reported(self):
        with patch.object(ledger_sequence, 'verify_controls', wraps=ledger_sequence.verify_controls) as verify:
            result = platform.collect(self.bundle)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(result['stages']['sequence']['cases_checked'], 4)
        self.assertFalse(result['stages']['sequence']['evm_executed'])
        self.assertTrue({'sequence/'+p for p in ledger_sequence.CONTROL_FILES} <= set(result['evidence_sha256']))

    def test_resealed_sequence_control_cannot_claim_validity(self):
        self.reseal('sequence/funds_late', 'result.json', lambda v: v.update(status='LEDGER_SEQUENCE_CONSISTENT'))
        with self.assertRaises(ValueError):
            platform.collect(self.bundle)

    def test_sequence_failure_blocks_final_publication(self):
        with patch.object(quality, 'run_check', return_value={'status': 'LOCAL_QA_PASS'}), \
             patch.object(platform, 'lab_main', return_value=0), \
             patch.object(platform, 'fuzz_main', return_value=0), \
             patch.object(accounting, 'run_examples'), \
             patch.object(benchmark_controls, 'create'), \
             patch.object(ledger_sequence, 'run_controls', side_effect=ValueError('control failed')), \
             patch.object(platform, '_finish') as finish, self.assertRaises(ValueError):
            platform.run_platform(self.root/'sequence-failure')
        finish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
