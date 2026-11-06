from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_dossier_attestation as fixtures
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import create_signer, load_signer, public_bytes
from nqc_defense.files import sha256
from nqc_defense.signer_registry import (ORIGIN, SignerRegistry, bundle_bytes, row_head, signed_row,
    verify_bundle, verify_registered)


class RegistryTests(unittest.TestCase):
    apply = fixtures.AttestationTests.apply
    view = fixtures.AttestationTests.view
    change = fixtures.AttestationTests.change
    capture = fixtures.AttestationTests.capture
    issue = fixtures.AttestationTests.issue

    def setUp(self):
        fixtures.AttestationTests.setUp(self)
        self.data = self.issue(); self.digest = sha256(self.data)
        self.authority_root = self.root/'authority'
        self.authority_digest = create_signer(self.authority_root)['public_key_sha256']
        self.authority = load_signer(self.authority_root, self.authority_digest)
        self.registry = SignerRegistry.create(self.root/'registry', public_bytes(self.authority),
            self.authority_digest, 'tenant', 'host', self.policy.digest)
        self.registry_head = self.registry.change(self.authority, 'activate', self.key_pin, 'activate',
            'Initial signer', ORIGIN, self.public_key)['receipt']
        self.serial = 100

    def register(self, **changes):
        self.serial += 1
        arguments = dict(authority_key=self.authority, data=self.data, digest=self.digest,
            dossier=self.dossier, dossier_digest=self.dossier_digest, pins=self.pins, key_id=self.key_pin,
            request_id=f'record_{self.serial}', reason='Register validated dossier', expected=self.registry_head)
        arguments.update(changes)
        result = self.registry.record(**arguments); self.registry_head = result['current_checkpoint']
        return result

    def rotate(self, **changes):
        self.serial += 1
        arguments = dict(authority_key=self.authority, action='rotate', key_id=self.key_pin,
            request_id=f'rotate_{self.serial}', reason='Rotate signing key', expected=self.registry_head,
            new_public_key=public_bytes(secrets.token_bytes(32)))
        arguments.update(changes)
        result = self.registry.change(**arguments); self.registry_head = result['current_checkpoint']
        return result

    def revoke(self, **changes):
        self.serial += 1
        arguments = dict(authority_key=self.authority, action='revoke', key_id=self.key_pin,
            request_id=f'revoke_{self.serial}', reason='Revoke signing key', expected=self.registry_head)
        arguments.update(changes)
        result = self.registry.change(**arguments); self.registry_head = result['current_checkpoint']
        return result

    def verify(self, receipt_ref, **changes):
        data = self.registry.export(self.registry_head)
        arguments = dict(bundle=data, bundle_digest=sha256(data), registry_digest=self.registry.digest,
            authority_digest=self.authority_digest, current_checkpoint=self.registry_head, receipt=receipt_ref,
            data=self.data, digest=self.digest, dossier=self.dossier, dossier_digest=self.dossier_digest, pins=self.pins)
        arguments.update(changes)
        return verify_registered(**arguments)

    def test_register_rotate_and_validate_historical_and_new_signers(self):
        old = self.register()['receipt']; original = self.data
        new_key = secrets.token_bytes(32); new_pin = sha256(public_bytes(new_key))
        self.rotate(new_public_key=public_bytes(new_key))
        result = self.verify(old)
        self.assertTrue(result['registry_accepted'])
        self.assertEqual(result['signer_status_at_checkpoint'], 'retired')
        data = self.issue(signing_key=new_key, public_key_digest=new_pin)
        new = self.register(data=data, digest=sha256(data), key_id=new_pin)['receipt']
        self.assertEqual(self.verify(new, data=data, digest=sha256(data))['signer_status_at_checkpoint'], 'active')
        self.assertTrue(self.verify(old)['registry_accepted'])
        self.assertEqual(original, self.data)

    def test_retired_key_cannot_register_new_signature(self):
        self.register(); self.rotate()
        value = json.loads(self.dossier); value['captured_ns'] += 1; dossier = canonical(value)
        data = self.issue(dossier=dossier, dossier_digest=sha256(dossier))
        with self.assertRaisesRegex(Rejected, 'registry_signer_not_active'):
            self.register(data=data, digest=sha256(data), dossier=dossier, dossier_digest=sha256(dossier))

    def test_signature_without_prior_registration_is_not_historical_acceptance(self):
        self.rotate()
        with self.assertRaisesRegex(Rejected, 'registry_attestation_not_recorded'):
            self.verify(self.registry_head)

    def test_revoked_key_rejects_previously_registered_attestation(self):
        receipt = self.register()['receipt']; self.revoke()
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'):
            self.verify(receipt)
        from nqc_defense.dossier_attestation import verify_attestation
        self.assertTrue(verify_attestation(self.data, self.digest, self.dossier, self.dossier_digest,
            self.pins, self.public_key, self.key_pin)['signature_verified'])

    def test_revoking_retired_key_does_not_revoke_replacement(self):
        old = self.register()['receipt']; new_key = secrets.token_bytes(32); new_pin = sha256(public_bytes(new_key))
        self.rotate(new_public_key=public_bytes(new_key)); self.revoke()
        data = self.issue(signing_key=new_key, public_key_digest=new_pin)
        new = self.register(data=data, digest=sha256(data), key_id=new_pin)['receipt']
        self.assertTrue(self.verify(new, data=data, digest=sha256(data))['registry_accepted'])
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'):
            self.verify(old)

    def test_new_activation_after_revoke_requires_never_used_key(self):
        self.revoke()
        with self.assertRaisesRegex(Rejected, 'registry_key_reuse'):
            self.registry.change(self.authority, 'activate', self.key_pin, 'again', 'No reuse', self.registry_head, self.public_key)
        public = public_bytes(secrets.token_bytes(32))
        result = self.registry.change(self.authority, 'activate', sha256(public), 'new', 'Fresh key', self.registry_head, public)
        self.assertTrue(result['applied'])

    def test_authority_key_cannot_be_a_dossier_signer(self):
        with self.assertRaisesRegex(Rejected, 'registry_key_reuse'):
            self.rotate(new_public_key=public_bytes(self.authority))

    def test_wrong_authority_rejected_before_untrusted_payload_processing(self):
        with self.assertRaisesRegex(Rejected, 'registry_administrator_required'):
            self.register(authority_key=self.signing_key, data=b'bad')
        with self.assertRaisesRegex(Rejected, 'registry_administrator_required'):
            self.rotate(authority_key=self.policy.key)

    def test_record_requires_valid_attestation(self):
        value = json.loads(self.data); value['signature_hex'] = '00'*64; data = canonical(value)
        with self.assertRaisesRegex(Rejected, 'attestation_signature_invalid'):
            self.register(data=data, digest=sha256(data))
        self.assertEqual(self.registry.status()['registered_attestations'], 0)

    def test_scope_is_frozen_to_policy_tenant_and_asset(self):
        other = SignerRegistry.create(self.root/'other', public_bytes(self.authority), self.authority_digest,
                                     'another', 'host', self.policy.digest)
        head = other.change(self.authority, 'activate', self.key_pin, 'activate', 'Initialize', ORIGIN, self.public_key)['receipt']
        with self.assertRaisesRegex(Rejected, 'registry_scope'):
            other.record(self.authority, self.data, self.digest, self.dossier, self.dossier_digest,
                self.pins, self.key_pin, 'record', 'Wrong scope', head)

    def test_key_changes_and_recording_require_current_external_checkpoint(self):
        with self.assertRaisesRegex(Rejected, 'registry_checkpoint_mismatch'):
            self.register(expected=ORIGIN)
        with self.assertRaisesRegex(Rejected, 'registry_checkpoint_mismatch'):
            self.rotate(expected=ORIGIN)
        with self.assertRaisesRegex(Rejected, 'registry_checkpoint_mismatch'):
            self.registry.export(ORIGIN)

    def test_exact_record_retry_recovers_receipt_after_rotation(self):
        before = self.registry_head; original = self.register(request_id='retry')['receipt']; self.rotate()
        current = self.registry_head
        result = self.register(request_id='retry', expected=before)
        self.assertFalse(result['applied']); self.assertTrue(result['idempotent_retry'])
        self.assertEqual(result['receipt'], original); self.assertEqual(result['current_checkpoint'], current)

    def test_retry_after_revocation_only_recovers_receipt_not_acceptance(self):
        before = self.registry_head; original = self.register(request_id='retry')['receipt']; self.revoke()
        self.assertEqual(self.register(request_id='retry', expected=before)['receipt'], original)
        with self.assertRaisesRegex(Rejected, 'registry_signer_revoked'):
            self.verify(original)

    def test_changed_retry_and_duplicate_registration_are_rejected(self):
        before = self.registry_head; self.register(request_id='retry')
        with self.assertRaisesRegex(Rejected, 'registry_request_conflict'):
            self.register(request_id='retry', expected=before, reason='Changed')
        with self.assertRaisesRegex(Rejected, 'registry_request_conflict'):
            self.register(request_id='retry')
        with self.assertRaisesRegex(Rejected, 'registry_attestation_already_recorded'):
            self.register()

    def test_rotate_retry_is_idempotent(self):
        before = self.registry_head; new_public = public_bytes(secrets.token_bytes(32))
        result = self.rotate(request_id='rotate_retry', new_public_key=new_public)
        repeated = self.rotate(request_id='rotate_retry', expected=before, new_public_key=new_public)
        self.assertEqual(result['receipt'], repeated['receipt']); self.assertFalse(repeated['applied'])

    def test_competing_rotations_have_one_winner(self):
        expected = self.registry_head
        def worker(index):
            try:
                return self.registry.change(self.authority, 'rotate', self.key_pin, f'race{index}', 'Concurrent rotation',
                    expected, public_bytes(secrets.token_bytes(32)))['applied']
            except Rejected as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertCountEqual(results, [True, 'registry_checkpoint_mismatch'])

    def test_restart_preserves_keys_and_registered_receipts(self):
        receipt = self.register()['receipt']; self.rotate()
        self.registry = SignerRegistry(self.registry.root, self.registry.digest, self.authority_digest)
        self.assertTrue(self.verify(receipt)['registry_accepted'])

    def test_public_replay_without_io_or_clock(self):
        receipt = self.register()['receipt']; bundle = self.registry.export(self.registry_head)
        with ExitStack() as stack:
            for name in ('builtins.open', 'os.open', 'sqlite3.connect', 'socket.socket', 'time.time_ns', 'pathlib.Path.read_bytes'):
                stack.enter_context(patch(name, side_effect=AssertionError('unexpected IO')))
            result = verify_registered(bundle, sha256(bundle), self.registry.digest, self.authority_digest,
                self.registry_head, receipt, self.data, self.digest, self.dossier, self.dossier_digest, self.pins)
        self.assertTrue(result['registry_accepted'])

    def test_verification_after_registry_and_all_secrets_removed(self):
        receipt = self.register()['receipt']; bundle = self.registry.export(self.registry_head)
        for root in (self.registry.root, self.authority_root, self.signer, self.policy.root, self.store.root):
            shutil.rmtree(root)
        result = verify_registered(bundle, sha256(bundle), self.registry.digest, self.authority_digest,
            self.registry_head, receipt, self.data, self.digest, self.dossier, self.dossier_digest, self.pins)
        self.assertTrue(result['registry_accepted'])

    def test_registry_tail_rollback_rejected_by_retained_checkpoint(self):
        self.register(); expected = self.registry_head
        with self.registry.connection(write=True) as db:
            db.execute('DELETE FROM entries WHERE revision=2')
        with self.assertRaisesRegex(Rejected, 'registry_checkpoint_mismatch'):
            self.registry.status(expected)
        self.assertEqual(self.registry.status()['checkpoint']['revision'], 1)
        self.assertFalse(self.registry.status()['independent_freshness'])

    def test_old_public_bundle_cannot_satisfy_new_revocation_checkpoint(self):
        receipt = self.register()['receipt']; before = self.registry_head; bundle = self.registry.export(before)
        self.revoke()
        with self.assertRaisesRegex(Rejected, 'registry_checkpoint_mismatch'):
            self.verify(receipt, bundle=bundle, bundle_digest=sha256(bundle))
        historical = self.verify(receipt, bundle=bundle, bundle_digest=sha256(bundle), current_checkpoint=before)
        self.assertTrue(historical['registry_accepted']); self.assertFalse(historical['limits']['independent_freshness'])

    def test_bundle_pin_authority_config_and_receipt_cannot_be_substituted(self):
        receipt = self.register()['receipt']
        for changes in ({'bundle_digest':'e'*64}, {'registry_digest':'e'*64}, {'authority_digest':'e'*64},
                        {'receipt':{'revision':receipt['revision'], 'head':'e'*64}}):
            with self.assertRaises(Rejected):
                self.verify(receipt, **changes)

    def test_reordered_or_truncated_signed_rows_fail_external_target(self):
        self.register(); bundle = json.loads(self.registry.export(self.registry_head))
        for rows in (bundle['rows'][:-1], list(reversed(bundle['rows'])), bundle['rows'][1:]):
            data = canonical({**bundle, 'rows':rows})
            with self.assertRaises(Rejected):
                verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, self.registry_head)

    def test_changed_payload_signature_and_wrong_signed_binding_are_rejected(self):
        bundle = json.loads(self.registry.export(self.registry_head))
        for value in ('{}', '\ud800', b'bad'):
            if isinstance(value, bytes):
                with self.registry.connection(write=True) as db:
                    db.execute('UPDATE entries SET payload=?', (value,))
                with self.assertRaises(Rejected):
                    self.registry.status()
                continue
            changed = json.loads(canonical(bundle)); changed['rows'][0][1] = value; data = canonical(changed)
            with self.assertRaises(Rejected):
                verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, self.registry_head)

    def test_authority_signed_invalid_transition_is_rejected(self):
        bundle = json.loads(self.registry.export(self.registry_head))
        event = json.loads(bundle['rows'][0][1]); event['action'] = 'rotate'
        row = signed_row(self.authority, 1, ORIGIN['head'], event)
        data = bundle_bytes(self.registry.config, [row]); head = {'revision':1, 'head':row_head(row)}
        with self.assertRaisesRegex(Rejected, 'registry_rotation_state'):
            verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, head)

    def test_boolean_revision_unknown_fields_and_noncanonical_bundle_rejected(self):
        value = json.loads(self.registry.export(self.registry_head))
        for changed in ({**value, 'extra':True}, {**value, 'rows':{}}, {**value, 'schema':'unknown'}):
            data = canonical(changed)
            with self.assertRaises(Rejected):
                verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, self.registry_head)
        value['rows'][0][0] = True; data = canonical(value)
        with self.assertRaisesRegex(Rejected, 'integer_range'):
            verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, self.registry_head)

    def test_row_key_payload_and_export_capacity_fail_without_commit(self):
        before = self.registry_head
        with patch('nqc_defense.signer_registry.MAX_ROWS', 1):
            with self.assertRaisesRegex(Rejected, 'registry_capacity'):
                self.register()
        with patch('nqc_defense.signer_registry.MAX_KEYS', 1):
            with self.assertRaisesRegex(Rejected, 'registry_key_capacity'):
                self.rotate()
        with patch('nqc_defense.signer_registry.MAX_EVENT_BYTES', 1):
            with self.assertRaisesRegex(Rejected, 'registry_payload'):
                self.registry.status()
        with patch('nqc_defense.signer_registry.MAX_BUNDLE', 1):
            with self.assertRaisesRegex(Rejected, 'registry_bundle_size'):
                self.register()
        self.assertEqual(self.registry.status()['checkpoint'], before)

    def test_insert_failure_rolls_back_rotation(self):
        with self.registry.connection(write=True) as db:
            db.execute("CREATE TRIGGER reject_write BEFORE INSERT ON entries BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.rotate()
        self.assertEqual(self.registry.status()['active_key'], self.key_pin)
        self.assertEqual(self.registry.status()['checkpoint'], self.registry_head)

    def test_database_missing_or_unsafe_permissions_are_not_silently_recreated(self):
        path = self.registry.path; os.chmod(path, 0o644)
        with self.assertRaisesRegex(Rejected, 'registry_database_permissions'):
            self.registry.status()
        os.chmod(path, 0o600); path.unlink()
        with self.assertRaises(OSError):
            self.registry.status()
        self.assertFalse(path.exists())

    def test_configuration_changes_rejected_by_existing_instance(self):
        (self.registry.root/'config.json').write_bytes(b'{}')
        with self.assertRaisesRegex(Rejected, 'registry_configuration_changed'):
            self.registry.status()

    def test_publication_is_private_idempotent_and_reverified(self):
        self.register(); output = self.root/'registry-bundle.json'
        receipt = self.registry.publish(output, self.registry_head); inode = output.stat().st_ino
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt, self.registry.publish(output, self.registry_head)); self.assertEqual(output.stat().st_ino, inode)
        with patch('nqc_defense.signer_registry.publish_local', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.registry.publish(self.root/'failed.json', self.registry_head)

    def test_management_reason_and_identifier_validation(self):
        for changes in ({'request_id':'../bad'}, {'reason':''}, {'reason':'\ud800'}, {'reason':'x'*4097}):
            with self.assertRaises(Rejected):
                self.rotate(**changes)

    def crash_rotation(self, after_commit):
        public = public_bytes(secrets.token_bytes(32))
        params = self.root/'crash-registry.json'
        params.write_bytes(canonical({'registry_digest':self.registry.digest, 'authority_digest':self.authority_digest,
            'expected':self.registry_head, 'key_id':self.key_pin, 'new_public':public.hex(), 'after_commit':after_commit}))
        script = '''
from contextlib import contextmanager
import json,os,sys
from pathlib import Path
from nqc_defense.review_policy import read_credential
from nqc_defense.signer_registry import SignerRegistry
root=Path(sys.argv[1]); p=json.loads((root/'crash-registry.json').read_bytes())
registry=SignerRegistry(root/'registry',p['registry_digest'],p['authority_digest']); original=registry.connection
@contextmanager
def connection(write=False):
    with original(write=write) as db:
        if write and not p['after_commit']:
            db.create_function('terminate_test_process',0,lambda:os._exit(77))
            db.execute('CREATE TEMP TRIGGER die AFTER INSERT ON entries BEGIN SELECT terminate_test_process(); END')
        yield db
    if write and p['after_commit']:
        os._exit(78)
registry.connection=connection
registry.change(read_credential(root/'authority/signing.key'),'rotate',p['key_id'],'crash','Rotate signing key',
                p['expected'],bytes.fromhex(p['new_public']))
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.root)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(result.returncode, 78 if after_commit else 77, result.stderr)
        return public

    def test_real_process_exit_before_commit_preserves_active_key(self):
        self.crash_rotation(False)
        status = self.registry.status(self.registry_head)
        self.assertEqual(status['active_key'], self.key_pin)
        self.assertTrue(self.register()['applied'])

    def test_real_process_exit_after_commit_recovers_identical_rotation(self):
        public = self.crash_rotation(True)
        self.assertEqual(self.registry.status()['active_key'], sha256(public))
        result = self.rotate(request_id='crash', new_public_key=public)
        self.assertFalse(result['applied']); self.assertTrue(result['idempotent_retry'])

    def test_publication_rejects_unsafe_output_and_changed_readback(self):
        output = self.root/'public'; output.mkdir(mode=0o755)
        with self.assertRaisesRegex(Rejected, 'attestation_directory_permissions'):
            self.registry.publish(output/'bundle.json', self.registry_head)
        target = self.root/'original'; target.write_bytes(b'keep'); symlink = self.root/'link'; symlink.symlink_to(target)
        with self.assertRaises(Rejected):
            self.registry.publish(symlink, self.registry_head)
        self.assertEqual(target.read_bytes(), b'keep')
        from nqc_defense.signer_registry import read_local
        def changed(root, name, maximum):
            return b'changed' if name == 'bundle.json' else read_local(root, name, maximum)
        with patch('nqc_defense.signer_registry.read_local', side_effect=changed):
            with self.assertRaisesRegex(Rejected, 'registry_publication_changed'):
                self.registry.publish(self.root/'bundle.json', self.registry_head)

    def test_signature_and_record_pin_validation_with_signed_authority_rows(self):
        receipt = self.register()['receipt']; value = json.loads(self.registry.export(self.registry_head))
        for mutation in ('wrong_scope', 'reused_key', 'unknown_action', 'noncanonical_payload'):
            changed = json.loads(canonical(value))
            event = json.loads(changed['rows'][-1][1])
            if mutation == 'wrong_scope': event['pins']['policy_digest'] = 'f'*64
            if mutation == 'reused_key': event.update(action='activate', key_id=self.key_pin, new_public_key_hex=self.public_key.hex(),
                pins=None, attestation_digest=None, dossier_digest=None)
            if mutation == 'unknown_action': event['action'] = 'unknown'
            row = signed_row(self.authority, 2, changed['rows'][-1][2], event)
            if mutation == 'noncanonical_payload':
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                from nqc_defense.signer_registry import DOMAIN
                row[1] = json.dumps(event, indent=2)
                row[3] = Ed25519PrivateKey.from_private_bytes(self.authority).sign(DOMAIN+canonical([row[0], row[2], row[1]])).hex()
            changed['rows'][-1] = row; data = canonical(changed); target = {'revision':2, 'head':row_head(row)}
            with self.subTest(mutation=mutation), self.assertRaises(Rejected):
                verify_bundle(data, sha256(data), self.registry.digest, self.authority_digest, target)
        with self.assertRaisesRegex(Rejected, 'registry_record_binding'):
            self.verify(receipt, pins={**self.pins, 'tenant':'other'})

    def test_unhashable_digest_and_malformed_receipt_are_controlled(self):
        receipt = self.register()['receipt']
        with self.assertRaises(Rejected):
            self.verify(receipt, digest=[])
        with self.assertRaises(Rejected):
            self.verify(receipt, receipt={'revision':True, 'head':receipt['head']})

    def test_cli_key_lifecycle_record_export_and_public_verify(self):
        tool = Path(__file__).resolve().parents[1]/'tools/signer_registry.py'
        def call(*args, success=True):
            process = subprocess.run([sys.executable, '-B', str(tool), *map(str,args)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0 if success else 2, process.stdout+process.stderr)
            self.assertEqual(process.stderr, '')
            return json.loads(process.stdout)
        scope = self.root/'scope.json'; scope.write_bytes(canonical({'tenant':'tenant','asset':'host','policy_digest':self.policy.digest}))
        root = self.root/'cli-registry'
        result = call('init', '--registry-root', root, '--authority-public-file', self.authority_root/'verify.key',
                      '--authority-public-digest', self.authority_digest, '--scope-file', scope)
        common = ['--registry-root',root,'--registry-digest',result['registry_digest'],'--authority-public-digest',self.authority_digest]
        request = self.root/'request.json'
        request.write_bytes(canonical({'action':'activate','key_id':self.key_pin,'request_id':'activate',
            'reason':'CLI activation','expected':ORIGIN,'new_public_key_hex':self.public_key.hex()}))
        activated = call('change',*common,'--authority-key-file',self.authority_root/'signing.key','--request-file',request)
        request.write_bytes(canonical({'key_id':self.key_pin,'request_id':'record','reason':'CLI record','expected':activated['receipt']}))
        self.attestation_path.write_bytes(self.data); pins = self.root/'pins.json'; pins.write_bytes(canonical(self.pins))
        artifacts = ['--pins-file',pins,'--attestation-file',self.attestation_path,'--attestation-digest',self.digest,
                     '--dossier-file',self.dossier_path,'--dossier-digest',self.dossier_digest]
        registered = call('record',*common,*artifacts,'--authority-key-file',self.authority_root/'signing.key','--request-file',request)
        expected = self.root/'head.json'; expected.write_bytes(canonical(registered['receipt']))
        receipt = self.root/'receipt.json'; receipt.write_bytes(canonical(registered['receipt']))
        bundle = self.root/'bundle.json'; exported = call('export',*common,'--expected-file',expected,'--output',bundle)
        status = call('status',*common,'--expected-file',expected)
        self.assertEqual(status['registered_attestations'],1)
        for private in (root,self.registry.root,self.authority_root,self.signer,self.policy.root,self.store.root):
            shutil.rmtree(private)
        public = ['--registry-digest',result['registry_digest'],'--authority-public-digest',self.authority_digest,
                  '--expected-file',expected,'--receipt-file',receipt,'--bundle-file',bundle,'--bundle-digest',exported['bundle_digest']]
        self.assertTrue(call('verify',*public,*artifacts)['registry_accepted'])
        expected.write_bytes(canonical(ORIGIN))
        rejected = call('verify',*public,*artifacts,success=False)
        self.assertEqual(rejected['reason'],'registry_checkpoint_mismatch')


if __name__ == '__main__':
    unittest.main()
