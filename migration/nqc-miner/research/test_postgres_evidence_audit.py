"""Offline audit regressions; these never launch or simulate PostgreSQL."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pg_evidence_audit', ROOT / 'scripts/audit_termux_postgres_evidence.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
ARCHIVE = ROOT / 'evidence/termux-postgres-20261022/received.tar.gz'


class PostgresEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = audit.read_archive(ARCHIVE)

    def pack(self, changes=None, rehash=True, extra=None, omit=None):
        data = dict(self.data)
        data.update(changes or {})
        if omit:
            data.pop(omit)
        if rehash:
            data['SHA256SUMS'] = ''.join(f'{hashlib.sha256(value).hexdigest()}  ./{name}\n'
                for name, value in sorted(data.items()) if name != 'SHA256SUMS').encode()
        path = Path(self.temp.name) / 'changed.tar.gz'
        with tarfile.open(path, 'w:gz') as tar:
            for name, value in data.items():
                entry = tarfile.TarInfo('evidence/' + name)
                entry.size = len(value)
                tar.addfile(entry, io.BytesIO(value))
            if extra:
                tar.addfile(extra, io.BytesIO(b''))
        return path

    def test_returned_archive_matches_exact_source_and_results(self):
        result = audit.audit(ARCHIVE)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['manifest_files_verified'], 24)
        self.assertEqual(len(result['sql_checks_passed']), 30)
        self.assertFalse(result['real_journal_importer_executed'])

    def test_changed_payload_rejected_by_original_manifest(self):
        with self.assertRaises(audit.AuditError):
            audit.audit(self.pack({'cases.log': self.data['cases.log'] + b'changed'}, rehash=False))

    def test_missing_evidence_rejected_even_with_rehashed_manifest(self):
        with self.assertRaises(audit.AuditError):
            audit.audit(self.pack(omit='shutdown.log'))

    def test_duplicate_traversal_and_symlink_members_rejected(self):
        duplicate = tarfile.TarInfo('evidence/result.json')
        traversal = tarfile.TarInfo('evidence/../outside')
        link = tarfile.TarInfo('evidence/link')
        link.type = tarfile.SYMTYPE
        link.linkname = '../../outside'
        for entry in [duplicate, traversal, link]:
            with self.subTest(entry=entry.name), self.assertRaises(audit.AuditError):
                audit.audit(self.pack(extra=entry))

    def test_rehashed_false_sql_pass_or_wrong_state_is_rejected(self):
        changes = [
            {'cases.log': self.data['cases.log'].replace(b'MINER_PASS: dedicated_database', b'MINER_PASS: missing_case')},
            {'cases.log': self.data['cases.log'] + b'\nMINER_PASS: dedicated_database\n'},
            {'writer-denials.log': self.data['writer-denials.log'].replace(b'42501', b'23505')},
        ]
        for change in changes:
            with self.subTest(files=list(change)), self.assertRaises(audit.AuditError):
                audit.audit(self.pack(change))

    def test_rehashed_foreign_sql_or_runner_identity_is_rejected(self):
        for change in [{'postgres.sql': self.data['postgres.sql'] + b'-- changed\n'},
                       {'runner.sha256': b'0' * 64 + b'  /sdcard/Download/nqc-miner-postgres-check.sh\n'}]:
            with self.subTest(files=list(change)), self.assertRaises(audit.AuditError):
                audit.audit(self.pack(change))

    def test_changed_restart_snapshot_is_rejected(self):
        with self.assertRaises(audit.AuditError):
            audit.audit(self.pack({'after-restart.json': self.data['after-restart.json'] + b' '}))

    def test_network_authentication_and_shutdown_regressions_rejected(self):
        changes = [
            {'postgresql.conf': self.data['postgresql.conf'] + b"\nlisten_addresses = '*'\n"},
            {'pg_hba.conf': self.data['pg_hba.conf'].replace(b'peer', b'trust')},
            {'shutdown.log': b'shutdown requested but not confirmed\n'},
        ]
        for change in changes:
            with self.subTest(files=list(change)), self.assertRaises(audit.AuditError):
                audit.audit(self.pack(change))


if __name__ == '__main__':
    unittest.main()
