"""Offline preparation with the actual Rust verifier; never emulates PostgreSQL."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

import prepare_postgres_import as importer
import test_export_parquet as fixtures
from export_parquet import ExportError

DB_ID = 'dfb1a49f-38d1-40ab-b19d-90a9577271be'


class PreparePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.topic = json.loads(subprocess.check_output([str(cls.binary), 'topics']))['morpho-blue'][1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nqc-miner-import-prepare-')
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.output = self.root / 'prepared'

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, **kwargs):
        return fixtures.ParquetExportTests.fixture(self, **({'version': 2} | kwargs))

    def prepare(self, **kwargs):
        return importer.prepare_import(self.state, self.output, self.binary, DB_ID, **kwargs)

    def test_exact_source_rows_and_transport_with_real_rust_verification(self):
        lines = self.fixture()
        before = {p.name: p.read_bytes() for p in self.state.iterdir()}
        manifest = self.prepare()
        request = json.loads((self.output / 'request.json').read_bytes())
        self.assertEqual([bytes.fromhex(row['raw_line_hex']) for row in request['records']], lines)
        self.assertEqual(bytes.fromhex(request['original_owner_hex']), before['owner.json'])
        self.assertEqual(bytes.fromhex(request['original_config_hex']), before['config.json'])
        self.assertEqual(request['journal_sha256'], hashlib.sha256(b''.join(lines)).hexdigest())
        self.assertEqual(manifest['records'], 3)
        self.assertFalse(manifest['database_applied'])
        self.assertFalse(manifest['delivery_enabled'])
        self.assertFalse(manifest['authenticity_verified'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.state.iterdir()})
        hex_payload = re.search(r"decode\('([0-9a-f]+)', 'hex'\)", (self.output / 'import.sql').read_text())[1]
        self.assertEqual(json.loads(bytes.fromhex(hex_payload)), request)
        for filename, key in [('request.json','request_sha256'), ('import.sql','sql_sha256')]:
            self.assertEqual(hashlib.sha256((self.output/filename).read_bytes()).hexdigest(), manifest[key])

    def test_repeated_preparation_is_deterministic(self):
        self.fixture()
        self.prepare()
        first_request = (self.output / 'request.json').read_bytes()
        first_sql = (self.output / 'import.sql').read_bytes()
        self.output = self.root / 'second'
        self.prepare()
        self.assertEqual(first_request, (self.output / 'request.json').read_bytes())
        self.assertEqual(first_sql, (self.output / 'import.sql').read_bytes())

    def test_canonical_owner_hash_is_distinct_from_original_whitespace(self):
        lines = self.fixture()
        owner_path = self.state / 'owner.json'
        owner_path.write_text(json.dumps(json.loads(owner_path.read_bytes()), indent=3, sort_keys=True)+'\n')
        manifest = self.prepare()
        self.assertEqual(manifest['owner_sha256'], json.loads(lines[0])['owner_sha256'])
        self.assertNotEqual(manifest['owner_sha256'], manifest['original_owner_sha256'])

    def test_invalidation_is_retained_and_never_silently_filtered(self):
        lines = self.fixture(invalidated=True)
        manifest = self.prepare()
        request = json.loads((self.output/'request.json').read_bytes())
        self.assertTrue(manifest['contains_invalidation'])
        self.assertEqual(manifest['records'],4)
        self.assertEqual(request['records'][-1]['record_kind'], 'invalidated')
        self.assertEqual(bytes.fromhex(request['records'][-1]['raw_line_hex']), lines[-1])

    def test_empty_verified_journal_has_no_invented_records(self):
        self.fixture(empty=True)
        manifest = self.prepare()
        self.assertEqual(manifest['records'],0)
        self.assertEqual(manifest['journal_sha256'],hashlib.sha256(b'').hexdigest())

    def test_legacy_owner_is_rejected_before_creating_output(self):
        self.fixture(version=1)
        with self.assertRaisesRegex(ExportError,'v2'): self.prepare()
        self.assertFalse(self.output.exists())

    def test_unbound_or_malformed_database_uuid_is_rejected(self):
        self.fixture()
        for bad in ('',None,True,DB_ID.upper(),'0'*32,'00000000-0000-0000-0000-000000000000',"x'; DROP SCHEMA public; --"):
            with self.subTest(value=bad),self.assertRaises(ExportError):
                importer.prepare_import(self.state,self.output,self.binary,bad)
        self.assertFalse(self.output.exists())

    def test_foreign_identity_and_mixed_build_do_not_create_import(self):
        self.fixture()
        path = self.state/'owner.json'; original = path.read_bytes()
        for before,after in ((b'nqc_miner_v1',b'observer'),(b'3'*64,b'4'*64)):
            path.write_bytes(original.replace(before,after))
            with self.assertRaises(ExportError): self.prepare()
            self.assertFalse((self.output/'manifest.json').exists())
            if self.output.exists():
                self.output = self.root/'different'

    def test_actual_rust_rejects_corruption_without_completion_manifest(self):
        self.fixture()
        path = self.state/'events.jsonl'
        path.write_bytes(path.read_bytes().replace(b'"observed_at":110',b'"observed_at":111',1))
        with self.assertRaisesRegex(ExportError,'Rust verifier rejected'): self.prepare()
        self.assertFalse((self.output/'manifest.json').exists())
        self.assertFalse((self.output/'import.sql').exists())

    def test_changed_copy_after_verification_is_rejected(self):
        self.fixture()
        original = importer.export_journal
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            path = args[1]/'source/config.json'
            path.write_bytes(path.read_bytes()+b' ')
            return result
        with mock.patch.object(importer,'export_journal',side_effect=changed):
            with self.assertRaisesRegex(ExportError,'source bytes changed'): self.prepare()
        self.assertFalse((self.output/'manifest.json').exists())

    def test_overwrite_overlap_and_symlink_cannot_touch_foreign_files(self):
        self.fixture()
        self.output.mkdir(); sentinel=self.output/'untouched.txt';sentinel.write_text('keep')
        with self.assertRaises(ExportError): self.prepare()
        self.assertEqual(sentinel.read_text(),'keep')
        with self.assertRaises(ExportError):
            importer.prepare_import(self.state,self.state/'nested',self.binary,DB_ID)
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ExportError):
            importer.prepare_import(self.state,alias/'new-output',self.binary,DB_ID)

    def test_resource_bounds_are_strict(self):
        self.fixture()
        for kwargs in ({'maximum_bytes':True},{'maximum_records':1.5},{'maximum_bytes':importer.MAX_BYTES+1},
                       {'maximum_records':0},{'maximum_records':1},{'maximum_bytes':1}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ExportError): self.prepare(**kwargs)
            self.assertFalse((self.output/'manifest.json').exists())
            self.output=self.root/('next-'+str(len(list(self.root.iterdir()))))

    def test_raw_payload_cannot_escape_sql_hex_literal(self):
        request={'attack':"'); COMMIT; DROP SCHEMA public; --\\n\\! command\n$miner$",'unicode':'ñ漢字'}
        sql=importer.transaction_sql(request).decode()
        self.assertNotIn('DROP SCHEMA',sql)
        self.assertNotIn('\\! command',sql)
        self.assertEqual(sql.count('COMMIT;'),1)
        encoded=re.search(r"decode\('([0-9a-f]+)', 'hex'\)",sql)[1]
        self.assertEqual(json.loads(bytes.fromhex(encoded)),request)


if __name__=='__main__':
    unittest.main()
