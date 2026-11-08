"""Closed private ZIP transport using real bytes; mutations are declared controls."""
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

from superhunter import bundle_recovery as recovery, portable_copy as portable, quality, safe_io


class PortableCopyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.source = self.root / 'source'; self.source.mkdir()
        (self.source / 'private-input-name.json').write_bytes(b'{"private-lab-data":')
        (self.source / 'binary.bin').write_bytes(b'\xff\x00\xfe')
        self.bundle = self.root / 'preserved'; self.archive = self.root / 'portable.zip'
        self.digest = quality.sha(safe_io.canonical(quality.source_snapshot()))
        self.preserve()

    def preserve(self):
        if self.bundle.exists(): shutil.rmtree(self.bundle)
        anchor = recovery.inspect(self.source)['input_anchor']
        r = recovery.preserve(self.source, self.bundle, source_digest=self.digest, input_anchor=anchor)
        self.args = {'source_digest': self.digest, 'input_anchor': anchor, 'recovery_anchor': r['recovery_anchor']}

    def make(self, **changes):
        return portable.export(self.bundle, self.archive, **{**self.args, 'include_private_bytes': True, **changes})

    def verify(self, **changes):
        return portable.verify(self.archive, **{**self.args, 'archive_anchor': quality.sha(self.archive.read_bytes()), **changes})

    def complete(self):
        shutil.rmtree(self.source); safe_io.write_new_bundle(self.source, {'private-input-name.json': b'private-lab-data'})
        self.preserve()

    def data(self): return recovery._read_recovery(self.bundle)

    def write_packet(self, saved):
        marker = {'schema_version': 1, 'sha256': {n: quality.sha(v) for n, v in saved.items() if n != 'COMPLETE.json'}}
        saved['COMPLETE.json'] = safe_io.canonical(marker)
        self.args['recovery_anchor'] = quality.sha(saved['COMPLETE.json'])
        self.archive.write_bytes(portable._encode(saved))

    def custom_zip(self, entries, *, compression=zipfile.ZIP_STORED, stamp=portable.STAMP, comment=b''):
        out = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(out, 'w') as z:
                z.comment = comment
                for name, raw in entries:
                    info = zipfile.ZipInfo(name, date_time=stamp); info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o600) << 16; info.compress_type = compression
                    z.writestr(info, raw)
        self.archive.write_bytes(out.getvalue())

    def cli(self, command, **changes):
        args = [sys.executable, '-B', '-m', 'superhunter', command]
        values = {**self.args, **changes}
        for name, value in values.items():
            args.append('--' + name.replace('_', '-'))
            if value is not True: args.append(str(value))
        return subprocess.run(args, cwd=quality.ROOT.parent, capture_output=True, timeout=20)

    def test_archive_verifies_after_source_and_copy_are_removed(self):
        result = self.make(); before = self.archive.read_bytes()
        shutil.rmtree(self.source); shutil.rmtree(self.bundle)
        checked = self.verify(archive_anchor=result['archive_anchor'])
        self.assertEqual(checked['state'], 'PRESERVED_ARCHIVE_VERIFIED')
        self.assertEqual(checked['captured_input_state'], 'INCOMPLETE_NO_MARKER')
        self.assertFalse(checked['source_bundle_current_state_checked'])
        self.assertFalse(checked['original_current_state_checked']); self.assertFalse(checked['original_restored'])
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertFalse(self.source.exists()); self.assertFalse(self.bundle.exists())

    def test_private_bytes_need_explicit_acknowledgment(self):
        for flag in (False, None, 1, 'yes'):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'PRIVATE_BYTES_ACK_REQUIRED'):
                self.make(include_private_bytes=flag)
            self.assertFalse(self.archive.exists())

    def test_deterministic_export_keeps_source_exact_and_private_mode(self):
        original = recovery._capture(self.source); saved = self.data(); result = self.make()
        first = self.archive.read_bytes(); self.archive = self.root / 'second.zip'; second = self.make()
        self.assertEqual(first, self.archive.read_bytes()); self.assertEqual(result['archive_anchor'], second['archive_anchor'])
        self.assertEqual(recovery._capture(self.source), original); self.assertEqual(self.data(), saved)
        self.assertEqual(stat.S_IMODE(self.archive.stat().st_mode), 0o600)
        self.assertTrue(result['private_original_bytes_included']); self.assertTrue(result['source_bundle_current_state_checked'])
        self.assertFalse(result['encrypted']); self.assertFalse(result['redacted'])

    def test_complete_capture_is_not_authenticated_or_semantically_approved(self):
        self.complete(); self.make(); r = self.verify()
        self.assertEqual(r['captured_input_state'], 'BUNDLE_BYTES_COMPLETE')
        for name in ('producer_authenticated', 'execution_authenticated', 'semantic_validation_performed'):
            self.assertFalse(r[name])

    def test_empty_original_retains_incomplete_state(self):
        for p in self.source.iterdir(): p.unlink()
        self.preserve(); self.make(); r = self.verify()
        self.assertEqual(r['observed_files'], 0); self.assertEqual(r['captured_input_state'], 'INCOMPLETE_NO_MARKER')

    def test_invalid_original_marker_stays_invalid(self):
        (self.source / 'COMPLETE.json').write_bytes(b'{"interrupted":')
        self.preserve(); self.make()
        self.assertEqual(self.verify()['captured_input_state'], 'INVALID_MARKER')

    def test_existing_archive_never_overwritten(self):
        self.archive.write_bytes(b'keep this file')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_NEW_FILE'): self.make()
        self.assertEqual(self.archive.read_bytes(), b'keep this file')

    def test_export_cannot_write_inside_source_bundle(self):
        self.archive = self.bundle / 'extra.zip'
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_OUTPUT_OVERLAP'): self.make()
        self.assertFalse(self.archive.exists())

    def test_output_symlink_and_symlink_parent_rejected(self):
        target = self.root / 'target'; target.write_bytes(b'unchanged'); self.archive.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SYMLINK'): self.make()
        self.assertEqual(target.read_bytes(), b'unchanged')
        self.archive.unlink(); link = self.root / 'alias'; link.symlink_to(self.root, target_is_directory=True)
        self.archive = link / 'another.zip'
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SYMLINK'): self.make()

    def test_archive_symlink_fifo_and_checkout_path_rejected(self):
        self.make(); target = self.archive; self.archive = self.root / 'alias.zip'; self.archive.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SYMLINK'): self.verify()
        self.archive.unlink(); os.mkfifo(self.archive)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILE'):
            portable.verify(self.archive, **self.args, archive_anchor='0' * 64)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_REPOSITORY_OVERLAP'):
            portable.verify(quality.ROOT / 'safe_io.py', **self.args, archive_anchor='0' * 64)

    def test_verifier_does_not_extract_read_source_or_execute(self):
        self.make(); shutil.rmtree(self.source); shutil.rmtree(self.bundle)
        with patch.object(zipfile.ZipFile, 'extract', side_effect=AssertionError('extract')), \
             patch.object(zipfile.ZipFile, 'extractall', side_effect=AssertionError('extractall')), \
             patch.object(recovery, '_read_recovery', side_effect=AssertionError('source read')), \
             patch('subprocess.Popen', side_effect=AssertionError('execution')):
            self.assertEqual(self.verify()['state'], 'PRESERVED_ARCHIVE_VERIFIED')

    def test_archive_can_be_moved_without_source_paths(self):
        result = self.make(); moved = self.root / 'renamed.zip'; self.archive.rename(moved); self.archive = moved
        self.assertEqual(self.verify(archive_anchor=result['archive_anchor'])['state'], 'PRESERVED_ARCHIVE_VERIFIED')

    def test_changed_archive_rejected_by_external_archive_anchor(self):
        r = self.make(); self.archive.write_bytes(self.archive.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_ANCHOR'): self.verify(archive_anchor=r['archive_anchor'])

    def test_corrupt_crc_rejected_even_with_new_archive_anchor(self):
        self.make(); raw = bytearray(self.archive.read_bytes())
        position = raw.index(b'{'); raw[position] = ord('['); self.archive.write_bytes(raw)
        with self.assertRaises(zipfile.BadZipFile): self.verify()

    def test_duplicate_archive_entries_rejected(self):
        entries = list(self.data().items()); self.custom_zip(entries + [entries[0]])
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_INVENTORY'): self.verify()

    def test_traversal_nested_and_unexpected_archive_names_rejected(self):
        entries = list(self.data().items())
        for name in ('../outside', '/absolute', 'folder/observed-000.bin', 'unknown.bin'):
            self.custom_zip(entries + [(name, b'inert fixture')])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'ARCHIVE_INVENTORY'): self.verify()
        self.assertEqual({p.name for p in self.root.iterdir()}, {'source', 'preserved', 'portable.zip'})

    def test_compression_is_rejected_before_opening_member_data(self):
        self.custom_zip(list(self.data().items()), compression=zipfile.ZIP_DEFLATED)
        with patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('member opened')):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_ENTRY'): self.verify()

    def test_directory_count_bound_checked_before_zipfile_allocation(self):
        self.make(); raw = self.archive.read_bytes(); fields = list(struct.unpack('<4s4H2LH', raw[-22:]))
        fields[3] = fields[4] = portable.MAX_ENTRIES + 1
        self.archive.write_bytes(raw[:-22] + struct.pack('<4s4H2LH', *fields))
        with patch.object(zipfile, 'ZipFile', side_effect=AssertionError('directory allocated')):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_DIRECTORY'): self.verify()

    def test_entry_size_and_total_budget_rejected(self):
        saved = self.data(); saved['observed-000.bin'] = b'x' * (safe_io.MAX_BYTES + 1)
        self.archive.write_bytes(portable._encode(saved))
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_ENTRY'): self.verify()
        self.archive.write_bytes(portable._encode(self.data()))
        with patch.object(portable, 'MAX_PACKAGE_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_TOTAL_BYTES'): self.verify()

    def test_archive_file_budget_checked_before_parsing(self):
        self.make()
        with patch.object(portable, 'MAX_ARCHIVE_BYTES', 22):
            with patch.object(portable, '_decode', side_effect=AssertionError('decoded')):
                with self.assertRaisesRegex(ValueError, 'ARCHIVE_BYTES'): self.verify()

    def test_comments_suffix_and_noncanonical_timestamps_rejected(self):
        entries = list(self.data().items())
        self.custom_zip(entries, comment=b'comment')
        with self.assertRaises(ValueError): self.verify()
        self.custom_zip(entries, stamp=(2026, 1, 1, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_ENTRY'): self.verify()
        self.archive.write_bytes(portable._encode(self.data()) + b'suffix')
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_DIRECTORY'): self.verify()

    def test_out_of_order_equivalent_archive_rejected(self):
        self.custom_zip(sorted(self.data().items(), reverse=True))
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_NONCANONICAL'): self.verify()

    def test_resealed_changed_content_cannot_replace_input_anchor(self):
        saved = self.data(); saved['observed-000.bin'] += b'altered'
        report = json.loads(saved['recovery.json'])
        report['mapping'][0].update(bytes=len(saved['observed-000.bin']), sha256=quality.sha(saved['observed-000.bin']))
        saved['recovery.json'] = safe_io.canonical(report); self.write_packet(saved)
        with self.assertRaisesRegex(ValueError, 'COPY_INPUT_ANCHOR'): self.verify()

    def test_resealed_promoted_report_rejected(self):
        saved = self.data(); report = json.loads(saved['recovery.json'])
        report['assessment']['state'] = 'BUNDLE_BYTES_COMPLETE'; saved['recovery.json'] = safe_io.canonical(report)
        self.write_packet(saved)
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.verify()

    def test_wrong_input_recovery_and_source_anchors_prevent_export(self):
        for key in self.args:
            with self.subTest(key=key), self.assertRaises(ValueError): self.make(**{key: '0' * 64})
            self.assertFalse(self.archive.exists())

    def test_injected_archive_change_between_reads_rejected(self):
        self.make(); reader = portable._read; calls = 0
        def changed(path):
            nonlocal calls
            calls += 1
            if calls == 2: path.write_bytes(path.read_bytes() + b'changed during read')
            return reader(path)
        with patch.object(portable, '_read', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_EVIDENCE_CHANGED'): self.verify()

    def test_injected_source_change_between_reads_rejected(self):
        self.make(); snapshot = quality.source_snapshot()
        with patch.object(quality, 'source_snapshot', side_effect=[snapshot, {**snapshot, 'changed.py': '0' * 64}]):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_EVIDENCE_CHANGED'): self.verify()

    def test_sync_failure_never_reports_export_success(self):
        with patch.object(portable.os, 'fsync', side_effect=OSError('injected sync failure')):
            with self.assertRaises(OSError): self.make()
        # Full bytes may remain after a failed fsync. Byte validity is NOT a
        # claim that the exporter returned successfully or that power loss is safe.
        self.assertTrue(self.archive.exists())
        self.assertEqual(self.verify()['state'], 'PRESERVED_ARCHIVE_VERIFIED')

    def test_source_change_after_write_rejects_and_retains_output(self):
        verify = portable.verify
        def changed(*args, **kwargs):
            result = verify(*args, **kwargs)
            saved = self.data(); saved['REVIEW.md'] += b'changed'
            marker = json.loads(saved['COMPLETE.json']); marker['sha256']['REVIEW.md'] = quality.sha(saved['REVIEW.md'])
            (self.bundle / 'REVIEW.md').write_bytes(saved['REVIEW.md'])
            (self.bundle / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))
            return result
        with patch.object(portable, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_SOURCE_CHANGED_AFTER_WRITE'): self.make()
        self.assertTrue(self.archive.exists()); self.assertEqual(self.verify()['state'], 'PRESERVED_ARCHIVE_VERIFIED')

    def test_cli_preserves_incomplete_state_and_private_output(self):
        made = self.cli('export-preserved-copy', bundle=self.bundle, out=self.archive, include_private_bytes=True)
        self.assertEqual(made.returncode, 1); self.assertEqual(made.stderr, b'')
        r = json.loads(made.stdout); shutil.rmtree(self.source); shutil.rmtree(self.bundle)
        checked = self.cli('verify-preserved-archive', archive=self.archive, archive_anchor=r['archive_anchor'])
        self.assertEqual(checked.returncode, 1); self.assertEqual(checked.stderr, b'')
        self.assertEqual(json.loads(checked.stdout)['captured_input_state'], 'INCOMPLETE_NO_MARKER')
        for secret in (b'private-input-name', b'private-lab-data', str(self.root).encode()):
            self.assertNotIn(secret, made.stdout); self.assertNotIn(secret, checked.stdout)

    def test_cli_acknowledgment_missing_rejects_without_file(self):
        result = self.cli('export-preserved-copy', bundle=self.bundle, out=self.archive)
        self.assertEqual(result.returncode, 2); self.assertEqual(result.stderr, b'')
        self.assertFalse(self.archive.exists()); self.assertEqual(json.loads(result.stdout)['state'], 'PRESERVED_ARCHIVE_REJECTED')

    def test_cli_complete_archive_returns_zero(self):
        self.complete(); made = self.cli('export-preserved-copy', bundle=self.bundle, out=self.archive, include_private_bytes=True)
        self.assertEqual(made.returncode, 0)
        checked = self.cli('verify-preserved-archive', archive=self.archive, archive_anchor=json.loads(made.stdout)['archive_anchor'])
        self.assertEqual(checked.returncode, 0); self.assertFalse(json.loads(checked.stdout)['producer_authenticated'])

    def test_cli_invalid_anchor_returns_two(self):
        self.make(); checked = self.cli('verify-preserved-archive', archive=self.archive, archive_anchor='0' * 64)
        self.assertEqual(checked.returncode, 2); self.assertEqual(checked.stderr, b'')
        self.assertEqual(json.loads(checked.stdout), {'state': 'PRESERVED_ARCHIVE_REJECTED'})


    def legacy_metadata(self):
        # Synthetic producer identity for unit tests, not a historical execution.
        # Acceptance separately uses unchanged PR98 packages actually saved earlier.
        saved = self.data(); report = json.loads(saved['recovery.json']); report['source_digest'] = '1' * 64
        saved['recovery.json'] = safe_io.canonical(report)
        saved['COMPLETE.json'] = safe_io.canonical({'schema_version': 1, 'sha256':
            {n: quality.sha(v) for n, v in saved.items() if n != 'COMPLETE.json'}})
        for name in ('recovery.json', 'COMPLETE.json'): (self.bundle / name).write_bytes(saved[name])
        self.args['recovery_anchor'] = quality.sha(saved['COMPLETE.json'])
        return '1' * 64

    def test_explicit_earlier_identity_keeps_history_and_current_reader_separate(self):
        old = self.legacy_metadata(); before = self.data()
        made = self.make(preserved_source_digest=old); checked = self.verify(preserved_source_digest=old)
        self.assertEqual(made['source_digest'], self.digest); self.assertEqual(checked['source_digest'], self.digest)
        self.assertEqual(made['preserved_source_digest'], old); self.assertEqual(checked['preserved_source_digest'], old)
        self.assertEqual(self.data(), before); self.assertEqual(portable._decode(self.archive.read_bytes()), before)
        self.assertFalse(checked['producer_authenticated'])

    def test_earlier_identity_is_not_inferred_from_untrusted_report(self):
        self.legacy_metadata()
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.make()
        self.assertFalse(self.archive.exists())

    def test_wrong_earlier_identity_rejected_even_with_valid_archive_anchor(self):
        old = self.legacy_metadata(); self.make(preserved_source_digest=old)
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.verify(preserved_source_digest='2' * 64)

    def test_earlier_identity_cannot_replace_current_reader_pin(self):
        old = self.legacy_metadata()
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SOURCE'):
            self.make(source_digest=old, preserved_source_digest=old)
        self.assertFalse(self.archive.exists())

    def test_earlier_identity_does_not_enable_unknown_report_profiles(self):
        old = self.legacy_metadata(); report = json.loads((self.bundle / 'recovery.json').read_bytes())
        report['profile'] = 'unknown-history-profile'; raw = safe_io.canonical(report)
        (self.bundle / 'recovery.json').write_bytes(raw)
        marker = json.loads((self.bundle / 'COMPLETE.json').read_bytes()); marker['sha256']['recovery.json'] = quality.sha(raw)
        (self.bundle / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))
        self.args['recovery_anchor'] = quality.sha((self.bundle / 'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'COPY_PACKAGE_CONTENT'): self.make(preserved_source_digest=old)
        self.assertFalse(self.archive.exists())

    def test_output_sibling_of_checkout_allowed_without_touching_checkout(self):
        checkout = self.root / 'checkout'; checkout.mkdir(); (checkout / 'keep').write_bytes(b'unchanged')
        with patch.object(portable.owned_capture, 'ROOT', checkout):
            self.make(); self.assertEqual(self.verify()['state'], 'PRESERVED_ARCHIVE_VERIFIED')
        self.assertEqual({p.name for p in checkout.iterdir()}, {'keep'})
        self.assertEqual((checkout / 'keep').read_bytes(), b'unchanged')

    def test_cli_reports_both_current_and_preserved_identities(self):
        old = self.legacy_metadata()
        made = self.cli('export-preserved-copy', bundle=self.bundle, out=self.archive,
                        include_private_bytes=True, preserved_source_digest=old)
        self.assertEqual(made.returncode, 1); self.assertEqual(made.stderr, b'')
        checked = self.cli('verify-preserved-archive', archive=self.archive,
                           archive_anchor=json.loads(made.stdout)['archive_anchor'], preserved_source_digest=old)
        self.assertEqual(checked.returncode, 1); self.assertEqual(checked.stderr, b'')
        result = json.loads(checked.stdout)
        self.assertEqual(result['source_digest'], self.digest); self.assertEqual(result['preserved_source_digest'], old)


if __name__ == '__main__': unittest.main()
