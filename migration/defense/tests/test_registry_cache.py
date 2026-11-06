from dataclasses import FrozenInstanceError
import gc
import json
import sqlite3
import unittest
import weakref
from unittest.mock import patch

import test_registry_mirror as fixtures
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import EMPTY, RegistryMirror
from nqc_defense.signer_registry import VerifiedRegistry, verify_bundle, verify_registered


class RegistryCacheTests(unittest.TestCase):
    apply = fixtures.MirrorTests.apply
    view = fixtures.MirrorTests.view
    change = fixtures.MirrorTests.change
    capture = fixtures.MirrorTests.capture
    issue = fixtures.MirrorTests.issue
    register = fixtures.MirrorTests.register
    rotate = fixtures.MirrorTests.rotate
    revoke = fixtures.MirrorTests.revoke
    sync = fixtures.MirrorTests.sync
    verify = fixtures.MirrorTests.verify

    def setUp(self):
        fixtures.MirrorTests.setUp(self)

    def test_warm_receiver_rereads_storage_without_replaying_unchanged_registry(self):
        self.sync(); connect = sqlite3.connect
        with (patch('nqc_defense.signer_registry.verify_bundle',side_effect=AssertionError('unnecessary registry replay')),
              patch('nqc_defense.registry_mirror.sqlite3.connect',wraps=connect) as connections):
            self.assertTrue(self.verify()['registry_report']['registry_accepted'])
            self.assertTrue(self.verify()['registry_report']['registry_accepted'])
            self.mirror.status(self.mirror_receipt)
            self.assertEqual(connections.call_count,3)

    def test_cold_verification_replays_once_and_preserves_public_result(self):
        self.sync(); bundle = self.registry.export(self.registry_head)
        self.mirror = RegistryMirror(self.mirror.root,self.registry.digest,self.authority_digest)
        with patch('nqc_defense.signer_registry.verify_bundle',wraps=verify_bundle) as replay:
            result = self.verify()
            self.assertEqual(replay.call_count,1)
            self.assertEqual(self.verify(),result)
            self.assertEqual(replay.call_count,1)
        expected = verify_registered(bundle,sha256(bundle),self.registry.digest,self.authority_digest,self.registry_head,
            self.registration,self.data,self.digest,self.dossier,self.dossier_digest,self.pins)
        self.assertEqual(result['registry_report'],expected)

    def test_cache_clear_requires_fresh_replay(self):
        self.sync(); self.mirror.clear_cache()
        with patch('nqc_defense.signer_registry.verify_bundle',wraps=verify_bundle) as replay:
            self.verify(); self.assertEqual(replay.call_count,1)
            self.mirror.clear_cache(); self.verify(); self.assertEqual(replay.call_count,2)

    def test_changed_stored_bytes_are_rejected_despite_unchanged_declared_digest(self):
        self.sync()
        with self.mirror.connection(write=True) as db:
            body = db.execute('SELECT bundle FROM snapshot').fetchone()[0]
            db.execute('UPDATE snapshot SET bundle=?',(body+b' ',))
        with self.assertRaisesRegex(Rejected,'registry_bundle_digest'): self.verify()

    def test_changed_stored_bytes_and_recomputed_digest_do_not_poison_cache(self):
        self.sync()
        with self.mirror.connection(write=True) as db:
            value = json.loads(db.execute('SELECT bundle FROM snapshot').fetchone()[0])
            value['rows'][-1][1] = '{}'; body = canonical(value)
            db.execute('UPDATE snapshot SET bundle=?,bundle_digest=?',(body,sha256(body)))
        with self.assertRaisesRegex(Rejected,'registry_signature_invalid'): self.verify()

    def test_generation_mutation_is_not_ignored_by_cache(self):
        self.sync()
        with self.mirror.connection(write=True) as db: db.execute('UPDATE snapshot SET generation=generation+1')
        with self.assertRaisesRegex(Rejected,'mirror_previous_receipt'): self.verify()

    def test_previous_receipt_mutation_is_not_ignored_by_cache(self):
        self.sync(); self.rotate(); self.sync()
        with self.mirror.connection(write=True) as db:
            previous = json.loads(db.execute('SELECT previous FROM snapshot').fetchone()[0])
            previous['bundle_digest'] = 'f'*64
            db.execute('UPDATE snapshot SET previous=?',(canonical(previous),))
        with self.assertRaisesRegex(Rejected,'mirror_previous_digest'): self.verify()

    def test_warm_cache_does_not_skip_external_receipt_or_identity(self):
        self.sync()
        with self.assertRaisesRegex(Rejected,'mirror_receipt_mismatch'): self.verify(expected=EMPTY)
        (self.mirror.root/'identity.json').write_bytes(b'{}')
        with self.assertRaisesRegex(Rejected,'mirror_identity_changed'): self.verify()

    def test_every_warm_call_rechecks_attestation_and_dossier_bytes(self):
        self.sync()
        with self.assertRaisesRegex(Rejected,'attestation_digest'): self.verify(data=self.data+b' ')
        with self.assertRaisesRegex(Rejected,'dossier_digest'): self.verify(dossier=self.dossier+b' ')
        with self.assertRaisesRegex(Rejected,'registry_attestation_not_recorded'): self.verify(digest='e'*64)
        with self.assertRaisesRegex(Rejected,'registry_record_binding'): self.verify(pins={**self.pins,'tenant':'other'})

    def test_returned_reports_and_receipts_cannot_mutate_cached_snapshot(self):
        self.sync(); report = self.verify(); status = self.mirror.status()
        report['registry_report']['registry_checkpoint']['head'] = 'e'*64
        report['registry_report']['signature_report']['signer_report']['facts']['review']['stage'] = 'invented'
        status['receipt']['registry_checkpoint']['revision'] = 0
        fresh = self.verify()
        self.assertEqual(fresh['registry_report']['registry_checkpoint'],self.registry_head)
        self.assertEqual(fresh['registry_report']['signature_report']['signer_report']['facts']['review']['stage'],'closed')
        self.assertEqual(self.mirror.status()['receipt'],self.mirror_receipt)

    def test_prepared_registry_requires_validated_factory_and_immutable_data(self):
        bundle = self.registry.export(self.registry_head)
        prepared = VerifiedRegistry.from_bundle(bundle,sha256(bundle),self.registry.digest,self.authority_digest,self.registry_head)
        with self.assertRaises(TypeError): VerifiedRegistry()
        with self.assertRaises(FrozenInstanceError): prepared.registry_digest = 'e'*64
        with self.assertRaises(TypeError): prepared._keys[self.key_pin] = ('00'*32,'active')
        with self.assertRaises(TypeError): prepared._records[self.digest] = ()
        self.assertFalse(hasattr(prepared,'__dict__'))
        exposed = prepared.checkpoint; exposed['head'] = 'e'*64
        self.assertEqual(prepared.checkpoint,self.registry_head)

    def test_prepared_factory_rejects_untrusted_data_and_wrong_target(self):
        bundle = self.registry.export(self.registry_head)
        with self.assertRaises(Rejected):
            VerifiedRegistry.from_bundle(bundle+b' ',sha256(bundle),self.registry.digest,self.authority_digest,self.registry_head)
        with self.assertRaises(Rejected):
            VerifiedRegistry.from_bundle(bundle,sha256(bundle),self.registry.digest,self.authority_digest,{'revision':0,'head':'0'*64})

    def test_retained_prepared_object_is_explicitly_historical_after_revocation(self):
        bundle = self.registry.export(self.registry_head)
        old = VerifiedRegistry.from_bundle(bundle,sha256(bundle),self.registry.digest,self.authority_digest,self.registry_head)
        old_head = self.registry_head; self.sync(); self.revoke(); self.sync()
        report = old.verify(self.registration,self.data,self.digest,self.dossier,self.dossier_digest,self.pins)
        self.assertEqual(report['registry_checkpoint'],old_head)
        self.assertFalse(report['limits']['independent_freshness'])
        with self.assertRaisesRegex(Rejected,'registry_signer_revoked'): self.verify()

    def test_receiver_retains_only_one_prepared_snapshot(self):
        self.sync(); old = weakref.ref(self.mirror._cache[3])
        self.rotate(); self.sync(); gc.collect()
        self.assertIsNone(old())
        current = weakref.ref(self.mirror._cache[3]); self.mirror.clear_cache(); gc.collect()
        self.assertIsNone(current())

    def test_changed_database_permissions_are_checked_on_every_warm_read(self):
        import os
        self.sync(); os.chmod(self.mirror.path,0o644)
        with self.assertRaisesRegex(Rejected,'mirror_database_permissions'): self.verify()


if __name__ == '__main__':
    unittest.main()
