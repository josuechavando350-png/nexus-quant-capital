"""Writer preflight and real own-process SIGKILL at explicitly instrumented cuts."""
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bundle_recovery as recovery, owned_process, safe_io


class BundleWriterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.out = self.root / 'new-parent' / 'bundle'

    def test_invalid_bytes_leave_no_directory_and_valid_retry_succeeds(self):
        with self.assertRaises(ValueError): safe_io.write_new_bundle(self.out, {'first': b'valid', 'second': 'invalid'})
        self.assertFalse(self.out.parent.exists())
        safe_io.write_new_bundle(self.out, {'second': b'valid'})
        self.assertEqual(recovery.inspect(self.out)['assessment']['state'], 'BUNDLE_BYTES_COMPLETE')

    def test_unreadable_reserved_and_invalid_names_rejected_before_writes(self):
        for name in ('a:b', 'a\\b', '../bad', 'nested/file', '', '.', 'COMPLETE.json', safe_io.PENDING_MARKER, 'a\0b'):
            with self.subTest(name=name), self.assertRaises(ValueError): safe_io.write_new_bundle(self.out, {name: b'x'})
            self.assertFalse(self.out.parent.exists())

    def test_non_dictionary_empty_and_nonbytes_payloads_rejected(self):
        for payload in ({}, [], {'a': bytearray(b'x')}, {'a': None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError): safe_io.write_new_bundle(self.out, payload)
            self.assertFalse(self.out.parent.exists())

    def test_payload_and_manifest_budget_checked_before_directory_creation(self):
        with self.assertRaises(ValueError): safe_io.write_new_bundle(self.out, {'a': b'x' * (safe_io.MAX_BYTES + 1)})
        self.assertFalse(self.out.parent.exists())
        with patch.object(safe_io, 'MAX_BYTES', 100):
            with self.assertRaisesRegex(ValueError, 'manifest'): safe_io.write_new_bundle(self.out, {'a': b'x', 'b': b'y'})
        self.assertFalse(self.out.parent.exists())

    def test_normal_publication_keeps_original_manifest_format_and_private_modes(self):
        payload = {'first': b'one', 'second': b'two'}
        events = []; fsync = os.fsync
        def synced(fd):
            events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file'); fsync(fd)
        with patch.object(safe_io.os, 'fsync', side_effect=synced): safe_io.write_new_bundle(self.out, payload)
        self.assertEqual(set(p.name for p in self.out.iterdir()), {'first', 'second', 'COMPLETE.json'})
        self.assertEqual((self.out / 'COMPLETE.json').read_bytes(), safe_io.canonical({'schema_version': 1,
            'sha256': {name: recovery.quality.sha(value) for name, value in payload.items()}}))
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in self.out.iterdir()))
        self.assertEqual(events, ['file', 'file', 'directory', 'file', 'directory'])

    def test_existing_bundle_is_never_overwritten(self):
        safe_io.write_new_bundle(self.out, {'data': b'old'})
        original = {p.name: p.read_bytes() for p in self.out.iterdir()}
        with self.assertRaises(FileExistsError): safe_io.write_new_bundle(self.out, {'data': b'new'})
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_publication_collision_does_not_overwrite_existing_marker(self):
        link = os.link
        def collided(src, dst, **kwargs):
            fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=kwargs['dst_dir_fd'])
            with os.fdopen(fd, 'wb') as stream: stream.write(b'existing marker')
            return link(src, dst, **kwargs)
        with patch.object(safe_io.os, 'link', side_effect=collided):
            with self.assertRaises(FileExistsError): safe_io.write_new_bundle(self.out, {'data': b'content'})
        self.assertEqual((self.out / 'COMPLETE.json').read_bytes(), b'existing marker')
        self.assertTrue((self.out / safe_io.PENDING_MARKER).exists())

    def test_payload_sync_error_leaves_no_committed_marker(self):
        with patch.object(safe_io.os, 'fsync', side_effect=OSError('synthetic sync failure')):
            with self.assertRaises(OSError): safe_io.write_new_bundle(self.out, {'data': b'content'})
        self.assertFalse((self.out / 'COMPLETE.json').exists())
        self.assertEqual(recovery.inspect(self.out)['assessment']['state'], 'INCOMPLETE_NO_MARKER')


class InterruptedWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name); cls.results = {}; cls.states = {}
        worker = Path(__file__).resolve().parents[1] / 'owned_bundle_interrupt_worker.py'
        for mode in ('clean', 'payload-synced', 'marker-half', 'marker-synced', 'marker-linked'):
            work = cls.root / mode; work.mkdir()
            with (work / 'stdout').open('wb') as stdout, (work / 'stderr').open('wb') as stderr:
                process = owned_process.run([sys.executable, '-I', '-B', str(worker), mode], cwd=work,
                    env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}, timeout=15, stdout=stdout, stderr=stderr)
            cls.results[mode] = process.returncode
            cls.states[mode] = recovery.inspect(work / 'bundle')['assessment']['state']
            if (work / 'stderr').read_bytes(): raise AssertionError('unexpected worker stderr')

    def test_real_sigkill_after_payload_preserves_incomplete_source(self):
        self.assertEqual(self.results['payload-synced'], -signal.SIGKILL)
        source = self.root / 'payload-synced/bundle'
        self.assertEqual(set(p.name for p in source.iterdir()), {'first.json'})
        self.assertEqual(self.states['payload-synced'], 'INCOMPLETE_NO_MARKER')

    def test_real_sigkill_during_marker_never_publishes_partial_complete(self):
        self.assertEqual(self.results['marker-half'], -signal.SIGKILL)
        source = self.root / 'marker-half/bundle'
        self.assertFalse((source / 'COMPLETE.json').exists())
        self.assertTrue((source / safe_io.PENDING_MARKER).exists())
        with self.assertRaises(ValueError): safe_io.strict_json((source / safe_io.PENDING_MARKER).read_bytes())
        self.assertEqual(self.states['marker-half'], 'INCOMPLETE_NO_MARKER')

    def test_real_sigkill_after_marker_sync_does_not_infer_publication(self):
        self.assertEqual(self.results['marker-synced'], -signal.SIGKILL)
        source = self.root / 'marker-synced/bundle'
        self.assertFalse((source / 'COMPLETE.json').exists())
        self.assertIn('sha256', safe_io.strict_json((source / safe_io.PENDING_MARKER).read_bytes()))
        self.assertEqual(self.states['marker-synced'], 'INCOMPLETE_NO_MARKER')

    def test_real_sigkill_after_link_remains_cleanup_pending(self):
        self.assertEqual(self.results['marker-linked'], -signal.SIGKILL)
        source = self.root / 'marker-linked/bundle'
        self.assertEqual((source / 'COMPLETE.json').stat().st_ino, (source / safe_io.PENDING_MARKER).stat().st_ino)
        self.assertEqual(self.states['marker-linked'], 'COMMIT_CLEANUP_PENDING')

    def test_uninterrupted_control_is_only_structurally_complete(self):
        self.assertEqual(self.results['clean'], 0)
        self.assertEqual(self.states['clean'], 'BUNDLE_BYTES_COMPLETE')
        self.assertTrue(all(v is False for v in recovery.inspect(self.root / 'clean/bundle')['limitations'].values()))


class CapturedWriterIdentityTests(unittest.TestCase):
    """Stored native observations are derivation inputs, not fresh execution."""
    def test_prior_capture_is_retained_and_rejected_as_stale(self):
        from superhunter import evm_accounting
        original = Path(__file__).parent / 'fixtures/evm_accounting_capture.json'
        with self.assertRaisesRegex(ValueError, 'STALE_EVM_ENGINE'):
            evm_accounting.derive(safe_io.strict_json(original.read_bytes()), '2026-11-05T23:00:00+00:00')

    def test_current_capture_is_bound_to_writer_and_executable_snapshot(self):
        from superhunter import evm_accounting, evm_execution, quality
        name = 'tests/fixtures/evm_accounting_capture_io_v2.json'
        raw = (quality.ROOT / name).read_bytes(); captured = safe_io.strict_json(raw)
        self.assertEqual(captured['engine'], evm_execution.engine_identity())
        self.assertEqual(quality.source_snapshot()[name], quality.sha(raw))
        result = evm_accounting.derive(captured, '2026-11-05T23:00:00+00:00')
        self.assertEqual(result['calls_checked'], 18)
        self.assertFalse(result['derivation_reran_evm'])


if __name__ == '__main__': unittest.main()
