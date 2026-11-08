"""Operational findings from real fixed lab trials; altered records are controls."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_boundary_diagnosis as diagnosis, quality
from superhunter.safe_io import canonical


class OwnedRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name); cls.original = cls.root / 'original'
        cls.digest = quality.sha(canonical(quality.source_snapshot()))
        cls.before = diagnosis.boundary.review(diagnosis.ROOT)
        cls.result = diagnosis.create(cls.original, source_digest=cls.digest)
        cls.after = diagnosis.boundary.review(diagnosis.ROOT)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root); self.addCleanup(temp.cleanup)
        self.work = Path(temp.name); self.bundle = self.work / 'bundle'
        shutil.copytree(self.original, self.bundle)
        self.anchor = self.result['experiment_anchor']

    def report(self):
        return json.loads((self.bundle / 'diagnosis.json').read_bytes())

    def observation(self):
        return json.loads((self.bundle / 'observation.json').read_bytes())

    def verify(self, **changes):
        return diagnosis.verify(self.bundle, **{'source_digest': self.digest, 'experiment_anchor': self.anchor, **changes})

    def rewrite(self, name, value):
        (self.bundle / name).write_bytes(value if type(value) is bytes else canonical(value))
        marker = {'schema_version': 1, 'sha256': {p.name: quality.sha(p.read_bytes())
                  for p in self.bundle.iterdir() if p.name != 'COMPLETE.json'}}
        (self.bundle / 'COMPLETE.json').write_bytes(canonical(marker))
        self.anchor = quality.sha((self.bundle / 'COMPLETE.json').read_bytes())

    def incomplete(self):
        # Preserve only the actual baseline observation. This is a deliberately
        # truncated test record, not an observed host interruption.
        observation = self.observation(); observation['trials'] = observation['trials'][:1]
        for number in range(1, 5):
            for stream in ('stdout', 'stderr'):
                (self.bundle / ('trial-%d.%s' % (number, stream))).unlink()
        files, _ = diagnosis.boundary._capture(diagnosis.ROOT)
        baseline = {**diagnosis.boundary.review(diagnosis.ROOT), 'ignored_python_cache_files': 0}
        raw = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        result = diagnosis.analyze(observation, raw, diagnosis.inventory(files), baseline, source_digest=self.digest)
        self.rewrite('observation.json', observation)
        self.rewrite('diagnosis.json', result)
        self.rewrite('REVIEW.md', diagnosis.render(result))

    def test_findings_are_derived_from_actual_fault_and_restoration(self):
        result = self.verify(); observation = self.observation()
        self.assertEqual(result['schema_version'], 2)
        self.assertEqual(result['profile'], 'owned-boundary-fault-repair-experiment-v2')
        self.assertEqual(self.before, self.after)
        self.assertEqual(len(result['operational_findings']), 2)
        for finding, number in zip(result['operational_findings'], (1, 3)):
            self.assertEqual(finding['observed_delta'], observation['trials'][number]['delta'])
            self.assertEqual([e['index'] for e in finding['evidence']], [0, number, number + 1])
            self.assertEqual([e['returncode'] for e in finding['evidence']], [0, 2, 0])
            for event in finding['evidence']:
                original = observation['trials'][event['index']]
                self.assertTrue(all(event[k] == original[k] for k in event))

    def test_mode_only_plan_preserves_original_content_reference(self):
        result = self.verify(); finding = result['operational_findings'][1]
        delta = finding['observed_delta'][0]
        self.assertEqual(delta['before']['sha256'], delta['after']['sha256'])
        action = result['remediation_plan'][1]
        self.assertEqual(action['operation'], 'RESTORE_REVIEWED_GIT_MODE')
        self.assertEqual(action['expected_after'], delta['before'])
        self.assertEqual(action['expected_after']['mode'], '100644')

    def test_missing_file_plan_has_exact_reviewed_reference(self):
        result = self.verify(); finding = result['operational_findings'][0]
        delta = finding['observed_delta'][0]
        self.assertIsNone(delta['after'])
        self.assertEqual(result['remediation_plan'][0]['operation'], 'RESTORE_REVIEWED_FILE_BYTES_AND_MODE')
        self.assertEqual(result['remediation_plan'][0]['expected_after'], delta['before'])

    def test_plans_require_fresh_preconditions_and_full_inventory_postcondition(self):
        result = self.verify()
        for action in result['remediation_plan']:
            self.assertFalse(action['execution_enabled']); self.assertFalse(action['live_preconditions_checked'])
            self.assertTrue(action['human_review_required'])
            self.assertEqual(action['scope'], 'FRESH_OWNED_LAB_COPY_ONLY')
            self.assertIn('RECONFIRM_SPECIFIC_DELTA', action['preconditions'])
            self.assertIn('UNRELATED_FILE_OR_MODE_CHANGES', action['stop_if'])
            self.assertEqual(action['postconditions']['full_inventory_sha256'], self.before['source_inventory_sha256'])
            self.assertTrue(action['postconditions']['no_unrelated_inventory_delta'])

    def test_incomplete_verified_diagnosis_has_no_findings_or_actions(self):
        self.incomplete(); result = self.verify()
        self.assertEqual(result['status'], 'OWNED_FAULT_DIAGNOSIS_INCONCLUSIVE')
        self.assertEqual(result['operational_findings'], [])
        self.assertEqual(result['remediation_plan'], [])
        self.assertIn('inconcluso', diagnosis.render(result).decode())

    def test_incomplete_cannot_borrow_completed_findings(self):
        complete = self.report(); self.incomplete(); value = self.report()
        value['operational_findings'] = complete['operational_findings']
        value['remediation_plan'] = complete['remediation_plan']
        self.rewrite('diagnosis.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_action_cannot_enable_execution(self):
        value = self.report(); value['remediation_plan'][0]['execution_enabled'] = True
        self.rewrite('diagnosis.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_action_cannot_change_subject(self):
        value = self.report(); value['remediation_plan'][0]['relative_path'] = 'unrelated-file'
        self.rewrite('diagnosis.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_plan_cannot_change_expected_bytes_or_mode(self):
        initial = self.report()
        for field, replacement in [('sha256', '0'*64), ('mode', '100755')]:
            value = copy.deepcopy(initial); value['remediation_plan'][0]['expected_after'][field] = replacement
            self.rewrite('diagnosis.json', value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_findings_cannot_promote_incident_or_security_severity(self):
        initial = self.report()
        for name, replacement in [('vulnerability_confirmed', True), ('incident_confirmed', True), ('security_severity', 'critical')]:
            value = copy.deepcopy(initial); value['operational_findings'][0][name] = replacement
            self.rewrite('diagnosis.json', value)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_report_cannot_claim_current_state_or_human_approval(self):
        initial = self.report()
        for name in ('remediation_execution_enabled', 'current_target_state_checked', 'human_approval_recorded'):
            value = copy.deepcopy(initial); value[name] = True; self.rewrite('diagnosis.json', value)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_plan_cannot_drop_stops_or_postconditions(self):
        initial = self.report()
        for name in ('preconditions', 'postconditions', 'stop_if'):
            value = copy.deepcopy(initial); del value['remediation_plan'][0][name]
            self.rewrite('diagnosis.json', value)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_resealed_finding_cannot_swap_fault_evidence(self):
        value = self.report()
        value['operational_findings'][0]['evidence'] = value['operational_findings'][1]['evidence']
        self.rewrite('diagnosis.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_rendered_plan_is_rederived_and_tampering_rejected(self):
        text = (self.bundle / 'REVIEW.md').read_bytes()
        self.assertIn(b'RESTORE_REVIEWED_GIT_MODE', text)
        self.rewrite('REVIEW.md', text + b'Run an unreviewed repair now.\n')
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_REPORT'): self.verify()

    def test_verification_does_not_run_repairs_or_repeat_trials(self):
        with (patch.object(diagnosis.owned_process, 'run', side_effect=AssertionError('execution')),
              patch.object(diagnosis, '_intervene', side_effect=AssertionError('repair'))):
            result = self.verify()
        self.assertFalse(result['remediation_execution_enabled'])
        self.assertEqual(diagnosis.boundary.review(diagnosis.ROOT), self.before)

    def test_v1_receipt_is_not_silently_relabelled(self):
        value = self.observation(); value['schema_version'] = 1
        value['profile'] = 'owned-boundary-fault-repair-experiment-v1'
        self.rewrite('observation.json', value)
        with self.assertRaisesRegex(ValueError, 'DIAGNOSIS_ORIGIN'): self.verify()

    def test_cli_reports_counts_without_private_paths_or_identity(self):
        process = subprocess.run([sys.executable, '-B', '-m', 'superhunter', 'verify-owned-boundary-diagnosis',
            '--bundle', str(self.bundle), '--source-digest', self.digest, '--experiment-anchor', self.anchor],
            cwd=quality.ROOT.parent, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['operational_findings'], 2); self.assertEqual(result['remediation_actions'], 2)
        self.assertFalse(result['remediation_execution_enabled'])
        self.assertNotIn(str(self.bundle).encode(), process.stdout)
        self.assertNotIn(self.result['experiment_id'].encode(), process.stdout)

    def test_cli_incomplete_preserves_exit_one_and_zero_actions(self):
        self.incomplete()
        process = subprocess.run([sys.executable, '-B', '-m', 'superhunter', 'verify-owned-boundary-diagnosis',
            '--bundle', str(self.bundle), '--source-digest', self.digest, '--experiment-anchor', self.anchor],
            cwd=quality.ROOT.parent, capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 1, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['operational_findings'], 0); self.assertEqual(result['remediation_actions'], 0)
