"""Real local Ed25519 custody over verified indexes; keys stay ephemeral in RAM."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from superhunter import bundle_recovery as recovery, custody, portable_copy as portable, preserved_index as index, preserved_custody as joined, quality, safe_io

CASE = 'a08bf02d-4e27-4cf9-af00-710b5fdf48cf'
PRODUCER = 'ephemeral-owned-index-custodian'


class PreservedCustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp=tempfile.TemporaryDirectory();cls.addClassCleanup(temp.cleanup);cls.base=Path(temp.name)
        cls.digest=quality.sha(safe_io.canonical(quality.source_snapshot()))
        cls.template=cls.base/'template';cls.template.mkdir()
        source=cls.base/'source';source.mkdir();(source/'data.bin').write_bytes(b'private-incomplete-own-data')
        preserved=cls.base/'preserved';input_anchor=recovery.inspect(source)['input_anchor']
        made=recovery.preserve(source,preserved,source_digest=cls.digest,input_anchor=input_anchor)
        archives=cls.template/'archives';archives.mkdir()
        r=portable.export(preserved,archives/'copy.zip',source_digest=cls.digest,input_anchor=input_anchor,
                          recovery_anchor=made['recovery_anchor'],include_private_bytes=True)
        manifest=cls.base/'manifest.json';manifest.write_bytes(safe_io.canonical({'schema_version':1,
            'profile':index.MANIFEST_PROFILE,'archives':[{'id':'one','file':'copy.zip',**{key:r[key] for key in index.PINS}}]}))
        cls.manifest_anchor=quality.sha(manifest.read_bytes())
        made=index.build(manifest,archives,cls.template/'index',source_digest=cls.digest,manifest_anchor=cls.manifest_anchor)
        cls.index_anchor=made['index_anchor']

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        shutil.copytree(self.template/'index',self.root/'index');shutil.copytree(self.template/'archives',self.root/'archives')
        self.bundle=self.root/'index';self.archives=self.root/'archives';self.seal=self.root/'seal'
        self.trust=self.root/'private-trust.json';self.out=self.root/'review';self.key=Ed25519PrivateKey.generate()
        self.now=datetime.now(timezone.utc)-timedelta(seconds=1)
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.policy={'schema_version':1,'profile':custody.PROFILE,'keys':[{'key_id':custody.sha(public),
            'public_key_hex':public.hex(),'producer_id':PRODUCER,'case_ids':[CASE],
            'valid_from':(self.now-timedelta(days=1)).isoformat(),'valid_until':(self.now+timedelta(days=2)).isoformat(),
            'revoked':False}]}
        self.save_trust();self.make_seal()

    def save_trust(self):
        self.trust.write_bytes(safe_io.canonical(self.policy));self.trust_anchor=quality.sha(self.trust.read_bytes())

    def make_seal(self):
        if self.seal.exists():shutil.rmtree(self.seal)
        statement=custody.attest(self.bundle,self.key,self.policy,case_id=CASE,producer_id=PRODUCER,
                                 issued_at=self.now.isoformat(),expires_at=(self.now+timedelta(days=1)).isoformat())
        safe_io.write_new_bundle(self.seal,{'attestation.json':safe_io.canonical(statement),'REVIEW.md':custody._summary(statement)})
        self.seal_anchor=quality.sha((self.seal/'COMPLETE.json').read_bytes())

    def context(self):
        return {'source_digest':self.digest,'manifest_anchor':self.manifest_anchor,'index_anchor':self.index_anchor,
                'seal_anchor':self.seal_anchor,'trust_anchor':self.trust_anchor,'case_id':CASE,'producer_id':PRODUCER}

    def create(self,**changes):
        return joined.create(**{'bundle':self.bundle,'archive_root':self.archives,'seal':self.seal,'trust':self.trust,
                                 'out':self.out,**self.context(),**changes})

    def verify(self,**changes):
        return joined.verify(**{'bundle':self.bundle,'archive_root':self.archives,'seal':self.seal,'trust':self.trust,
            'report':self.out,'report_anchor':quality.sha((self.out/'COMPLETE.json').read_bytes()),**self.context(),**changes})

    def reseal(self,root):
        marker={'schema_version':1,'sha256':{p.name:quality.sha(p.read_bytes()) for p in root.iterdir() if p.name!='COMPLETE.json'}}
        (root/'COMPLETE.json').write_bytes(safe_io.canonical(marker))

    def test_real_signature_and_archive_check_preserve_incomplete_state(self):
        result=self.create();checked=self.verify()
        self.assertTrue(result['custody_signature_verified']);self.assertTrue(result['archive_bytes_checked'])
        self.assertEqual(result['counts']['incomplete_unique_archives'],1);self.assertEqual(checked['counts'],result['counts'])
        for name in joined.LIMITS:self.assertIs(result[name],False)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode),0o700)
        for path in self.out.iterdir():self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_valid_signature_cannot_approve_false_index_counts(self):
        p=self.bundle/'index.json';report=json.loads(p.read_bytes());report['counts']['unique_archives']=500
        p.write_bytes(safe_io.canonical(report));self.reseal(self.bundle);self.index_anchor=quality.sha((self.bundle/'COMPLETE.json').read_bytes())
        self.make_seal()
        self.assertTrue(custody.verify_seal(self.bundle,self.seal,self.trust,case_id=CASE,producer_id=PRODUCER)['signature_valid'])
        with self.assertRaisesRegex(ValueError,'INDEX_CONTENT'):self.create()
        self.assertFalse(self.out.exists())

    def test_correct_signed_index_still_requires_archive_bytes(self):
        p=self.archives/'copy.zip';raw=p.read_bytes();p.unlink()
        with self.assertRaises(ValueError):self.create()
        p.write_bytes(raw+b'changed')
        with self.assertRaises(ValueError):self.create()

    def test_external_trust_pin_is_required_even_for_valid_key(self):
        with self.assertRaisesRegex(ValueError,'TRUST_ANCHOR'):self.create(trust_anchor='0'*64)
        self.policy['keys'][0]['valid_until']=(self.now+timedelta(days=3)).isoformat();self.trust.write_bytes(safe_io.canonical(self.policy))
        with self.assertRaisesRegex(ValueError,'TRUST_ANCHOR'):self.create()

    def test_all_external_anchors_and_source_identities_checked(self):
        self.create()
        for key in ('source_digest','manifest_anchor','index_anchor','seal_anchor','trust_anchor','report_anchor','index_source_digest','review_source_digest'):
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify(**{key:'0'*64})

    def test_revoked_key_with_updated_policy_anchor_is_rejected(self):
        self.policy['keys'][0]['revoked']=True;self.save_trust()
        with self.assertRaisesRegex(ValueError,'KEY_REVOKED'):self.create()

    def test_wrong_case_or_producer_rejected(self):
        for change in ({'case_id':'b08bf02d-4e27-4cf9-af00-710b5fdf48cf'},{'producer_id':'other-custodian'}):
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):self.create(**change)

    def test_expired_seal_and_expiry_during_index_verification_rejected(self):
        expired=(self.now+timedelta(days=1,seconds=1)).isoformat()
        with patch.object(custody,'now_text',return_value=expired):
            with self.assertRaisesRegex(ValueError,'ATTESTATION_TIME'):self.create()
        real=index.verify
        def later(*args,**kwargs):
            r=real(*args,**kwargs);p=patch.object(custody,'now_text',return_value=expired);p.start();self.addCleanup(p.stop);return r
        with patch.object(index,'verify',side_effect=later):
            with self.assertRaisesRegex(ValueError,'ATTESTATION_TIME'):self.create()

    def test_corrupt_signature_with_new_seal_anchor_is_rejected(self):
        p=self.seal/'attestation.json';statement=json.loads(p.read_bytes());signature=bytearray.fromhex(statement['signature_hex'])
        signature[0]^=1;statement['signature_hex']=signature.hex();p.write_bytes(safe_io.canonical(statement));self.reseal(self.seal)
        self.seal_anchor=quality.sha((self.seal/'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNATURE'):self.create()

    def test_trust_inside_evidence_or_symlink_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXTERNAL_TRUST_REQUIRED'):self.create(trust=self.bundle/'inputs.json')
        actual=self.root/'actual-trust';self.trust.rename(actual);self.trust.symlink_to(actual)
        with self.assertRaisesRegex(ValueError,'SYMLINK'):self.create()

    def test_trust_change_during_index_check_is_rejected(self):
        real=index.verify
        def change(*args,**kwargs):
            r=real(*args,**kwargs);self.trust.write_bytes(self.trust.read_bytes()+b' ');return r
        with patch.object(index,'verify',side_effect=change):
            with self.assertRaisesRegex(ValueError,'TRUST_CHANGED'):self.create()

    def test_archive_change_during_final_signature_check_is_rejected(self):
        real=custody.verify_seal;calls=0
        def change(*args,**kwargs):
            nonlocal calls
            r=real(*args,**kwargs);calls+=1
            if calls==2:
                p=self.archives/'copy.zip';p.write_bytes(p.read_bytes()+b'changed')
            return r
        with patch.object(custody,'verify_seal',side_effect=change):
            with self.assertRaisesRegex(ValueError,'INDEX_ARCHIVES_CHANGED'):self.create()

    def test_index_or_seal_change_during_semantic_check_is_rejected(self):
        real=index.verify
        def change(*args,**kwargs):
            r=real(*args,**kwargs);p=self.seal/'REVIEW.md';p.write_bytes(p.read_bytes()+b'changed');return r
        with patch.object(index,'verify',side_effect=change):
            with self.assertRaises(ValueError):self.create()

    def test_resealed_report_authentication_promotion_is_rejected(self):
        self.create();p=self.out/'custody.json';report=json.loads(p.read_bytes());report['limitations']['execution_authenticated']=True
        p.write_bytes(safe_io.canonical(report));self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'PRESERVED_CUSTODY_CONTENT'):self.verify()

    def test_extra_pending_or_modified_review_rejected(self):
        self.create();pending=self.out/safe_io.PENDING_MARKER;pending.write_bytes(b'pending')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.verify()
        pending.unlink();(self.out/'REVIEW.md').write_bytes(b'all authenticated');self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'CONTENT'):self.verify()

    def test_late_failure_keeps_new_report_without_success(self):
        real=joined.write_new_bundle
        def change(*args,**kwargs):
            real(*args,**kwargs);self.trust.write_bytes(self.trust.read_bytes()+b' ')
        with patch.object(joined,'write_new_bundle',side_effect=change):
            with self.assertRaises(ValueError):self.create()
        self.assertTrue(self.out.exists())
        with self.assertRaises(ValueError):self.verify()

    def test_no_old_input_or_key_material_written_to_report(self):
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.create();self.verify()
        self.assertTrue(all((self.root/path).read_bytes()==raw for path,raw in before.items()))
        self.assertEqual({p.name for p in self.out.iterdir()},joined.FILES)
        self.assertNotIn(b'private-incomplete-own-data',(self.out/'custody.json').read_bytes())

    def test_historical_review_identity_is_explicit(self):
        self.create();p=self.out/'custody.json';report=json.loads(p.read_bytes());report['review_source_digest']='1'*64
        p.write_bytes(safe_io.canonical(report));self.reseal(self.out)
        with self.assertRaisesRegex(ValueError,'CONTENT'):self.verify()
        r=self.verify(review_source_digest='1'*64);self.assertEqual(r['source_digest'],self.digest)
        self.assertEqual(r['review_source_digest'],'1'*64);self.assertFalse(r['producer_authenticated'])

    def test_cli_preserves_incomplete_state_and_private_identity(self):
        values={'bundle':self.bundle,'archive_root':self.archives,'seal':self.seal,'trust':self.trust,'out':self.out,**self.context()}
        args=[sys.executable,'-B','-m','superhunter','review-preserved-custody']
        for key,value in values.items():args.extend(['--'+key.replace('_','-'),str(value)])
        result=subprocess.run(args,cwd=quality.ROOT.parent,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,1,result.stdout);self.assertTrue(json.loads(result.stdout)['custody_signature_verified'])
        for private in (str(self.root).encode(),CASE.encode(),PRODUCER.encode(),b'private-incomplete-own-data'):
            self.assertNotIn(private,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
