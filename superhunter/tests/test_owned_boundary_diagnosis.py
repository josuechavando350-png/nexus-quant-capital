"""Real own-copy interventions; mocks explicitly exercise infrastructure failures."""
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_boundary_diagnosis as diagnosis, quality
from superhunter.safe_io import canonical


class DiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name); cls.original = cls.root / 'original'
        cls.source = quality.sha(canonical(quality.source_snapshot()))
        cls.before = diagnosis.boundary.review(diagnosis.ROOT)
        cls.result = diagnosis.create(cls.original, source_digest=cls.source)
        cls.after = diagnosis.boundary.review(diagnosis.ROOT)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name); self.bundle = self.work / 'bundle'
        shutil.copytree(self.original, self.bundle)
        self.anchor = self.result['experiment_anchor']

    def observation(self): return json.loads((self.bundle / 'observation.json').read_bytes())

    def verify(self, **changes):
        return diagnosis.verify(self.bundle, **{'source_digest': self.source, 'experiment_anchor': self.anchor, **changes})

    def rewrite(self, name, value):
        raw = value if type(value) is bytes else canonical(value)
        (self.bundle / name).write_bytes(raw)
        manifest = json.loads((self.bundle / 'COMPLETE.json').read_bytes())
        manifest['sha256'][name] = quality.sha(raw)
        (self.bundle / 'COMPLETE.json').write_bytes(canonical(manifest))
        self.anchor = quality.sha((self.bundle / 'COMPLETE.json').read_bytes())

    def test_real_faults_repairs_and_same_error_different_causes(self):
        result = self.verify(); self.assertEqual(result, self.result)
        self.assertEqual(result['status'], 'OWNED_FAULT_DIAGNOSIS_CONFIRMED_IN_LAB')
        self.assertEqual([r['returncode'] for r in result['checks']], [0, 2, 0, 2, 0])
        self.assertEqual(self.before, self.after)
        self.assertEqual((self.bundle / 'trial-1.stdout').read_bytes(), (self.bundle / 'trial-3.stdout').read_bytes())
        self.assertEqual(result['hypotheses']['error_code_alone_identifies_missing_file'], 'REFUTED_IN_FIXED_LAB')
        self.assertEqual(result['hypotheses']['content_change_required_for_rejection'], 'REFUTED_IN_FIXED_LAB')

    def test_inventory_proves_only_fixed_copy_file_intervention(self):
        observation = self.observation()
        for index in (0, 2, 4): self.assertEqual(observation['trials'][index]['delta'], [])
        missing = observation['trials'][1]['delta']; changed = observation['trials'][3]['delta']
        self.assertEqual([r['path'] for r in missing], [diagnosis.FIXED_FILE])
        self.assertEqual([r['path'] for r in changed], [diagnosis.FIXED_FILE])
        self.assertIsNone(missing[0]['after'])
        self.assertEqual(changed[0]['before']['sha256'], changed[0]['after']['sha256'])
        self.assertEqual((changed[0]['before']['mode'], changed[0]['after']['mode']), ('100644', '100755'))

    def test_verifier_does_not_execute_or_modify_checkout(self):
        with (patch.object(diagnosis.owned_process, 'run', side_effect=AssertionError('must not run')),
              patch.object(diagnosis, '_intervene', side_effect=AssertionError('must not write'))):
            result = self.verify()
        self.assertTrue(all(v is False for v in result['limitations'].values()))

    def test_wrong_external_source_and_anchor_rejected(self):
        for name in ('source_digest', 'experiment_anchor'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.verify(**{name: '0' * 64})

    def test_original_anchor_rejects_rehashed_receipt(self):
        original = self.anchor; value = self.observation(); value['origin'] = 'different'
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_ANCHOR'): self.verify(experiment_anchor=original)

    def test_reordered_or_duplicate_trials_rejected(self):
        original = self.observation()
        for indices in ((0, 3, 2, 1, 4), (0, 1, 2, 1, 4)):
            value = copy.deepcopy(original); value['trials'] = [value['trials'][i] for i in indices]
            self.rewrite('observation.json', value)
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_TRIAL_ORDER'): self.verify()

    def test_false_intervention_or_extra_file_delta_rejected(self):
        original = self.observation()
        for changed in ([], [{'path': 'unrelated.py', 'before': None, 'after': None}]):
            value = copy.deepcopy(original); value['trials'][1]['delta'] = changed
            self.rewrite('observation.json', value)
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_INTERVENTION'): self.verify()

    def test_before_after_inventory_mismatch_rejected(self):
        value = self.observation(); value['trials'][2]['inventory_after_sha256'] = '0' * 64
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_INTERVENTION'): self.verify()

    def test_boolean_exit_and_budget_rejected(self):
        original = self.observation()
        for name in ('returncode', 'wall_budget_seconds'):
            value = copy.deepcopy(original); value['trials'][0][name] = False
            self.rewrite('observation.json', value)
            with self.assertRaises(ValueError): self.verify()

    def test_trial_clocks_cannot_overlap_or_change_elapsed(self):
        original = self.observation()
        value = copy.deepcopy(original)
        value['trials'][1]['clock'] = copy.deepcopy(value['trials'][0]['clock'])
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_CLOCK_ORDER'): self.verify()
        value = copy.deepcopy(original); value['trials'][0]['clock']['elapsed_ns'] += 1
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_CLOCK_ARITHMETIC'): self.verify()

    def test_cannot_hide_an_unexpected_result_with_later_repairs(self):
        value = self.observation(); value['trials'][1]['returncode'] = 0
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_CONTINUED_AFTER_FAILURE'): self.verify()

    def test_resealed_report_cannot_invent_hypotheses(self):
        result = json.loads((self.bundle / 'diagnosis.json').read_bytes())
        result['hypotheses']['error_code_alone_identifies_missing_file'] = 'SUPPORTED_IN_FIXED_LAB'
        self.rewrite('diagnosis.json', result)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_authentication_or_general_causation_cannot_be_promoted(self):
        original = self.observation()
        for key in ('independent_execution_authenticated', 'general_causation_proved', 'vulnerability_confirmed'):
            value = copy.deepcopy(original); value['limitations'][key] = True
            self.rewrite('observation.json', value)
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_LIMITATIONS'): self.verify()

    def test_missing_extra_and_symlink_streams_rejected(self):
        extra = self.bundle / 'extra'; extra.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_INVENTORY'): self.verify()
        extra.unlink(); stream = self.bundle / 'trial-1.stdout'; raw = stream.read_bytes(); stream.unlink()
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_INVENTORY'): self.verify()
        outside = self.work / 'outside'; outside.write_bytes(raw); stream.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)): self.verify()

    def test_unknown_or_duplicate_observation_fields_rejected(self):
        value = self.observation(); value['unknown'] = 1; self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_SCHEMA'): self.verify()
        self.rewrite('observation.json', b'{"trials":[],"trials":[]}')
        with self.assertRaises(ValueError): self.verify()

    def test_timeout_preserves_partial_evidence_without_promotion(self):
        out = self.work / 'timeout'
        def timeout(*args, **kwargs):
            kwargs['stdout'].write(b'partial output')
            raise subprocess.TimeoutExpired(['PRIVATE_COMMAND'], 30)
        with patch.object(diagnosis.owned_process, 'run', side_effect=timeout) as run:
            result = diagnosis.create(out, source_digest=self.source)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result['status'], 'OWNED_FAULT_DIAGNOSIS_INCONCLUSIVE')
        self.assertEqual((out / 'trial-0.stdout').read_bytes(), b'partial output')
        self.assertIsNone(result['checks'][0]['returncode']); self.assertTrue(result['checks'][0]['timed_out'])
        self.assertEqual(diagnosis.verify(out, source_digest=self.source, experiment_anchor=result['experiment_anchor']), result)

    def test_nonzero_unexpected_process_preserves_private_stderr(self):
        out = self.work / 'failed'
        def failed(*args, **kwargs):
            kwargs['stderr'].write(b'SYNTHETIC_PRIVATE_STDERR')
            return SimpleNamespace(returncode=1)
        with patch.object(diagnosis.owned_process, 'run', side_effect=failed):
            result = diagnosis.create(out, source_digest=self.source)
        self.assertEqual(result['status'], 'OWNED_FAULT_DIAGNOSIS_INCONCLUSIVE')
        self.assertEqual((out / 'trial-0.stderr').read_bytes(), b'SYNTHETIC_PRIVATE_STDERR')
        self.assertNotIn('SYNTHETIC_PRIVATE_STDERR', (out / 'REVIEW.md').read_text())
        self.assertEqual(diagnosis.verify(out, source_digest=self.source, experiment_anchor=result['experiment_anchor']), result)

    def test_cli_keeps_nonzero_for_verified_inconclusive(self):
        out = self.work / 'inconclusive'; stream = io.StringIO()
        with patch.object(diagnosis.owned_process, 'run', return_value=SimpleNamespace(returncode=7)), redirect_stdout(stream):
            code = diagnosis.main(['diagnose-owned-boundary', '--source-digest', self.source, '--out', str(out)])
        self.assertEqual(code, 1); response = json.loads(stream.getvalue())
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = diagnosis.main(['verify-owned-boundary-diagnosis', '--source-digest', self.source,
                '--bundle', str(out), '--experiment-anchor', response['experiment_anchor']])
        self.assertEqual(code, 1); self.assertEqual(json.loads(stream.getvalue())['trials_observed'], 1)

    def test_existing_root_and_symlinked_output_rejected_before_launch(self):
        link = self.work / 'link'; link.symlink_to(self.root, target_is_directory=True)
        for out in (self.bundle, diagnosis.ROOT / 'new', link / 'new'):
            with self.subTest(out=out), patch.object(diagnosis.owned_process, 'run') as run:
                with self.assertRaises(ValueError): diagnosis.create(out, source_digest=self.source)
                run.assert_not_called()

    def test_copy_mutation_during_worker_rejected(self):
        original = diagnosis.owned_process.run
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            path = Path(kwargs['cwd']) / 'owned-checkout/superhunter/README.md'
            path.write_bytes(path.read_bytes() + b'changed copy only')
            return result
        with patch.object(diagnosis.owned_process, 'run', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_COPY_CHANGED'):
                diagnosis.create(self.work / 'changed', source_digest=self.source)
        self.assertEqual(self.before, diagnosis.boundary.review(diagnosis.ROOT))

    def test_output_budget_rejected_without_positive_bundle(self):
        out = self.work / 'oversized'
        def oversized(*args, **kwargs):
            kwargs['stdout'].write(b'x' * (diagnosis.capture.OUTPUT_BYTES + 1))
            return SimpleNamespace(returncode=0)
        with patch.object(diagnosis.owned_process, 'run', side_effect=oversized):
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_OUTPUT_BUDGET'):
                diagnosis.create(out, source_digest=self.source)
        self.assertFalse(out.exists())

    def test_original_source_change_aborts_before_publishing(self):
        original = quality.source_snapshot(); changed = {**original, 'owned_boundary_diagnosis.py': '0' * 64}
        with patch.object(quality, 'source_snapshot', side_effect=[original, changed]), \
             patch.object(diagnosis.owned_process, 'run', return_value=SimpleNamespace(returncode=9)):
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_ORIGINAL_CHANGED'):
                diagnosis.create(self.work / 'changed', source_digest=self.source)

    def test_reader_rechecks_evidence_after_analysis(self):
        original = diagnosis._read; calls = 0
        def changed(root):
            nonlocal calls
            result = original(root); calls += 1
            if calls == 2: result['trial-0.stdout'] += b' '
            return result
        with patch.object(diagnosis, '_read', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_EVIDENCE_CHANGED'): self.verify()

    def test_cli_real_experiment_and_separate_verifier(self):
        command = [sys.executable, '-B', '-m', 'superhunter']; out = self.work / 'cli'
        first = subprocess.run(command + ['diagnose-owned-boundary', '--out', str(out), '--source-digest', self.source],
                               cwd=diagnosis.ROOT, capture_output=True, timeout=45)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        result = json.loads(first.stdout)
        second = subprocess.run(command + ['verify-owned-boundary-diagnosis', '--bundle', str(out), '--source-digest', self.source,
                                          '--experiment-anchor', result['experiment_anchor']],
                                cwd=diagnosis.ROOT, capture_output=True, timeout=45)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(json.loads(second.stdout)['trials_observed'], 5)


if __name__ == '__main__':
    unittest.main()
