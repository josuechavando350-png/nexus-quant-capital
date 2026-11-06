from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_review_credentials as fixtures
from nqc_defense.audit import mac
from nqc_defense.case_review import CaseReview
from nqc_defense.codec import Rejected, canonical
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ORIGIN, ReviewCredentials
from nqc_defense.review_policy import ReviewPolicy


class ExpiryTests(unittest.TestCase):
    apply = fixtures.CredentialTests.apply
    view = fixtures.CredentialTests.view
    change = fixtures.CredentialTests.change

    def setUp(self):
        fixtures.CredentialTests.setUp(self)
        self.now = 100
        clock = patch('nqc_defense.review_clock.time.time_ns', side_effect=lambda: self.now)
        clock.start(); self.addCleanup(clock.stop)

    def limit(self, deadline=200, actor='ana', **kwargs):
        return self.change('set_expiry', actor=actor, expires_at_ns=deadline, **kwargs)

    def floor(self):
        with self.store.transaction() as db:
            row = db.execute('SELECT payload FROM review_clock WHERE policy=?',(self.policy.digest,)).fetchone()
        return json.loads(row[0])['observed_ns'] if row else None

    def test_initial_unbounded_credentials_report_no_deadline(self):
        state = self.lifecycle.status(self.policy.key)
        self.assertIsNone(state['actors']['ana']['expires_at_ns'])
        self.assertIsNone(state['clock'])
        self.assertTrue(state['actors']['ana']['active'])

    def test_setting_deadline_preserves_credential_bytes_and_case(self):
        path = self.policy.root/'credentials/ana.key'; before = path.read_bytes()
        self.limit()
        self.assertEqual(path.read_bytes(),before)
        self.assertTrue(self.apply()['applied'])
        self.assertEqual(self.store.cases('tenant','host')[0],self.case)

    def test_deadline_boundary_is_exclusive_for_writes(self):
        self.limit(); self.now = 199
        self.apply()
        self.now = 200
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply('note')
        self.assertEqual(self.view()['review']['notes_count'],0)

    def test_expired_reader_cannot_obtain_case_history(self):
        self.apply(); self.limit(actor='reader'); self.now = 200
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.view()
        self.assertEqual(self.floor(),200)

    def test_status_distinguishes_expiry_and_revocation_without_appending(self):
        self.limit(); head = dict(self.credential_head); self.now = 200
        state = self.lifecycle.status(self.policy.key)
        self.assertEqual(state['checkpoint'],head)
        self.assertEqual(state['actors']['ana'],{'active':False,'revoked':False,'expired':True,'expires_at_ns':200})
        self.change()
        state = self.lifecycle.status(self.policy.key)
        self.assertTrue(state['actors']['ana']['revoked'])
        self.assertFalse(state['actors']['ana']['expired'])

    def test_deadline_in_the_past_immediately_denies_credential(self):
        self.limit(50)
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply()

    def test_existing_deadline_can_only_be_shortened_without_new_token(self):
        self.limit(); self.limit(150)
        for deadline in (150,200):
            with self.assertRaisesRegex(Rejected,'credential_expiry_must_shorten'):
                self.limit(deadline)
        self.assertEqual(self.lifecycle.status(self.policy.key)['actors']['ana']['expires_at_ns'],150)

    def test_missing_and_invalid_deadlines_rejected_before_activation(self):
        for deadline in (None,False,0,-1,2**63,1.5,'200'):
            with self.subTest(deadline=deadline), self.assertRaises(Rejected):
                self.limit(deadline)
        self.assertIsNone(self.floor())
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],ORIGIN)

    def test_revoked_actor_cannot_receive_set_expiry(self):
        self.change()
        with self.assertRaisesRegex(Rejected,'credential_expiry_state'):
            self.limit()

    def test_set_expiry_does_not_accept_a_replacement_token(self):
        with self.assertRaisesRegex(Rejected,'credential_unexpected_token'):
            self.limit(credential=secrets.token_bytes(32))

    def test_rotating_without_deadline_preserves_existing_limit(self):
        self.limit()
        token = secrets.token_bytes(32)
        self.change('rotate',credential=token); self.tokens['ana'] = token
        self.assertEqual(self.lifecycle.status(self.policy.key)['actors']['ana']['expires_at_ns'],200)
        self.now = 200
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply()

    def test_rotating_expired_credential_requires_explicit_future_deadline(self):
        self.limit(); self.now = 200
        token = secrets.token_bytes(32)
        with self.assertRaisesRegex(Rejected,'credential_expiry_not_future'):
            self.change('rotate',credential=token)
        self.change('rotate',credential=token,expires_at_ns=300); self.tokens['ana'] = token
        self.assertTrue(self.apply()['applied'])

    def test_new_issue_cannot_already_be_expired(self):
        for deadline in (99,100):
            with self.assertRaisesRegex(Rejected,'credential_expiry_not_future'):
                self.change('rotate',credential=secrets.token_bytes(32),expires_at_ns=deadline)
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],ORIGIN)

    def test_renewal_preserves_expiry_and_requires_future_limit_after_expiry(self):
        self.limit(); self.change(); self.now = 200
        token = secrets.token_bytes(32)
        with self.assertRaisesRegex(Rejected,'credential_expiry_not_future'):
            self.change('renew',credential=token)
        self.change('renew',credential=token,expires_at_ns=300); self.tokens['ana'] = token
        self.assertTrue(self.apply()['applied'])

    def test_unbounded_legacy_rotation_remains_explicitly_unbounded(self):
        self.change('rotate',credential=secrets.token_bytes(32))
        self.assertIsNone(self.lifecycle.status(self.policy.key)['actors']['ana']['expires_at_ns'])
        self.assertIsNone(self.floor())

    def test_expired_confirmer_cannot_close_review(self):
        self.apply(); self.apply('assess',verdict='benign'); self.limit(actor='boris'); self.now = 200
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply('close',actor='boris')
        self.assertEqual(self.view()['review']['stage'],'investigating')

    def test_valid_historical_actions_remain_readable_after_expiry(self):
        self.limit(); self.apply(); before = self.view()['history']; self.now = 200
        self.assertEqual(self.view()['history'],before)

    def test_expired_token_cannot_retrieve_idempotent_retry_result(self):
        self.limit(); self.apply(request_id='once'); self.now = 200
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply(request_id='once',expected=ORIGIN)

    def test_expiry_during_evidence_verification_prevents_write(self):
        self.limit(); self.apply()
        from nqc_defense.case_evidence import verify_bundle
        def advancing(*args):
            result = verify_bundle(*args); self.now = 200; return result
        with patch('nqc_defense.case_review.verify_bundle',side_effect=advancing):
            with self.assertRaisesRegex(Rejected,'review_credential_expired'):
                self.apply('note')
        self.assertEqual(self.floor(),200)
        self.assertEqual(self.view()['review']['notes_count'],0)

    def test_expiry_after_insert_rolls_back_action_and_commits_clock_floor(self):
        from contextlib import contextmanager
        self.limit(); self.apply(); original = self.store.transaction
        @contextmanager
        def transaction():
            with original() as db:
                def advance():
                    self.now = 200
                    return 1
                db.create_function('advance_test_clock',0,advance)
                db.execute('CREATE TEMP TRIGGER advance_clock AFTER INSERT ON case_reviews BEGIN SELECT advance_test_clock(); END')
                yield db
        self.store.transaction = transaction
        try:
            with self.assertRaisesRegex(Rejected,'review_credential_expired'):
                self.apply('note')
        finally:
            self.store.transaction = original
        self.assertEqual(self.floor(),200)
        self.assertEqual(self.view()['review']['notes_count'],0)
        self.now = 150
        with self.assertRaisesRegex(Rejected,'credential_clock_regressed'):
            self.apply('note')

    def test_expiry_while_reconstructing_history_denies_read(self):
        self.apply(); self.limit(actor='reader'); original = self.review._load
        def advancing(*args):
            result = original(*args); self.now = 200; return result
        with patch.object(self.review,'_load',side_effect=advancing):
            with self.assertRaisesRegex(Rejected,'review_credential_expired'):
                self.view()
        self.assertEqual(self.floor(),200)

    def test_clock_regression_is_rejected_after_reopening_store(self):
        self.limit(); self.now = 150; self.apply()
        reopened = CaseReview(OperationsStore(self.store.root),ReviewPolicy(self.policy.root,self.policy.digest))
        self.now = 149
        with self.assertRaisesRegex(Rejected,'credential_clock_regressed'):
            reopened.view('reader',self.tokens['reader'],'tenant','host',self.case['case_id'],expected_credentials=self.credential_head)

    def test_rejected_expiry_observation_prevents_reactivation_after_clock_rollback(self):
        self.limit(); self.now = 250
        with self.assertRaisesRegex(Rejected,'review_credential_expired'):
            self.apply()
        self.now = 150
        with self.assertRaisesRegex(Rejected,'credential_clock_regressed'):
            self.apply()
        self.assertEqual(self.floor(),250)

    def test_stale_request_commits_time_floor_without_case_change(self):
        self.limit(); self.now = 150
        with self.assertRaisesRegex(Rejected,'credential_checkpoint_mismatch'):
            self.apply(expected_credentials=ORIGIN)
        self.assertEqual(self.floor(),150)
        self.assertEqual(self.view()['checkpoint'],ORIGIN)

    def test_clock_row_cannot_be_deleted_and_silently_reinitialized(self):
        self.limit()
        with self.store.transaction() as db:
            db.execute('DELETE FROM review_clock')
        reopened = ReviewCredentials(self.store,self.policy)
        with self.assertRaisesRegex(Rejected,'credential_clock_missing'):
            reopened.status(self.policy.key)
        with self.assertRaisesRegex(Rejected,'credential_clock_missing'):
            self.limit(150)
        self.assertIsNone(self.floor())

    def test_clock_tampering_fails_closed(self):
        self.limit()
        with self.store.transaction() as db:
            db.execute("UPDATE review_clock SET payload='{}'")
        with self.assertRaisesRegex(Rejected,'credential_clock_integrity'):
            self.view()

    def test_clock_cannot_reference_missing_lifecycle_history(self):
        self.limit()
        with self.store.transaction() as db:
            db.execute('DELETE FROM review_credentials')
        with self.assertRaisesRegex(Rejected,'credential_history_missing'):
            self.view(expected_credentials=ORIGIN)

    def test_authenticated_clock_for_wrong_policy_is_rejected(self):
        self.limit()
        with self.store.transaction() as db:
            value = json.loads(db.execute('SELECT payload FROM review_clock').fetchone()[0])
            value['policy_digest'] = 'f'*64; payload = canonical(value).decode()
            db.execute('UPDATE review_clock SET payload=?,mac=?',(payload,mac(self.policy.key,1,ORIGIN['head'],payload)))
        with self.assertRaisesRegex(Rejected,'credential_clock_binding'):
            self.view()

    def test_clock_write_failure_prevents_case_action(self):
        self.limit()
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_clock BEFORE UPDATE ON review_clock BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.apply()
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM case_reviews').fetchone()[0],0)

    def test_first_deadline_and_clock_initialization_are_atomic(self):
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_clock BEFORE INSERT ON review_clock BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.limit()
        self.assertIsNone(self.floor())
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],ORIGIN)
        self.assertTrue(self.apply()['applied'])

    def test_repeat_deadline_request_after_expiry_is_idempotent(self):
        self.limit(request_id='bounded'); head = dict(self.credential_head); self.now = 200
        retry = self.limit(request_id='bounded',expected=ORIGIN)
        self.assertFalse(retry['applied']); self.assertEqual(retry['checkpoint'],head)

    def test_same_request_with_changed_deadline_rejected(self):
        self.limit(request_id='bounded')
        with self.assertRaisesRegex(Rejected,'credential_request_conflict'):
            self.limit(150,request_id='bounded',expected=ORIGIN)

    def test_lifecycle_v1_bytes_survive_expiry_migration(self):
        token = secrets.token_bytes(32)
        self.change('rotate',credential=token); self.tokens['ana'] = token
        with self.store.transaction() as db:
            event = json.loads(db.execute('SELECT payload FROM review_credentials').fetchone()[0])
            event.pop('expires_at_ns'); event['schema'] = 'nqc-review-credential-event-v1'
            payload = canonical(event).decode(); head = mac(self.policy.key,1,ORIGIN['head'],payload)
            db.execute('UPDATE review_credentials SET payload=?,mac=?',(payload,head))
            original = db.execute('SELECT * FROM review_credentials').fetchall()
        self.credential_head = {'revision':1,'head':head}
        self.limit(); self.apply()
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT * FROM review_credentials WHERE revision=1').fetchall(),original)

    def test_lifecycle_schema_downgrade_after_v2_is_rejected(self):
        self.change('rotate',credential=secrets.token_bytes(32)); self.change(actor='reader')
        with self.store.transaction() as db:
            payload,previous = db.execute('SELECT payload,previous FROM review_credentials WHERE revision=2').fetchone()
            event = json.loads(payload); event.pop('expires_at_ns'); event['schema'] = 'nqc-review-credential-event-v1'
            payload = canonical(event).decode()
            db.execute('UPDATE review_credentials SET payload=?,mac=? WHERE revision=2',(payload,mac(self.policy.key,2,previous,payload)))
        with self.assertRaisesRegex(Rejected,'credential_schema_regression'):
            self.lifecycle.status(self.policy.key)

    def test_historical_action_at_deadline_rejected_even_with_valid_mac(self):
        self.limit(); self.apply()
        with self.store.transaction() as db:
            event = json.loads(db.execute('SELECT payload FROM case_reviews').fetchone()[0])
            event['recorded_ns'] = 200; payload = canonical(event).decode()
            db.execute('UPDATE case_reviews SET payload=?,mac=?',(payload,mac(self.policy.key,1,ORIGIN['head'],payload)))
        with self.assertRaisesRegex(Rejected,'credential_history_expiry'):
            self.view()

    def test_two_concurrent_first_deadlines_have_one_committed_winner(self):
        def worker(deadline):
            try:
                return self.lifecycle.change(self.policy.key,'ana','set_expiry','race',f'limit_{deadline}',ORIGIN,expires_at_ns=deadline)['applied']
            except Rejected as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker,[200,300]))
        self.assertCountEqual(results,[True,'credential_checkpoint_mismatch'])
        state = self.lifecycle.status(self.policy.key)
        self.assertEqual(state['checkpoint']['revision'],1)
        self.assertEqual(state['clock']['observed_ns'],100)

    def test_confirmed_expiry_rejection_survives_process_exit(self):
        self.limit()
        params = self.root/'expiry-process.json'
        params.write_bytes(canonical({'policy_digest':self.policy.digest,'case_id':self.case['case_id'],'credential_checkpoint':self.credential_head}))
        script = '''
import json,os,sys
from pathlib import Path
from unittest.mock import patch
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy,read_credential
from nqc_defense.case_review import CaseReview
from nqc_defense.codec import Rejected
root=Path(sys.argv[1]); p=json.loads((root/'expiry-process.json').read_bytes())
review=CaseReview(OperationsStore(root/'ops'),ReviewPolicy(root/'policy',p['policy_digest']))
with patch('nqc_defense.review_clock.time.time_ns',return_value=200):
    try:
        review.view('ana',read_credential(root/'policy/credentials/ana.key'),'tenant','host',p['case_id'],expected_credentials=p['credential_checkpoint'])
    except Rejected as exc:
        if str(exc)=='review_credential_expired':
            os._exit(78)
os._exit(79)
'''
        result = subprocess.run([sys.executable,'-B','-c',script,str(self.root)],cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,78,result.stderr)
        self.assertEqual(self.floor(),200)
        self.now = 199
        with self.assertRaisesRegex(Rejected,'credential_clock_regressed'):
            self.apply()

    def test_process_death_before_expiry_commit_preserves_unbounded_state(self):
        params = self.root/'expiry-process.json'; params.write_bytes(canonical({'policy_digest':self.policy.digest}))
        script = '''
from contextlib import contextmanager
import json,os,sys
from pathlib import Path
from nqc_defense.operations import OperationsStore
from nqc_defense.review_policy import ReviewPolicy
from nqc_defense.review_credentials import ReviewCredentials,ORIGIN
root=Path(sys.argv[1]); p=json.loads((root/'expiry-process.json').read_bytes())
store=OperationsStore(root/'ops'); policy=ReviewPolicy(root/'policy',p['policy_digest']); lifecycle=ReviewCredentials(store,policy)
original=store.transaction
@contextmanager
def transaction():
    with original() as db:
        db.create_function('terminate_test_process',0,lambda:os._exit(77))
        db.execute('CREATE TEMP TRIGGER death AFTER INSERT ON review_clock BEGIN SELECT terminate_test_process(); END')
        yield db
store.transaction=transaction
lifecycle.change(policy.key,'ana','set_expiry','crash','crash_1',ORIGIN,expires_at_ns=1)
'''
        result = subprocess.run([sys.executable,'-B','-c',script,str(self.root)],cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertIsNone(self.floor())
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],ORIGIN)
        self.assertTrue(self.apply()['applied'])

    def test_cli_expired_read_denies_without_traceback(self):
        tool = Path(__file__).resolve().parents[1]/'tools/review_credentials.py'
        request = self.root/'expire.json'
        request.write_bytes(canonical({'actor':'ana','action':'set_expiry','reason':'CLI expiry','request_id':'expire_cli',
                                       'expected':ORIGIN,'expires_at_ns':1}))
        result = subprocess.run([sys.executable,'-B',str(tool),'change','--operations-root',str(self.store.root),
             '--policy-root',str(self.policy.root),'--policy-digest',self.policy.digest,'--admin-key-file',str(self.policy.root/'audit.key'),
             '--request-file',str(request)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        cp = self.root/'credential-checkpoint.json'; cp.write_bytes(canonical(json.loads(result.stdout)['checkpoint']))
        result = subprocess.run([sys.executable,'-B',str(tool.parent/'case_review.py'),'view','--operations-root',str(self.store.root),
             '--policy-root',str(self.policy.root),'--policy-digest',self.policy.digest,'--actor','ana','--credential-file',str(self.policy.root/'credentials/ana.key'),
             '--tenant','tenant','--asset','host','--case-id',self.case['case_id'],'--credential-checkpoint',str(cp)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['reason'],'review_credential_expired')
        self.assertEqual(result.stderr,'')


if __name__ == '__main__':
    unittest.main()
