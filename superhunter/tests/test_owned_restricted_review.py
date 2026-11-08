"""Actual own restricted acquisition, then separately declared evidence controls."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import (owned_restricted_review as restricted, owned_compute_guard as guard,
                         owned_boundary_diagnosis as lab, quality, repository_boundary as boundary)
from superhunter.safe_io import canonical

ROOT = Path(__file__).resolve().parents[2]


class RestrictedReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.bundle = cls.base/'actual'
        cls.source = quality.sha(canonical(quality.source_snapshot()))
        cls.made = restricted.create(cls.bundle, source_digest=cls.source)
        if cls.made['status'] != 'OWNED_RESTRICTED_LAB_PASS':
            raise AssertionError('actual restricted worker did not pass')
        cls.raw = lab._read(cls.bundle)
        cls.observation = json.loads(cls.raw['observation.json'])
        files, _ = boundary._capture(ROOT)
        cls.original = lab.inventory(files)
        cls.baseline = {**boundary.review(ROOT), 'ignored_python_cache_files': 0}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.observed = copy.deepcopy(self.observation)
        self.streams = dict(self.raw)

    def analyze(self):
        return restricted.analyze(self.observed, self.streams, self.original, self.baseline,
                                  source_digest=self.source)

    def changed_output(self, index, mutate):
        key = f'trial-{index}.stdout'
        value = json.loads(self.streams[key])
        mutate(value)
        self.streams[key] = canonical(value)
        self.observed['trials'][index]['stdout_sha256'] = quality.sha(self.streams[key])
        self.observed['trials'][index]['stdout_bytes'] = len(self.streams[key])

    def truncate_after(self, count):
        self.observed['trials'] = self.observed['trials'][:count]
        for index in range(count, 5):
            for stream in ('stdout', 'stderr'):
                self.streams.pop(f'trial-{index}.{stream}')

    def test_actual_five_restricted_trials_and_distinct_worker_identity(self):
        result = self.analyze()
        self.assertEqual(result['status'], 'OWNED_RESTRICTED_LAB_PASS')
        self.assertEqual(result['restricted_trials_matched'], 5)
        self.assertEqual([t['returncode'] for t in self.observed['trials']], [0,2,0,2,0])
        self.assertNotEqual(self.observed['worker_sha256'], quality.sha((ROOT/'superhunter/owned_boundary_trial_worker.py').read_bytes()))
        for i in range(5):
            value = json.loads(self.streams[f'trial-{i}.stdout'])
            self.assertEqual(value['filter_proof'], guard.expected_proof(value['filter_proof']['socket_controls_before_filter']))
            self.assertFalse(value['filter_proof']['input_acquisition_inside_filter'])
        self.assertEqual(result['operational_findings_created'], 0)

    def test_verifier_never_reexecutes_filter_or_repairs_source(self):
        before = boundary.review(ROOT)
        with patch.object(restricted.owned_process, 'run', side_effect=AssertionError('must not run')):
            checked = restricted.verify(self.bundle, source_digest=self.source,
                                        experiment_anchor=self.made['experiment_anchor'])
        self.assertEqual(checked, self.made)
        self.assertEqual(boundary.review(ROOT), before)

    def test_historical_worker_identity_cannot_be_relabelled(self):
        self.observed['worker_sha256'] = quality.sha((ROOT/'superhunter/owned_boundary_trial_worker.py').read_bytes())
        with self.assertRaisesRegex(ValueError, 'RESTRICTED_SOURCE'):
            self.analyze()

    def test_legacy_unrestricted_stdout_cannot_pass_as_restricted(self):
        self.truncate_after(1)
        self.streams['trial-0.stdout'] = canonical(self.baseline)
        self.observed['trials'][0].update(stdout_sha256=quality.sha(self.streams['trial-0.stdout']),
                                         stdout_bytes=len(self.streams['trial-0.stdout']))
        result = self.analyze()
        self.assertEqual(result['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')
        self.assertEqual(result['restricted_trials_matched'], 0)

    def test_filter_guarantee_promotion_prevents_success(self):
        self.truncate_after(1)
        self.changed_output(0, lambda v: v['filter_proof'].update(general_hostile_code_sandbox_proved=True))
        self.assertEqual(self.analyze()['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')

    def test_input_acquisition_cannot_be_claimed_inside_filter(self):
        self.truncate_after(1)
        self.changed_output(0, lambda v: v['filter_proof'].update(input_acquisition_inside_filter=True))
        self.assertEqual(self.analyze()['restricted_trials_matched'], 0)

    def test_filter_phase_must_be_inside_parent_observation(self):
        self.truncate_after(1)
        end = self.observed['trials'][0]['clock']['monotonic_end_ns']
        self.changed_output(0, lambda v: v['phase_clocks'].update(filter_controls_finished_monotonic_ns=end+1))
        self.assertEqual(self.analyze()['restricted_trials_matched'], 0)

    def test_worker_inventory_must_match_parent_observation(self):
        self.truncate_after(1)
        self.changed_output(0, lambda v: v.update(input_inventory_sha256='0'*64))
        self.assertEqual(self.analyze()['restricted_trials_matched'], 0)

    def test_failure_cannot_be_hidden_by_later_repairs(self):
        self.changed_output(1, lambda v: v['boundary_result'].update(reason='OTHER_REASON'))
        with self.assertRaisesRegex(ValueError, 'RESTRICTED_CONTINUED_AFTER_FAILURE'):
            self.analyze()

    def test_declared_partial_record_is_inconclusive_without_controls(self):
        self.truncate_after(1)
        result = self.analyze()
        self.assertEqual(result['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')
        self.assertEqual(result['declared_integrity_controls_supported'], [])

    def test_declared_timeout_preserves_inconclusive_and_stop(self):
        self.truncate_after(1)
        self.observed['trials'][0].update(timed_out=True, returncode=None)
        self.assertEqual(self.analyze()['restricted_trials_matched'], 0)
        self.assertEqual(self.analyze()['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')

    def test_actual_unavailable_worker_response_is_inconclusive(self):
        # A real worker reads a deliberately wrong own marker; no IO/failure is mocked.
        # Direct fixed-worker invocation avoids changing the producer's marker setup.
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            files, _ = boundary._capture(ROOT)
            lab._copy(files, root/'owned-checkout')
            (root/'owned-compute-control').write_bytes(b'declared wrong marker')
            process = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'superhunter'/restricted.WORKER)],
                cwd=root, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
            self.assertEqual(process.returncode, 3)
            self.assertEqual(process.stderr, b'')
            response = json.loads(process.stdout)
            self.assertEqual(response['status'], 'OWNED_RESTRICTED_REVIEW_UNAVAILABLE')
            self.assertEqual(response['failed_phase'], 'FILTER_INSTALLATION')
            self.assertEqual(response['reason'], 'COMPUTE_CONTROL_BYTES')
            self.assertFalse(response['unfiltered_fallback_executed'])
            self.truncate_after(1)
            self.streams['trial-0.stdout'] = process.stdout
            self.observed['trials'][0].update(returncode=3, stdout_sha256=quality.sha(process.stdout),
                                              stdout_bytes=len(process.stdout))
            self.assertEqual(self.analyze()['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')

    def test_actual_extra_descriptor_stops_producer_and_preserves_failed_trial(self):
        original_run = restricted.owned_process.run
        def inject_descriptor(command, **options):
            descriptor = os.open(options['cwd']/'owned-compute-control', os.O_RDONLY)
            try:
                return original_run(command, **options, pass_fds=(descriptor,))
            finally:
                os.close(descriptor)
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)/'declared-extra-descriptor-control'
            with patch.object(restricted.owned_process, 'run', side_effect=inject_descriptor):
                result = restricted.create(out, source_digest=self.source)
            self.assertEqual(result['status'], 'OWNED_RESTRICTED_LAB_INCONCLUSIVE')
            self.assertEqual(result['trials_observed'], 1)
            self.assertEqual(result['restricted_trials_matched'], 0)
            response = json.loads((out/'trial-0.stdout').read_bytes())
            self.assertEqual(response['reason'], 'COMPUTE_EXTRA_DESCRIPTOR')
            verified = restricted.verify(out, source_digest=self.source,
                                         experiment_anchor=result['experiment_anchor'])
            self.assertEqual(verified, result)

    def test_resealed_report_promotion_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            bundle = Path(name)/'altered'
            shutil.copytree(self.bundle, bundle)
            value = json.loads((bundle/'diagnosis.json').read_bytes())
            value['limitations']['runtime_isolation_proved'] = True
            (bundle/'diagnosis.json').write_bytes(canonical(value))
            marker = canonical({'schema_version': 1, 'sha256': {
                p.name: quality.sha(p.read_bytes()) for p in bundle.iterdir() if p.name != 'COMPLETE.json'}})
            (bundle/'COMPLETE.json').write_bytes(marker)
            with self.assertRaisesRegex(ValueError, 'RESTRICTED_REPORT'):
                restricted.verify(bundle, source_digest=self.source, experiment_anchor=quality.sha(marker))

    def test_separate_cli_verification_and_wrong_anchor(self):
        args = [sys.executable, '-B', '-m', 'superhunter', 'verify-owned-restricted-boundary',
                '--bundle', str(self.bundle), '--source-digest', self.source,
                '--experiment-anchor', self.made['experiment_anchor']]
        for anchor, expected in ((self.made['experiment_anchor'], 0), ('0'*64, 2)):
            args[-1] = anchor
            process = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30,
                                     env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
            self.assertEqual(process.returncode, expected)
            self.assertEqual(process.stderr, b'')
            self.assertNotIn(str(self.base).encode(), process.stdout)

    def test_claimed_filter_success_without_all_controls_is_inconclusive(self):
        self.truncate_after(1)
        self.changed_output(0, lambda v: v['filter_proof'].update(controls_denied_after_filter=['new_read']))
        self.assertEqual(self.analyze()['restricted_trials_matched'], 0)


if __name__ == '__main__':
    unittest.main()
