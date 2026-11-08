"""Real archive indexing; deliberately changed files are explicit local controls."""
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from superhunter import bundle_recovery as recovery, portable_copy as portable, preserved_index as index, quality, safe_io


class PreservedIndexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.archives = self.root / 'archives'; self.archives.mkdir()
        self.manifest = self.root / 'private-list.json'; self.out = self.root / 'index'
        self.digest = quality.sha(safe_io.canonical(quality.source_snapshot()))
        self.records = []
        self.add_archive('one', complete=True)
        self.save_manifest()

    def add_archive(self, name, *, complete=False, producer=None):
        source = self.root / (name + '-source')
        if complete: safe_io.write_new_bundle(source, {'data.bin': b'private-controlled-payload'})
        else:
            source.mkdir(); (source / 'data.bin').write_bytes(b'private-controlled-payload')
        bundle = self.root / (name + '-saved')
        input_anchor = recovery.inspect(source)['input_anchor']
        preserved = recovery.preserve(source, bundle, source_digest=self.digest, input_anchor=input_anchor)
        declared = producer or self.digest
        if producer:
            # Synthetic historical identity control, not execution of an earlier producer.
            saved = recovery._read_recovery(bundle); report = json.loads(saved['recovery.json'])
            report['source_digest'] = producer; saved['recovery.json'] = safe_io.canonical(report)
            marker = safe_io.canonical({'schema_version': 1, 'sha256': {n: quality.sha(v) for n, v in saved.items() if n != 'COMPLETE.json'}})
            (bundle / 'recovery.json').write_bytes(saved['recovery.json']); (bundle / 'COMPLETE.json').write_bytes(marker)
            preserved['recovery_anchor'] = quality.sha(marker)
        result = portable.export(bundle, self.archives / (name + '.zip'), source_digest=self.digest,
                                 input_anchor=input_anchor, recovery_anchor=preserved['recovery_anchor'],
                                 preserved_source_digest=declared, include_private_bytes=True)
        self.records.append({'id': name, 'file': name + '.zip', **{key: result[key] for key in index.PINS}})
        shutil.rmtree(source); shutil.rmtree(bundle)

    def save_manifest(self):
        self.records.sort(key=lambda row: row['id'])
        self.value = {'schema_version': 1, 'profile': index.MANIFEST_PROFILE, 'archives': self.records}
        self.manifest.write_bytes(safe_io.canonical(self.value))
        self.anchor = quality.sha(self.manifest.read_bytes())

    def build(self, **changes):
        return index.build(**{'manifest': self.manifest, 'archive_root': self.archives, 'out': self.out,
                              'source_digest': self.digest, 'manifest_anchor': self.anchor, **changes})

    def verify(self, **changes):
        return index.verify(**{'bundle': self.out, 'archive_root': self.archives, 'source_digest': self.digest,
                               'manifest_anchor': self.anchor, 'index_anchor': quality.sha((self.out / 'COMPLETE.json').read_bytes()), **changes})

    def alter_index(self, mutation):
        report = json.loads((self.out / 'index.json').read_bytes()); mutation(report)
        (self.out / 'index.json').write_bytes(safe_io.canonical(report))
        self.reseal()

    def reseal(self):
        marker = {'schema_version': 1, 'sha256': {p.name: quality.sha(p.read_bytes()) for p in self.out.iterdir() if p.name != 'COMPLETE.json'}}
        (self.out / 'COMPLETE.json').write_bytes(safe_io.canonical(marker))

    def alias(self):
        row = {**self.records[0], 'id': 'alias', 'file': 'alias.zip'}
        shutil.copyfile(self.archives / self.records[0]['file'], self.archives / row['file'])
        self.records.append(row); self.save_manifest()

    def cli(self, command, **changes):
        args = [sys.executable, '-B', '-m', 'superhunter', command]
        values = {'source_digest': self.digest, 'manifest_anchor': self.anchor, 'archive_root': self.archives, **changes}
        for name, value in values.items(): args.extend(['--' + name.replace('_', '-'), str(value)])
        return subprocess.run(args, cwd=quality.ROOT.parent, capture_output=True, timeout=30)

    def test_complete_collection_has_no_authenticity_claim(self):
        r = self.build(); checked = self.verify(index_anchor=r['index_anchor'])
        self.assertEqual(checked['state'], 'PRESERVED_INDEX_VERIFIED')
        self.assertEqual(checked['counts']['complete_unique_archives'], 1)
        for name in index.LIMITS: self.assertIs(checked[name], False)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        for path in self.out.iterdir(): self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_aliases_do_not_count_as_independent_evidence(self):
        self.alias(); r = self.build()
        self.assertEqual(r['counts']['entries'], 2); self.assertEqual(r['counts']['unique_archives'], 1)
        self.assertEqual(r['counts']['unique_input_inventories'], 1)
        self.assertEqual(r['counts']['duplicate_archive_entries'], 1)
        self.assertEqual(r['counts']['listed_archive_bytes'], 2 * r['counts']['unique_archive_bytes'])
        self.assertFalse(r['independent_experiments_proved'])
        report = json.loads((self.out / 'index.json').read_bytes())
        self.assertEqual(report['archive_groups'][0]['ids'], ['alias', 'one'])

    def test_distinct_archives_same_original_are_grouped_separately(self):
        self.add_archive('two', complete=True, producer='1' * 64); self.save_manifest()
        c = self.build()['counts']
        self.assertEqual((c['entries'], c['unique_archives'], c['unique_input_inventories']), (2, 2, 1))

    def test_incomplete_capture_is_retained_without_promotion(self):
        self.add_archive('two'); self.save_manifest(); c = self.build()['counts']
        self.assertEqual((c['complete_unique_archives'], c['incomplete_unique_archives']), (1, 1))
        rows = json.loads((self.out / 'index.json').read_bytes())['archives']
        self.assertEqual(rows[1]['captured_input_state'], 'INCOMPLETE_NO_MARKER')

    def test_inputs_and_archives_unchanged_and_external_manifest_can_be_removed(self):
        before = {p.name: p.read_bytes() for p in self.archives.iterdir()}; manifest = self.manifest.read_bytes()
        self.build(); self.assertEqual(self.manifest.read_bytes(), manifest); self.manifest.unlink()
        self.assertEqual(self.verify()['counts']['entries'], 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.archives.iterdir()})

    def test_collection_and_index_can_be_relocated(self):
        self.build(); moved = self.root / 'moved'; self.archives.rename(moved); self.archives = moved
        moved_index = self.root / 'moved-index'; self.out.rename(moved_index); self.out = moved_index
        self.assertEqual(self.verify()['state'], 'PRESERVED_INDEX_VERIFIED')

    def test_missing_or_changed_archive_rejects_entire_collection(self):
        self.build(); path = self.archives / 'one.zip'; raw = path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError): self.verify()
        path.write_bytes(raw + b'changed')
        with self.assertRaisesRegex(ValueError, 'INDEX_ARCHIVE_ANCHOR'): self.verify()

    def test_archive_alias_with_conflicting_pin_is_rejected(self):
        self.alias(); self.records[0]['input_anchor'] = '0' * 64; self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'COPY_INPUT_ANCHOR'): self.build()
        self.assertFalse(self.out.exists())

    def test_each_external_anchor_is_required(self):
        self.build()
        for key in ('source_digest', 'manifest_anchor', 'index_anchor'):
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify(**{key: '0' * 64})

    def test_resealed_count_inflation_is_rejected(self):
        self.build(); self.alter_index(lambda r: r['counts'].update(unique_archives=100))
        with self.assertRaisesRegex(ValueError, 'INDEX_CONTENT'): self.verify()

    def test_resealed_independence_and_completion_promotions_rejected(self):
        self.add_archive('two'); self.save_manifest(); self.build()
        original = (self.out / 'index.json').read_bytes()
        for mutation in (lambda r: r['limitations'].update(independent_experiments_proved=True),
                         lambda r: r['archives'][1].update(captured_input_state='BUNDLE_BYTES_COMPLETE')):
            self.alter_index(mutation)
            with self.assertRaisesRegex(ValueError, 'INDEX_CONTENT'): self.verify()
            (self.out / 'index.json').write_bytes(original); self.reseal()

    def test_resealed_review_changes_are_rejected(self):
        self.build(); (self.out / 'REVIEW.md').write_bytes(b'Everything is authenticated'); self.reseal()
        with self.assertRaisesRegex(ValueError, 'INDEX_CONTENT'): self.verify()

    def test_extra_index_file_and_pending_marker_rejected(self):
        self.build()
        for name in ('unexpected.bin', safe_io.PENDING_MARKER):
            path = self.out / name; path.write_bytes(b'pending')
            with self.assertRaisesRegex(ValueError, 'INDEX_BUNDLE_INVENTORY'): self.verify()
            path.unlink()

    def test_index_with_missing_or_invalid_marker_rejected(self):
        self.build(); marker = self.out / 'COMPLETE.json'; marker.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'INDEX_BUNDLE_ANCHOR'): self.verify()
        marker.unlink()
        with self.assertRaises(ValueError): index.verify(self.out, self.archives, source_digest=self.digest,
                                                       manifest_anchor=self.anchor, index_anchor='0' * 64)

    def test_manifest_closed_schema_and_canonical_encoding(self):
        valid = self.manifest.read_bytes()
        candidates = [valid + b' ', b'{"schema_version":1,"schema_version":1}',
                      safe_io.canonical({**self.value, 'extra': True}),
                      safe_io.canonical({**self.value, 'schema_version': True}),
                      safe_io.canonical({**self.value, 'profile': 'other'})]
        for raw in candidates:
            self.manifest.write_bytes(raw)
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError): self.build(manifest_anchor=quality.sha(raw))
        self.assertFalse(self.out.exists())

    def test_duplicate_ids_or_filenames_rejected(self):
        row = self.records[0]
        for changed in ({**row, 'file': 'other.zip'}, {**row, 'id': 'two'}):
            value = {**self.value, 'archives': [row, changed]}; raw = safe_io.canonical(value)
            with self.assertRaisesRegex(ValueError, 'INDEX_DUPLICATE_RECORD'): index._manifest(raw, quality.sha(raw))

    def test_manifest_rejects_paths_invalid_ids_unknown_fields_and_bad_pins(self):
        row = self.records[0]
        cases = [{'file': name} for name in ('../one.zip', '/one.zip', 'dir/one.zip', 'a\\one.zip', '.hidden.zip', 'one.ZIP')]
        cases += [{'id': value} for value in ('', 'a b', 'ñ', 'a' * 65, True)]
        cases += [{'input_anchor': 'A' * 64}, {'extra': 1}]
        for change in cases:
            raw = safe_io.canonical({**self.value, 'archives': [{**row, **change}]})
            with self.subTest(change=change), self.assertRaises(ValueError): index._manifest(raw, quality.sha(raw))

    def test_empty_oversized_and_unsorted_manifest_records_rejected(self):
        row = self.records[0]
        for records in ([], [row] * 65, [{**row, 'id': 'z', 'file': 'z.zip'}, row]):
            raw = safe_io.canonical({**self.value, 'archives': records})
            with self.assertRaises(ValueError): index._manifest(raw, quality.sha(raw))

    def test_manifest_size_bound_before_read(self):
        self.manifest.write_bytes(b' ' * (index.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'INDEX_MANIFEST_BYTES'): self.build()

    def test_total_archive_budget_rejects_before_verification(self):
        with patch.object(index, 'MAX_TOTAL_BYTES', 1), patch.object(portable, 'verify', side_effect=AssertionError('verified')):
            with self.assertRaisesRegex(ValueError, 'INDEX_TOTAL_BYTES'): self.build()
        self.assertFalse(self.out.exists())

    def test_manifest_archive_and_index_symlinks_rejected(self):
        raw = self.manifest.read_bytes(); self.manifest.unlink(); real = self.root / 'real'; real.write_bytes(raw)
        self.manifest.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.build()
        self.manifest.unlink(); self.manifest.write_bytes(raw)
        p = self.archives / 'one.zip'; real_zip = self.root / 'real.zip'; p.rename(real_zip); p.symlink_to(real_zip)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.build()
        p.unlink(); real_zip.rename(p); self.build(); real_index = self.root / 'real-index'; self.out.rename(real_index)
        self.out.symlink_to(real_index, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'): self.verify()

    def test_manifest_fifo_rejected_without_blocking(self):
        self.manifest.unlink(); os.mkfifo(self.manifest)
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_FILE'): self.build()

    def test_output_never_overwrites_existing_directory(self):
        self.out.mkdir(); (self.out / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(ValueError): self.build()
        self.assertEqual((self.out / 'keep').read_bytes(), b'unchanged')

    def test_repository_inputs_and_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'REPOSITORY_OVERLAP'): self.build(manifest=quality.ROOT / 'quality.py')
        with self.assertRaisesRegex(ValueError, 'REPOSITORY_OVERLAP'): self.build(out=quality.ROOT / 'new-private-index')

    def test_earlier_archive_changed_during_later_verification_rejected(self):
        self.add_archive('two'); self.save_manifest(); real = portable.verify
        def changed(path, **kwargs):
            r = real(path, **kwargs)
            if path.name == 'two.zip':
                first = self.archives / 'one.zip'; first.write_bytes(first.read_bytes() + b'changed')
            return r
        with patch.object(portable, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INDEX_ARCHIVES_CHANGED'): self.build()
        self.assertFalse(self.out.exists())

    def test_same_bytes_replacement_during_verification_rejected(self):
        real = portable.verify
        def replaced(path, **kwargs):
            r = real(path, **kwargs); raw = path.read_bytes(); replacement = path.with_suffix('.replacement')
            replacement.write_bytes(raw); replacement.replace(path); return r
        with patch.object(portable, 'verify', side_effect=replaced):
            with self.assertRaisesRegex(ValueError, 'INDEX_ARCHIVES_CHANGED'): self.build()

    def test_manifest_change_during_archive_verification_rejected(self):
        real = portable.verify
        def changed(path, **kwargs):
            r = real(path, **kwargs); self.manifest.write_bytes(self.manifest.read_bytes() + b' '); return r
        with patch.object(portable, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INDEX_MANIFEST_CHANGED'): self.build()

    def test_source_change_after_collection_rejected(self):
        real = index._collect
        def collected(*args):
            result = real(*args)
            patcher = patch.object(quality, 'source_snapshot', return_value={'changed': True}); patcher.start()
            self.addCleanup(patcher.stop); return result
        with patch.object(index, '_collect', side_effect=collected):
            with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE_CHANGED'): self.build()

    def test_change_after_output_write_does_not_return_success_or_delete_output(self):
        real = index.write_new_bundle
        def written(*args):
            real(*args); p = self.archives / 'one.zip'; p.write_bytes(p.read_bytes() + b'changed')
        with patch.object(index, 'write_new_bundle', side_effect=written):
            with self.assertRaisesRegex(ValueError, 'INDEX_ARCHIVES_CHANGED'): self.build()
        self.assertTrue(self.out.exists())
        with self.assertRaises(ValueError): self.verify()

    def test_index_change_during_archive_verification_rejected(self):
        self.build(); real = portable.verify
        def changed(path, **kwargs):
            r = real(path, **kwargs); p = self.out / 'REVIEW.md'; p.write_bytes(p.read_bytes() + b'changed'); return r
        with patch.object(portable, 'verify', side_effect=changed):
            with self.assertRaises(ValueError): self.verify()

    def test_historical_index_identity_is_explicit_and_separate(self):
        self.build(); self.alter_index(lambda r: r.update(index_source_digest='2' * 64))
        with self.assertRaisesRegex(ValueError, 'INDEX_CONTENT'): self.verify()
        result = self.verify(index_source_digest='2' * 64)
        self.assertEqual(result['source_digest'], self.digest); self.assertEqual(result['index_source_digest'], '2' * 64)
        self.assertFalse(result['producer_authenticated'])
        with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE'): self.verify(source_digest='2' * 64, index_source_digest='2' * 64)

    def test_no_directory_discovery_extraction_or_execution(self):
        (self.archives / 'ignored.zip').write_bytes(b'unrelated data')
        with patch.object(zipfile.ZipFile, 'extractall', side_effect=AssertionError('extract')), \
             patch('subprocess.Popen', side_effect=AssertionError('execute')):
            self.assertEqual(self.build()['counts']['entries'], 1)

    def test_cli_complete_and_invalid_have_distinct_exit_codes(self):
        r = self.cli('index-preserved-archives', manifest=self.manifest, out=self.out)
        self.assertEqual(r.returncode, 0, r.stdout); result = json.loads(r.stdout)
        r = self.cli('verify-preserved-index', bundle=self.out, index_anchor=result['index_anchor'])
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.cli('verify-preserved-index', bundle=self.out, index_anchor='0' * 64)
        self.assertEqual(r.returncode, 2); self.assertEqual(json.loads(r.stdout), {'state': 'PRESERVED_INDEX_REJECTED'})

    def test_cli_mixed_collection_stays_incomplete_and_private(self):
        self.add_archive('two'); self.save_manifest()
        r = self.cli('index-preserved-archives', manifest=self.manifest, out=self.out)
        self.assertEqual(r.returncode, 1, r.stdout); result = json.loads(r.stdout)
        r = self.cli('verify-preserved-index', bundle=self.out, index_anchor=result['index_anchor'])
        self.assertEqual(r.returncode, 1, r.stdout)
        for private in (b'private-controlled-payload', b'private-list', b'one.zip', str(self.root).encode()):
            self.assertNotIn(private, r.stdout + r.stderr)


if __name__ == '__main__': unittest.main()
