"""Real Rust/Polars source pipeline, explicit fake client at the DB boundary."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import archive_collection as archive
import sync_postgres_collection as sync
import test_archive_collection as fixtures
from test_collection_transport import LocalClient, response
import collection_transport as transport


class SyncCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = Path(os.environ['NQC_MINER_TEST_BINARY'])
        cls.topic = json.loads(subprocess.check_output([str(cls.binary), 'topics']))['aave-v3'][0]

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='nqc-sync-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.client = LocalClient(self.root); self.addCleanup(self.client.socket_patch.stop)
        self.state, self.store = self.root / 'source', self.root / 'archive'
        self.output = self.root / 'job'
        self.config = fixtures.fixture(self.state, self.topic)
        archive.init_archive(self.store, self.client.target['archive_id'])
        self.outcome = 'applied'
        self.submit = transport.apply_bundle
        self.patch = mock.patch.object(transport, 'apply_bundle', side_effect=self.deliver)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def deliver(self, bundle, target, output):
        request, manifest, _ = transport.load_bundle(bundle, target)
        messages = response(request, manifest, status='quarantined' if self.outcome == 'quarantined' else 'imported',
                            quarantined=self.outcome == 'quarantined')
        if self.outcome == 'unknown': messages = messages[:1]
        self.client.configure(b'\n'.join(transport.packed(m) for m in messages) + b'\n')
        # Fake executable code is stable across replies; its hash remains pinned.
        self.assertEqual(target['psql_sha256'], self.client.target['psql_sha256'])
        with self.assertRaisesRegex(ValueError, 'busy'):
            with archive.archive_lock(self.store): pass
        for directory in [self.state, *sorted(self.state.glob('window-*'))]:
            with (directory / 'writer.lock').open('rb') as stream:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self.submit(bundle, target, output)

    def run_sync(self):
        return sync.sync_collection(self.state, self.store, self.output, self.binary,
                                    self.client.target, self.config['run_id'])

    def test_full_capture_prepare_delivery_pipeline_preserves_source_and_reports(self):
        before = {p.relative_to(self.state): p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        result = self.run_sync()
        self.assertEqual(result['outcome'], 'applied'); self.assertTrue(result['commit_confirmed'])
        self.assertEqual((result['windows'], result['records']), (2, 4))
        self.assertTrue(result['source_stable_through_delivery'])
        self.assertEqual(before, {p.relative_to(self.state): p.read_bytes() for p in self.state.rglob('*') if p.is_file()})
        self.assertIn('nqc_miner_sync_applied 1', (self.output / 'metrics.prom').read_text())

    def test_retry_has_new_attempt_and_never_trusts_local_success_cursor(self):
        first = self.run_sync(); original = (self.output / 'result.json').read_bytes()
        old = self.output; self.output = self.root / 'retry'
        second = self.run_sync()
        self.assertEqual(first['request_sha256'], second['request_sha256'])
        self.assertEqual((old / 'result.json').read_bytes(), original)
        self.assertEqual(len(list((self.store / 'commits').glob('*.json'))), 1)

    def test_unknown_delivery_preserved_and_next_attempt_reverifies(self):
        self.outcome = 'unknown'; first = self.run_sync()
        self.assertEqual(first['outcome'], 'unknown'); self.assertFalse(first['commit_confirmed'])
        self.outcome = 'applied'; self.output = self.root / 'retry'
        self.assertEqual(self.run_sync()['outcome'], 'applied')

    def test_parent_revocation_after_prior_success_reaches_delivery_without_children(self):
        self.run_sync()
        fixtures.journal(self.state, self.config, [{'kind': 'invalidated', 'chain_id': 1,
            'from_block': 10, 'reason': 'artificial late source revocation'}])
        shutil.rmtree(self.state / 'window-00000000000000000000')
        shutil.rmtree(self.state / 'window-00000000000000000001')
        self.output = self.root / 'revocation'; self.outcome = 'quarantined'
        result = self.run_sync()
        self.assertEqual(result['outcome'], 'quarantined'); self.assertTrue(result['commit_confirmed'])
        self.assertEqual((result['windows'], result['records']), (0, 1))

    def test_wrong_archive_and_run_rejected_before_output_or_mutation(self):
        before = {p.relative_to(self.store): p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
        self.client.target['archive_id'] = '00000000-0000-4000-8000-000000000001'
        with self.assertRaises(transport.DeliveryError): self.run_sync()
        self.assertFalse(self.output.exists())
        self.assertEqual(before, {p.relative_to(self.store): p.read_bytes() for p in self.store.rglob('*') if p.is_file()})

    def test_source_advance_between_prepare_and_send_is_not_delivered(self):
        prepare = sync.collection.prepare_collection
        def mutate(*args, **kwargs):
            manifest = prepare(*args, **kwargs)
            fixtures.journal(self.state, self.config, [{'kind': 'invalidated', 'chain_id': 1,
                'from_block': 10, 'reason': 'artificial source advance'}])
            return manifest
        with mock.patch.object(sync.collection, 'prepare_collection', side_effect=mutate):
            result = self.run_sync()
        self.assertEqual(result['outcome'], 'unknown'); self.assertFalse((self.output / 'delivery').exists())
        self.assertFalse((self.root / 'sent.sql').exists())

    def test_source_noncooperating_mutation_after_commit_retains_ack_without_current_claim(self):
        def mutate(bundle, target, output):
            delivered = self.deliver(bundle, target, output)
            (self.state / 'events.jsonl').write_bytes(b'changed by injected noncooperating writer\n')
            return delivered
        with mock.patch.object(transport, 'apply_bundle', side_effect=mutate): result = self.run_sync()
        self.assertEqual(result['outcome'], 'unknown'); self.assertTrue(result['commit_confirmed'])
        self.assertTrue(json.loads((self.output / 'delivery/result.json').read_bytes())['commit_confirmed'])
        self.assertNotIn('source_stable_through_delivery', result)

    def test_new_archive_receipt_between_prepare_and_send_is_not_delivered(self):
        prepare = sync.collection.prepare_collection
        def advance(*args, **kwargs):
            manifest = prepare(*args, **kwargs)
            fixtures.fixture(self.state, self.topic, windows=3)
            archive.archive_collection(self.state, self.store, self.binary)
            return manifest
        with mock.patch.object(sync.collection, 'prepare_collection', side_effect=advance):
            result = self.run_sync()
        self.assertEqual(result['outcome'], 'unknown'); self.assertFalse((self.output / 'delivery').exists())
        self.assertEqual(len(list((self.store / 'commits').glob('*.json'))), 2)

    def test_active_source_writer_prevents_capture_or_delivery(self):
        with (self.state / 'writer.lock').open('rb') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_sync()
        self.assertEqual(result['outcome'], 'unknown'); self.assertFalse((self.root / 'sent.sql').exists())
        self.assertEqual(len(list((self.store / 'commits').glob('*.json'))), 0)

    def test_existing_job_and_nested_archive_output_are_not_adopted(self):
        self.output.mkdir(); (self.output / 'keep').write_bytes(b'untouched')
        with self.assertRaises(transport.DeliveryError): self.run_sync()
        self.assertEqual((self.output / 'keep').read_bytes(), b'untouched')
        self.output = self.store / 'nested'
        with self.assertRaises(transport.DeliveryError): self.run_sync()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
