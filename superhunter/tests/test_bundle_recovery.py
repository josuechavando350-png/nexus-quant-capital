"""Preserve real local bytes without repairing or approving the source bundle."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bundle_recovery as recovery, quality, safe_io


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.source = self.root / 'input'; self.source.mkdir()
        (self.source / 'data.json').write_bytes(b'{"interrupted":')
        self.out = self.root / 'saved'
        self.digest = quality.sha(safe_io.canonical(quality.source_snapshot()))
        self.input_anchor = recovery.inspect(self.source)['input_anchor']

    def preserve(self):
        return recovery.preserve(self.source, self.out, source_digest=self.digest, input_anchor=self.input_anchor)

    def verify(self, **changes):
        return recovery.verify(self.source, self.out, **{'source_digest': self.digest, 'input_anchor': self.input_anchor,
            'recovery_anchor': quality.sha((self.out / 'COMPLETE.json').read_bytes()), **changes})

    def reseal(self, name, raw):
        (self.out / name).write_bytes(raw)
        marker = json.loads((self.out / 'COMPLETE.json').read_bytes()); marker['sha256'][name] = quality.sha(raw)
        (self.out / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))

    def complete(self):
        shutil.rmtree(self.source); safe_io.write_new_bundle(self.source, {'data.json': b'{}'})
        self.input_anchor = recovery.inspect(self.source)['input_anchor']

    def test_preservation_does_not_complete_or_change_input(self):
        before = recovery._capture(self.source)
        result = self.preserve(); self.assertEqual(self.verify(), result)
        self.assertEqual(recovery._capture(self.source), before)
        self.assertFalse((self.source / 'COMPLETE.json').exists())
        self.assertEqual((self.out / 'observed-000.bin').read_bytes(), b'{"interrupted":')
        self.assertEqual(result['assessment']['state'], 'INCOMPLETE_NO_MARKER')
        self.assertTrue(all(v is False for v in result['limitations'].values()))

    def test_empty_input_remains_unknown_not_completed(self):
        (self.source / 'data.json').unlink(); self.input_anchor = recovery.inspect(self.source)['input_anchor']
        result = self.preserve(); self.assertEqual(self.verify(), result)
        self.assertEqual(result['mapping'], []); self.assertIsNone(result['assessment']['expected_payload_files'])
        self.assertEqual(result['assessment']['state'], 'INCOMPLETE_NO_MARKER')

    def test_complete_input_is_not_semantically_approved(self):
        self.complete(); result = self.preserve(); self.assertEqual(self.verify(), result)
        self.assertEqual(result['assessment']['state'], 'BUNDLE_BYTES_COMPLETE')
        self.assertFalse(result['limitations']['semantic_validation_performed'])

    def test_truncated_marker_is_preserved_as_invalid(self):
        (self.source / 'COMPLETE.json').write_bytes(b'{"schema_version":')
        self.input_anchor = recovery.inspect(self.source)['input_anchor']
        result = self.preserve(); self.assertEqual(self.verify(), result)
        self.assertEqual(result['assessment']['state'], 'INVALID_MARKER')

    def test_duplicate_boolean_and_unknown_marker_fields_remain_invalid(self):
        values = [b'{"schema_version":1,"schema_version":1}',
                  safe_io.canonical({'schema_version': True, 'sha256': {'data.json': '0' * 64}}),
                  safe_io.canonical({'schema_version': 1, 'sha256': {}, 'extra': True})]
        for raw in values:
            (self.source / 'COMPLETE.json').write_bytes(raw)
            self.assertEqual(recovery.inspect(self.source)['assessment']['state'], 'INVALID_MARKER')

    def test_missing_mismatched_and_unexpected_files_are_distinct(self):
        self.complete(); marker = json.loads((self.source / 'COMPLETE.json').read_bytes())
        marker['sha256']['missing.bin'] = '0' * 64
        (self.source / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))
        (self.source / 'data.json').write_bytes(b'different'); (self.source / 'extra.bin').write_bytes(b'extra')
        assessment = recovery.inspect(self.source)['assessment']
        self.assertEqual(assessment['state'], 'CONTENT_MISMATCH')
        self.assertEqual(assessment['missing_files'], ['missing.bin'])
        self.assertEqual(assessment['mismatched_files'], ['data.json'])
        self.assertEqual(assessment['unexpected_files'], ['extra.bin'])

    def test_pending_marker_conflict_cannot_be_ignored(self):
        self.complete(); (self.source / safe_io.PENDING_MARKER).write_bytes(b'different')
        self.assertEqual(recovery.inspect(self.source)['assessment']['state'], 'PENDING_MARKER_CONFLICT')

    def test_cleanup_pending_is_not_silently_repaired(self):
        self.complete(); os.link(self.source / 'COMPLETE.json', self.source / safe_io.PENDING_MARKER)
        self.input_anchor = recovery.inspect(self.source)['input_anchor']
        result = self.preserve(); self.assertEqual(self.verify(), result)
        self.assertEqual(result['assessment']['state'], 'COMMIT_CLEANUP_PENDING')
        self.assertTrue((self.source / safe_io.PENDING_MARKER).exists())

    def test_wrong_input_anchor_prevents_output_creation(self):
        with self.assertRaisesRegex(ValueError, 'RECOVERY_INPUT_ANCHOR'):
            recovery.preserve(self.source, self.out, source_digest=self.digest, input_anchor='0' * 64)
        self.assertFalse(self.out.exists())

    def test_all_verifier_anchors_are_required(self):
        self.preserve()
        for key in ('source_digest', 'input_anchor', 'recovery_anchor'):
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(**{key: '0' * 64})

    def test_promoted_recovery_report_rejected_even_with_new_manifest(self):
        self.preserve(); report = json.loads((self.out / 'recovery.json').read_bytes())
        report['assessment']['state'] = 'BUNDLE_BYTES_COMPLETE'
        self.reseal('recovery.json', safe_io.canonical(report))
        with self.assertRaisesRegex(ValueError, 'RECOVERY_PACKAGE_CONTENT'): self.verify()

    def test_changed_saved_bytes_with_rehashed_manifest_rejected(self):
        self.preserve(); self.reseal('observed-000.bin', b'fabricated complete data')
        with self.assertRaisesRegex(ValueError, 'RECOVERY_PACKAGE_CONTENT'): self.verify()

    def test_unknown_package_file_is_rejected(self):
        self.preserve(); (self.out / 'extra').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'RECOVERY_PACKAGE_INVENTORY'): self.verify()

    def test_changed_source_after_inspection_is_rejected(self):
        (self.source / 'data.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'RECOVERY_INPUT_ANCHOR'): self.preserve()
        self.assertFalse(self.out.exists())

    def test_change_during_capture_rejected(self):
        original = recovery.read_artifact
        def changed(root, name):
            raw = original(root, name)
            if root == self.source: (root / name).write_bytes(raw + b'change')
            return raw
        with patch.object(recovery, 'read_artifact', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'RECOVERY_INPUT_CHANGED'): recovery.inspect(self.source)

    def test_change_after_preservation_is_detected_and_not_reported_successful(self):
        original = recovery.write_new_bundle
        def changed(out, files):
            original(out, files); (self.source / 'data.json').write_bytes(b'changed after copy')
        with patch.object(recovery, 'write_new_bundle', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'RECOVERY_INPUT_CHANGED_AFTER_WRITE'): self.preserve()
        self.assertTrue(self.out.exists())  # Retain bytes for review; never erase evidence.
        with self.assertRaises(ValueError): self.verify()

    def test_symlink_nested_directory_and_fifo_are_rejected(self):
        for kind in ('symlink', 'directory', 'fifo'):
            path = self.source / 'bad'
            if kind == 'symlink': path.symlink_to(self.root / 'missing')
            elif kind == 'directory': path.mkdir()
            else: os.mkfifo(path)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'RECOVERY_REGULAR_FILES_ONLY'):
                recovery.inspect(self.source)
            if kind == 'directory': path.rmdir()
            else: path.unlink()

    def test_overlap_existing_and_repository_output_rejected(self):
        self.out.mkdir()
        for out in (self.out, self.source / 'nested', self.root, recovery.owned_capture.ROOT / 'new'):
            with self.subTest(out=out), self.assertRaises(ValueError):
                recovery.preserve(self.source, out, source_digest=self.digest, input_anchor=self.input_anchor)

    def test_symlinked_source_root_rejected(self):
        link = self.root / 'link'; link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError): recovery.inspect(link)

    def test_file_count_and_total_byte_budgets_are_checked(self):
        (self.source / 'second').write_bytes(b'x')
        with patch.object(recovery, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'RECOVERY_INVENTORY'): recovery.inspect(self.source)
        with patch.object(recovery, 'MAX_TOTAL_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'RECOVERY_TOTAL_BYTES'): recovery.inspect(self.source)

    def test_cli_preserves_nonzero_for_incomplete_source(self):
        command = [sys.executable, '-B', '-m', 'superhunter']; repo = recovery.owned_capture.ROOT
        def call(args):
            result = subprocess.run(command + args, cwd=repo, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stderr, b''); return json.loads(result.stdout)
        inspected = call(['inspect-local-bundle', '--source', str(self.source)])
        made = call(['preserve-local-bundle', '--source', str(self.source), '--out', str(self.out),
                     '--source-digest', self.digest, '--input-anchor', inspected['input_anchor']])
        verified = call(['verify-preserved-bundle', '--source', str(self.source), '--bundle', str(self.out),
                         '--source-digest', self.digest, '--input-anchor', self.input_anchor,
                         '--recovery-anchor', made['recovery_anchor']])
        self.assertEqual(verified['state'], 'INCOMPLETE_NO_MARKER')


if __name__ == '__main__': unittest.main()
