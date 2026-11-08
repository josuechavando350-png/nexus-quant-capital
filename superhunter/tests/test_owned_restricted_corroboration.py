"""Real own inputs plus explicitly declared altered/truncated evidence controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_restricted_corroboration as joint
from superhunter import owned_boundary_diagnosis as diagnosis, owned_restricted_review as restricted, quality
from superhunter.safe_io import canonical

ROOT = Path(__file__).resolve().parents[2]


class RestrictedCorroborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix='own-corroboration-')
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        cls.source = quality.sha(canonical(quality.source_snapshot()))
        cls.standard, cls.native = cls.root/'standard', cls.root/'restricted'
        cls.standard_result = diagnosis.create(cls.standard, source_digest=cls.source)
        cls.native_result = restricted.create(cls.native, source_digest=cls.source)
        if cls.standard_result['status'] != 'OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB' or cls.native_result['status'] != 'OWNED_RESTRICTED_LAB_PASS':
            raise AssertionError('actual own control acquisition failed')
        cls.context = {'source_digest':cls.source, 'diagnosis_anchor':cls.standard_result['experiment_anchor'],
                       'restricted_anchor':cls.native_result['experiment_anchor']}
        cls.args = {'diagnosis_bundle':cls.standard, 'restricted_bundle':cls.native, **cls.context}
        cls.bundle = cls.root/'joint'
        cls.made = joint.create(cls.bundle, **cls.args)
        cls.raw_standard = diagnosis._read(cls.standard)
        cls.raw_native = diagnosis._read(cls.native)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='own-corroboration-control-')
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)

    def reseal(self, root):
        marker = canonical({'schema_version':1,'sha256':{
            p.name:quality.sha(p.read_bytes()) for p in root.iterdir() if p.name != 'COMPLETE.json'}})
        (root/'COMPLETE.json').write_bytes(marker)
        return quality.sha(marker)

    def altered(self, source, name):
        target = self.work/name
        shutil.copytree(source,target)
        return target

    def verify(self, **changes):
        return joint.verify(**{'bundle':self.bundle, 'corroboration_anchor':self.made['corroboration_anchor'],
                               **self.args, **changes})

    def test_actual_ten_trials_bind_two_existing_findings_and_plans(self):
        checked = self.verify()
        self.assertEqual(checked,self.made)
        self.assertEqual(checked['status'],'OWNED_CORROBORATION_MATCH')
        self.assertEqual(checked['paired_trials_observed'],5)
        self.assertTrue(all(row['equivalent_review_outcome_and_inventory'] for row in checked['pairs']))
        self.assertEqual([row['raw_boundary_results_equal'] for row in checked['pairs']], [True,False,True,False,True])
        self.assertEqual([row['comparison_rule'] for row in checked['pairs']],
                         ['EXACT_BASELINE_BYTES','FIXED_REJECTION_REASON_WITH_PROFILE_LABELS',
                          'EXACT_BASELINE_BYTES','FIXED_REJECTION_REASON_WITH_PROFILE_LABELS','EXACT_BASELINE_BYTES'])
        self.assertEqual([r['existing_finding_id'] for r in checked['existing_findings_corroborated']],
                         ['missing-fixed-manifest','changed-fixed-mode'])
        for linked,finding,plan in zip(checked['existing_findings_corroborated'],
                                      self.standard_result['operational_findings'],self.standard_result['remediation_plan']):
            self.assertEqual(linked['existing_finding_sha256'],quality.sha(canonical(finding)))
            self.assertEqual(linked['existing_plan_sha256'],quality.sha(canonical(plan)))
            self.assertFalse(linked['new_finding_created'])
        self.assertEqual(checked['limitations']['new_findings_created'],0)
        self.assertEqual(diagnosis._read(self.standard),self.raw_standard)
        self.assertEqual(diagnosis._read(self.native),self.raw_native)

    def test_create_and_verify_never_launch_a_process(self):
        with patch('subprocess.Popen',side_effect=AssertionError('read-only consumer')):
            made = joint.create(self.work/'out',**self.args)
            checked = joint.verify(self.work/'out',corroboration_anchor=made['corroboration_anchor'],**self.args)
        self.assertEqual(made,checked)

    def test_real_extra_descriptor_failure_cannot_corroborate_existing_findings(self):
        original = restricted.owned_process.run
        def inherited(command,**options):
            descriptor = os.open(options['cwd']/'owned-compute-control',os.O_RDONLY)
            try:return original(command,**options,pass_fds=(descriptor,))
            finally:os.close(descriptor)
        native = self.work/'actual-extra-descriptor'
        with patch.object(restricted.owned_process,'run',inherited):
            failed = restricted.create(native,source_digest=self.source)
        result = joint.create(self.work/'out',**{**self.args,'restricted_bundle':native,
                              'restricted_anchor':failed['experiment_anchor']})
        self.assertEqual(result['status'],'OWNED_CORROBORATION_INCONCLUSIVE')
        self.assertEqual(result['paired_trials_observed'],1)
        self.assertEqual(result['existing_findings_corroborated'],[])
        self.assertEqual(result['limitations']['new_findings_created'],0)

    def test_declared_truncated_diagnosis_is_inconclusive_even_with_complete_native(self):
        altered = self.altered(self.standard,'declared-truncation')
        observed = json.loads((altered/'observation.json').read_bytes())
        observed['trials'] = observed['trials'][:1]
        for index in range(1,5):
            for stream in ('stdout','stderr'):(altered/f'trial-{index}.{stream}').unlink()
        files,_ = diagnosis.boundary._capture(ROOT)
        baseline = {**diagnosis.boundary.review(ROOT),'ignored_python_cache_files':0}
        result = diagnosis.analyze(observed,{p.name:p.read_bytes() for p in altered.iterdir()},
                                   diagnosis.inventory(files),baseline,source_digest=self.source)
        (altered/'observation.json').write_bytes(canonical(observed))
        (altered/'diagnosis.json').write_bytes(canonical(result))
        (altered/'REVIEW.md').write_bytes(diagnosis.render(result))
        result = joint.compare(**{**self.args,'diagnosis_bundle':altered,'diagnosis_anchor':self.reseal(altered)})
        self.assertEqual(result['status'],'OWNED_CORROBORATION_INCONCLUSIVE')
        self.assertEqual(result['existing_findings_corroborated'],[])

    def test_duplicate_experiment_identity_is_rejected_after_native_reverification(self):
        altered = self.altered(self.native,'declared-duplicate-identity')
        observation = json.loads((altered/'observation.json').read_bytes())
        observation['experiment_id'] = self.standard_result['experiment_id']
        report = json.loads((altered/'diagnosis.json').read_bytes())
        report['experiment_id'] = observation['experiment_id']
        (altered/'observation.json').write_bytes(canonical(observation))
        (altered/'diagnosis.json').write_bytes(canonical(report))
        (altered/'REVIEW.md').write_bytes(restricted.render(report))
        anchor = self.reseal(altered)
        self.assertEqual(restricted.verify(altered,source_digest=self.source,experiment_anchor=anchor)['status'],
                         'OWNED_RESTRICTED_LAB_PASS')
        with self.assertRaisesRegex(ValueError,'CORROBORATION_DUPLICATE_EXPERIMENT_ID'):
            joint.compare(**{**self.args,'restricted_bundle':altered,'restricted_anchor':anchor})

    def test_wrong_source_or_either_input_anchor_is_rejected(self):
        for key in ('source_digest','diagnosis_anchor','restricted_anchor'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                joint.compare(**{**self.args,key:'0'*64})

    def test_arbitrary_rejection_label_cannot_borrow_a_matching_reason(self):
        changed = self.altered(self.native,'wrong-rejection-label')
        worker = json.loads((changed/'trial-1.stdout').read_bytes())
        worker['boundary_result']['status'] = 'OWNED_BOUNDARY_TRIAL_REJECTED'
        raw = canonical(worker);(changed/'trial-1.stdout').write_bytes(raw)
        observation = json.loads((changed/'observation.json').read_bytes())
        observation['trials'][1].update(stdout_sha256=quality.sha(raw),stdout_bytes=len(raw))
        (changed/'observation.json').write_bytes(canonical(observation))
        with self.assertRaises(ValueError):
            joint.compare(**{**self.args,'restricted_bundle':changed,'restricted_anchor':self.reseal(changed)})

    def test_identical_anchors_and_swapped_profiles_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'CORROBORATION_DISTINCT_ANCHORS'):
            joint.compare(**{**self.args,'restricted_anchor':self.context['diagnosis_anchor']})
        with self.assertRaises(ValueError):
            joint.compare(self.native,self.standard,source_digest=self.source,
                          diagnosis_anchor=self.context['restricted_anchor'],restricted_anchor=self.context['diagnosis_anchor'])

    def test_input_mutation_after_its_verification_prevents_publication(self):
        changed = self.altered(self.standard,'changed-during-read')
        original = joint._input
        def alter_after(module,path,source,anchor):
            result = original(module,path,source,anchor)
            if path == changed:
                with (changed/'trial-0.stdout').open('ab') as stream:stream.write(b' ')
            return result
        out = self.work/'unpublished'
        with patch.object(joint,'_input',alter_after), self.assertRaises(ValueError):
            joint.create(out,**{**self.args,'diagnosis_bundle':changed})
        self.assertFalse(out.exists())

    def test_resealed_report_cannot_promote_guarantees_or_finding_count(self):
        mutations = (
            lambda r:r['limitations'].update(independent_execution_authenticated=True),
            lambda r:r['limitations'].update(new_findings_created=2),
            lambda r:r.update(clock_domain_authenticated=True),
            lambda r:r['existing_findings_corroborated'].pop(),
            lambda r:r['pairs'][0].update(filter_proof_sha256='0'*64))
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                changed = self.altered(self.bundle,'changed-report-'+str(index))
                value = json.loads((changed/'comparison.json').read_bytes());mutate(value)
                (changed/'comparison.json').write_bytes(canonical(value))
                with self.assertRaisesRegex(ValueError,'CORROBORATION_REPORT'):
                    self.verify(bundle=changed,corroboration_anchor=self.reseal(changed))

    def test_input_context_cannot_be_reassigned_after_resealing(self):
        changed = self.altered(self.bundle,'changed-context')
        value = json.loads((changed/'inputs.json').read_bytes());value['diagnosis_anchor']='0'*64
        (changed/'inputs.json').write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError,'CORROBORATION_CONTEXT'):
            self.verify(bundle=changed,corroboration_anchor=self.reseal(changed))

    def test_overlap_missing_inputs_and_symlink_inputs_are_rejected(self):
        with self.assertRaises(ValueError):joint.create(self.standard/'nested',**self.args)
        with self.assertRaises((ValueError,OSError)):self.verify(restricted_bundle=self.work/'absent')
        link = self.work/'alias';link.symlink_to(self.native,target_is_directory=True)
        with self.assertRaises(ValueError):self.verify(restricted_bundle=link)
        self.assertEqual(diagnosis._read(self.standard),self.raw_standard)

    def test_unexpected_file_and_changed_review_text_are_rejected(self):
        extra = self.altered(self.bundle,'extra');(extra/'unexpected').write_bytes(b'declared control')
        with self.assertRaisesRegex(ValueError,'CORROBORATION_INVENTORY'):self.verify(bundle=extra)
        changed = self.altered(self.bundle,'changed-text');(changed/'REVIEW.md').write_bytes(b'unsupported claim')
        with self.assertRaisesRegex(ValueError,'CORROBORATION_REPORT'):
            self.verify(bundle=changed,corroboration_anchor=self.reseal(changed))

    def test_separate_cli_verification_and_private_failure_diagnostics(self):
        arguments = ['verify-owned-restricted-corroboration','--bundle',str(self.bundle),
                     '--corroboration-anchor',self.made['corroboration_anchor']]
        for key,value in self.args.items():arguments.extend(['--'+key.replace('_','-'),str(value)])
        result = subprocess.run([sys.executable,'-B','-m','superhunter',*arguments],cwd=ROOT,
            capture_output=True,timeout=30,env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        self.assertEqual((result.returncode,result.stderr),(0,b''))
        self.assertEqual(json.loads(result.stdout)['existing_findings_corroborated'],2)
        self.assertNotIn(str(self.root).encode(),result.stdout)
        bad = arguments.copy();bad[bad.index('--corroboration-anchor')+1]='0'*64
        result = subprocess.run([sys.executable,'-B','-m','superhunter',*bad],cwd=ROOT,
            capture_output=True,timeout=30,env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        self.assertEqual((result.returncode,result.stderr),(2,b''))
        self.assertNotIn(str(self.root).encode(),result.stdout)

    def test_reported_intervals_do_not_authenticate_host_or_clock(self):
        result = self.verify()
        self.assertEqual([r['experiment_id'] for r in result['reported_intervals']],
                         [self.standard_result['experiment_id'],self.native_result['experiment_id']])
        self.assertFalse(result['clock_domain_authenticated'])
        self.assertFalse(result['causal_independence_proved'])
        self.assertFalse(result['limitations']['independent_host_proved'])


if __name__ == '__main__':
    unittest.main()
