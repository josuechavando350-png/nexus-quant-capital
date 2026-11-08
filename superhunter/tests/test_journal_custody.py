"""Real local parsers/verifiers/crypto over explicitly synthetic journal data."""
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
import io,json
from pathlib import Path
import shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from superhunter import custody,journal_custody as jc,journal_ingest as journal,quality
from superhunter.safe_io import canonical,write_new_bundle

CASE='23666d9f-7db1-4ae9-b17b-54fef3c7558d'
PRODUCER='synthetic-journal-lab'
PRIVATE='SYNTHETIC_PRIVATE_MESSAGE_ONLY'


class JournalCustodyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.raw=self.root/'input.jsonl';self.journal=self.root/'journal';self.seal=self.root/'seal'
        self.trust=self.root/'trust.json';self.out=self.root/'report';self.key=Ed25519PrivateKey.generate()
        self.now=datetime.now(timezone.utc);pub=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.policy={'schema_version':1,'profile':custody.PROFILE,'keys':[{
            'key_id':custody.sha(pub),'public_key_hex':pub.hex(),'producer_id':PRODUCER,'case_ids':[CASE],
            'valid_from':(self.now-timedelta(days=1)).isoformat(),'valid_until':(self.now+timedelta(days=2)).isoformat(),
            'revoked':False}]}
        self.trust.write_bytes(canonical(self.policy))
        self.prepare([1793984400000000,1793984400010000],1)

    def prepare(self,ticks,uncertainty):
        if self.journal.exists():shutil.rmtree(self.journal)
        self.raw.write_bytes(b''.join(canonical({'__REALTIME_TIMESTAMP':str(n),'MESSAGE':PRIVATE}) for n in ticks))
        journal.ingest(self.raw,'owned-source',uncertainty,self.journal);self.sign()
        self.context={'source_digest':quality.sha(canonical(quality.source_snapshot())),
            'journal_anchor':quality.sha((self.journal/'COMPLETE.json').read_bytes()),
            'seal_anchor':quality.sha((self.seal/'COMPLETE.json').read_bytes()),'case_id':CASE,'producer_id':PRODUCER,
            'expected_source_id':'owned-source','expected_clock_uncertainty_ms':uncertainty}

    def sign(self):
        if self.seal.exists():shutil.rmtree(self.seal)
        s=custody.attest(self.journal,self.key,self.policy,case_id=CASE,producer_id=PRODUCER,
             issued_at=self.now.isoformat(),expires_at=(self.now+timedelta(days=1)).isoformat())
        write_new_bundle(self.seal,{'attestation.json':canonical(s),'REVIEW.md':custody._summary(s)})

    def collect(self,**changes):
        return jc.collect(self.journal,self.seal,self.trust,**{**self.context,**changes})

    def create(self):return jc.create(self.journal,self.seal,self.trust,self.out,**self.context)

    def verify(self):
        return jc.verify(self.journal,self.seal,self.trust,self.out,
            report_anchor=quality.sha((self.out/'COMPLETE.json').read_bytes()),**self.context)

    def reseal(self,root,name,raw):
        (root/name).write_bytes(raw);m=json.loads((root/'COMPLETE.json').read_bytes())
        m['sha256'][name]=quality.sha(raw);(root/'COMPLETE.json').write_bytes(canonical(m))

    def test_consistent_journal_has_verified_custody_but_no_authentic_clock(self):
        r=self.create();self.assertEqual(self.verify(),r)
        self.assertEqual(r['status'],'CUSTODY_VERIFIED_DECLARED_ORDER_CONSISTENT')
        self.assertTrue(r['custody_signature_verified']);self.assertTrue(all(v is False for v in r['limitations'].values()))
        self.assertEqual(r['records'],2)

    def test_signed_overlap_stays_inconclusive(self):
        self.prepare([1793984400000000,1793984400001000],10)
        r=self.create();self.assertEqual(self.verify(),r)
        self.assertEqual(r['status'],'CUSTODY_VERIFIED_INCONCLUSIVE_ORDER')
        self.assertEqual(len(r['uncertain_edges']),1)

    def test_signed_contradiction_stays_contradictory(self):
        self.prepare([1793984400010000,1793984400000000],0)
        r=self.collect();self.assertEqual(r['status'],'CUSTODY_VERIFIED_CONTRADICTION')
        self.assertEqual(len(r['contradictions']),1)

    def test_maximum_timestamp_flows_through_real_signature_and_verifiers(self):
        self.prepare([journal.MAX_US-1,journal.MAX_US],1)
        self.assertEqual(self.collect()['status'],'CUSTODY_VERIFIED_INCONCLUSIVE_ORDER')

    def test_source_identity_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'TEMPORAL_CONTEXT'):self.collect(expected_source_id='different')

    def test_operator_cannot_silently_reduce_clock_uncertainty(self):
        with self.assertRaisesRegex(ValueError,'TEMPORAL_CONTEXT'):self.collect(expected_clock_uncertainty_ms=0)

    def test_boolean_uncertainty_rejected(self):
        with self.assertRaises(ValueError):self.collect(expected_clock_uncertainty_ms=True)

    def test_wrong_anchors_rejected(self):
        for key in ('source_digest','journal_anchor','seal_anchor'):
            with self.subTest(key=key),self.assertRaises(ValueError):self.collect(**{key:'0'*64})

    def test_revoked_key_rejected(self):
        self.policy['keys'][0]['revoked']=True;self.trust.write_bytes(canonical(self.policy))
        with self.assertRaisesRegex(ValueError,'KEY_REVOKED'):self.collect()

    def test_expired_signature_rejected(self):
        with patch.object(custody,'now_text',return_value=(self.now+timedelta(days=1,seconds=1)).isoformat()):
            with self.assertRaisesRegex(ValueError,'ATTESTATION_TIME'):self.collect()

    def test_wrong_case_rejected(self):
        with self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):
            self.collect(case_id='33666d9f-7db1-4ae9-b17b-54fef3c7558d')

    def test_bad_signature_with_new_manifest_rejected(self):
        s=json.loads((self.seal/'attestation.json').read_bytes());s['signature_hex']='00'*64
        self.reseal(self.seal,'attestation.json',canonical(s));self.context['seal_anchor']=quality.sha((self.seal/'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNATURE'):self.collect()

    def test_signature_does_not_replace_semantic_replay(self):
        r=json.loads((self.journal/'receipt.json').read_bytes());r['lines'][1]['offset']=0
        self.reseal(self.journal,'receipt.json',canonical(r));self.sign()
        self.context.update(journal_anchor=quality.sha((self.journal/'COMPLETE.json').read_bytes()),
                            seal_anchor=quality.sha((self.seal/'COMPLETE.json').read_bytes()))
        with self.assertRaisesRegex(ValueError,'LINE_OFFSETS_CHANGED'):self.collect()

    def test_extra_file_rejected(self):
        (self.journal/'extra.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.collect()

    def test_symlink_input_rejected(self):
        original=self.root/'original';self.journal.rename(original);self.journal.symlink_to(original,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'SYMLINK'):self.collect()

    def test_trust_must_be_external(self):
        t=self.journal/'trust.json';t.write_bytes(self.trust.read_bytes())
        with self.assertRaisesRegex(ValueError,'EXTERNAL_TRUST_REQUIRED'):
            jc.collect(self.journal,self.seal,t,**self.context)

    def test_original_message_does_not_enter_report_or_console(self):
        self.create()
        for p in self.out.iterdir():self.assertNotIn(PRIVATE.encode(),p.read_bytes())
        self.assertIn(PRIVATE.encode(),(self.journal/'journal.jsonl').read_bytes())

    def test_promoted_report_rejected_even_when_rehashed(self):
        self.create();r=json.loads((self.out/'report.json').read_bytes());r['limitations']['clock_bound_authenticated']=True
        self.reseal(self.out,'report.json',canonical(r))
        with self.assertRaisesRegex(ValueError,'REPORT_MISMATCH'):self.verify()

    def test_changed_trust_during_review_rejected(self):
        original=journal.verify
        def change(path):
            result=original(path);self.trust.write_bytes(self.trust.read_bytes()+b' ');return result
        with patch.object(journal,'verify',side_effect=change):
            with self.assertRaisesRegex(ValueError,'TRUST_CHANGED'):self.collect()

    def test_revoke_after_report_creation_invalidates_fresh_acceptance(self):
        self.create();self.policy['keys'][0]['revoked']=True;self.trust.write_bytes(canonical(self.policy))
        with self.assertRaisesRegex(ValueError,'KEY_REVOKED'):self.verify()

    def test_cli_separate_processes_preserve_nonzero_for_uncertainty(self):
        self.prepare([1793984400000000,1793984400001000],10)
        common=['--journal-bundle',str(self.journal),'--seal',str(self.seal),'--trust',str(self.trust)]
        for k,v in self.context.items():common+=['--'+k.replace('_','-'),str(v)]
        for module,command,extra in [('superhunter','review-journal-custody',['--out',str(self.out)]),
                ('superhunter.journal_custody','verify-journal-custody',['--bundle',str(self.out)])]:
            if command.startswith('verify'):extra+=['--report-anchor',quality.sha((self.out/'COMPLETE.json').read_bytes())]
            p=subprocess.run([sys.executable,'-B','-m',module,command,*common,*extra],cwd=quality.ROOT.parent,
                             capture_output=True,timeout=15)
            self.assertEqual(p.returncode,1,p.stdout);self.assertEqual(p.stderr,b'')
            self.assertEqual(json.loads(p.stdout)['status'],'CUSTODY_VERIFIED_INCONCLUSIVE_ORDER')

    def test_invalid_cli_paths_are_redacted(self):
        args=['review-journal-custody','--journal-bundle','PRIVATE_PATH','--seal','PRIVATE_PATH','--trust','PRIVATE_PATH','--out','PRIVATE_PATH']
        for k,v in self.context.items():args+=['--'+k.replace('_','-'),str(v)]
        with redirect_stdout(io.StringIO()) as out:code=jc.main(args)
        self.assertEqual(code,2);self.assertNotIn('PRIVATE_PATH',out.getvalue())


if __name__=='__main__':unittest.main()
