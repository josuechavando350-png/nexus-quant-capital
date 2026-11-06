"""Regressions for combining the existing local defensive branches.

Synthetic package receipts below test reconciliation only; release evidence is
produced by running the actual complete suite in a separate worker.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import shutil
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from superhunter import platform, project_context, quality, review
from superhunter.safe_io import canonical, strict_json
import test_platform as fixtures

CANARY = 'SYNTHETIC_NOT_A_REAL_SECRET_RECONCILIATION'


class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PlatformTests.setUpClass()

    def setUp(self):
        self.fixture = fixtures.PlatformTests('test_full_review_roundtrip')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.bundle
        self.root = self.fixture.root

    def test_checklists_share_status_and_evidence(self):
        plan = platform.integration_plan()
        projection = review.milestones()
        self.assertEqual(projection, project_context.milestone_projection(plan))
        self.assertEqual(sum(x['status'] == 'PARTIAL' for x in projection['items']), 3)
        for original, legacy in zip(plan['items'], projection['items']):
            self.assertEqual(original['required_tests'], legacy['tests'])
            self.assertEqual(original['scope'], legacy['boundary'])

    def test_every_prior_test_identity_is_retained(self):
        origin = strict_json((platform.ROOT/'reconciliation-origins.json').read_bytes())
        actual = set(platform._test_inventory())
        self.assertGreaterEqual(len(origin['test_ids']), 364)
        self.assertTrue(set(origin['test_ids']) <= actual)
        self.assertEqual(set(origin['inputs']), {'pr35','pr37','privacy_regression'})

    def test_quality_registers_every_runtime_module(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        self.assertIn('context', quality.COMPONENTS)
        self.assertIn('review', quality.COMPONENTS['platform']['depends'])
        self.assertIn('regression', quality.COMPONENTS['platform']['depends'])
        self.assertIn('privacy', quality.COMPONENTS['platform']['depends'])

    def test_both_policies_in_source_identity(self):
        snapshot = quality.source_snapshot()
        for name in ('integration-checklist.json','integration_milestones.json','reconciliation-origins.json'):
            self.assertIn(name,snapshot)

    def test_legacy_status_cannot_drift(self):
        plan=platform.integration_plan();legacy=review.milestones()
        legacy['items'][21]['status']='PENDING'
        with self.assertRaisesRegex(ValueError,'checklists disagree'):
            project_context.verify_projection(plan,legacy)

    def test_legacy_evidence_cannot_be_removed(self):
        plan=platform.integration_plan();legacy=review.milestones()
        legacy['items'][0]['tests']=[]
        with self.assertRaises(ValueError):project_context.verify_projection(plan,legacy)

    def test_projection_rejects_boolean_ids(self):
        plan=platform.integration_plan();plan['items'][0]['id']=True
        with self.assertRaises(ValueError):project_context.milestone_projection(plan)

    def test_projection_rejects_missing_requirement(self):
        plan=platform.integration_plan();plan['items'].pop()
        with self.assertRaises(ValueError):project_context.milestone_projection(plan)

    def test_projection_requires_evidence_for_partial_work(self):
        plan=platform.integration_plan();plan['items'][21]['required_tests']=[]
        with self.assertRaises(ValueError):project_context.milestone_projection(plan)

    def test_two_report_formats_agree_on_current_state(self):
        unified=platform.collect(self.bundle)
        native=review.create_review(self.bundle/'qa',self.bundle/'lab',self.bundle/'fuzz',self.fixture.root/'portable')
        self.assertEqual(unified['stages']['qa']['source_digest'],native['source_digest'])
        self.assertEqual(unified['stages']['qa']['tests_run'],native['unit_tests'])
        self.assertEqual(native['milestones'],{'bounded':12,'partial':3,'pending':12})
        self.assertFalse(native['production_certified'])
        self.assertFalse(unified['platform_complete'])

    def test_html_and_redaction_metadata_are_bound(self):
        platform._finish(self.bundle)
        self.assertTrue((self.bundle/'review/index.html').is_file())
        meta=strict_json((self.bundle/'review/redaction.json').read_bytes())
        self.assertTrue(meta['manual_review_required'])
        self.assertTrue(meta['source_evidence_unchanged'])
        self.fixture.reseal('review','redaction.json',lambda d:d.update(manual_review_required=False))
        with self.assertRaises(ValueError):platform.verify_platform(self.bundle)

    def test_display_redaction_preserves_original_record(self):
        result=platform.collect(self.bundle)
        original=deepcopy(result)
        result['integration']['items'][0]['scope']='password='+CANARY
        before=canonical(result)
        docs=platform._documents(result)
        for name in ('INTEGRATION.md','index.html'):
            self.assertNotIn(CANARY.encode(),docs[name])
        self.assertEqual(canonical(result),before)
        self.assertIn(CANARY.encode(),docs['review.json'])  # private raw evidence is not a public export
        self.assertNotEqual(original,result)

    def test_public_diagnostics_hide_arguments(self):
        for command in ('review-platform','verify-platform','review','verify-review'):
            with self.subTest(command=command):
                proc=subprocess.run([sys.executable,'-B','-m','superhunter',command,'--unknown','password='+CANARY],
                                    cwd=platform.ROOT.parent,capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,2)
                self.assertNotIn(CANARY,proc.stdout+proc.stderr)

    def test_regression_and_review_commands_remain_reachable(self):
        for command in ('compare-checks','verify-comparison','review','review-platform'):
            with self.subTest(command=command):
                proc=subprocess.run([sys.executable,'-B','-m','superhunter',command,'--help'],
                                    cwd=platform.ROOT.parent,capture_output=True,text=True,timeout=10)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)

    def test_collection_rejects_legacy_projection_drift(self):
        real=platform.read_artifact
        def altered(root,name):
            raw=real(root,name)
            if name=='integration_milestones.json':
                value=strict_json(raw);value['items'][0]['boundary']='drift';return canonical(value)
            return raw
        with patch.object(platform,'read_artifact',side_effect=altered),self.assertRaisesRegex(ValueError,'checklists disagree'):
            platform.collect(self.bundle)

    def test_reconciled_validation_does_not_certify_capabilities(self):
        result=platform.collect(self.bundle)
        self.assertFalse(result['platform_complete'])
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertEqual(result['capabilities']['counts'],{'PARTIAL':9,'PLANNED':24,'REDESIGN_REQUIRED':17})
        self.assertFalse(any(x['status']=='COMPLETE' for x in result['capabilities']['items']))


    def test_registry_projection_has_no_drift(self):
        canonical_plan = platform.integration_plan()
        projection = review.milestones()
        self.assertEqual(projection, project_context.milestone_projection(canonical_plan))
        for item, legacy in zip(canonical_plan['items'], projection['items']):
            self.assertEqual(legacy['id'], f"B{item['id']:02d}")
            self.assertEqual(legacy['tests'], item['required_tests'])
            self.assertEqual(legacy['boundary'], item['scope'])
        self.assertEqual([i['id'] for i in canonical_plan['items'] if i['status']=='PARTIAL'], [22,25,27])

    def test_old_acceptance_requirements_from_both_branches_retained(self):
        items = platform.integration_plan()['items']
        self.assertIn('test_quality.QualityTests.test_missing_runtime_file_detected', items[0]['required_tests'])
        self.assertIn('test_integration.IntegrationTests.test_cli_export_then_import', items[0]['required_tests'])
        tests = project_context.test_inventory(quality.ROOT)
        for prefix, minimum in [('test_review.',27),('test_platform.',35),('test_privacy.',36)]:
            with self.subTest(suite=prefix):
                self.assertGreaterEqual(sum(i.startswith(prefix) for i in tests), minimum)

    def test_divergent_milestone_status_blocks_review(self):
        incompatible = review.milestones()
        incompatible['items'][21]['status']='PENDING'
        incompatible['items'][21]['tests']=[]
        real = review.read_artifact
        def changed(root, name):
            return canonical(incompatible) if name == 'integration_milestones.json' else real(root, name)
        with patch('superhunter.review.read_artifact',side_effect=changed), self.assertRaisesRegex(ValueError,'canonical integration'):
            review.milestones()

    def test_boolean_id_not_equal_to_first_requirement(self):
        plan = platform.integration_plan()
        plan['items'][0]['id']=True
        with patch('superhunter.platform.read_artifact',return_value=canonical(plan)), self.assertRaisesRegex(ValueError,'order/group'):
            platform.integration_plan()

    def test_review_requires_full_current_inventory(self):
        receipt = self.fixture.receipt
        selected = next(t for t in receipt['discovered'] if t not in quality.REQUIRED_TESTS and
                        t not in {n for i in review.milestones()['items'] for n in i['tests']})
        receipt['discovered'].remove(selected)
        receipt['tests']=[t for t in receipt['tests'] if t['id'] != selected]
        receipt['tests_run']-=1
        shutil.rmtree(self.bundle/'qa');self.fixture.make_qa()
        with self.assertRaisesRegex(ValueError,'complete current test inventory'):
            review.create_review(self.bundle/'qa',self.bundle/'lab',self.bundle/'fuzz',self.root/'incomplete')
        self.assertFalse((self.root/'incomplete').exists())

    def test_one_workflow_emits_both_report_modes_with_same_facts(self):
        result = platform._finish(self.bundle)
        portable = review.verify_review(self.bundle/'publication')
        self.assertEqual(portable['source_digest'],result['source_digest'])
        self.assertEqual(portable['unit_tests'],result['stages']['qa']['tests_run'])
        self.assertEqual(portable['milestones'],{'bounded':12,'partial':3,'pending':12})
        self.assertEqual(portable['capabilities'],result['capabilities']['counts'])
        self.assertTrue((self.bundle/'publication/index.html').is_file())
        self.assertFalse(result['platform_complete'])
        self.assertFalse(portable['vulnerability_confirmed'])

    def test_missing_publication_is_incomplete_not_pass(self):
        platform._finish(self.bundle)
        shutil.rmtree(self.bundle/'publication')
        with self.assertRaisesRegex(ValueError,'missing platform stages'):
            platform.verify_platform(self.bundle)

    def test_packaging_failure_cannot_leave_verifiable_success(self):
        with patch.object(review,'create_review',side_effect=OSError('synthetic failure')),self.assertRaises(OSError):
            platform._finish(self.bundle)
        with self.assertRaisesRegex(ValueError,'missing platform stages'):
            platform.verify_platform(self.bundle)

    def test_resealed_portable_report_not_accepted_by_combined_verifier(self):
        platform._finish(self.bundle)
        self.fixture.reseal('publication','review.json',lambda v:v.update(unit_tests=99999))
        with self.assertRaisesRegex(ValueError,'recomputed facts'):
            platform.verify_platform(self.bundle)

    def test_portable_package_does_not_depend_on_source_evidence_directories(self):
        platform._finish(self.bundle)
        portable = self.bundle/'publication'
        for sub in ('qa','lab','fuzz','review'):shutil.rmtree(self.bundle/sub)
        self.assertEqual(review.verify_review(portable)['status'],'LOCAL_REVIEW_PASS')
        with self.assertRaises(ValueError):platform.verify_platform(self.bundle)

    def test_qa_log_original_is_not_silently_rewritten_by_packager(self):
        qa=self.bundle/'qa'
        raw=f'UNIT FIXTURE ONLY; password={CANARY}\n'.encode()
        (qa/'tests.log').write_bytes(raw)
        marker=strict_json((qa/'COMPLETE.json').read_bytes())
        marker['sha256']['tests.log']=hashlib.sha256(raw).hexdigest()
        (qa/'COMPLETE.json').write_bytes(canonical(marker))
        platform._finish(self.bundle)
        self.assertEqual((qa/'tests.log').read_bytes(), raw)
        self.assertEqual((self.bundle/'publication/qa--tests.log').read_bytes(), raw)
        human=(self.bundle/'publication/REVIEW.md').read_text()
        self.assertNotIn(CANARY,human)
        self.assertIn('incluye evidencias originales',human)
        self.assertNotIn(CANARY,(self.bundle/'publication/index.html').read_text())

    def test_report_redacts_recognizable_sensitive_text_not_raw_facts(self):
        platform._finish(self.bundle)
        facts=review.verify_review(self.bundle/'publication')
        plan=review.milestones();caps=quality.catalog()
        plan['items'][0]['boundary']=f'password={CANARY}'
        text=review.render_markdown(facts,plan,caps)
        self.assertNotIn(CANARY,text)
        self.assertIn(CANARY,plan['items'][0]['boundary'])
        self.assertNotIn(CANARY.encode(),review.render_html(f'password={CANARY}'))

    def test_all_command_argument_errors_hide_sensitive_values(self):
        for command in ('review','verify-review','review-platform','verify-platform','fuzz-lab','verify-fuzz'):
            with self.subTest(command=command):
                p=subprocess.run([sys.executable,'-B','-m','superhunter',command,'--unknown',CANARY],
                                 cwd=quality.ROOT.parent,capture_output=True,text=True,timeout=10)
                self.assertNotEqual(p.returncode,0)
                self.assertNotIn(CANARY,p.stdout+p.stderr)

    def test_privacy_connected_to_both_review_components(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])
        for component in ('transport','quality','platform','review'):
            self.assertIn('privacy',quality.COMPONENTS[component]['depends'])
        item=quality.catalog()['items'][28]
        self.assertEqual(item['status'],'PARTIAL')
        self.assertIn('privacy',item['components'])

    def test_both_registry_inputs_are_in_source_identity(self):
        snapshot=quality.source_snapshot()
        self.assertIn('integration-checklist.json',snapshot)
        self.assertIn('integration_milestones.json',snapshot)
        self.assertIn('capabilities.json',snapshot)

    def test_changes_in_same_version_source_during_portable_verification_rejected(self):
        platform._finish(self.bundle)
        old=quality.source_snapshot;count=0
        def changed():
            nonlocal count
            count+=1
            return old() if count<=2 else {**old(),'changed.py':'0'*64}
        with patch.object(quality,'source_snapshot',side_effect=changed),self.assertRaisesRegex(ValueError,'source changed'):
            review.verify_review(self.bundle/'publication')

    def test_combined_report_does_not_claim_perfect_guardian(self):
        result=platform._finish(self.bundle)
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertFalse(result['independently_authenticated'])
        self.assertEqual(len(result['integration']['items']),27)
        self.assertEqual(len(result['capabilities']['items']),50)
        self.assertEqual(result['capabilities']['counts'],{'PLANNED':24,'PARTIAL':9,'REDESIGN_REQUIRED':17})

    def test_private_report_keeps_cli_outputs_minimal(self):
        platform._finish(self.bundle)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(platform.main(['verify-platform','--bundle',str(self.bundle)]),0)
        result=json.loads(output.getvalue())
        self.assertNotIn('draft',result)
        self.assertNotIn('review',result)
        self.assertFalse(result['platform_complete'])

if __name__=='__main__':
    unittest.main()
