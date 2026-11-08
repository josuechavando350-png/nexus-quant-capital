"""Real Ed25519 operations; ephemeral keys and explicitly synthetic local data.

RFC vectors verify the library primitive. Other tests verify the integration,
trust boundaries and negative controls; no proof of vulnerabilities is claimed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import rsa

from superhunter import custody as c
from superhunter.safe_io import canonical, strict_json, write_new_bundle

CASE = '46d27a53-54c5-4ca8-afda-0efff8ba4352'
OTHER_CASE = '16d27a53-54c5-4ca8-afda-0efff8ba4352'
NAME = 'local-fixture-producer'
AT = '2026-11-04T12:00:00+00:00'
EXPIRES = '2026-11-05T12:00:00+00:00'


class CustodyTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(); self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.bundle = self.root/'evidence'
        write_new_bundle(self.bundle, {'result.json': canonical({'fixture_only':True,'observations':2}),
                                       'REVIEW.md': b'SYNTHETIC CUSTODY FIXTURE ONLY\n'})
        self.private = Ed25519PrivateKey.generate()
        self.trust = self.trust_for(self.private)
        self.statement = c.attest(self.bundle, self.private, self.trust, case_id=CASE,
                                  producer_id=NAME, issued_at=AT, expires_at=EXPIRES)

    def trust_for(self, key):
        raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return {'schema_version':1, 'profile':c.PROFILE, 'keys':[{
            'key_id':c.sha(raw), 'public_key_hex':raw.hex(), 'producer_id':NAME,
            'case_ids':[CASE], 'valid_from':'2026-11-01T00:00:00+00:00',
            'valid_until':'2026-12-01T00:00:00+00:00', 'revoked':False}]}

    def verify(self, **kwargs):
        args = dict(expected_case_id=CASE, expected_producer_id=NAME, at=AT)
        args.update(kwargs)
        return c.verify_attestation(self.bundle,self.statement,self.trust,**args)

    def mutate_rehash(self, bundle, filename, raw):
        (bundle/filename).write_bytes(raw)
        marker = strict_json((bundle/'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = c.sha(raw)
        (bundle/'COMPLETE.json').write_bytes(canonical(marker))

    def resign(self):
        self.statement['signature_hex'] = self.private.sign(c.DOMAIN+canonical(self.statement['payload'])).hex()

    def make_key_files(self, *, real_clock=False):
        if real_clock:
            now=datetime.now(timezone.utc)
            self.trust['keys'][0].update(valid_from=(now-timedelta(days=1)).isoformat(),
                                         valid_until=(now+timedelta(days=2)).isoformat())
            expiry=(now+timedelta(days=1)).isoformat()
        else:
            expiry=EXPIRES
        self.key_file=self.root/'custody-key.pem'
        self.key_file.write_bytes(self.private.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.key_file.chmod(0o600)
        self.trust_file=self.root/'trusted-public-keys.json'
        self.trust_file.write_bytes(canonical(self.trust))
        return expiry

    def test_rfc8032_known_vector_matches_real_crypto(self):
        # RFC8032 section 7.1 TEST 1; public, non-secret interoperability fixture.
        seed=bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
        expected_public='d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a'
        expected_signature=('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'
                            '5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')
        key=Ed25519PrivateKey.from_private_bytes(seed)
        self.assertEqual(key.public_key().public_bytes_raw().hex(),expected_public)
        self.assertEqual(key.sign(b'').hex(),expected_signature)
        key.public_key().verify(bytes.fromhex(expected_signature),b'')
        with self.assertRaises(InvalidSignature):key.public_key().verify(bytes.fromhex(expected_signature),b'changed')

    def test_valid_signature_authenticates_only_custody(self):
        result=self.verify()
        self.assertEqual(result['status'],'TRUSTED_CUSTODY_SIGNATURE_VALID')
        self.assertTrue(result['signature_valid']);self.assertTrue(result['trusted_key_scope_matched'])
        for key in c.LIMITS:self.assertIs(result[key],False)
        self.assertFalse(result['human_identity_verified']);self.assertFalse(result['semantic_evidence_verified'])
        self.assertNotIn('finding',result)

    def test_same_inputs_sign_deterministically(self):
        again=c.attest(self.bundle,self.private,self.trust,case_id=CASE,producer_id=NAME,issued_at=AT,expires_at=EXPIRES)
        self.assertEqual(again,self.statement)

    def test_rehashed_modified_evidence_still_fails_signature_binding(self):
        self.mutate_rehash(self.bundle,'result.json',canonical({'fixture_only':False,'observations':999}))
        with self.assertRaisesRegex(c.CustodyError,'SIGNED_EVIDENCE_MISMATCH'):self.verify()

    def test_raw_evidence_edit_rejected(self):
        (self.bundle/'result.json').write_bytes(b'changed')
        with self.assertRaisesRegex(c.CustodyError,'ARTIFACT_HASH_MISMATCH'):self.verify()

    def test_unsigned_payload_modification_rejected(self):
        self.statement['payload']['expires_at']='2026-11-06T12:00:00+00:00'
        with self.assertRaisesRegex(c.CustodyError,'INVALID_SIGNATURE'):self.verify()

    def test_wrong_signature_rejected(self):
        self.statement['signature_hex']='00'*64
        with self.assertRaisesRegex(c.CustodyError,'INVALID_SIGNATURE'):self.verify()

    def test_signature_cannot_cross_message_domain(self):
        self.statement['signature_hex']=self.private.sign(canonical(self.statement['payload'])).hex()
        with self.assertRaisesRegex(c.CustodyError,'INVALID_SIGNATURE'):self.verify()

    def test_untrusted_valid_signer_rejected(self):
        other=Ed25519PrivateKey.generate()
        self.statement=c.attest(self.bundle,other,self.trust_for(other),case_id=CASE,producer_id=NAME,issued_at=AT,expires_at=EXPIRES)
        with self.assertRaisesRegex(c.CustodyError,'UNTRUSTED_KEY'):self.verify()

    def test_embedded_public_key_cannot_replace_trust(self):
        self.statement['public_key_hex']=self.trust['keys'][0]['public_key_hex']
        with self.assertRaisesRegex(c.CustodyError,'ATTESTATION_SCHEMA'):self.verify()

    def test_revoked_key_invalidates_existing_statement(self):
        self.trust['keys'][0]['revoked']=True
        with self.assertRaisesRegex(c.CustodyError,'KEY_REVOKED'):self.verify()

    def test_key_expiry_and_statement_expiry_checked(self):
        with self.assertRaisesRegex(c.CustodyError,'ATTESTATION_TIME'):self.verify(at=EXPIRES)
        self.trust['keys'][0]['valid_until']='2026-11-04T13:00:00Z'
        with self.assertRaisesRegex(c.CustodyError,'KEY_VALIDITY'):self.verify()

    def test_future_signature_not_accepted(self):
        with self.assertRaisesRegex(c.CustodyError,'ATTESTATION_TIME'):self.verify(at='2026-11-04T11:59:59Z')

    def test_expected_case_and_producer_required(self):
        for args in ({'expected_case_id':OTHER_CASE},{'expected_producer_id':'different-producer'}):
            with self.subTest(args=args),self.assertRaisesRegex(c.CustodyError,'CONTEXT_MISMATCH'):self.verify(**args)

    def test_trust_restricted_to_case(self):
        self.trust['keys'][0]['case_ids']=[OTHER_CASE]
        with self.assertRaisesRegex(c.CustodyError,'KEY_SCOPE_MISMATCH'):self.verify()

    def test_trust_restricted_to_producer(self):
        self.trust['keys'][0]['producer_id']='other'
        with self.assertRaisesRegex(c.CustodyError,'KEY_SCOPE_MISMATCH'):self.verify()

    def test_all_security_claims_false_even_with_valid_signature(self):
        self.statement['payload']['limitations']['vulnerability_confirmed']=True
        self.resign()
        with self.assertRaisesRegex(c.CustodyError,'EXCESSIVE_CLAIM'):self.verify()

    def test_json_boolean_is_not_number(self):
        self.statement['payload']['limitations']['execution_verified']=0
        self.resign()
        with self.assertRaisesRegex(c.CustodyError,'EXCESSIVE_CLAIM'):self.verify()
        self.statement['payload']['schema_version']=True
        with self.assertRaisesRegex(c.CustodyError,'PAYLOAD_VERSION'):self.verify()

    def test_audit_events_recomputed_even_if_signed_by_valid_key(self):
        self.statement['payload']['audit']['entries'][1]['data']['case_id']=OTHER_CASE
        self.resign()
        with self.assertRaisesRegex(c.CustodyError,'SIGNED_AUDIT_MISMATCH'):self.verify()

    def test_native_diablo_audit_is_executed(self):
        native=c.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as append:
            self.verify()
        self.assertEqual(append.call_count,3)

    def test_exact_manifest_bytes_bound(self):
        raw=(self.bundle/'COMPLETE.json').read_bytes()
        (self.bundle/'COMPLETE.json').write_bytes(raw+b'\n')
        with self.assertRaisesRegex(c.CustodyError,'SIGNED_EVIDENCE_MISMATCH'):self.verify()

    def test_unlisted_file_not_silently_excluded(self):
        (self.bundle/'secret.txt').write_bytes(b'synthetic')
        with self.assertRaisesRegex(c.CustodyError,'UNDECLARED_ARTIFACT'):self.verify()

    def test_missing_file_or_manifest_rejected(self):
        (self.bundle/'result.json').unlink()
        with self.assertRaises((OSError,c.CustodyError)):self.verify()
        (self.bundle/'COMPLETE.json').unlink()
        with self.assertRaises((OSError,c.CustodyError)):self.verify()

    def test_symlink_artifact_rejected(self):
        data=(self.bundle/'result.json').read_bytes();(self.bundle/'result.json').unlink()
        (self.root/'outside').write_bytes(data);(self.bundle/'result.json').symlink_to(self.root/'outside')
        with self.assertRaises((OSError,c.CustodyError)):self.verify()

    def test_root_symlink_rejected(self):
        (self.root/'alias').symlink_to(self.bundle,target_is_directory=True)
        with self.assertRaisesRegex(c.CustodyError,'DIRECTORY_SYMLINK'):c.capture_bundle(self.root/'alias')

    def test_nested_bundle_not_silently_walked(self):
        (self.bundle/'nested').mkdir()
        with self.assertRaisesRegex(c.CustodyError,'UNDECLARED_ARTIFACT'):self.verify()

    def test_duplicate_manifest_keys_rejected(self):
        (self.bundle/'COMPLETE.json').write_bytes(b'{"schema_version":1,"schema_version":1,"sha256":{}}')
        with self.assertRaises(ValueError):self.verify()

    def test_artifact_names_cannot_traverse(self):
        for name in ('../key.pem','/tmp/x','x/y','x\\y','COMPLETE.json'):
            with self.subTest(name=name):
                (self.bundle/'COMPLETE.json').write_bytes(canonical({'schema_version':1,'sha256':{name:'0'*64}}))
                with self.assertRaisesRegex(c.CustodyError,'ARTIFACT_NAME'):self.verify()

    def test_file_and_total_limits(self):
        with patch.object(c,'MAX_FILES',1),self.assertRaisesRegex(c.CustodyError,'MANIFEST_FILES'):self.verify()
        with patch.object(c,'MAX_TOTAL_BYTES',1),self.assertRaisesRegex(c.CustodyError,'TOTAL_BYTES_LIMIT'):self.verify()

    def test_key_duplicate_hash_or_invalid_public_key_rejected(self):
        self.trust['keys']*=2
        with self.assertRaisesRegex(c.CustodyError,'TRUST_KEY_ID'):self.verify()
        self.trust['keys']=self.trust['keys'][:1];self.trust['keys'][0]['public_key_hex']='x'*64
        with self.assertRaisesRegex(c.CustodyError,'HEX_FORMAT'):self.verify()

    def test_unknown_algorithm_not_downgraded(self):
        for algo in ('none','HS256','ed25519'):
            self.statement['algorithm']=algo
            with self.assertRaisesRegex(c.CustodyError,'ALGORITHM_NOT_ALLOWED'):self.verify()

    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(c.CustodyError,'TIMEZONE_REQUIRED'):self.verify(at='2026-11-04T12:00:00')

    def test_no_network_or_shell_used(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.assertTrue(self.verify()['signature_valid'])

    def test_signature_plaintext_does_not_contain_private_material(self):
        self.assertNotIn(self.private.private_bytes_raw().hex(),canonical(self.statement).decode())
        self.assertNotIn('BEGIN PRIVATE KEY',canonical(self.statement).decode())
        self.assertNotIn('public_key_hex',self.statement)

    def test_changed_during_capture_blocks_signing(self):
        actual=c.capture_bundle(self.bundle);changed={**actual,'total_bytes':999}
        with patch.object(c,'capture_bundle',side_effect=[actual,changed]),self.assertRaisesRegex(c.CustodyError,'CHANGED_DURING_SIGNING'):
            c.attest(self.bundle,self.private,self.trust,case_id=CASE,producer_id=NAME,issued_at=AT,expires_at=EXPIRES)

    def test_private_file_permissions_enforced(self):
        self.make_key_files();self.key_file.chmod(0o644)
        with self.assertRaisesRegex(c.CustodyError,'PRIVATE_KEY_FILE_PROTECTION'):c._key_file(self.key_file)

    def test_private_symlink_or_hardlink_rejected(self):
        self.make_key_files();alias=self.root/'alias.pem';alias.symlink_to(self.key_file)
        with self.assertRaises((ValueError,OSError)):c._key_file(alias)
        alias.unlink();os.link(self.key_file,alias)
        with self.assertRaisesRegex(c.CustodyError,'PRIVATE_KEY_FILE_PROTECTION'):c._key_file(self.key_file)

    def test_private_file_must_be_ed25519(self):
        self.make_key_files();key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        with self.assertRaisesRegex(c.CustodyError,'ED25519_PRIVATE_KEY_REQUIRED'):c._key_file(self.key_file)

    def test_trust_must_be_external_to_evidence(self):
        self.make_key_files();inside=self.bundle/'trust.json';inside.write_bytes(canonical(self.trust))
        with self.assertRaisesRegex(c.CustodyError,'TRUST_OR_KEY_INSIDE_EVIDENCE'):
            c.seal(self.bundle,self.root/'seal',self.key_file,inside,case_id=CASE,producer_id=NAME,expires_at=EXPIRES)

    def test_detached_seal_preserves_originals(self):
        expiry=self.make_key_files(real_clock=True);before={p.name:p.read_bytes() for p in self.bundle.iterdir()}
        c.seal(self.bundle,self.root/'seal',self.key_file,self.trust_file,case_id=CASE,producer_id=NAME,expires_at=expiry)
        self.assertTrue(c.verify_seal(self.bundle,self.root/'seal',self.trust_file,case_id=CASE,producer_id=NAME)['signature_valid'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.bundle.iterdir()})
        self.assertEqual({p.name for p in (self.root/'seal').iterdir()},c.SEAL_FILES|{'COMPLETE.json'})
        self.assertEqual((self.root/'seal').stat().st_mode&0o777,0o700)
        for p in (self.root/'seal').iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_existing_seal_cannot_be_overwritten(self):
        expiry=self.make_key_files(real_clock=True);out=self.root/'seal'
        c.seal(self.bundle,out,self.key_file,self.trust_file,case_id=CASE,producer_id=NAME,expires_at=expiry)
        with self.assertRaisesRegex(c.CustodyError,'NEW_OUTPUT_REQUIRED'):
            c.seal(self.bundle,out,self.key_file,self.trust_file,case_id=CASE,producer_id=NAME,expires_at=expiry)

    def test_rehashed_seal_cannot_change_signature(self):
        expiry=self.make_key_files(real_clock=True);out=self.root/'seal'
        c.seal(self.bundle,out,self.key_file,self.trust_file,case_id=CASE,producer_id=NAME,expires_at=expiry)
        s=strict_json((out/'attestation.json').read_bytes());s['signature_hex']='0'*128
        self.mutate_rehash(out,'attestation.json',canonical(s))
        with self.assertRaisesRegex(c.CustodyError,'INVALID_SIGNATURE'):
            c.verify_seal(self.bundle,out,self.trust_file,case_id=CASE,producer_id=NAME)

    def test_cli_real_sign_and_separate_verify(self):
        expiry=self.make_key_files(real_clock=True);out=self.root/'seal'
        common=['--bundle',str(self.bundle),'--trust',str(self.trust_file),'--case-id',CASE,'--producer',NAME]
        for args in (['seal-evidence',*common,'--key-file',str(self.key_file),'--expires-at',expiry,'--out',str(out)],
                     ['verify-custody',*common,'--seal',str(out)]):
            run=subprocess.run([sys.executable,'-B','-m','superhunter',*args],cwd=c.ROOT.parent,
                               capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertTrue(json.loads(run.stdout)['signature_valid'])
            self.assertNotIn(NAME,run.stdout);self.assertNotIn(str(self.root),run.stdout)

    def test_cli_diagnostics_hide_paths_values_and_no_replay_flag(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            c.main(['verify-custody','--bundle','SECRET_VALUE'])
        self.assertNotIn('SECRET_VALUE',stream.getvalue())
        with patch('sys.stderr',new_callable=io.StringIO),self.assertRaises(SystemExit):
            c.main(['verify-custody','--bundle','x','--trust','y','--seal','z',
                    '--case-id',CASE,'--producer',NAME,'--at',AT])

    def test_relocated_evidence_uses_bytes_not_location(self):
        clone=self.root/'copied';shutil.copytree(self.bundle,clone)
        result=c.verify_attestation(clone,self.statement,self.trust,expected_case_id=CASE,expected_producer_id=NAME,at=AT)
        self.assertTrue(result['signature_valid'])

    def test_real_native_lab_bundle_can_be_sealed(self):
        from superhunter.local_lab import run_local, verify_local_bundle
        path=self.root/'native-lab';run_local(path)
        self.assertEqual(verify_local_bundle(path)['status'],'LOCAL_INTEGRATION_PASS')
        statement=c.attest(path,self.private,self.trust,case_id=CASE,producer_id=NAME,issued_at=AT,expires_at=EXPIRES)
        result=c.verify_attestation(path,statement,self.trust,expected_case_id=CASE,expected_producer_id=NAME,at=AT)
        self.assertTrue(result['signature_valid']);self.assertFalse(result['execution_verified'])


if __name__=='__main__':unittest.main()
