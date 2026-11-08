"""Actual own-process capture plus explicitly altered copies for rejection controls."""
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

from superhunter import owned_capture as capture, quality
from superhunter.safe_io import canonical


class OwnedCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.source = quality.sha(canonical(quality.source_snapshot()))
        cls.original = cls.root / 'original'
        cls.children = []
        popen = subprocess.Popen
        def observed(*args, **kwargs):
            process = popen(*args, **kwargs)
            cls.children.append(process.pid)
            return process
        with patch.object(capture.owned_process.subprocess, 'Popen', side_effect=observed):
            cls.result = capture.create(cls.original, source_digest=cls.source)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.bundle = self.work / 'bundle'
        shutil.copytree(self.original, self.bundle)
        self.anchor = self.result['capture_anchor']

    def verify(self, **changes):
        return capture.verify(self.bundle, **{'source_digest': self.source,
                              'capture_anchor': self.anchor, **changes})

    def rewrite(self, name, value):
        raw = value if type(value) is bytes else canonical(value)
        (self.bundle / name).write_bytes(raw)
        manifest = json.loads((self.bundle / 'COMPLETE.json').read_bytes())
        manifest['sha256'][name] = quality.sha(raw)
        (self.bundle / 'COMPLETE.json').write_bytes(canonical(manifest))
        self.anchor = quality.sha((self.bundle / 'COMPLETE.json').read_bytes())

    def observation(self):
        return json.loads((self.bundle / 'observation.json').read_bytes())

    def test_real_capture_and_read_only_verifier(self):
        self.assertEqual(len(self.children), 1)
        self.assertNotEqual(self.children[0], os.getpid())
        with self.assertRaises(ChildProcessError): os.waitpid(self.children[0], os.WNOHANG)
        with patch.object(capture.owned_process, 'run', side_effect=AssertionError('must not execute')):
            result = self.verify()
        self.assertEqual(result['status'], 'OWNED_CAPTURE_CONSISTENT')
        self.assertEqual(result['historical_files_checked'], 642)
        self.assertGreater(result['elapsed_ns'], 0)
        self.assertTrue(all(v is False for v in result['limitations'].values()))

    def test_format_is_own_observation_not_journald(self):
        observation = self.observation()
        self.assertEqual(observation['profile'], capture.PROFILE)
        self.assertEqual(observation['origin'], 'own_parent_process_observation')
        self.assertNotIn('__REALTIME_TIMESTAMP', observation)
        self.assertFalse(observation['limitations']['journald_acquisition'])

    def test_saved_bundle_has_no_paths_environment_or_raw_stderr(self):
        raw = b''.join(p.read_bytes() for p in self.bundle.iterdir())
        self.assertNotIn(str(capture.ROOT).encode(), raw)
        self.assertNotIn(str(Path(sys.executable).parent).encode(), raw)
        self.assertNotIn(str(self.root).encode(), raw)
        self.assertEqual(set(p.name for p in self.bundle.iterdir()), capture.FILES | {'COMPLETE.json'})

    def test_wrong_external_anchors_rejected(self):
        for name in ('source_digest', 'capture_anchor'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.verify(**{name: '0' * 64})

    def test_original_anchor_rejects_rewritten_observation(self):
        old = self.anchor
        changed = self.observation(); changed['clock']['realtime_start_ns'] += 1
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_ANCHOR'): self.verify(capture_anchor=old)

    def test_rehashed_boundary_change_rejected(self):
        changed = json.loads((self.bundle / 'boundary.stdout').read_bytes())
        changed['historical_files_checked'] -= 1
        raw = canonical(changed); self.rewrite('boundary.stdout', raw)
        observation = self.observation()
        observation.update(stdout_sha256=quality.sha(raw), stdout_bytes=len(raw))
        self.rewrite('observation.json', observation)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_BOUNDARY_RESULT'): self.verify()

    def test_independent_authentication_cannot_be_promoted(self):
        changed = self.observation(); changed['limitations']['independent_execution_authenticated'] = True
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_LIMITATIONS'): self.verify()

    def test_forged_origin_rejected(self):
        changed = self.observation(); changed['origin'] = 'journalctl-export'
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_ORIGIN'): self.verify()

    def test_worker_identity_change_rejected(self):
        changed = self.observation(); changed['worker_sha256'] = '0' * 64
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_SOURCE'): self.verify()

    def test_exit_and_stderr_failures_cannot_be_rehashed_to_pass(self):
        original = self.observation()
        for name, value in (('exit_code', 1), ('exit_code', False), ('stderr_bytes', 1), ('wall_budget_seconds', 180)):
            with self.subTest(name=name, value=value):
                changed = copy.deepcopy(original); changed[name] = value
                self.rewrite('observation.json', changed)
                with self.assertRaisesRegex(ValueError, 'CAPTURE_PROCESS_RESULT'): self.verify()

    def test_clock_requires_exact_integer_arithmetic(self):
        original = self.observation()
        for name, value in (('elapsed_ns', True), ('elapsed_ns', 1.5), ('monotonic_end_ns', -1),
                            ('realtime_end_ns', 2**63), ('realtime_delta_ns', True)):
            with self.subTest(name=name):
                changed = copy.deepcopy(original); changed['clock'][name] = value
                self.rewrite('observation.json', changed)
                with self.assertRaises(ValueError): self.verify()

    def test_clock_order_and_elapsed_mismatch_rejected(self):
        original = self.observation()
        for change in ({'elapsed_ns': original['clock']['elapsed_ns'] + 1},
                       {'monotonic_end_ns': original['clock']['monotonic_start_ns'] - 1}):
            changed = copy.deepcopy(original); changed['clock'].update(change)
            self.rewrite('observation.json', changed)
            with self.assertRaisesRegex(ValueError, 'CAPTURE_CLOCK_ARITHMETIC'): self.verify()

    def test_clock_rollback_is_preserved_not_called_accurate_utc(self):
        # A coherent edited clock with a NEW anchor is not authenticated time.
        # This is a schema control, not an observed real host rollback.
        changed = self.observation(); clock = changed['clock']
        clock.update(realtime_end_ns=clock['realtime_start_ns'] - 1,
                     realtime_delta_ns=-1, realtime_moved_backwards=True)
        self.rewrite('observation.json', changed); self.rewrite('REVIEW.md', capture.render(changed))
        self.assertEqual(self.verify()['status'], 'OWNED_CAPTURE_CONSISTENT')
        self.assertFalse(self.verify()['limitations']['utc_accuracy_authenticated'])

    def test_hidden_clock_rollback_rejected(self):
        changed = self.observation(); clock = changed['clock']
        clock.update(realtime_end_ns=clock['realtime_start_ns'] - 1,
                     realtime_delta_ns=-1, realtime_moved_backwards=False)
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_CLOCK_ROLLBACK'): self.verify()

    def test_report_change_rejected_even_with_fresh_manifest(self):
        self.rewrite('REVIEW.md', b'Authenticated execution\n')
        with self.assertRaisesRegex(ValueError, 'CAPTURE_REPORT'): self.verify()

    def test_unknown_and_duplicate_fields_rejected(self):
        changed = self.observation(); changed['private_message'] = 'do not propagate'
        self.rewrite('observation.json', changed)
        with self.assertRaisesRegex(ValueError, 'CAPTURE_SCHEMA'): self.verify()
        self.rewrite('observation.json', b'{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.verify()

    def test_extra_missing_and_symlink_artifacts_rejected(self):
        extra = self.bundle / 'extra'; extra.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'CAPTURE_INVENTORY'): self.verify()
        extra.unlink()
        path = self.bundle / 'boundary.stdout'; raw = path.read_bytes(); path.unlink()
        with self.assertRaisesRegex(ValueError, 'CAPTURE_INVENTORY'): self.verify()
        outside = self.work / 'stdout'; outside.write_bytes(raw); path.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)): self.verify()

    def test_existing_and_repository_outputs_rejected_before_launch(self):
        for out in (self.bundle, capture.ROOT / 'superhunter' / 'unwanted-capture', capture.ROOT.parent):
            with self.subTest(out=out), patch.object(capture.owned_process, 'run') as run:
                with self.assertRaises(ValueError): capture.create(out, source_digest=self.source)
                run.assert_not_called()

    def test_symlinked_output_parent_rejected_before_launch(self):
        link = self.work / 'link'; link.symlink_to(self.root, target_is_directory=True)
        with patch.object(capture.owned_process, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'CAPTURE_SYMLINK'):
                capture.create(link / 'new', source_digest=self.source)
            run.assert_not_called()

    def test_source_change_during_capture_rejected(self):
        snapshot = quality.source_snapshot(); changed = {**snapshot, 'owned_capture.py': '0' * 64}
        out = self.work / 'new'
        with patch.object(quality, 'source_snapshot', side_effect=[snapshot, changed]):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_INPUT_CHANGED'):
                capture.create(out, source_digest=self.source)
        self.assertFalse(out.exists())

    def test_failed_process_does_not_create_positive_bundle(self):
        out = self.work / 'new'
        with patch.object(capture.owned_process, 'run', return_value=SimpleNamespace(returncode=2)):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_PROCESS_FAILED'):
                capture.create(out, source_digest=self.source)
        self.assertFalse(out.exists())

    def test_timeout_creates_no_bundle_and_cli_omits_private_command(self):
        out = self.work / 'new'; stream = io.StringIO()
        with patch.object(capture.owned_process, 'run', side_effect=subprocess.TimeoutExpired(['PRIVATE'], 30)), redirect_stdout(stream):
            code = capture.main(['capture-owned-boundary', '--source-digest', self.source, '--out', str(out)])
        self.assertEqual(code, 2); self.assertNotIn('PRIVATE', stream.getvalue())
        self.assertFalse(out.exists())

    def test_worker_output_is_bounded(self):
        def oversized(*args, **kwargs):
            kwargs['stdout'].write(b'x' * (capture.OUTPUT_BYTES + 1))
            return SimpleNamespace(returncode=0)
        with patch.object(capture.owned_process, 'run', side_effect=oversized):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_OUTPUT_BUDGET'):
                capture.create(self.work / 'new', source_digest=self.source)

    def test_verifier_rechecks_evidence_after_semantic_review(self):
        original = capture._read; calls = 0
        def changed(root):
            nonlocal calls
            result = original(root); calls += 1
            if calls == 2: result['boundary.stdout'] += b' '
            return result
        with patch.object(capture, '_read', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_EVIDENCE_CHANGED'): self.verify()

    def test_worker_rejects_arguments(self):
        result = subprocess.run([sys.executable, '-I', '-B', str(capture.ROOT / 'superhunter' / 'owned_boundary_worker.py'), 'PRIVATE'],
                                capture_output=True, timeout=30, cwd=self.work)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), {'status': 'OWNED_BOUNDARY_WORKER_BLOCKED'})
        self.assertEqual(result.stderr, b'')

    def test_cli_capture_and_verify_in_separate_processes(self):
        command = [sys.executable, '-B', '-m', 'superhunter']
        out = self.work / 'cli'
        result = subprocess.run(command + ['capture-owned-boundary', '--out', str(out), '--source-digest', self.source],
                                cwd=capture.ROOT, capture_output=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(result.stdout)
        verified = subprocess.run(command + ['verify-owned-boundary-capture', '--bundle', str(out), '--source-digest', self.source,
                                             '--capture-anchor', receipt['capture_anchor']],
                                  cwd=capture.ROOT, capture_output=True, timeout=40)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertEqual(json.loads(verified.stdout)['status'], 'OWNED_CAPTURE_CONSISTENT')


if __name__ == '__main__':
    unittest.main()
