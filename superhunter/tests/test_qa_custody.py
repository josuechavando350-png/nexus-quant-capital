"""Real custody crypto and verifiers over fabricated QA receipts, not execution.

Full-QA acceptance is separate. Keys are ephemeral and never written to disk.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from superhunter import custody, qa_custody as q, quality
from superhunter.quality_worker import partition_ids
from superhunter.safe_io import canonical, write_new_bundle

CASE='b741bdfa-3d93-41c8-97db-8c4dbfa8ef6e'
PRODUCER='synthetic-qa-custody-test'


class QACustodyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.qa=self.root/'qa';self.workers=self.root/'workers'
        self.seal=self.root/'seal';self.trust=self.root/'trust.json';self.out=self.root/'report'
        self.snapshot=quality.source_snapshot();self.ids=sorted(quality.REQUIRED_TESTS)
        rows=[];logs=[]
        for index,ids in enumerate(partition_ids(self.ids,8)):
            row={'schema_version':1,'sources_before':self.snapshot,'sources_after':self.snapshot,
                 'global_discovered':self.ids,'discovered':ids,
                 'tests':[{'id':i,'outcome':'PASS'} for i in ids],
                 'tests_run':len(ids),'failures':0,'errors':0,'skipped':0,
                 'expected_failures':0,'unexpected_successes':0,
                 'python':'SYNTHETIC-UNIT-RECEIPT','log_privacy':'synthetic',
                 'partition_count':8,'partition_index':index}
            log=f'SYNTHETIC QA RECEIPT ONLY {index}; no tests executed\n'.encode()
            write_new_bundle(self.workers/f'worker-{index}',{'receipt.json':canonical(row),'tests.log':log})
            rows.append(row);logs.append(f'=== FIXED QA PARTITION {index+1}/8 ===\n'.encode()+log)
        self.receipt=quality.compact_partition_receipt(quality.aggregate_receipts(rows,self.snapshot))
        result=quality.assess(self.receipt,self.snapshot)
        self.assertEqual(result['status'],'LOCAL_QA_PASS')
        write_new_bundle(self.qa,{'receipt.json':canonical(self.receipt),'quality.json':canonical(result),
            'source-snapshot.json':canonical(self.snapshot),
            'CHECKLIST.md':quality.checklist(quality.catalog(),result).encode(),'tests.log':b'\n'.join(logs)})
        self.key=Ed25519PrivateKey.generate();self.now=datetime.now(timezone.utc)
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.policy={'schema_version':1,'profile':custody.PROFILE,'keys':[{
            'key_id':custody.sha(public),'public_key_hex':public.hex(),'producer_id':PRODUCER,
            'case_ids':[CASE],'valid_from':(self.now-timedelta(days=1)).isoformat(),
            'valid_until':(self.now+timedelta(days=2)).isoformat(),'revoked':False}]}
        self.trust.write_bytes(canonical(self.policy));self.make_seal()
        self.context={'source_digest':quality.sha(canonical(self.snapshot)),
            'qa_anchor':quality.sha((self.qa/'COMPLETE.json').read_bytes()),
            'seal_anchor':quality.sha((self.seal/'COMPLETE.json').read_bytes()),
            'case_id':CASE,'producer_id':PRODUCER}

    def make_seal(self):
        if self.seal.exists(): shutil.rmtree(self.seal)
        statement=custody.attest(self.qa,self.key,self.policy,case_id=CASE,producer_id=PRODUCER,
            issued_at=self.now.isoformat(),expires_at=(self.now+timedelta(days=1)).isoformat())
        write_new_bundle(self.seal,{'attestation.json':canonical(statement),'REVIEW.md':custody._summary(statement)})

    def collect(self,**kwargs):
        context={**self.context,**kwargs}
        return q.collect(self.qa,self.workers,self.seal,self.trust,**context)

    def create(self):
        return q.create(self.qa,self.workers,self.seal,self.trust,self.out,**self.context)

    def verify(self):
        return q.verify(self.qa,self.workers,self.seal,self.trust,self.out,
            report_anchor=quality.sha((self.out/'COMPLETE.json').read_bytes()),**self.context)

    def reseal(self,root,name,raw):
        (root/name).write_bytes(raw)
        marker=json.loads((root/'COMPLETE.json').read_bytes());marker['sha256'][name]=quality.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_real_signature_and_all_receipts_verified(self):
        result=self.create();self.assertEqual(self.verify(),result)
        self.assertTrue(result['custody_signature_verified'])
        self.assertEqual(result['tests_run'],len(self.ids));self.assertEqual(len(result['workers']),8)
        self.assertTrue(result['aggregate_log_reconstructed'])
        self.assertTrue(all(value is False for value in result['limitations'].values()))

    def test_external_anchors_required(self):
        for key in ('qa_anchor','seal_anchor','source_digest'):
            with self.subTest(key=key),self.assertRaises(ValueError):self.collect(**{key:'0'*64})

    def test_wrong_case_rejected(self):
        with self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):
            self.collect(case_id='c741bdfa-3d93-41c8-97db-8c4dbfa8ef6e')

    def test_wrong_producer_rejected(self):
        with self.assertRaisesRegex(ValueError,'CONTEXT_MISMATCH'):self.collect(producer_id='other-producer')

    def test_revoked_key_rejected(self):
        self.policy['keys'][0]['revoked']=True;self.trust.write_bytes(canonical(self.policy))
        with self.assertRaisesRegex(ValueError,'KEY_REVOKED'):self.collect()

    def test_expired_attestation_rejected(self):
        later=(self.now+timedelta(days=1,seconds=1)).isoformat()
        with patch.object(custody,'now_text',return_value=later):
            with self.assertRaisesRegex(ValueError,'ATTESTATION_TIME'):self.collect()

    def test_trust_cannot_be_loaded_from_evidence(self):
        nested=self.workers/'trust.json';nested.write_bytes(self.trust.read_bytes())
        with self.assertRaisesRegex(ValueError,'EXTERNAL_TRUST_REQUIRED'):
            q.collect(self.qa,self.workers,self.seal,nested,**self.context)

    def test_bad_signature_rejected_even_with_new_hashes(self):
        statement=json.loads((self.seal/'attestation.json').read_bytes());statement['signature_hex']='00'*64
        self.reseal(self.seal,'attestation.json',canonical(statement))
        self.context['seal_anchor']=quality.sha((self.seal/'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'INVALID_SIGNATURE'):self.collect()

    def test_missing_worker_rejected(self):
        shutil.rmtree(self.workers/'worker-7')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.collect()

    def test_extra_worker_rejected(self):
        (self.workers/'worker-8').mkdir()
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.collect()

    def test_symlink_worker_rejected(self):
        saved=self.root/'saved-worker';(self.workers/'worker-0').rename(saved)
        (self.workers/'worker-0').symlink_to(saved,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'SYMLINK'):self.collect()

    def test_raw_worker_log_edit_rejected(self):
        (self.workers/'worker-0/tests.log').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'MANIFEST'):self.collect()

    def test_resealed_worker_log_rejected(self):
        self.reseal(self.workers/'worker-0','tests.log',b'altered but rehashed')
        with self.assertRaisesRegex(ValueError,'LOG_RECONSTRUCTION'):self.collect()

    def test_resealed_worker_receipt_rejected(self):
        root=self.workers/'worker-0';row=json.loads((root/'receipt.json').read_bytes())
        row['python']='ALTERED-CLAIM';self.reseal(root,'receipt.json',canonical(row))
        with self.assertRaisesRegex(ValueError,'WORKER_MISMATCH'):self.collect()

    def test_signed_changed_aggregate_log_rejected(self):
        self.reseal(self.qa,'tests.log',b'changed aggregate, correctly signed')
        self.make_seal()
        self.context.update(qa_anchor=quality.sha((self.qa/'COMPLETE.json').read_bytes()),
                            seal_anchor=quality.sha((self.seal/'COMPLETE.json').read_bytes()))
        with self.assertRaisesRegex(ValueError,'LOG_RECONSTRUCTION'):self.collect()

    def test_valid_signature_does_not_override_failed_qa(self):
        # Replace with a consistent nonpartitioned blocked QA receipt, then sign.
        receipt={'schema_version':1,'sources_before':self.snapshot,'sources_after':self.snapshot,
                 'discovered':self.ids,'tests':[{'id':i,'outcome':'PASS'} for i in self.ids],
                 'tests_run':len(self.ids),'failures':1,'errors':0,'skipped':0,
                 'expected_failures':0,'unexpected_successes':0}
        result=quality.assess(receipt,self.snapshot)
        self.assertEqual(result['status'],'LOCAL_QA_BLOCKED')
        for name,raw in {'receipt.json':canonical(receipt),'quality.json':canonical(result),
                'CHECKLIST.md':quality.checklist(quality.catalog(),result).encode()}.items():
            self.reseal(self.qa,name,raw)
        self.make_seal()
        self.context.update(qa_anchor=quality.sha((self.qa/'COMPLETE.json').read_bytes()),
                            seal_anchor=quality.sha((self.seal/'COMPLETE.json').read_bytes()))
        with self.assertRaisesRegex(ValueError,'QA_NOT_PASS'):self.collect()

    def test_report_cannot_promote_execution_authentication(self):
        self.create();result=json.loads((self.out/'report.json').read_bytes())
        result['limitations']['execution_authenticated']=True
        self.reseal(self.out,'report.json',canonical(result))
        with self.assertRaisesRegex(ValueError,'REPORT_MISMATCH'):self.verify()

    def test_report_anchor_checked_before_inputs(self):
        self.create()
        with self.assertRaisesRegex(ValueError,'REPORT_ANCHOR'):
            q.verify(self.qa,self.workers,self.seal,self.trust,self.out,report_anchor='0'*64,**self.context)

    def test_revocation_after_creation_invalidates_report(self):
        self.create();self.policy['keys'][0]['revoked']=True;self.trust.write_bytes(canonical(self.policy))
        with self.assertRaisesRegex(ValueError,'KEY_REVOKED'):self.verify()

    def test_changed_trust_during_review_rejected(self):
        original=quality.verify_bundle
        def changed(root):
            value=original(root);self.trust.write_bytes(canonical({**self.policy,'extra':'changed'}));return value
        with patch.object(quality,'verify_bundle',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'TRUST_CHANGED'):self.collect()

    def test_changed_worker_during_review_rejected(self):
        original=q._capture;calls=0
        def changed(root,files):
            nonlocal calls
            raw=original(root,files)
            if root==self.workers/'worker-7':
                calls+=1
                if calls==1:self.reseal(self.workers/'worker-0','tests.log',b'changed after collection')
            return raw
        with patch.object(q,'_capture',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'WORKER_CHANGED'):self.collect()

    def test_reject_output_overlap_and_existing_output(self):
        for out in (self.qa/'report',self.workers,self.root):
            with self.subTest(out=out),self.assertRaises(ValueError):
                q.create(self.qa,self.workers,self.seal,self.trust,out,**self.context)

    def test_cli_creation_and_verification_in_separate_processes(self):
        common=['--qa',str(self.qa),'--workers',str(self.workers),'--seal',str(self.seal),'--trust',str(self.trust)]
        for key,value in self.context.items():common+=['--'+key.replace('_','-'),value]
        for module,command,extra in (
            ('superhunter','review-qa-custody',['--out',str(self.out)]),
            ('superhunter.qa_custody','verify-qa-custody',['--bundle',str(self.out)])):
            if command=='verify-qa-custody':extra+=['--report-anchor',quality.sha((self.out/'COMPLETE.json').read_bytes())]
            run=subprocess.run([sys.executable,'-B','-m',module,command,*common,*extra],
                cwd=quality.ROOT.parent,capture_output=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stdout);self.assertEqual(run.stderr,b'')
            self.assertEqual(json.loads(run.stdout)['status'],'QA_RECEIPTS_AND_CUSTODY_VERIFIED')

    def test_cli_redacts_paths(self):
        common=['--qa','SECRET_PATH','--workers','SECRET_PATH','--seal','SECRET_PATH','--trust','SECRET_PATH',
                '--out','SECRET_PATH']
        for key,value in self.context.items():common+=['--'+key.replace('_','-'),value]
        with redirect_stdout(io.StringIO()) as output:
            result=q.main(['review-qa-custody',*common])
        self.assertEqual(result,2);self.assertNotIn('SECRET_PATH',output.getvalue())


if __name__=='__main__':unittest.main()
