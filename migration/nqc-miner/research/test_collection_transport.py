"""Client protocol/fault tests. Fake psql is explicit; these do not execute SQL."""
import copy
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import collection_transport as transport


def fixtures():
    root = ROOT / 'evidence/termux-collection-20261022/execution'
    values = {name: transport.parse(bytes.fromhex(raw)) for name, raw in re.findall(
        r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);",
        (root / 'fixtures.sql').read_text())}
    return values, json.loads((root / 'fixture-verification.json').read_bytes())['fixtures']


def response(request, manifest, *, status='imported', inserted=None, quarantined=False, head=None):
    result = {'parent_run_id': manifest['run_id'], 'status': status,
              'inserted': manifest['records'] if inserted is None else inserted,
              'reason': None, 'receipt_sequence': manifest['receipt_sequence']}
    ack = {'schema': 'nqc-miner-collection-ack-v1', 'parent_run_id': manifest['run_id'],
           'database_id': manifest['database_id'], 'archive_id': manifest['archive_id'],
           'quarantined': quarantined,
           'head_sequence': manifest['receipt_sequence'] if head is None else head,
           'stored_receipt': {'receipt_sequence': manifest['receipt_sequence'],
              'receipt_sha256': manifest['receipt_sha256'], 'snapshot_sha256': manifest['snapshot_sha256'],
              'request_sha256': transport.sha(transport.jsonb_text(request).encode())}}
    if status == 'quarantined':
        result['reason'] = 'parent_invalidated'
    if status == 'stale' or (status == 'quarantined' and result['inserted'] == 0):
        result = {k: result[k] for k in ['parent_run_id', 'status', 'inserted']}
    return result, ack


class LocalClient:
    def __init__(self, root):
        self.root = root
        directory = root / 's'; directory.mkdir(mode=0o700)
        # The executor forbids socket creation. Model only the stat result at
        # this boundary; the fake process never connects or claims SQL execution.
        self.socket_path = directory / '.s.PGSQL.55435'
        self.socket_path.write_bytes(b'offline socket metadata fixture')
        original_stat = Path.stat
        def socket_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == self.socket_path:
                fields = list(result); fields[0] = stat.S_IFSOCK | 0o700
                return os.stat_result(fields)
            return result
        self.socket_patch = mock.patch.object(Path, 'stat', socket_stat)
        self.socket_patch.start()
        self.binary = root / 'fake-psql'
        self.target = {'schema': 'nqc-miner-local-postgres-target-v1',
            'database_id': 'dfb1a49f-38d1-40ab-b19d-90a9577271be',
            'archive_id': '9ff8211f-7187-466f-8dfb-46b3df60795d',
            'socket_directory': str(directory), 'port': 55435,
            'login_user': pwd.getpwuid(os.getuid()).pw_name, 'psql': str(self.binary), 'psql_sha256': ''}
        self.configure(b'')

    def configure(self, output, *, mode='normal', code=0):
        (self.root / 'reply').write_bytes(output)
        body = f'''#!{sys.executable}
import os,sys,json,time
from pathlib import Path
root=Path({str(self.root)!r})
(root/'sent.sql').write_bytes(sys.stdin.buffer.read())
(root/'child-env.json').write_text(json.dumps(dict(os.environ)))
(root/'child-args.json').write_text(json.dumps(sys.argv))
if {mode!r} == 'sleep': time.sleep(30)
if {mode!r} == 'flood':
    while True: sys.stdout.buffer.write(b'x'*8192); sys.stdout.buffer.flush()
sys.stdout.buffer.write((root/'reply').read_bytes());sys.stdout.buffer.flush()
if {code} != 0: sys.stderr.write('ERROR: XX000 credential-do-not-publish\\n')
raise SystemExit({code})
'''
        self.binary.write_text(body); self.binary.chmod(0o700)
        self.target['psql_sha256'] = transport.sha(self.binary.read_bytes())


class CollectionTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests, cls.reports = fixtures()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='nqc-ct-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.client = LocalClient(self.root); self.addCleanup(self.client.socket_patch.stop)
        self.bundle = self.root / 'bundle'; self.bundle.mkdir()
        self.select('normal-two')
        self.output = self.root / 'delivery'

    def select(self, name):
        self.request = copy.deepcopy(self.requests[name])
        self.manifest = copy.deepcopy(self.reports[name]['manifest'])
        (self.bundle / 'request.json').write_bytes(transport.packed(self.request) + b'\n')
        (self.bundle / 'manifest.json').write_bytes(transport.packed(self.manifest) + b'\n')
        self.reply = response(self.request, self.manifest)
        self.configure(self.reply)

    def configure(self, messages, **kwargs):
        self.client.configure(b'\n'.join(transport.packed(m) for m in messages) + b'\n', **kwargs)

    def apply(self, **kwargs):
        return transport.apply_bundle(self.bundle, self.client.target, self.output, **kwargs)

    def test_exact_source_pins_and_generated_sql_never_execute_bundle_sql(self):
        for name, digest in transport.FUNCTION_HASHES.items():
            file, tag = ('postgres_import.sql', 'miner') if name.endswith('journal') else ('postgres_collection.sql', 'collection')
            source = (ROOT / 'infra' / file).read_text()
            body = re.search(r'AS \$' + tag + r'\$(.*?)\$' + tag + r'\$;', source, re.S)[1]
            self.assertEqual(transport.sha(body.encode()), digest)
        (self.bundle / 'import.sql').write_text('\\! echo do-not-execute\n')
        value = self.apply()
        self.assertEqual(value['outcome'], 'applied'); self.assertTrue(value['commit_confirmed'])
        sql = (self.root / 'sent.sql').read_text()
        self.assertNotIn('do-not-execute', sql)
        self.assertLess(sql.index('COMMIT;'), sql.index("'nqc-miner-collection-ack-v1'"))
        self.assertEqual(json.loads((self.output / 'result.json').read_bytes()), value)
        self.assertEqual(json.loads((self.output / 'attempt.json').read_bytes())['outcome'], 'unknown')

    def test_ambient_connection_settings_are_removed_and_target_is_explicit(self):
        with mock.patch.dict(os.environ, {'PGHOST': 'foreign', 'PGHOSTADDR': '1.2.3.4',
            'PGDATABASE': 'observer', 'PGUSER': 'other', 'PGOPTIONS': '-c role=owner',
            'PGPASSWORD': 'credential-do-not-publish', 'PGSERVICE': 'foreign', 'PSQLRC': '/evil'}):
            self.assertEqual(self.apply()['outcome'], 'applied')
        env = json.loads((self.root / 'child-env.json').read_text())
        for name in ['PGHOST', 'PGHOSTADDR', 'PGDATABASE', 'PGUSER', 'PGOPTIONS', 'PGPASSWORD', 'PGSERVICE', 'PSQLRC']:
            self.assertNotIn(name, env)
        # libpq has no require_auth=peer; requirepeer binds the server's OS user.
        self.assertEqual(env['PGREQUIREAUTH'], 'none')
        self.assertEqual(env['PGREQUIREPEER'], self.client.target['login_user'])
        args = json.loads((self.root / 'child-args.json').read_text())
        self.assertEqual(args[args.index('-d') + 1], 'nqc_miner_v1')
        self.assertIn('-X', args); self.assertIn('-w', args)

    def test_result_before_commit_without_ack_is_unknown(self):
        self.configure([self.reply[0]])
        value = self.apply()
        self.assertEqual(value['outcome'], 'unknown'); self.assertFalse(value['commit_confirmed'])

    def test_nonzero_client_even_with_ack_is_unknown_and_redacted(self):
        self.configure(self.reply, code=3)
        value = self.apply()
        self.assertEqual(value['outcome'], 'unknown'); self.assertEqual(value['sqlstates'], ['XX000'])
        self.assertNotIn('credential-do-not-publish', (self.output / 'result.json').read_text())

    def test_wrong_ack_identity_or_receipt_never_confirms(self):
        changes = [('database_id', '0'*36), ('archive_id', '0'*36), ('parent_run_id', 'foreign'),
                   ('head_sequence', True), ('quarantined', 0), ('stored_receipt', None)]
        for index, (key, value) in enumerate(changes):
            with self.subTest(field=key):
                messages = copy.deepcopy(self.reply); messages[1][key] = value
                self.configure(messages); self.output = self.root / f'bad-{index}'
                self.assertEqual(self.apply()['outcome'], 'unknown')

    def test_json_ambiguity_extra_lines_and_boolean_counts_rejected(self):
        raw = b'\n'.join(transport.packed(m) for m in self.reply) + b'\n'
        for i, altered in enumerate([raw + b'{}\n', raw.replace(b'"inserted":4', b'"inserted":true'),
            raw.replace(b'"quarantined":false', b'"quarantined":true,"quarantined":false')]):
            self.client.configure(altered); self.output = self.root / f'json-{i}'
            self.assertEqual(self.apply()['outcome'], 'unknown')

    def test_quarantine_is_committed_but_not_success(self):
        self.select('normal-revoked')
        self.configure(response(self.request, self.manifest, status='quarantined', inserted=1, quarantined=True))
        value = self.apply()
        self.assertEqual(value['outcome'], 'quarantined'); self.assertTrue(value['commit_confirmed'])

    def test_quarantine_after_active_result_wins_and_stale_is_not_current(self):
        messages = copy.deepcopy(self.reply); messages[1]['quarantined'] = True
        self.configure(messages); self.assertEqual(self.apply()['outcome'], 'quarantined')
        self.output = self.root / 'stale'
        self.configure(response(self.request, self.manifest, status='stale', inserted=0, head=1))
        self.assertEqual(self.apply()['outcome'], 'superseded')

    def test_idempotent_reconciliation_and_newer_head(self):
        self.configure(response(self.request, self.manifest, status='idempotent', inserted=0))
        self.assertEqual(self.apply()['outcome'], 'applied')
        self.output = self.root / 'newer'
        self.configure(response(self.request, self.manifest, status='idempotent', inserted=0, head=1))
        self.assertEqual(self.apply()['outcome'], 'superseded')

    def test_request_manifest_and_target_mismatch_before_process(self):
        for i, field in enumerate(['database_id', 'archive_id', 'request_sha256', 'receipt_sha256', 'snapshot_sha256']):
            manifest = copy.deepcopy(self.manifest); manifest[field] = '0'*64
            (self.bundle / 'manifest.json').write_bytes(transport.packed(manifest))
            with self.subTest(field=field), self.assertRaises((transport.DeliveryError, ValueError)):
                self.apply()
            self.assertFalse(self.output.exists()); self.assertFalse((self.root / 'sent.sql').exists())

    def test_symlinks_socket_type_permissions_and_client_hash(self):
        path = self.root / 'alias'; path.symlink_to(self.bundle)
        with self.assertRaises(transport.DeliveryError): transport.apply_bundle(path, self.client.target, self.output)
        directory = Path(self.client.target['socket_directory']); directory.chmod(0o755)
        with self.assertRaises(transport.DeliveryError): self.apply()
        directory.chmod(0o700)
        self.client.target['psql_sha256'] = '0'*64
        with self.assertRaises(transport.DeliveryError): self.apply()
        self.assertFalse(self.output.exists())

    def test_unmocked_regular_file_cannot_replace_unix_socket(self):
        self.client.socket_patch.stop()
        with self.assertRaisesRegex(transport.DeliveryError, 'Unix socket'):
            self.apply()
        self.assertFalse((self.root / 'sent.sql').exists())

    def test_existing_or_overlapping_output_is_preserved(self):
        self.output.mkdir(); (self.output / 'keep').write_text('untouched')
        with self.assertRaises(transport.DeliveryError): self.apply()
        self.assertEqual((self.output / 'keep').read_text(), 'untouched')
        with self.assertRaises(transport.DeliveryError):
            transport.apply_bundle(self.bundle, self.client.target, self.bundle / 'nested')

    def test_timeout_and_output_flood_are_bounded_and_unknown(self):
        for mode in ['sleep', 'flood']:
            self.configure(self.reply, mode=mode); self.output = self.root / mode
            value = self.apply(timeout=1)
            self.assertEqual(value['outcome'], 'unknown'); self.assertTrue(value['limited'])
            self.assertLess(value['elapsed_ms'], 5000)

    def test_post_commit_disk_failure_never_emits_false_success(self):
        original = transport.write_new
        def fail(path, raw):
            if path.name == 'result.json': raise OSError('disk full')
            return original(path, raw)
        with mock.patch.object(transport, 'write_new', side_effect=fail), self.assertRaises(OSError): self.apply()
        self.assertTrue((self.output / 'attempt.json').exists()); self.assertFalse((self.output / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
