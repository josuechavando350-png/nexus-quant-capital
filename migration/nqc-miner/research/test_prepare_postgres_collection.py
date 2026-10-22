"""Actual Rust/Polars preparation tests; fixtures are invented, not market data."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import archive_collection as archive
import prepare_postgres_collection as collection
import test_archive_collection as fixtures
from export_parquet import ExportError

ARCHIVE_ID = '9ff8211f-7187-466f-8dfb-46b3df60795d'
DATABASE_ID = 'dfb1a49f-38d1-40ab-b19d-90a9577271be'


class PrepareCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.topic = json.loads(subprocess.check_output([str(cls.binary), 'topics']))['aave-v3'][0]

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='nqc-miner-collection-pg-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state, self.store, self.output = [self.root / n for n in ['source', 'archive', 'bundle']]
        self.config = fixtures.fixture(self.state, self.topic)
        archive.init_archive(self.store, ARCHIVE_ID)

    def capture(self):
        return archive.archive_collection(self.state, self.store, self.binary)['receipt']

    def prepare(self):
        return collection.prepare_collection(self.store, self.output, self.binary,
                                             ARCHIVE_ID, DATABASE_ID, self.config['run_id'])

    def revoke(self):
        fixtures.journal(self.state, self.config, [{'kind': 'invalidated', 'chain_id': 1,
                          'from_block': 10, 'reason': 'artificial collection revocation'}])

    def test_published_collection_reverified_and_preserves_every_source_byte(self):
        receipt = self.capture()
        before = {p.relative_to(self.store): p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
        result = self.prepare()
        request = json.loads((self.output / 'request.json').read_bytes())
        self.assertEqual((result['windows'], result['records']), (2, 4))
        self.assertEqual(result['receipt_sha256'], receipt['sha256'])
        self.assertFalse(result['database_applied'])
        for n in ['owner.json', 'config.json', 'collector.json', 'events.jsonl']:
            self.assertEqual((self.output / 'source' / n).read_bytes(), (self.state / n).read_bytes())
        for i, window in enumerate(request['windows']):
            self.assertEqual(window['index'], i)
            raw = b''.join(bytes.fromhex(r['raw_line_hex']) for r in window['journal']['records'])
            self.assertEqual(raw, (self.state / f'window-{i:020}/events.jsonl').read_bytes())
        self.assertEqual(before, {p.relative_to(self.store): p.read_bytes() for p in self.store.rglob('*') if p.is_file()})

    def test_latest_receipt_and_extension_selected_without_editing_prior_bundle(self):
        self.capture(); first = self.prepare()
        first_bytes = (self.output / 'request.json').read_bytes()
        fixtures.fixture(self.state, self.topic, windows=3)
        latest = self.capture(); old = self.output; self.output = self.root / 'extended'
        current = self.prepare()
        self.assertEqual(current['windows'], 3)
        self.assertGreater(current['receipt_sequence'], first['receipt_sequence'])
        self.assertEqual(current['receipt_sha256'], latest['sha256'])
        self.assertEqual((old / 'request.json').read_bytes(), first_bytes)

    def test_revocation_is_prepared_even_when_child_windows_are_missing(self):
        self.capture(); self.revoke(); shutil.rmtree(self.state / 'window-00000000000000000001')
        latest = self.capture(); result = self.prepare()
        self.assertEqual(result['status'], 'quarantined')
        self.assertEqual((result['windows'], result['records']), (0, 1))
        request = json.loads((self.output / 'request.json').read_bytes())
        self.assertEqual(request['windows'], [])
        self.assertEqual(request['control']['records'][0]['record_kind'], 'invalidated')
        self.assertEqual(result['receipt_sha256'], latest['sha256'])

    def test_revocation_can_be_first_published_receipt(self):
        self.revoke(); self.capture()
        self.assertEqual(self.prepare()['status'], 'quarantined')

    def test_unpublished_object_is_not_importable(self):
        with mock.patch.object(archive, 'publish_receipt', side_effect=OSError('injected publication failure')):
            with self.assertRaises(OSError): self.capture()
        with self.assertRaisesRegex(ExportError, 'no published'): self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_archive_database_and_run_are_rejected(self):
        self.capture()
        for aid, did, rid in [(DATABASE_ID, DATABASE_ID, self.config['run_id']),
                              (ARCHIVE_ID, '00000000-0000-0000-0000-000000000000', self.config['run_id']),
                              (ARCHIVE_ID, DATABASE_ID, 'not-published'), (ARCHIVE_ID, DATABASE_ID, '../other')]:
            with self.subTest(archive=aid, database=did, run=rid), self.assertRaises(ExportError):
                collection.prepare_collection(self.store, self.output, self.binary, aid, did, rid)
        self.assertFalse(self.output.exists())

    def test_existing_output_overlap_and_symlink_are_rejected(self):
        self.capture(); self.output.mkdir(); (self.output / 'keep').write_text('untouched')
        with self.assertRaises(ExportError): self.prepare()
        self.assertEqual((self.output / 'keep').read_text(), 'untouched')
        for target in [self.store / 'nested', self.root / 'alias']:
            if target.name == 'alias': target.symlink_to(self.output)
            with self.assertRaises(ExportError):
                collection.prepare_collection(self.store, target, self.binary, ARCHIVE_ID, DATABASE_ID, self.config['run_id'])

    def test_tampered_archive_or_busy_archive_never_prepared(self):
        receipt = self.capture()
        with archive.archive_lock(self.store):
            with self.assertRaisesRegex(ExportError, 'busy'): self.prepare()
        source = self.store / 'objects' / receipt['snapshot_sha256'] / 'source/config.json'
        source.write_bytes(source.read_bytes() + b' ')
        with self.assertRaisesRegex(ExportError, 'changed'): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())

    def test_reactivation_with_rehashed_receipt_chain_is_rejected(self):
        original = self.capture(); self.revoke(); revoked = self.capture()
        forged = {k: v for k, v in original.items() if k != 'sha256'}
        forged.update(sequence=2, previous_sha256=revoked['sha256'])
        forged['sha256'] = fixtures.digest(archive.packed(forged))
        (self.store / 'commits/00000000000000000002.json').write_bytes(archive.packed(forged)+b'\n')
        with self.assertRaisesRegex(ExportError, 'permanent'): self.prepare()

    def test_changed_private_copy_after_verification_is_rejected(self):
        self.capture(); original = collection.journal.prepare_import
        def alter(*args, **kwargs):
            result = original(*args, **kwargs)
            p = self.output / 'source/config.json'; p.write_bytes(p.read_bytes() + b' ')
            return result
        with mock.patch.object(collection.journal, 'prepare_import', side_effect=alter):
            with self.assertRaisesRegex(ExportError, 'changed'): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())

    def test_partial_failure_does_not_publish_manifest_or_sql(self):
        self.capture(); original = collection.journal.prepare_import
        def fail(*args, **kwargs):
            if args[0].name.startswith('window-'): raise ExportError('injected child failure')
            return original(*args, **kwargs)
        with mock.patch.object(collection.journal, 'prepare_import', side_effect=fail):
            with self.assertRaisesRegex(ExportError, 'child failure'): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())
        self.assertFalse((self.output / 'import.sql').exists())

    def test_child_request_changed_after_its_manifest_is_rejected(self):
        self.capture(); original = collection.journal.prepare_import
        def alter(*args, **kwargs):
            result = original(*args, **kwargs)
            p = args[1] / 'request.json'; p.write_bytes(p.read_bytes() + b' ')
            return result
        with mock.patch.object(collection.journal, 'prepare_import', side_effect=alter):
            with self.assertRaisesRegex(ExportError, 'changed before collection binding'): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())

    def test_windows_source_records_and_request_have_aggregate_bounds(self):
        self.capture()
        for field, value in [('MAX_WINDOWS', 1), ('MAX_SOURCE_BYTES', 1), ('MAX_REQUEST_BYTES', 1)]:
            with self.subTest(bound=field), mock.patch.object(collection, field, value):
                with self.assertRaises(ExportError): self.prepare()
            self.assertFalse((self.output / 'manifest.json').exists())
            self.output = self.root / ('next-' + field)
        with mock.patch.object(collection.journal, 'MAX_RECORDS', 3):
            with self.assertRaises(ExportError): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())

    def test_repeat_is_deterministic_and_sql_payload_cannot_escape(self):
        self.capture(); self.prepare(); first = (self.output / 'request.json').read_bytes()
        self.output = self.root / 'again'; self.prepare()
        self.assertEqual(first, (self.output / 'request.json').read_bytes())
        encoded = re.search(r"decode\('([0-9a-f]+)', 'hex'\)", (self.output / 'import.sql').read_text())[1]
        self.assertEqual(json.loads(bytes.fromhex(encoded)), json.loads(first))
        payload = {'attack': "'); DROP SCHEMA public; --\n\\! command", 'unicode': 'ñ漢字'}
        sql = collection.transaction_sql(payload).decode()
        self.assertNotIn('DROP SCHEMA', sql); self.assertNotIn('\\! command', sql)
        self.assertEqual(sql.count('COMMIT;'), 1)


if __name__ == '__main__':
    unittest.main()
