"""Returned native sync evidence: reject altered facts even after rehashing."""
import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_termux_sync_evidence as audit
ARCHIVE = ROOT / 'evidence/termux-sync-20261022/received.tar.gz'


class SyncEvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data = audit.read_archive(ARCHIVE)

    def pack(self, changes=None, omit=None, extra=None, rehash=True):
        d = {**self.data, **(changes or {})}
        if omit: d.pop(omit)
        if rehash:
            d['SHA256SUMS'] = ''.join(f'{audit.sha(v)}  ./{k}\n' for k, v in sorted(d.items()) if k != 'SHA256SUMS').encode()
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'evidence.tar.gz'
        with tarfile.open(path, 'w:gz') as t:
            for n, v in d.items():
                m = tarfile.TarInfo('evidence/' + n); m.size = len(v); t.addfile(m, io.BytesIO(v))
            if extra: t.addfile(extra, io.BytesIO(b''))
        return path

    def reject(self, changes=None, **kwargs):
        with self.assertRaises((audit.AuditError, ValueError)):
            audit.audit(self.pack(changes, **kwargs))

    def changed(self, name, mutate):
        v = json.loads(self.data[name]); mutate(v)
        return {name: json.dumps(v).encode()}

    def test_original_all_attempts_sources_snapshot_and_restart(self):
        r = audit.audit(ARCHIVE)
        self.assertEqual(r['manifest_files_verified'], 74)
        self.assertEqual(r['attempts_verified'], 16)
        self.assertEqual(len(r['client_checks_passed']), 17)
        self.assertEqual(r['snapshot_rows_verified']['ledger'], 24)
        self.assertEqual(r['snapshot_rows_verified']['eligible_ledger'], 12)
        self.assertTrue(r['final_shutdown_confirmed'])
        self.assertFalse(r['production_integration'])

    def test_missing_nested_file_duplicate_or_traversal(self):
        self.reject(omit='attempts/initial/attempt.json')
        for name in ['evidence/result.json', 'evidence/../outside', '/absolute', 'evidence/attempts/unlisted/x']:
            self.reject(extra=tarfile.TarInfo(name))
        m = tarfile.TarInfo('evidence/linked'); m.type = tarfile.SYMTYPE; m.linkname = '/tmp/x'
        self.reject(extra=m)
        self.reject({'server.log': b'x' * 1_000_001})

    def test_bad_manifest_and_rehashed_inputs(self):
        self.reject({'runtime.log': b'fake'}, rehash=False)
        for n in ['collection_transport.py', 'postgres.sql', 'fixtures.sql', 'postgres_transport_runtime.py', 'transport-source.json']:
            self.reject({n: self.data[n] + b'\n'})

    def test_durable_attempt_hashes_bind_request_target_and_generated_sql(self):
        for field in ['request_sha256', 'manifest_sha256', 'target_sha256', 'sql_sha256', 'receipt_sha256']:
            self.reject(self.changed('attempts/initial/attempt.json', lambda v: v.update({field: '0'*64})))

    def test_consistent_fake_ack_still_rejected(self):
        changes = self.changed('attempts/initial/result.json', lambda v: v['acknowledgment']['stored_receipt'].update(request_sha256='0'*64))
        runtime = json.loads(self.data['runtime-results.json']); runtime['results']['initial'] = json.loads(changes['attempts/initial/result.json'])
        changes['runtime-results.json'] = json.dumps(runtime).encode(); self.reject(changes)

    def test_false_success_after_lost_ack_rejected(self):
        changes = self.changed('attempts/lost-ack/result.json', lambda v: v.update(commit_confirmed=True))
        runtime = json.loads(self.data['runtime-results.json']); runtime['results']['lost-ack'] = json.loads(changes['attempts/lost-ack/result.json'])
        changes['runtime-results.json'] = json.dumps(runtime).encode(); self.reject(changes)
        self.reject(self.changed('fault-lost-ack-underlying.json', lambda v: v.update(returncode=2)))

    def test_fault_program_and_actual_sql_are_bound(self):
        self.reject({'fault-before-commit.py': self.data['fault-before-commit.py'].replace(b'pg_sleep(30)', b'pg_sleep(1)')})
        self.reject({'fault-lost-ack-input.sha256': b'0'*64+b'\n'})
        self.reject({'fault-before-commit-input.sha256': b'0'*64+b'\n'})

    def test_timeout_must_have_observed_owned_precommit_backend(self):
        self.reject(self.changed('timeout-observed-wait.json', lambda v: v.update(pid=1)))
        self.reject(self.changed('timeout-observed-wait.json', lambda v: v.update(wait_event='ClientRead')))
        self.reject({'timeout-owned-backends.json': b'[1]'})

    def test_revoked_rows_cannot_reappear_even_with_consistent_restart(self):
        snap = json.loads(self.data['before-restart.json']); snap['eligible_ledger'].append(copy.deepcopy(snap['ledger'][0]))
        raw = json.dumps(snap).encode(); self.reject({'before-restart.json': raw, 'after-restart.json': raw})

    def test_original_payload_and_disabled_relay_preserved(self):
        for table, field, value in [('ledger', 'raw_line', '\\x00'), ('outbox', 'delivery_enabled', True), ('runs', 'signing_enabled', True)]:
            snap = json.loads(self.data['before-restart.json']); snap[table][0][field] = value
            raw = json.dumps(snap).encode(); self.reject({'before-restart.json': raw, 'after-restart.json': raw})

    def test_numeric_boolean_and_duplicate_json_rejected(self):
        self.reject(self.changed('result.json', lambda v: v.update(production_integration=0)))
        self.reject({'result.json': self.data['result.json'].replace(b'"status":"pass"', b'"status":"fail","status":"pass"')})

    def test_unexpected_errors_network_and_missing_shutdown(self):
        self.reject({'server.log': self.data['server.log'] + b'\n[999] ERROR: unexpected\n'})
        self.reject({'server.log': self.data['server.log'] + b'\nlistening on IPv4\n'})
        self.reject({'shutdown.log': b''})
        self.reject({'postgresql.conf': self.data['postgresql.conf'] + b'\nfsync=off\n'})


if __name__ == '__main__': unittest.main()
