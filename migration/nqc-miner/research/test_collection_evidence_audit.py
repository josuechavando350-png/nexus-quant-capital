"""Tamper regressions for returned collection evidence; no server is launched."""
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_termux_collection_evidence as audit

ARCHIVE = ROOT / 'evidence/termux-collection-20261022/received.tar.gz'


class CollectionEvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = audit.read_archive(ARCHIVE)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'altered.tar.gz'

    def pack(self, changes=None, omit=None, rehash=True, extra=None):
        data = {**self.data, **(changes or {})}
        if omit:
            data.pop(omit)
        if rehash:
            data['SHA256SUMS'] = ''.join(f'{audit.sha(v)}  ./{k}\n' for k, v in sorted(data.items())
                                        if k != 'SHA256SUMS').encode()
        with tarfile.open(self.path, 'w:gz') as archive:
            for name, value in data.items():
                member = tarfile.TarInfo('evidence/' + name)
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
            if extra:
                archive.addfile(extra, io.BytesIO(b''))
        return self.path

    def reject(self, changes, **kwargs):
        with self.assertRaises(audit.AuditError):
            audit.audit(self.pack(changes, **kwargs))

    def test_original_source_outcomes_and_all_snapshot_rows(self):
        result = audit.audit(ARCHIVE)
        self.assertEqual(result['manifest_files_verified'], 44)
        self.assertEqual(len(result['sql_checks_passed']), 33)
        self.assertEqual(result['import_responses_verified'], 14)
        self.assertEqual(result['snapshot_rows_verified'], {'runs': 20, 'ledger': 29, 'outbox': 29, 'quarantine': 3, 'collections': 7, 'windows': 13, 'receipts': 9, 'revocations': 4, 'eligible_ledger': 12, 'eligible_outbox': 12, 'identity': 1})
        self.assertTrue(result['final_shutdown_confirmed'])
        self.assertFalse(result['production_integration'])

    def test_manifest_damage_missing_file_and_duplicate_entries(self):
        self.reject({'cases.log': self.data['cases.log'] + b'changed'}, rehash=False)
        self.reject({}, omit='interruption.json')
        self.reject({'SHA256SUMS': self.data['SHA256SUMS'] + self.data['SHA256SUMS'].splitlines(keepends=True)[0]}, rehash=False)

    def test_archive_paths_links_duplicate_and_size_are_bounded(self):
        duplicate = tarfile.TarInfo('evidence/result.json')
        traversal = tarfile.TarInfo('evidence/../outside')
        link = tarfile.TarInfo('evidence/link')
        link.type, link.linkname = tarfile.SYMTYPE, '../../outside'
        for member in [duplicate, traversal, link]:
            with self.subTest(path=member.name):
                self.reject({}, extra=member)
        self.reject({'server.log': b'x' * 1_000_001})

    def test_rehashed_foreign_input_and_runner_rejected(self):
        for name in ['postgres.sql', 'postgres_import.sql', 'postgres_collection.sql', 'fixtures.sql', 'fixture-verification.json', 'cases.sql', 'holder.sql']:
            with self.subTest(name=name):
                self.reject({name: self.data[name] + b'\n'})
        self.reject({'runner.sha256': self.data['runner.sha256'].replace(b'a425', b'0000', 1)})

    def test_labels_and_actual_return_values_both_required(self):
        for value in [self.data['cases.log'].replace(b'MINER_COLLECTION_PASS: initial_two_windows', b'MINER_COLLECTION_PASS: unknown'),
                      self.data['cases.log'] + b'MINER_COLLECTION_PASS: initial_two_windows\n',
                      self.data['cases.log'].replace(b'"inserted": 2', b'"inserted": 0', 1)]:
            self.reject({'cases.log': value})

    def test_guard_and_permission_sqlstates_required(self):
        for name, state in [('writer-denials.log', b'42501'), ('outsider-denial.log', b'42501'),
                            ('wrong-database.log', b'P0001'), ('duplicate-collection.log', b'42P07')]:
            with self.subTest(name=name):
                self.reject({name: self.data[name].replace(state, b'XX000')})

    def test_concurrency_requires_waiters_and_distinct_outcomes(self):
        self.reject({'concurrent-2.json': self.data['concurrent-1.json']})
        self.reject({'holder.log': b'DO\n'})
        self.reject({'concurrent-1.stderr': b'connection failed\n'})

    def test_interruption_requires_rollback_and_valid_retry(self):
        self.reject({'interruption.json': self.data['interruption.json'].replace(b'true', b'false', 1)})
        self.reject({'interruption-retry.json': self.data['interruption-retry.json'].replace(b'"inserted": 4', b'"inserted": 0')})
        self.reject({'terminate-session.txt': b'f\n'})
        self.reject({'server.log': self.data['server.log'].replace(b"name='interrupt'; SELECT pg_sleep", b"name='other'; SELECT pg_sleep")})

    def test_matching_restart_snapshots_still_must_match_original_fixtures(self):
        mutations = [
            lambda s: s['ledger'][0].update(raw_line='\\x00'),
            lambda s: s['runs'][0].update(original_owner='\\x00'),
            lambda s: s['outbox'][0].update(payload='\\x00'),
            lambda s: s['quarantine'][0].update(reason='owner_conflict'),
            lambda s: s['ledger'].pop(),
            lambda s: s['runs'][0].update(observer_bridge_enabled=True),
            lambda s: s['outbox'][0].update(delivery_enabled=0),
            lambda s: s.update(registry=[]),
            lambda s: s['windows'][0].update(record_count=3),
            lambda s: s['windows'][0].update(parent_run_id='pgcoll_normal'),
            lambda s: s['collections'][0].update(archive_id='00000000-0000-4000-8000-000000000001'),
            lambda s: s['collections'][0].update(collector_bytes='\\x00'),
            lambda s: s['revocations'].pop(),
            lambda s: s['revocations'][0].update(reason='parent_invalidated'),
            lambda s: s['eligible_ledger'].append(s['ledger'][0]),
            lambda s: s['eligible_outbox'][0].update(payload='\\x00'),
            lambda s: s['eligible_outbox'][0].update(created_at='2026-10-22T00:00:00Z'),
            lambda s: s['identity'][0].update(singleton=1),
            lambda s: s['runs'][0].update(created_at='2025-01-01T00:00:00Z'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                snapshot = json.loads(self.data['before-restart.json'])
                mutate(snapshot)
                raw = json.dumps(snapshot).encode()
                self.reject({'before-restart.json': raw, 'after-restart.json': raw})
        self.reject({'after-restart.json': self.data['after-restart.json'] + b' '})

    def test_network_authentication_and_durability(self):
        changes = [
            {'postgresql.conf': self.data['postgresql.conf'] + b"\nlisten_addresses = '*'\n"},
            {'postgresql.conf': self.data['postgresql.conf'] + b'\nfsync = off\n'},
            {'postgresql.conf': self.data['postgresql.conf'] + b"\ninclude = 'external.conf'\n"},
            {'pg_hba.conf': self.data['pg_hba.conf'].replace(b'peer', b'trust')},
        ]
        for change in changes:
            self.reject(change)

    def test_shutdown_and_unexpected_server_errors(self):
        self.reject({'shutdown.log': b'shutdown requested\n'})
        self.reject({'startup.log': self.data['startup.log'].replace(b'database system is shut down', b'database stopping')})
        self.reject({'server.log': self.data['server.log'] + b' [99999] FATAL: unexpected\n'})
        self.reject({'server.log': self.data['server.log'] + b' [99999] ERROR: unexpected\n'})

    def test_json_duplicate_nonfinite_and_boolean_integer_confusion(self):
        raw = self.data['result.json']
        for value in [raw.replace(b'"status":"pass"', b'"status":"failed","status":"pass"'),
                      raw.replace(b'"production_integration":false', b'"production_integration":0'),
                      raw.replace(b'"production_integration":false', b'"production_integration":NaN')]:
            self.reject({'result.json': value})


    def test_receipt_bytes_status_order_and_jsonb_request_binding(self):
        for field, value in [('original_receipt', '\\x00'), ('original_snapshot', '\\x00'),
                             ('request_sha256', '0' * 64), ('receipt_sha256', '0' * 64),
                             ('receipt_sequence', 99), ('source_status', 'quarantined'),
                             ('applied_status', 'quarantined')]:
            with self.subTest(field=field):
                snapshot = json.loads(self.data['before-restart.json'])
                snapshot['receipts'][0][field] = value
                raw = json.dumps(snapshot).encode()
                self.reject({'before-restart.json': raw, 'after-restart.json': raw})

    def test_jsonb_ordering_nested_unicode_and_unsupported_numbers(self):
        self.assertEqual(audit.jsonb_text({'bb': [True, None, {'é': 2, 'a': 3}], 'b': 1, 'aa': 0}),
                         '{"b": 1, "aa": 0, "bb": [true, null, {"a": 3, "é": 2}]}')
        with self.assertRaises(audit.AuditError):
            audit.jsonb_text({'a': 1.5})


if __name__ == '__main__':
    unittest.main()
