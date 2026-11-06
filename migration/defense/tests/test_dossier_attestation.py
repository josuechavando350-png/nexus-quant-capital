from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import test_review_dossier as fixtures
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import (DOMAIN, attest_dossier, create_signer, load_signer,
    public_bytes, publish_attestation, verify_attestation)
from nqc_defense.files import sha256


class AttestationTests(unittest.TestCase):
    apply = fixtures.DossierTests.apply
    view = fixtures.DossierTests.view
    change = fixtures.DossierTests.change
    capture = fixtures.DossierTests.capture

    def setUp(self):
        fixtures.DossierTests.setUp(self)
        self.capture(); self.dossier_path = self.output
        self.dossier = self.output.read_bytes(); self.dossier_digest = sha256(self.dossier)
        self.signer = self.root/'signer'
        self.key_pin = create_signer(self.signer)['public_key_sha256']
        self.signing_key = load_signer(self.signer, self.key_pin)
        self.public_key = (self.signer/'verify.key').read_bytes()
        self.attestation_path = self.root/'attestation.json'

    def issue(self, **changes):
        args = dict(dossier=self.dossier, dossier_digest=self.dossier_digest, pins=self.pins,
                    audit_key=self.policy.key, signing_key=self.signing_key, public_key_digest=self.key_pin)
        args.update(changes)
        return attest_dossier(**args)

    def verify(self, data=None, **changes):
        data = self.issue() if data is None else data
        args = dict(data=data, digest=sha256(data), dossier=self.dossier, dossier_digest=self.dossier_digest,
                    pins=self.pins, public_key=self.public_key, public_key_digest=self.key_pin)
        args.update(changes)
        return verify_attestation(**args)

    def publish(self, **changes):
        args = dict(output=self.attestation_path, dossier=self.dossier, dossier_digest=self.dossier_digest,
                    pins=self.pins, audit_key=self.policy.key, signing_key=self.signing_key,
                    public_key_digest=self.key_pin)
        args.update(changes)
        return publish_attestation(**args)

    def resigned(self, value):
        value['signature_hex'] = Ed25519PrivateKey.from_private_bytes(self.signing_key).sign(
            DOMAIN+canonical(value['statement'])).hex()
        return canonical(value)

    def test_issued_statement_contains_real_replay_and_explicit_trust_limits(self):
        result = self.verify()
        self.assertTrue(result['signature_verified'])
        self.assertTrue(result['dossier_bytes_matched'])
        self.assertEqual(result['signer_report']['facts']['review']['stage'], 'closed')
        self.assertEqual(result['signer_report']['assessment']['classification'], 'analyst_claim')
        self.assertTrue(result['limits']['report_is_issuer_assertion'])
        self.assertFalse(result['limits']['hmac_history_replayed_by_this_verifier'])
        self.assertFalse(result['limits']['independent_custody'])

    def test_public_verifier_uses_no_secrets_io_clock_or_hmac_replay(self):
        data = self.issue()
        with ExitStack() as stack:
            for target in ('builtins.open', 'os.open', 'sqlite3.connect', 'socket.socket', 'time.time_ns',
                           'pathlib.Path.read_bytes', 'nqc_defense.dossier_attestation.verify_dossier'):
                stack.enter_context(patch(target, side_effect=AssertionError('unexpected dependency')))
            self.assertTrue(self.verify(data)['signature_verified'])

    def test_verifies_after_original_store_logs_policy_and_signing_key_removed(self):
        data = self.issue()
        shutil.rmtree(self.store.root); shutil.rmtree(self.policy.root); shutil.rmtree(self.signer)
        self.log.unlink(); self.bundle_path.unlink()
        self.assertTrue(self.verify(data)['signature_verified'])

    def test_signer_creation_is_private_and_does_not_replace_existing_keys(self):
        self.assertEqual(self.signer.stat().st_mode & 0o777, 0o700)
        for name in ('signing.key', 'verify.key'):
            self.assertEqual((self.signer/name).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            create_signer(self.signer)
        self.assertEqual(load_signer(self.signer, self.key_pin), self.signing_key)

    def test_signer_pair_and_public_pin_must_match(self):
        with self.assertRaisesRegex(Rejected, 'attestation_public_key_pin'):
            load_signer(self.signer, 'f'*64)
        (self.signer/'signing.key').write_bytes(secrets.token_bytes(32))
        with self.assertRaisesRegex(Rejected, 'attestation_key_pair_mismatch'):
            load_signer(self.signer, self.key_pin)

    def test_signer_directory_key_permissions_symlinks_and_hardlinks_rejected(self):
        os.chmod(self.signer, 0o755)
        with self.assertRaisesRegex(Rejected, 'attestation_directory_permissions'):
            load_signer(self.signer, self.key_pin)
        os.chmod(self.signer, 0o700)
        key = self.signer/'signing.key'; os.chmod(key, 0o644)
        with self.assertRaisesRegex(Rejected, 'review_credential_permissions'):
            load_signer(self.signer, self.key_pin)
        os.chmod(key, 0o600); os.link(key, self.root/'key-link')
        with self.assertRaisesRegex(Rejected, 'review_credential_permissions'):
            load_signer(self.signer, self.key_pin)
        (self.root/'key-link').unlink(); key.rename(self.root/'moved-key'); key.symlink_to(self.root/'moved-key')
        with self.assertRaisesRegex(Rejected, 'review_credential_permissions'):
            load_signer(self.signer, self.key_pin)

    def test_audit_key_cannot_be_reused_as_signing_key(self):
        with self.assertRaisesRegex(Rejected, 'attestation_key_must_differ'):
            self.issue(signing_key=self.policy.key, public_key_digest=sha256(public_bytes(self.policy.key)))

    def test_key_sizes_rejected(self):
        for key in (b'', b'x'*31, b'x'*33, 'x'*32):
            with self.subTest(size=len(key)), self.assertRaises(Rejected):
                self.issue(signing_key=key)
            with self.subTest(public_size=len(key)), self.assertRaises(Rejected):
                self.verify(public_key=key)

    def test_wrong_audit_key_or_ordinary_reviewer_cannot_issue(self):
        for key in (secrets.token_bytes(32), self.tokens['ana']):
            with self.assertRaisesRegex(Rejected, 'review_audit_key_digest'):
                self.issue(audit_key=key)

    def test_dossier_corruption_and_stale_checkpoints_prevent_issuance(self):
        value = json.loads(self.dossier); value['review_rows'].pop()
        data = canonical(value)
        with self.assertRaisesRegex(Rejected, 'dossier_case_checkpoint'):
            self.issue(dossier=data, dossier_digest=sha256(data))
        with self.assertRaisesRegex(Rejected, 'dossier_digest'):
            self.issue(dossier=self.dossier+b' ')

    def test_public_key_substitution_fails_external_pin(self):
        with self.assertRaisesRegex(Rejected, 'attestation_public_key_pin'):
            self.verify(public_key=public_bytes(secrets.token_bytes(32)))

    def test_alternate_key_cannot_claim_original_signer(self):
        value = json.loads(self.issue())
        value['signature_hex'] = Ed25519PrivateKey.generate().sign(DOMAIN+canonical(value['statement'])).hex()
        with self.assertRaisesRegex(Rejected, 'attestation_signature_invalid'):
            self.verify(canonical(value))

    def test_external_receipt_digest_required(self):
        with self.assertRaisesRegex(Rejected, 'attestation_digest'):
            self.verify(digest='f'*64)

    def test_changed_dossier_bytes_cannot_match_receipt(self):
        data = self.issue(); changed = self.dossier+b' '
        with self.assertRaisesRegex(Rejected, 'dossier_digest'):
            self.verify(data, dossier=changed)
        with self.assertRaisesRegex(Rejected, 'attestation_statement_binding'):
            self.verify(data, dossier=changed, dossier_digest=sha256(changed))

    def test_scope_and_checkpoint_pins_must_match_statement_exactly(self):
        data = self.issue()
        for key, value in (('tenant', 'other'), ('asset', 'other'), ('case_id', 'e'*64),
                           ('case_checkpoint', {**self.pins['case_checkpoint'], 'head':'e'*64}),
                           ('minimum_clock_ns', 0)):
            with self.subTest(field=key), self.assertRaisesRegex(Rejected, 'attestation_statement_binding'):
                self.verify(data, pins={**self.pins, key:value})

    def test_changed_report_is_rejected_even_with_recomputed_outer_hash(self):
        value = json.loads(self.issue()); value['statement']['report']['facts']['review']['stage'] = 'investigating'
        with self.assertRaisesRegex(Rejected, 'attestation_signature_invalid'):
            self.verify(canonical(value))

    def test_signature_domain_is_mandatory(self):
        value = json.loads(self.issue())
        value['signature_hex'] = Ed25519PrivateKey.from_private_bytes(self.signing_key).sign(canonical(value['statement'])).hex()
        with self.assertRaisesRegex(Rejected, 'attestation_signature_invalid'):
            self.verify(canonical(value))

    def test_signature_encodings_are_strict(self):
        original = json.loads(self.issue())
        for signature in ('', 'ff'*63, 'ff'*65, 'FF'*64, 'gg'*64, 1, '\ud800'):
            with self.subTest(signature_type=type(signature).__name__), self.assertRaisesRegex(Rejected, 'attestation_signature_encoding'):
                self.verify(canonical({**original, 'signature_hex':signature}))

    def test_schema_fields_and_algorithm_are_fixed(self):
        original = json.loads(self.issue())
        for key, value in (('schema', 'other'), ('algorithm', 'Ed25519ph')):
            changed = json.loads(canonical(original)); changed['statement'][key] = value
            with self.assertRaisesRegex(Rejected, 'attestation_statement_schema'):
                self.verify(canonical(changed))
        for changed in ({**original, 'extra':True}, {**original, 'schema':'other'}, {**original, 'statement':[]}):
            with self.assertRaises(Rejected):
                self.verify(canonical(changed))

    def test_noncanonical_duplicate_fields_and_size_limits_rejected(self):
        value = json.loads(self.issue()); data = json.dumps(value, indent=2).encode()
        with self.assertRaisesRegex(Rejected, 'attestation_schema'):
            self.verify(data)
        with self.assertRaisesRegex(Rejected, 'invalid_json'):
            self.verify(b'{"schema":1,"schema":2}')
        data = self.issue()
        with patch('nqc_defense.dossier_attestation.MAX_ATTESTATION', len(data)-1):
            with self.assertRaisesRegex(Rejected, 'attestation_size'):
                self.verify(data)
        with patch('nqc_defense.dossier_attestation.MAX_DOSSIER', len(self.dossier)-1):
            with self.assertRaisesRegex(Rejected, 'dossier_size'):
                self.verify(data)

    def test_valid_signature_with_mismatched_report_scope_is_rejected(self):
        value = json.loads(self.issue()); value['statement']['report']['tenant'] = 'other'
        with self.assertRaisesRegex(Rejected, 'attestation_report_binding'):
            self.verify(self.resigned(value))

    def test_signed_report_checkpoint_binding_is_strict_including_boolean_revision(self):
        value = json.loads(self.issue())
        value['statement']['report']['facts']['credentials']['checkpoint']['revision'] = False
        with self.assertRaisesRegex(Rejected, 'attestation_report_binding'):
            self.verify(self.resigned(value))

    def test_signed_report_shape_rejections_are_controlled(self):
        original = json.loads(self.issue())
        for value in ({}, [], {'schema':'unknown'}):
            changed = json.loads(canonical(original)); changed['statement']['report'] = value
            with self.assertRaises(Rejected):
                self.verify(self.resigned(changed))

    def test_trusted_signer_can_assert_report_but_public_verifier_does_not_claim_hmac_replay(self):
        # Deliberately demonstrates the trust boundary; signatures do not establish factual truth.
        value = json.loads(self.issue()); value['statement']['report']['facts']['review']['notes_count'] = 99
        result = self.verify(self.resigned(value))
        self.assertTrue(result['signature_verified'])
        self.assertEqual(result['signer_report']['facts']['review']['notes_count'], 99)
        self.assertFalse(result['limits']['hmac_history_replayed_by_this_verifier'])
        self.assertTrue(result['limits']['report_is_issuer_assertion'])

    def test_historical_statement_does_not_claim_current_state_after_reopen(self):
        data = self.issue(); self.apply('reopen', actor='boris')
        self.assertEqual(self.verify(data)['signer_report']['facts']['review']['stage'], 'closed')
        self.assertFalse(self.verify(data)['limits']['current_state_attested'])
        with self.assertRaisesRegex(Rejected, 'attestation_statement_binding'):
            self.verify(data, pins={**self.pins, 'case_checkpoint':self.head})

    def test_deterministic_retry_keeps_identical_bytes_without_replacement(self):
        first = self.publish(); original = self.attestation_path.read_bytes()
        inode = self.attestation_path.stat().st_ino
        self.assertEqual(first, self.publish())
        self.assertEqual(original, self.attestation_path.read_bytes())
        self.assertEqual(inode, self.attestation_path.stat().st_ino)
        self.assertEqual(self.attestation_path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_identical_publication_is_consistent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _:self.publish(), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertTrue(self.verify(self.attestation_path.read_bytes())['signature_verified'])

    def test_public_directory_existing_content_and_symlink_rejected(self):
        public = self.root/'public'; public.mkdir(mode=0o755)
        with self.assertRaisesRegex(Rejected, 'attestation_directory_permissions'):
            self.publish(output=public/'receipt.json')
        self.attestation_path.write_bytes(b'keep')
        with self.assertRaisesRegex(Rejected, 'existing_file_differs'):
            self.publish()
        self.assertEqual(self.attestation_path.read_bytes(), b'keep')
        self.attestation_path.unlink(); self.attestation_path.symlink_to(self.dossier_path)
        with self.assertRaises(Rejected):
            self.publish()
        self.assertEqual(self.dossier_path.read_bytes(), self.dossier)

    def test_failed_publication_and_readback_do_not_report_success(self):
        with patch('nqc_defense.dossier_attestation.publish_local', side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.publish()
        with patch('nqc_defense.dossier_attestation.read_local', return_value=b'changed'):
            with self.assertRaisesRegex(Rejected, 'attestation_publication_changed'):
                self.publish()

    def test_incomplete_key_initialization_is_not_silently_adopted(self):
        from nqc_defense.files import create_local
        root = self.root/'incomplete'
        def failing(directory, name, data):
            if name == 'verify.key':
                raise OSError('injected')
            create_local(directory, name, data)
        with patch('nqc_defense.dossier_attestation.create_local', side_effect=failing):
            with self.assertRaises(OSError):
                create_signer(root)
        with self.assertRaises(Rejected):
            load_signer(root, self.key_pin)
        with self.assertRaises(FileExistsError):
            create_signer(root)

    def test_private_key_and_administrative_secret_fields_not_added(self):
        data = self.issue()
        for secret in (self.signing_key, self.policy.key, *self.tokens.values()):
            self.assertNotIn(secret.hex().encode(), data)

    def test_missing_optional_crypto_backend_is_controlled(self):
        original_import = __import__
        def unavailable(name, *args, **kwargs):
            if name.startswith('cryptography'):
                raise ImportError('injected')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=unavailable):
            with self.assertRaisesRegex(Rejected, 'attestation_dependency_unavailable'):
                public_bytes(self.signing_key)

    def test_rfc8032_vector_one_matches_installed_backend(self):
        # Public RFC 8032 section 7.1 TEST 1; never an operational key.
        seed = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
        expected_public = 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a'
        expected_signature = ('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'
                              '5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        key = Ed25519PrivateKey.from_private_bytes(seed)
        self.assertEqual(public_bytes(seed).hex(), expected_public)
        self.assertEqual(key.sign(b'').hex(), expected_signature)
        key.public_key().verify(bytes.fromhex(expected_signature), b'')

    def test_cli_full_flow_and_verification_without_private_material(self):
        tool = Path(__file__).resolve().parents[1]/'tools/dossier_attestation.py'
        def run(*args):
            return subprocess.run([sys.executable, '-B', str(tool), *map(str,args)], capture_output=True, text=True)
        root = self.root/'cli-signer'
        created = run('init-signer', '--signer-root', root)
        self.assertEqual(created.returncode, 0, created.stderr+created.stdout)
        pin = json.loads(created.stdout)['public_key_sha256']
        pins = self.root/'pins.json'; pins.write_bytes(canonical(self.pins))
        common = ['--pins-file', pins, '--dossier-file', self.dossier_path,
                  '--dossier-digest', self.dossier_digest, '--public-key-digest', pin]
        issued = run('issue', *common, '--signer-root', root, '--audit-key-file', self.policy.root/'audit.key',
                     '--output', self.attestation_path)
        self.assertEqual(issued.returncode, 0, issued.stderr+issued.stdout)
        receipt = json.loads(issued.stdout)
        public = self.root/'public.key'; public.write_bytes((root/'verify.key').read_bytes())
        shutil.rmtree(root); shutil.rmtree(self.signer); shutil.rmtree(self.store.root); shutil.rmtree(self.policy.root)
        self.log.unlink(); self.bundle_path.unlink()
        args = ['verify', *common, '--public-key-file', public, '--attestation-file', self.attestation_path,
                '--attestation-digest', receipt['attestation_digest']]
        verified = run(*args)
        self.assertEqual(verified.returncode, 0, verified.stderr+verified.stdout)
        self.assertTrue(json.loads(verified.stdout)['signature_verified'])
        value = json.loads(self.attestation_path.read_bytes()); value['signature_hex'] = '00'*64
        data = canonical(value); self.attestation_path.write_bytes(data); args[-1] = sha256(data)
        rejected = run(*args)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stderr, '')
        self.assertEqual(json.loads(rejected.stdout), {'success':False, 'reason':'attestation_signature_invalid'})


if __name__ == '__main__':
    unittest.main()
