"""Real local preservation and read-only verification after removing the source.

Data is a declared fixture; concurrent changes are explicitly injected.
The separate acceptance helper also uses actual own-process SIGKILL captures.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bundle_recovery as recovery, preserved_copy as copy, quality, safe_io


class PreservedCopyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.source = self.root / 'input'; self.source.mkdir()
        (self.source / 'a-private-name.json').write_bytes(b'{"private-lab-content":')
        (self.source / 'z.bin').write_bytes(b'\x00\xff\xfe')
        self.out = self.root / 'saved'
        self.digest = quality.sha(safe_io.canonical(quality.source_snapshot()))

    def preserve(self):
        self.input_anchor = recovery.inspect(self.source)['input_anchor']
        r = recovery.preserve(self.source, self.out, source_digest=self.digest, input_anchor=self.input_anchor)
        self.args = {'source_digest': self.digest, 'input_anchor': self.input_anchor, 'recovery_anchor': r['recovery_anchor']}
        return r

    def verify(self, **changes):
        return copy.verify(self.out, **{**self.args, **changes})

    def reseal(self, name, raw, *, accept_new_anchor=True):
        (self.out / name).write_bytes(raw)
        marker = json.loads((self.out / 'COMPLETE.json').read_bytes()); marker['sha256'][name] = quality.sha(raw)
        (self.out / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))
        if accept_new_anchor: self.args['recovery_anchor'] = quality.sha((self.out / 'COMPLETE.json').read_bytes())

    def report_change(self, change):
        r = json.loads((self.out / 'recovery.json').read_bytes()); change(r)
        self.reseal('recovery.json', safe_io.canonical(r))

    def complete(self):
        shutil.rmtree(self.source); safe_io.write_new_bundle(self.source, {'a-private-name.json': b'{"private-lab-content":1}'})

    def cli(self):
        args = [sys.executable, '-B', '-m', 'superhunter', 'verify-preserved-copy', '--bundle', str(self.out)]
        for name, value in self.args.items(): args += ['--' + name.replace('_', '-'), value]
        return subprocess.run(args, cwd=quality.ROOT.parent, capture_output=True, timeout=20)

    def test_original_removed_copy_still_verifies_as_incomplete(self):
        self.preserve(); before = recovery._read_recovery(self.out); shutil.rmtree(self.source)
        result = self.verify()
        self.assertEqual(result['state'], 'PRESERVED_COPY_VERIFIED')
        self.assertEqual(result['captured_input_state'], 'INCOMPLETE_NO_MARKER')
        self.assertEqual(result['observed_files'], 2)
        self.assertFalse(result['original_current_state_checked']); self.assertFalse(result['original_restored'])
        self.assertEqual(recovery._read_recovery(self.out), before); self.assertFalse(self.source.exists())

    def test_moved_copy_remains_verifiable_without_original_paths(self):
        self.preserve(); shutil.rmtree(self.source)
        moved = self.root / 'moved'; self.out.rename(moved); self.out = moved
        self.assertEqual(self.verify()['state'], 'PRESERVED_COPY_VERIFIED')

    def test_verifier_never_captures_original_executes_or_writes(self):
        self.preserve(); shutil.rmtree(self.source)
        with patch.object(recovery, '_capture', side_effect=AssertionError('original read')), \
             patch.object(recovery, 'write_new_bundle', side_effect=AssertionError('write')), \
             patch('subprocess.Popen', side_effect=AssertionError('execution')):
            self.assertEqual(self.verify()['state'], 'PRESERVED_COPY_VERIFIED')

    def test_changed_original_is_not_claimed_checked(self):
        self.preserve(); (self.source / 'z.bin').write_bytes(b'changed after capture')
        self.assertFalse(self.verify()['original_current_state_checked'])
        with self.assertRaisesRegex(ValueError, 'RECOVERY_ANCHOR'):
            recovery.verify(self.source, self.out, **self.args)

    def test_complete_capture_is_not_semantically_approved(self):
        self.complete(); self.preserve(); shutil.rmtree(self.source)
        r = self.verify(); self.assertEqual(r['captured_input_state'], 'BUNDLE_BYTES_COMPLETE')
        for name in ('original_current_state_checked', 'original_restored', 'producer_authenticated',
                     'execution_authenticated', 'semantic_validation_performed'):
            self.assertFalse(r[name])

    def test_empty_original_remains_unknown_without_marker(self):
        for p in self.source.iterdir(): p.unlink()
        self.preserve(); shutil.rmtree(self.source)
        r = self.verify(); self.assertEqual(r['observed_files'], 0)
        self.assertEqual(r['captured_input_state'], 'INCOMPLETE_NO_MARKER')

    def test_saved_invalid_original_marker_remains_invalid(self):
        (self.source / 'COMPLETE.json').write_bytes(b'{"schema_version":')
        self.preserve(); shutil.rmtree(self.source)
        self.assertEqual(self.verify()['captured_input_state'], 'INVALID_MARKER')

    def test_pending_cleanup_is_not_promoted_when_original_disappears(self):
        self.complete()
        (self.source / safe_io.PENDING_MARKER).write_bytes((self.source / 'COMPLETE.json').read_bytes())
        self.preserve(); shutil.rmtree(self.source)
        self.assertEqual(self.verify()['captured_input_state'], 'COMMIT_CLEANUP_PENDING')

    def test_external_input_anchor_is_mandatory(self):
        self.preserve()
        with self.assertRaisesRegex(ValueError, 'COPY_INPUT_ANCHOR'): self.verify(input_anchor='0' * 64)

    def test_external_recovery_anchor_rejects_resealed_package(self):
        self.preserve(); self.reseal('REVIEW.md', b'altered', accept_new_anchor=False)
        with self.assertRaisesRegex(ValueError, 'COPY_RECOVERY_ANCHOR'): self.verify()

    def test_changed_bytes_resealed_still_rejected_by_input_anchor(self):
        self.preserve(); raw = b'different bytes'
        self.reseal('observed-000.bin', raw)
        def change(r):
            r['mapping'][0].update(bytes=len(raw), sha256=quality.sha(raw))
        self.report_change(change)
        with self.assertRaisesRegex(ValueError, 'COPY_INPUT_ANCHOR'): self.verify()

    def test_report_cannot_promote_original_completion(self):
        self.preserve(); self.report_change(lambda r: r['assessment'].update(state='BUNDLE_BYTES_COMPLETE'))
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.verify()

    def test_report_cannot_invent_authentication_or_unknown_fields(self):
        self.preserve(); self.report_change(lambda r: r['limitations'].update(producer_authenticated=True))
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.verify()

    def test_missing_saved_file_rejected_even_with_resealed_manifest(self):
        self.preserve(); (self.out / 'observed-000.bin').unlink()
        marker = json.loads((self.out / 'COMPLETE.json').read_bytes()); marker['sha256'].pop('observed-000.bin')
        (self.out / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))
        self.args['recovery_anchor'] = quality.sha((self.out / 'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'COPY_FILE_MISSING'): self.verify()

    def test_extra_unmapped_file_rejected_with_consistent_manifest(self):
        self.preserve(); self.reseal('observed-999.bin', b'extra')
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.verify()

    def test_absolute_traversal_duplicate_and_nonstring_names_rejected(self):
        self.preserve(); original = (self.out / 'recovery.json').read_bytes()
        for name in ('/tmp/outside', '../outside', 'z.bin', [], None):
            self.reseal('recovery.json', original)
            self.report_change(lambda r: r['mapping'][0].update(name=name))
            with self.subTest(name=name), self.assertRaises(ValueError): self.verify()

    def test_mapping_boolean_size_and_reordered_slots_rejected(self):
        self.preserve(); original = (self.out / 'recovery.json').read_bytes()
        for field, value in (('bytes', True), ('saved_as', 'observed-001.bin'), ('sha256', 'INVALID')):
            self.reseal('recovery.json', original)
            self.report_change(lambda r: r['mapping'][0].update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError): self.verify()

    def test_duplicate_json_keys_rejected(self):
        self.preserve(); self.reseal('recovery.json', b'{"mapping":[],"mapping":[]}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): self.verify()

    def test_symlink_payload_and_repository_overlap_rejected(self):
        self.preserve(); path = self.out / 'observed-000.bin'; path.unlink()
        path.symlink_to(self.source / 'a-private-name.json')
        with self.assertRaises((ValueError, OSError)): self.verify()
        with self.assertRaisesRegex(ValueError, 'CAPTURE_REPOSITORY_OVERLAP'):
            copy.verify(quality.ROOT, **self.args)

    def test_wrong_source_digest_rejected_before_package_read(self):
        self.preserve()
        with patch.object(recovery, '_read_recovery', side_effect=AssertionError('unexpected read')):
            with self.assertRaisesRegex(ValueError, 'COPY_SOURCE'): self.verify(source_digest='0' * 64)

    def test_injected_concurrent_resealed_change_rejected(self):
        self.preserve(); reader = recovery._read_recovery; calls = 0
        def changed(root):
            nonlocal calls
            calls += 1
            if calls == 2: self.reseal('REVIEW.md', b'changed during verification')
            return reader(root)
        with patch.object(recovery, '_read_recovery', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'COPY_EVIDENCE_CHANGED'): self.verify()

    def test_injected_source_change_between_reads_rejected(self):
        self.preserve(); snapshot = quality.source_snapshot()
        with patch.object(quality, 'source_snapshot', side_effect=[snapshot, {**snapshot, 'changed.py': '0' * 64}]):
            with self.assertRaisesRegex(ValueError, 'COPY_EVIDENCE_CHANGED'): self.verify()

    def test_cli_after_original_removed_preserves_incomplete_status(self):
        self.preserve(); shutil.rmtree(self.source); result = self.cli()
        self.assertEqual(result.returncode, 1); self.assertEqual(result.stderr, b'')
        r = json.loads(result.stdout); self.assertEqual(r['captured_input_state'], 'INCOMPLETE_NO_MARKER')
        self.assertFalse(r['original_current_state_checked'])
        for private in (b'a-private-name', b'private-lab-content', str(self.root).encode()):
            self.assertNotIn(private, result.stdout)

    def test_cli_complete_capture_returns_zero_without_authentication(self):
        self.complete(); self.preserve(); shutil.rmtree(self.source); result = self.cli()
        self.assertEqual(result.returncode, 0); self.assertEqual(result.stderr, b'')
        self.assertFalse(json.loads(result.stdout)['producer_authenticated'])

    def test_cli_invalid_external_anchor_returns_two_without_private_content(self):
        self.preserve(); self.args['input_anchor'] = '0' * 64; result = self.cli()
        self.assertEqual(result.returncode, 2); self.assertEqual(result.stderr, b'')
        self.assertEqual(json.loads(result.stdout), {'state': 'PRESERVED_COPY_REJECTED'})


if __name__ == '__main__': unittest.main()
