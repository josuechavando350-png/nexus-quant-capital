from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import test_signer_registry as fixtures
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import EMPTY, RegistryMirror
from nqc_defense.signer_registry import ORIGIN, bundle_bytes, row_head, signed_row


class MirrorTests(unittest.TestCase):
    apply = fixtures.RegistryTests.apply
    view = fixtures.RegistryTests.view
    change = fixtures.RegistryTests.change
    capture = fixtures.RegistryTests.capture
    issue = fixtures.RegistryTests.issue
    register = fixtures.RegistryTests.register
    rotate = fixtures.RegistryTests.rotate
    revoke = fixtures.RegistryTests.revoke

    def setUp(self):
        fixtures.RegistryTests.setUp(self)
        self.registration = self.register()['receipt']
        self.mirror = RegistryMirror.create(self.root/'mirror', self.registry.digest, self.authority_digest)
        self.mirror_receipt = json.loads(canonical(EMPTY))

    def sync(self, **changes):
        data = self.registry.export(self.registry_head)
        args = dict(data=data, digest=sha256(data), target=self.registry_head, expected=self.mirror_receipt)
        args.update(changes); result = self.mirror.accept(**args); self.mirror_receipt = result['receipt']
        return result

    def verify(self, **changes):
        args = dict(expected=self.mirror_receipt, registration_receipt=self.registration,
                    data=self.data, digest=self.digest, dossier=self.dossier, dossier_digest=self.dossier_digest, pins=self.pins)
        args.update(changes)
        return self.mirror.verify(**args)

    def test_empty_mirror_requires_first_valid_snapshot(self):
        self.assertFalse(self.mirror.status()['initialized'])
        with self.assertRaisesRegex(Rejected, 'mirror_not_initialized'):
            self.verify()
        with self.assertRaisesRegex(Rejected, 'mirror_not_initialized'):
            self.mirror.export(EMPTY)
        self.sync(); self.assertTrue(self.verify()['registry_report']['registry_accepted'])

    def test_returned_initial_state_does_not_mutate_global_empty_receipt(self):
        self.mirror.status()['receipt']['registry_checkpoint']['revision'] = 3
        self.assertEqual(EMPTY['registry_checkpoint']['revision'],0)
        self.assertEqual(self.mirror.status()['receipt'],EMPTY)

    def test_rotation_and_revocation_are_applied_to_receiver(self):
        self.sync(); self.rotate(); self.sync()
        self.assertEqual(self.verify()['registry_report']['signer_status_at_checkpoint'],'retired')
        self.revoke(); self.sync()
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'):
            self.verify()

    def test_receiver_without_new_snapshot_explicitly_reports_local_view(self):
        self.sync(); self.revoke()
        report = self.verify()
        self.assertTrue(report['registry_report']['registry_accepted'])
        self.assertFalse(report['limits']['independent_freshness'])
        self.assertTrue(report['limits']['uses_locally_accepted_registry_snapshot'])

    def test_old_snapshot_cannot_replace_accepted_revocation(self):
        old_head = self.registry_head; old = self.registry.export(old_head)
        self.sync(); self.revoke(); self.sync()
        with self.assertRaisesRegex(Rejected, 'mirror_not_forward'):
            self.sync(data=old,digest=sha256(old),target=old_head)
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'):
            self.verify()

    def test_stale_receiver_receipt_is_rejected_for_sync_verify_and_export(self):
        self.sync(); self.rotate()
        with self.assertRaisesRegex(Rejected, 'mirror_receipt_mismatch'):
            self.sync(expected=EMPTY)
        with self.assertRaisesRegex(Rejected, 'mirror_receipt_mismatch'):
            self.verify(expected=EMPTY)
        with self.assertRaisesRegex(Rejected, 'mirror_receipt_mismatch'):
            self.mirror.export(EMPTY)

    def test_exact_last_update_retry_recovers_ack_without_new_generation(self):
        first = self.sync(); repeated = self.sync(expected=EMPTY)
        self.assertEqual(first['receipt'], repeated['receipt'])
        self.assertFalse(repeated['advanced']); self.assertTrue(repeated['idempotent_retry'])
        self.assertFalse(self.sync()['advanced'])

    def test_retry_of_older_update_after_later_advance_is_not_silently_accepted(self):
        old_head = self.registry_head; old = self.registry.export(old_head)
        self.sync(); self.rotate(); self.sync()
        with self.assertRaisesRegex(Rejected, 'mirror_receipt_mismatch'):
            self.sync(data=old,digest=sha256(old),target=old_head,expected=EMPTY)

    def test_signed_fork_with_longer_history_is_rejected(self):
        self.sync(); data = json.loads(self.registry.export(self.registry_head))
        public = public_bytes(secrets.token_bytes(32)); key_id = sha256(public)
        activation = json.loads(data['rows'][0][1])
        activation.update(key_id=key_id,new_public_key_hex=public.hex())
        first = signed_row(self.authority,1,ORIGIN['head'],activation)
        revoke = {**activation,'request_id':'fork_revoke','action':'revoke','new_public_key_hex':None}
        second = signed_row(self.authority,2,row_head(first),revoke)
        new_public = public_bytes(secrets.token_bytes(32))
        again = {**activation,'request_id':'fork_activate','key_id':sha256(new_public),'new_public_key_hex':new_public.hex()}
        third = signed_row(self.authority,3,row_head(second),again)
        fork = bundle_bytes(self.registry.config,[first,second,third]); target = {'revision':3,'head':row_head(third)}
        with self.assertRaisesRegex(Rejected, 'mirror_fork'):
            self.sync(data=fork,digest=sha256(fork),target=target)
        self.assertTrue(self.verify()['registry_report']['registry_accepted'])

    def test_scope_authority_and_bundle_corruption_do_not_advance(self):
        original = self.registry.export(self.registry_head)
        for args in ({'data':original+b' '},{'digest':'f'*64},{'target':ORIGIN}):
            with self.assertRaises(Rejected): self.sync(**args)
        self.assertEqual(self.mirror.status()['receipt'],EMPTY)

    def test_restart_and_loss_of_issuer_stores_do_not_break_received_view(self):
        self.sync(); expected = self.mirror_receipt
        for root in (self.registry.root,self.authority_root,self.policy.root,self.signer,self.store.root):
            shutil.rmtree(root)
        self.mirror = RegistryMirror(self.mirror.root,self.registry.digest,self.authority_digest)
        self.assertEqual(self.mirror.status(expected)['receipt'],expected)
        self.assertTrue(self.verify()['registry_report']['registry_accepted'])

    def test_metadata_and_bundle_corruption_are_rejected(self):
        self.sync()
        with self.mirror.connection(write=True) as db:
            db.execute('UPDATE snapshot SET bundle_digest=?',('f'*64,))
        with self.assertRaisesRegex(Rejected, 'registry_bundle_digest'):
            self.verify()

    def test_previous_receipt_and_prefix_corruption_are_rejected(self):
        self.sync(); self.rotate(); self.sync()
        with self.mirror.connection(write=True) as db:
            previous = json.loads(db.execute('SELECT previous FROM snapshot').fetchone()[0])
            previous['bundle_digest'] = 'f'*64
            db.execute('UPDATE snapshot SET previous=?',(canonical(previous),))
        with self.assertRaisesRegex(Rejected, 'mirror_previous_digest'):
            self.mirror.status()

    def test_whole_database_rollback_requires_external_receipt_and_is_detected_with_it(self):
        self.sync(); old = self.mirror.path.read_bytes(); old_receipt = self.mirror_receipt
        self.rotate(); self.sync(); latest = self.mirror_receipt
        self.mirror.path.write_bytes(old)
        with self.assertRaisesRegex(Rejected, 'mirror_receipt_mismatch'):
            self.mirror.status(latest)
        self.assertEqual(self.mirror.status()['receipt'],old_receipt)
        self.assertFalse(self.mirror.status()['independent_freshness'])

    def test_update_failure_keeps_previous_snapshot(self):
        self.sync(); before = self.mirror_receipt; self.rotate()
        with self.mirror.connection(write=True) as db:
            db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON snapshot BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.sync()
        self.assertEqual(self.mirror.status(before)['receipt'],before)

    def test_competing_syncs_have_one_cas_winner(self):
        first_head = self.registry_head; first = self.registry.export(first_head)
        self.rotate(); second_head = self.registry_head; second = self.registry.export(second_head)
        def worker(pair):
            body,target = pair
            try: return self.mirror.accept(body,sha256(body),target,EMPTY)['advanced']
            except Rejected as exc: return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(worker,[(first,first_head),(second,second_head)]))
        self.assertCountEqual(result,[True,'mirror_receipt_mismatch'])

    def test_verification_serializes_against_receiving_revocation(self):
        self.sync(); expected = self.mirror_receipt; self.revoke()
        bundle = self.registry.export(self.registry_head); started = threading.Event(); release = threading.Event()
        from nqc_defense.signer_registry import VerifiedRegistry
        original_verify = VerifiedRegistry.verify
        def paused(instance,*args,**kwargs):
            started.set()
            if not release.wait(3): raise AssertionError('coordination timeout')
            return original_verify(instance,*args,**kwargs)
        attempting = threading.Event()
        def receive():
            attempting.set()
            return self.mirror.accept(bundle,sha256(bundle),self.registry_head,expected)
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(VerifiedRegistry,'verify',new=paused):
            verification = pool.submit(self.verify)
            self.assertTrue(started.wait(3))
            incoming = pool.submit(receive)
            self.assertTrue(attempting.wait(3))
            with self.assertRaises(TimeoutError): incoming.result(timeout=0.1)
            release.set()
            self.assertEqual(verification.result()['mirror_receipt'],expected)
            self.mirror_receipt = incoming.result()['receipt']
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'): self.verify()

    def interrupted_sync(self, after_commit):
        bundle = self.registry.export(self.registry_head)
        (self.root/'crash-bundle.json').write_bytes(bundle)
        (self.root/'crash-mirror.json').write_bytes(canonical({'registry_digest':self.registry.digest,
            'authority_digest':self.authority_digest,'digest':sha256(bundle),'target':self.registry_head,
            'expected':self.mirror_receipt,'after_commit':after_commit}))
        code = '''
from contextlib import contextmanager
import json,os,sys
from pathlib import Path
from nqc_defense.registry_mirror import RegistryMirror
root=Path(sys.argv[1]); p=json.loads((root/'crash-mirror.json').read_bytes())
mirror=RegistryMirror(root/'mirror',p['registry_digest'],p['authority_digest']); original=mirror.connection
@contextmanager
def connection(write=False):
    with original(write=write) as db:
        if write and not p['after_commit']:
            db.create_function('terminate_test_process',0,lambda:os._exit(77))
            db.execute('CREATE TEMP TRIGGER die AFTER UPDATE ON snapshot BEGIN SELECT terminate_test_process(); END')
        yield db
    if write and p['after_commit']: os._exit(78)
mirror.connection=connection
mirror.accept((root/'crash-bundle.json').read_bytes(),p['digest'],p['target'],p['expected'])
'''
        result = subprocess.run([sys.executable,'-B','-c',code,str(self.root)],
            cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,78 if after_commit else 77,result.stderr)

    def test_real_process_termination_before_commit_preserves_old_receiver_view(self):
        self.interrupted_sync(False)
        self.assertEqual(self.mirror.status()['receipt'],EMPTY)
        self.assertTrue(self.sync()['advanced'])

    def test_real_process_termination_after_commit_recovers_ack(self):
        self.interrupted_sync(True)
        self.assertTrue(self.mirror.status()['initialized'])
        result = self.sync(expected=EMPTY)
        self.assertFalse(result['advanced']); self.assertTrue(result['idempotent_retry'])

    def test_no_secret_or_network_needed_for_received_verification(self):
        self.sync()
        with patch('socket.socket',side_effect=AssertionError('network')), patch('time.time_ns',side_effect=AssertionError('clock')):
            self.assertTrue(self.verify()['registry_report']['registry_accepted'])

    def test_unsafe_paths_missing_database_and_identity_changes_rejected(self):
        os.chmod(self.mirror.path,0o644)
        with self.assertRaisesRegex(Rejected,'mirror_database_permissions'): self.mirror.status()
        os.chmod(self.mirror.path,0o600)
        (self.mirror.root/'identity.json').write_bytes(b'{}')
        with self.assertRaisesRegex(Rejected,'mirror_identity_changed'): self.mirror.status()

    def test_missing_or_malformed_snapshot_never_reinitialized(self):
        with self.mirror.connection(write=True) as db: db.execute('DELETE FROM snapshot')
        with self.assertRaisesRegex(Rejected,'mirror_snapshot_missing'): self.mirror.status()

    def test_publication_preserves_exact_received_bytes(self):
        self.sync(); output = self.root/'received.json'
        result = self.mirror.publish(output,self.mirror_receipt)
        self.assertEqual(output.read_bytes(),self.registry.export(self.registry_head))
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertEqual(result,self.mirror.publish(output,self.mirror_receipt))

    def test_bad_external_receipt_is_rejected(self):
        self.sync()
        for bad in ({},[],{**self.mirror_receipt,'generation':True},
                    {**self.mirror_receipt,'registry_checkpoint':ORIGIN}):
            with self.assertRaises(Rejected): self.verify(expected=bad)

    def test_cli_init_receive_verify_export_and_revocation(self):
        tool = Path(__file__).resolve().parents[1]/'tools/registry_mirror.py'
        def call(*args,success=True):
            result = subprocess.run([sys.executable,'-B',str(tool),*map(str,args)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0 if success else 2,result.stdout+result.stderr)
            self.assertEqual(result.stderr,''); return json.loads(result.stdout)
        common = ['--mirror-root',self.root/'cli-mirror','--registry-digest',self.registry.digest,
                  '--authority-public-digest',self.authority_digest]
        call('init',*common)
        expected = self.root/'expected.json'; expected.write_bytes(canonical(EMPTY))
        target = self.root/'target.json'; target.write_bytes(canonical(self.registry_head))
        bundle = self.root/'bundle.json'; bundle.write_bytes(self.registry.export(self.registry_head))
        received = call('accept',*common,'--expected-file',expected,'--target-file',target,
                        '--bundle-file',bundle,'--bundle-digest',sha256(bundle.read_bytes()))
        expected.write_bytes(canonical(received['receipt']))
        pins = self.root/'pins.json'; pins.write_bytes(canonical(self.pins))
        registered = self.root/'receipt.json'; registered.write_bytes(canonical(self.registration))
        self.attestation_path.write_bytes(self.data)
        artifacts = ['--expected-file',expected,'--receipt-file',registered,'--pins-file',pins,
                     '--attestation-file',self.attestation_path,'--attestation-digest',self.digest,
                     '--dossier-file',self.dossier_path,'--dossier-digest',self.dossier_digest]
        self.assertTrue(call('verify',*common,*artifacts)['registry_report']['registry_accepted'])
        call('status',*common,'--expected-file',expected)
        exported = self.root/'exported.json'; call('export',*common,'--expected-file',expected,'--output',exported)
        self.assertEqual(exported.read_bytes(),bundle.read_bytes())
        self.revoke(); target.write_bytes(canonical(self.registry_head)); bundle.write_bytes(self.registry.export(self.registry_head))
        received = call('accept',*common,'--expected-file',expected,'--target-file',target,
                        '--bundle-file',bundle,'--bundle-digest',sha256(bundle.read_bytes()))
        expected.write_bytes(canonical(received['receipt']))
        self.assertEqual(call('verify',*common,*artifacts,success=False)['reason'],'registry_signer_revoked')


if __name__ == '__main__':
    unittest.main()
