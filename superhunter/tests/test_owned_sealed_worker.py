"""Native fixed children test post-filter input and preserve the old profile."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import (owned_compute_guard as guard, owned_process,
                         owned_sealed_input as sealed, repository_boundary as boundary)
from superhunter.safe_io import canonical

ROOT = Path(__file__).resolve().parents[2]


class SealedWorkerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'owned-compute-control').write_bytes(guard.MARKER_BYTES)

    def launch(self, descriptor, *, worker='owned_sealed_worker.py', pass_fds=(), args=()):
        with (self.root/'out').open('w+b') as out, (self.root/'err').open('w+b') as err:
            result = owned_process.run([sys.executable, '-I', '-B', str(ROOT/'superhunter'/worker), *args],
                cwd=self.root, env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=10,
                stdout=out, stderr=err, pass_fds=pass_fds, sealed_stdin=descriptor)
            out.seek(0); err.seek(0)
            raw, errors = out.read(), err.read()
        self.assertEqual(errors, b'')
        self.assertNotIn(str(self.root).encode(), raw)
        return result.returncode, json.loads(raw)

    def test_actual_own_source_is_read_and_reviewed_without_checkout(self):
        files, _ = boundary._capture(ROOT)
        with sealed.sealed_bytes(sealed.encode(files)) as descriptor:
            code, value = self.launch(descriptor)
        self.assertEqual(code, 0)
        self.assertEqual(value['boundary_result'], boundary._review_captured(files, 0))
        proof = value['filter_proof']
        self.assertEqual(proof, guard.sealed_expected_proof(proof['socket_controls_before_filter'], len(sealed.encode(files))))
        self.assertTrue(proof['worker_payload_read_inside_filter'])
        self.assertFalse(proof['parent_filesystem_acquisition_inside_filter'])
        phases = value['phase_clocks']
        self.assertLessEqual(phases['filter_controls_finished_monotonic_ns'], phases['sealed_input_finished_monotonic_ns'])
        self.assertLessEqual(phases['sealed_input_finished_monotonic_ns'], phases['review_finished_monotonic_ns'])
        self.assertFalse((self.root/'owned-checkout').exists())

    def test_malformed_sealed_data_fails_in_post_filter_read_phase(self):
        raw = sealed.encode({'own': {'mode': '100644', 'bytes': b'own bytes'}})
        for changed in (raw[:-1], raw+b'extra', b'INVALID!'+raw[8:]):
            with self.subTest(changed=changed[:16]), sealed.sealed_bytes(changed) as descriptor:
                code, value = self.launch(descriptor)
            self.assertEqual(code, 3)
            self.assertEqual(value['failed_phase'], 'SEALED_INPUT_READ')
            self.assertFalse(value['unfiltered_fallback_executed'])

    def test_valid_frame_with_incomplete_own_tree_is_blocked(self):
        with sealed.sealed_bytes(sealed.encode({'own': {'mode': '100644', 'bytes': b'own'}})) as descriptor:
            code, value = self.launch(descriptor)
        self.assertEqual(code, 2)
        self.assertEqual(value['boundary_result']['status'], 'REPOSITORY_BOUNDARY_BLOCKED')
        self.assertEqual(value['status'], 'OWNED_SEALED_REVIEW_OBSERVED')

    def test_actual_extra_descriptor_fails_before_payload(self):
        extra = os.open(self.root/'owned-compute-control', os.O_RDONLY)
        try:
            with sealed.sealed_bytes(sealed.encode({'own': {'mode': '100644', 'bytes': b''}})) as descriptor:
                code, value = self.launch(descriptor, pass_fds=(extra,))
        finally:
            os.close(extra)
        self.assertEqual((code, value['failed_phase'], value['reason']),
                         (3, 'FILTER_INSTALLATION', 'COMPUTE_EXTRA_DESCRIPTOR'))
        self.assertFalse(value['unfiltered_fallback_executed'])

    def test_no_target_or_command_arguments(self):
        with sealed.sealed_bytes(sealed.encode({'own': {'mode': '100644', 'bytes': b''}})) as descriptor:
            code, value = self.launch(descriptor, args=('--target', 'UNIT-ONLY'))
        self.assertEqual(code, 3)
        self.assertFalse(value['unfiltered_fallback_executed'])

    def test_old_guard_still_rejects_sealed_stdin(self):
        # The old worker captures before installing its old guard; use its own
        # dedicated guard test process instead of creating an incomplete checkout.
        script = (f'import sys\nsys.path.insert(0,{str(ROOT)!r})\nfrom pathlib import Path\n'
                  'from superhunter import owned_compute_guard as g\n'
                  'try: g.install(Path.cwd()/"owned-compute-control")\n'
                  'except g.ComputeGuardError as e: print(str(e)); raise SystemExit(2)\n')
        with sealed.sealed_bytes(sealed.encode({'own': {'mode': '100644', 'bytes': b''}})) as descriptor:
            result = subprocess.run([sys.executable, '-I', '-B', '-c', script], cwd=self.root,
                stdin=descriptor, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (2, b'COMPUTE_STDIN\n', b''))


if __name__ == '__main__':
    unittest.main()
