import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_registry_mirror as fixtures
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import MAX_SQLITE_ROW as MIRROR_ROW, RegistryMirror
from nqc_defense.signer_registry import MAX_BUNDLE, MAX_EVENT_BYTES, MAX_SQLITE_ROW as REGISTRY_ROW, ORIGIN, SignerRegistry
from nqc_defense.sqlite_limits import set_row_limit


class StorageLimitTests(unittest.TestCase):
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
        fixtures.MirrorTests.setUp(self); self.sync()

    def mutate_registry(self, statement, values=()):
        with sqlite3.connect(self.registry.path) as db: db.execute(statement,values)

    def mutate_mirror(self, statement, values=()):
        with sqlite3.connect(self.mirror.path) as db: db.execute(statement,values)

    def test_limits_are_applied_to_every_store_connection(self):
        for store,expected in ((self.registry,REGISTRY_ROW),(self.mirror,MIRROR_ROW)):
            for write in (False,True):
                with self.subTest(store=type(store).__name__,write=write), store.connection(write=write) as db:
                    self.assertEqual(db.getlimit(sqlite3.SQLITE_LIMIT_LENGTH),expected)

    def test_tighter_existing_runtime_limit_is_never_expanded(self):
        with sqlite3.connect(':memory:') as db:
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024)
            with self.assertRaisesRegex(Rejected,'sqlite_runtime_length_limit_too_small'): set_row_limit(db,REGISTRY_ROW)
            self.assertEqual(db.getlimit(sqlite3.SQLITE_LIMIT_LENGTH),1024)

    def test_invalid_configured_limit_is_rejected(self):
        with sqlite3.connect(':memory:') as db:
            for value in (True,0,1023,64*1024*1024+1):
                with self.subTest(value=value), self.assertRaises(Rejected): set_row_limit(db,value)

    def test_exact_maximum_event_still_writes_and_replays(self):
        registry = SignerRegistry.create(self.root/'max_event',public_bytes(self.authority),self.authority_digest,
            self.pins['tenant'],self.pins['asset'],self.pins['policy_digest'])
        key = secrets.token_bytes(32); key_id = sha256(public_bytes(key))
        event = registry._event('activate',key_id,'max','',public_bytes(key))
        padding = MAX_EVENT_BYTES-len(canonical(event)); reason = 'é'*(padding//6)+'x'*(padding%6)
        self.assertLessEqual(len(reason.encode()),4096)
        event['reason'] = reason; self.assertEqual(len(canonical(event)),MAX_EVENT_BYTES)
        head = registry.change(self.authority,'activate',key_id,'max',reason,ORIGIN,public_bytes(key))['receipt']
        self.assertEqual(registry.status(head)['active_key'],key_id)
        self.assertTrue(registry.export(head))

    def test_registry_oversized_payload_is_rejected_before_full_materialization(self):
        self.mutate_registry('UPDATE entries SET payload=? WHERE revision=1',('x'*(MAX_EVENT_BYTES+1),))
        statements = []
        with self.registry.connection() as db:
            db.set_trace_callback(statements.append)
            with self.assertRaisesRegex(Rejected,'registry_payload'): self.registry._load(db,self.registry_head)
        self.assertFalse(any(sql.startswith('SELECT revision,CAST(payload') for sql in statements))

    def test_huge_registry_value_is_stopped_by_sqlite(self):
        self.mutate_registry('UPDATE entries SET payload=CAST(zeroblob(?) AS TEXT) WHERE revision=1',(4*1024*1024,))
        with self.assertRaises(Rejected): self.registry.status(self.registry_head)

    def test_registry_field_types_and_sizes_are_checked(self):
        for column,value in (('payload',b'{}'),('previous','x'*63),('signature','x'*129)):
            with self.subTest(column=column):
                with sqlite3.connect(self.registry.path) as db:
                    old = db.execute(f'SELECT {column} FROM entries WHERE revision=1').fetchone()[0]
                self.mutate_registry(f'UPDATE entries SET {column}=? WHERE revision=1',(value,))
                reason = 'registry_payload' if column == 'payload' else 'registry_storage_shape'
                with self.assertRaisesRegex(Rejected,reason): self.registry.status()
                self.mutate_registry(f'UPDATE entries SET {column}=? WHERE revision=1',(old,))
        self.assertEqual(self.registry.status(self.registry_head)['checkpoint'],self.registry_head)

    def test_invalid_utf8_registry_text_is_a_controlled_rejection(self):
        self.mutate_registry("UPDATE entries SET payload=CAST(x'80' AS TEXT) WHERE revision=1")
        with self.assertRaisesRegex(Rejected,'registry_storage_encoding'): self.registry.status()

    def test_invalid_utf8_digest_is_a_controlled_rejection(self):
        self.mutate_mirror('UPDATE snapshot SET bundle_digest=CAST(? AS TEXT)',(b'\x80'*64,))
        with self.assertRaisesRegex(Rejected,'mirror_storage_encoding'): self.verify()

    def test_oversized_mirror_blob_is_not_returned_to_python(self):
        self.mutate_mirror('UPDATE snapshot SET bundle=zeroblob(?)',(MAX_BUNDLE+1,))
        statements = []
        with self.mirror.connection() as db:
            db.set_trace_callback(statements.append)
            with self.assertRaisesRegex(Rejected,'mirror_storage_shape'): self.mirror._load(db,self.mirror_receipt)
        self.assertFalse(any(sql.startswith('SELECT id,generation,bundle,') for sql in statements))

    def test_huge_mirror_blob_is_bounded_even_with_a_warm_cache(self):
        self.verify(); self.mutate_mirror('UPDATE snapshot SET bundle=zeroblob(?)',(64*1024*1024,))
        with self.assertRaises(Rejected): self.verify()

    def test_oversized_previous_receipt_is_not_loaded(self):
        self.mutate_mirror('UPDATE snapshot SET previous=zeroblob(4097)')
        with self.assertRaisesRegex(Rejected,'mirror_storage_shape'): self.verify()

    def test_mirror_dynamic_types_cannot_bypass_bounds(self):
        for column,value in (('generation',b'1'),('bundle','{}'),('bundle_digest',b'0'*64),('previous','{}')):
            with self.subTest(column=column):
                with sqlite3.connect(self.mirror.path) as db:
                    old = db.execute(f'SELECT {column} FROM snapshot').fetchone()[0]
                self.mutate_mirror(f'UPDATE snapshot SET {column}=?',(value,))
                with self.assertRaisesRegex(Rejected,'mirror_storage_shape'): self.verify()
                self.mutate_mirror(f'UPDATE snapshot SET {column}=?',(old,))
        self.assertTrue(self.verify()['registry_report']['registry_accepted'])

    def test_size_checks_do_not_replace_signatures(self):
        self.mutate_registry('UPDATE entries SET signature=? WHERE revision=1',('0'*128,))
        with self.assertRaisesRegex(Rejected,'registry_signature_invalid'): self.registry.status()

    def test_limited_write_failure_rolls_back_and_preserves_registry(self):
        before = self.registry.export(self.registry_head)
        with self.assertRaisesRegex(Rejected,'registry_storage_value_limit'):
            with self.registry.connection(write=True) as db:
                db.execute('UPDATE entries SET payload=? WHERE revision=1',('x'*(REGISTRY_ROW+1),))
        self.assertEqual(self.registry.export(self.registry_head),before)

    def test_limited_write_failure_rolls_back_and_preserves_mirror(self):
        before = self.mirror.export(self.mirror_receipt)
        with self.assertRaisesRegex(Rejected,'mirror_storage_value_limit'):
            with self.mirror.connection(write=True) as db:
                db.execute('UPDATE snapshot SET bundle=zeroblob(?)',(MIRROR_ROW+1,))
        self.assertEqual(self.mirror.export(self.mirror_receipt),before)

    def test_new_limits_preserve_rotation_revocation_and_reopened_cache(self):
        before = self.verify()['registry_report']['signature_report']; self.rotate(); self.sync()
        self.mirror = RegistryMirror(self.mirror.root,self.registry.digest,self.authority_digest)
        self.assertEqual(self.verify()['registry_report']['signature_report'],before)
        self.revoke(); self.sync()
        with self.assertRaisesRegex(Rejected,'registry_signer_revoked'): self.verify()


if __name__ == '__main__':
    unittest.main()
