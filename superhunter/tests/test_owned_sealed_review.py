"""Real own worker consumer and consistency controls; no external target."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_sealed_review as lab, quality
from superhunter.safe_io import canonical, read_artifact, write_new_bundle


class SealedReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.bundle = cls.root/'native'
        cls.digest = quality.sha(canonical(quality.source_snapshot()))
        cls.created = lab.create(cls.bundle, source_digest=cls.digest)
        cls.raw = lab._read(cls.bundle)
        cls.observed = json.loads(cls.raw['observation.json'])
        _, _, cls.frame, cls.baseline = lab._source(cls.digest)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def analyze(self, observation=None, raw=None):
        return lab.analyze(observation or self.observed, raw or self.raw,
                           source_digest=self.digest, frame=self.frame, baseline=self.baseline)

    def test_native_parent_worker_and_verifier_agree(self):
        self.assertEqual(self.created['status'], 'OWNED_SEALED_LAB_PASS')
        self.assertEqual(lab.verify(self.bundle, source_digest=self.digest,
                         experiment_anchor=self.created['experiment_anchor']), self.created)
        self.assertTrue(self.created['worker_payload_read_inside_filter_observed'])
        self.assertEqual(self.created['operational_findings_created'], 0)
        self.assertTrue(all(value is False for value in self.created['limitations'].values()))

    def test_verifier_never_runs_child_or_installs_filter(self):
        with patch.object(lab.owned_process, 'run', side_effect=AssertionError('no replay')), \
             patch.object(lab.guard, 'install_sealed', side_effect=AssertionError('no filter')):
            value = lab.verify(self.bundle, source_digest=self.digest,
                               experiment_anchor=self.created['experiment_anchor'])
        self.assertEqual(value, self.created)

    def test_resealed_report_cannot_promote_guarantees(self):
        for key in ('host_authenticated', 'runtime_isolation_proved', 'memory_integrity_proved'):
            result = json.loads(self.raw['result.json'])
            result['limitations'][key] = True
            out = self.root/('promotion-'+key)
            raw = {k: v for k, v in self.raw.items() if k != 'COMPLETE.json'}
            raw['result.json'] = canonical(result)
            write_new_bundle(out, raw)
            anchor = quality.sha(read_artifact(out, 'COMPLETE.json'))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'REPORT'):
                lab.verify(out, source_digest=self.digest, experiment_anchor=anchor)

    def test_wrong_frame_inventory_worker_and_source_rejected(self):
        for key in ('input_frame_sha256', 'input_inventory_sha256', 'worker_sha256', 'source_digest'):
            observation = copy.deepcopy(self.observed)
            observation[key] = '0'*64
            with self.subTest(key=key), self.assertRaises(ValueError): self.analyze(observation)
        observation = copy.deepcopy(self.observed)
        observation['input_frame_bytes'] = True
        with self.assertRaisesRegex(ValueError, 'FRAME'): self.analyze(observation)

    def test_closed_observation_schema_and_limits(self):
        for key, value in (('extra', True), ('profile', 'owned-restricted-boundary-lab-v1'),
                           ('schema_version', True), ('experiment_id', 'UNIT-ONLY'),
                           ('wall_budget_seconds', 31), ('returncode', True)):
            observation = copy.deepcopy(self.observed)
            observation[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.analyze(observation)
        observation = copy.deepcopy(self.observed)
        observation['limitations']['parent_filesystem_acquisition_inside_filter'] = True
        with self.assertRaisesRegex(ValueError, 'LIMITS'): self.analyze(observation)

    def changed_worker(self, value):
        raw = dict(self.raw)
        raw['worker.stdout'] = canonical(value)
        observation = copy.deepcopy(self.observed)
        observation['stdout_sha256'] = quality.sha(raw['worker.stdout'])
        observation['stdout_bytes'] = len(raw['worker.stdout'])
        return self.analyze(observation, raw)

    def test_input_phase_before_filter_is_inconclusive(self):
        worker = json.loads(self.raw['worker.stdout'])
        worker['phase_clocks']['sealed_input_finished_monotonic_ns'] = (
            worker['phase_clocks']['filter_controls_finished_monotonic_ns']-1)
        self.assertEqual(self.changed_worker(worker)['status'], 'OWNED_SEALED_LAB_INCONCLUSIVE')

    def test_worker_phase_outside_parent_is_inconclusive(self):
        for key, stamp in (('filter_controls_finished_monotonic_ns', self.observed['clock']['monotonic_start_ns']-1),
                           ('review_finished_monotonic_ns', self.observed['clock']['monotonic_end_ns']+1),
                           ('sealed_input_finished_monotonic_ns', True)):
            worker = json.loads(self.raw['worker.stdout'])
            worker['phase_clocks'][key] = stamp
            with self.subTest(key=key):
                self.assertFalse(self.changed_worker(worker)['restricted_observation_matched'])

    def test_old_profile_and_weaker_proof_cannot_pass(self):
        for alteration in ('old-profile', 'old-guard', 'no-seal', 'wrong-frame'):
            worker = json.loads(self.raw['worker.stdout'])
            if alteration == 'old-profile': worker['profile'] = 'owned-preloaded-boundary-review-v1'
            if alteration == 'old-guard': worker['filter_proof'] = lab.guard.expected_proof(worker['filter_proof']['socket_controls_before_filter'])
            if alteration == 'no-seal': worker['filter_proof']['stdin_seals'].remove('F_SEAL_WRITE')
            if alteration == 'wrong-frame': worker['input_frame_sha256'] = '0'*64
            with self.subTest(alteration=alteration):
                self.assertFalse(self.changed_worker(worker)['restricted_observation_matched'])

    def test_malformed_worker_json_preserved_as_inconclusive(self):
        for output in (b'', b'{}', b'{"status":1,"status":2}\n', b'not-json'):
            raw = dict(self.raw); raw['worker.stdout'] = output
            observed = copy.deepcopy(self.observed)
            observed['stdout_sha256'], observed['stdout_bytes'] = quality.sha(output), len(output)
            with self.subTest(output=output):
                self.assertEqual(self.analyze(observed, raw)['status'], 'OWNED_SEALED_LAB_INCONCLUSIVE')

    def test_timeout_cannot_promote_even_matching_output(self):
        observed = copy.deepcopy(self.observed)
        observed['returncode'], observed['timed_out'] = None, True
        result = self.analyze(observed)
        self.assertFalse(result['restricted_observation_matched'])
        self.assertFalse(result['worker_payload_read_inside_filter_observed'])

    def test_stream_tamper_and_wrong_anchor_rejected(self):
        raw = dict(self.raw); raw['worker.stdout'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'STREAM'): self.analyze(raw=raw)
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            lab.verify(self.bundle, source_digest=self.digest, experiment_anchor='0'*64)

    def test_actual_extra_descriptor_retains_failure_bundle(self):
        extra = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        real_run = lab.owned_process.run
        def with_extra(*args, **kwargs):
            return real_run(*args, **kwargs, pass_fds=(extra,))
        out = self.root/'failed-native'
        try:
            with patch.object(lab.owned_process, 'run', side_effect=with_extra):
                result = lab.create(out, source_digest=self.digest)
        finally:
            os.close(extra)
        self.assertEqual(result['status'], 'OWNED_SEALED_LAB_INCONCLUSIVE')
        raw = lab._read(out)
        worker = json.loads(raw['worker.stdout'])
        self.assertEqual(worker['reason'], 'COMPUTE_EXTRA_DESCRIPTOR')
        self.assertFalse(worker['unfiltered_fallback_executed'])
        self.assertEqual(lab.verify(out, source_digest=self.digest,
                         experiment_anchor=result['experiment_anchor']), result)

    def test_input_change_before_publication_is_rejected(self):
        original = lab.boundary._capture
        calls = 0
        def changed(*args, **kwargs):
            nonlocal calls
            files, ignored = original(*args, **kwargs)
            calls += 1
            if calls == 3:
                files = dict(files)
                files['UNIT-ONLY'] = {'mode': '100644', 'bytes': b'own counter-control'}
            return files, ignored
        out = self.root/'changed-source'
        with patch.object(lab.boundary, '_capture', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_CHANGED'):
                lab.create(out, source_digest=self.digest)
        self.assertFalse(out.exists())

    def test_cli_verifies_actual_bundle_and_rejects_target_argument(self):
        env = {'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
        args = [sys.executable, '-B', '-m', 'superhunter', 'verify-owned-sealed-boundary',
                '--source-digest', self.digest, '--bundle', str(self.bundle),
                '--experiment-anchor', self.created['experiment_anchor']]
        result = subprocess.run(args, cwd=lab.ROOT, env=env, capture_output=True, timeout=15)
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        self.assertEqual(json.loads(result.stdout)['status'], 'OWNED_SEALED_LAB_PASS')
        bad = subprocess.run(args+['--target', 'UNIT-ONLY'], cwd=lab.ROOT, env=env,
                             capture_output=True, timeout=15)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn(str(self.root).encode(), bad.stderr+bad.stdout)


if __name__ == '__main__':
    unittest.main()
