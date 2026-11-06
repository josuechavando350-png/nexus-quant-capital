from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_case_review as fixtures
from nqc_defense.audit import mac
from nqc_defense.case_review import CaseReview
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ORIGIN, ReviewCredentials, create_credential
from nqc_defense.review_policy import ReviewPolicy, read_credential


class CredentialTests(unittest.TestCase):
    def setUp(self):
        fixtures.CaseReviewTests.setUp(self)
        self.lifecycle = self.review.credentials
        self.credential_head = dict(ORIGIN)
        self.admin_serial = 0

    def apply(self, *args, **kwargs):
        kwargs.setdefault('expected_credentials', self.credential_head)
        return fixtures.CaseReviewTests.apply(self, *args, **kwargs)

    def view(self, **kwargs):
        kwargs.setdefault('expected_credentials', self.credential_head)
        return fixtures.CaseReviewTests.view(self, **kwargs)

    def change(self, action='revoke', actor='ana', **kwargs):
        self.admin_serial += 1
        args = dict(admin_key=self.policy.key, actor=actor, action=action, reason='Lifecycle test',
                    request_id=f'change_{self.admin_serial}', expected=self.credential_head)
        args.update(kwargs)
        result = self.lifecycle.change(**args)
        self.credential_head = result['checkpoint']
        return result

    def test_revoke_blocks_existing_instance_and_copied_token(self):
        self.apply(); before = self.view()['history']
        copied = bytes(self.tokens['ana'])
        self.change()
        for call in (lambda: self.apply('note', credential=copied),
                     lambda: self.view(actor='ana', credential=copied)):
            with self.assertRaisesRegex(Rejected, 'review_unauthorized'):
                call()
        self.assertEqual(self.view()['history'], before)
        self.assertTrue((self.policy.root / 'credentials/ana.key').exists())

    def test_rotate_accepts_new_token_and_preserves_case_evidence(self):
        self.apply(); original = self.view()['history'][0]
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token)
        with self.assertRaisesRegex(Rejected, 'review_unauthorized'):
            self.apply('note')
        self.tokens['ana'] = token
        self.apply('note')
        result = self.view()
        self.assertEqual(result['history'][0], original)
        self.assertEqual(result['history'][1]['event']['credential_checkpoint'], self.credential_head)
        self.assertEqual(sha256(canonical(self.store.cases('tenant', 'host')[0])), self.case_digest)

    def test_renew_requires_revocation_and_different_token(self):
        token = secrets.token_bytes(32)
        with self.assertRaisesRegex(Rejected, 'credential_rotation_state'):
            self.change('renew', credential=token)
        self.change()
        with self.assertRaisesRegex(Rejected, 'credential_reuse'):
            self.change('renew', credential=self.tokens['ana'])
        self.change('renew', credential=token)
        self.tokens['ana'] = token
        self.assertTrue(self.apply()['applied'])

    def test_rotate_cannot_implicitly_reactivate_revoked_actor(self):
        self.change()
        with self.assertRaisesRegex(Rejected, 'credential_rotation_state'):
            self.change('rotate', credential=secrets.token_bytes(32))

    def test_revoke_twice_requires_exact_retry(self):
        self.change(request_id='revoke_1')
        with self.assertRaisesRegex(Rejected, 'credential_revoke_state'):
            self.change()
        self.assertFalse(self.change(request_id='revoke_1', expected=ORIGIN)['applied'])

    def test_renewed_reader_does_not_gain_write_permission(self):
        self.change(actor='reader')
        token = secrets.token_bytes(32)
        self.change('renew', actor='reader', credential=token)
        self.tokens['reader'] = token
        self.assertEqual(self.view()['review']['stage'], 'unreviewed')
        with self.assertRaisesRegex(Rejected, 'review_unauthorized'):
            self.apply(actor='reader')

    def test_cross_scope_still_rejected_after_rotation(self):
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token); self.tokens['ana'] = token
        for kwargs in ({'tenant':'other'}, {'asset':'other'}):
            with self.assertRaisesRegex(Rejected, 'review_unauthorized'):
                self.apply(**kwargs)

    def test_reviewer_cannot_manage_credentials(self):
        with self.assertRaisesRegex(Rejected, 'credential_administrator_required'):
            self.change(admin_key=self.tokens['ana'])
        with self.assertRaisesRegex(Rejected, 'credential_administrator_required'):
            self.lifecycle.status(self.tokens['reader'])
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'], ORIGIN)

    def test_reject_reuse_of_other_actor_or_audit_key(self):
        for token in (self.tokens['ana'], self.tokens['reader'], self.policy.key):
            with self.assertRaisesRegex(Rejected, 'credential_reuse'):
                self.change('rotate', credential=token)

    def test_all_previous_tokens_remain_retired(self):
        old = self.tokens['ana']; second = secrets.token_bytes(32)
        self.change('rotate', credential=second)
        self.change('rotate', credential=secrets.token_bytes(32))
        for token in (old, second):
            with self.assertRaisesRegex(Rejected, 'credential_reuse'):
                self.change('rotate', credential=token)

    def test_changed_lifecycle_requires_explicit_checkpoint(self):
        self.change()
        with self.assertRaisesRegex(Rejected, 'credential_checkpoint_required'):
            self.view(expected_credentials=None)
        with self.assertRaisesRegex(Rejected, 'credential_checkpoint_mismatch'):
            self.view(expected_credentials=ORIGIN)

    def test_stale_admin_change_cannot_overwrite_newer_generation(self):
        self.change()
        with self.assertRaisesRegex(Rejected, 'credential_checkpoint_mismatch'):
            self.change(actor='reader', expected=ORIGIN)

    def test_idempotent_rotation_returns_current_and_original_checkpoints(self):
        token = secrets.token_bytes(32)
        first = self.change('rotate', credential=token, request_id='stable')
        self.change(actor='reader')
        retry = self.change('rotate', credential=token, request_id='stable', expected=ORIGIN)
        self.assertFalse(retry['applied'])
        self.assertEqual(retry['operation_checkpoint'], first['checkpoint'])
        self.assertEqual(retry['checkpoint']['revision'], 2)

    def test_retry_with_changed_token_or_reason_is_rejected(self):
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token, request_id='stable')
        for kwargs in ({'credential':secrets.token_bytes(32)}, {'credential':token,'reason':'different'}):
            with self.assertRaisesRegex(Rejected, 'credential_request_conflict'):
                self.change('rotate', request_id='stable', expected=ORIGIN, **kwargs)

    def test_review_retry_after_rotation_does_not_duplicate_original_action(self):
        first = self.apply(request_id='review_once')
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token); self.tokens['ana'] = token
        retried = self.apply(request_id='review_once', expected=ORIGIN)
        self.assertFalse(retried['applied'])
        self.assertEqual(retried['operation_checkpoint'], first['checkpoint'])
        self.assertEqual(len(self.view()['history']), 1)

    def test_legacy_history_bytes_and_retry_survive_migration(self):
        self.apply(request_id='legacy')
        with self.store.transaction() as db:
            row = db.execute('SELECT payload FROM case_reviews').fetchone()
            event = json.loads(row[0]); event.pop('credential_checkpoint'); event['schema'] = 'nqc-case-review-v1'
            payload = canonical(event).decode(); head = mac(self.policy.key, 1, ORIGIN['head'], payload)
            db.execute('UPDATE case_reviews SET payload=?,mac=?', (payload,head))
            retained = db.execute('SELECT * FROM case_reviews').fetchall()
        self.head = {'revision':1,'head':head}
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token); self.tokens['ana'] = token
        self.assertFalse(self.apply(request_id='legacy', expected=ORIGIN)['applied'])
        self.apply('note')
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT * FROM case_reviews WHERE revision=1').fetchall(), retained)
        self.assertEqual([r['event']['schema'] for r in self.view()['history']], ['nqc-case-review-v1','nqc-case-review-v2'])

    def test_tail_rollback_rejected_against_retained_credential_checkpoint(self):
        self.change()
        with self.store.transaction() as db:
            db.execute('DELETE FROM review_credentials')
        with self.assertRaisesRegex(Rejected, 'credential_checkpoint_mismatch'):
            self.view()
        with self.assertRaisesRegex(Rejected, 'credential_checkpoint_mismatch'):
            self.change(actor='reader')

    def test_missing_lifecycle_history_referenced_by_review_rejected(self):
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token); self.tokens['ana'] = token
        self.apply()
        with self.store.transaction() as db:
            db.execute('DELETE FROM review_credentials')
        with self.assertRaisesRegex(Rejected, 'credential_history_missing'):
            self.view(expected_credentials=ORIGIN)

    def test_lifecycle_payload_change_detected(self):
        self.change()
        with self.store.transaction() as db:
            db.execute("UPDATE review_credentials SET payload='{}'")
        with self.assertRaisesRegex(Rejected, 'credential_history_integrity'):
            self.view()

    def test_lifecycle_sequence_gap_detected(self):
        self.change(); self.change(actor='reader')
        with self.store.transaction() as db:
            db.execute('DELETE FROM review_credentials WHERE revision=1')
        with self.assertRaisesRegex(Rejected, 'credential_history_sequence'):
            self.lifecycle.status(self.policy.key)

    def test_valid_mac_with_wrong_policy_binding_rejected(self):
        self.change()
        with self.store.transaction() as db:
            event = json.loads(db.execute('SELECT payload FROM review_credentials').fetchone()[0])
            event['policy_digest'] = 'f'*64; payload = canonical(event).decode()
            db.execute('UPDATE review_credentials SET payload=?,mac=?', (payload,mac(self.policy.key,1,ORIGIN['head'],payload)))
        with self.assertRaisesRegex(Rejected, 'credential_history_binding'):
            self.view()

    def test_malformed_mac_controlled_rejection(self):
        self.change()
        with self.store.transaction() as db:
            db.execute('UPDATE review_credentials SET mac=?', ('é'*64,))
        with self.assertRaises(Rejected):
            self.view()

    def test_policy_change_fails_management_and_review(self):
        (self.policy.root / 'policy.json').write_bytes(b'{}')
        with self.assertRaisesRegex(Rejected, 'review_policy_digest'):
            self.change()
        with self.assertRaisesRegex(Rejected, 'review_policy_digest'):
            self.view()

    def test_schema_regression_after_versioned_review_rejected(self):
        self.apply(); self.apply('note')
        with self.store.transaction() as db:
            payload, previous = db.execute('SELECT payload,previous FROM case_reviews WHERE revision=2').fetchone()
            event = json.loads(payload); event['schema'] = 'nqc-case-review-v1'; event.pop('credential_checkpoint')
            payload = canonical(event).decode()
            db.execute('UPDATE case_reviews SET payload=?,mac=? WHERE revision=2', (payload,mac(self.policy.key,2,previous,payload)))
        with self.assertRaisesRegex(Rejected, 'review_schema_regression'):
            self.view()

    def test_old_credential_generation_cannot_follow_newer_review_generation(self):
        token = secrets.token_bytes(32)
        self.change('rotate', credential=token); self.tokens['ana'] = token
        self.apply(); self.apply('note')
        with self.store.transaction() as db:
            payload, previous = db.execute('SELECT payload,previous FROM case_reviews WHERE revision=2').fetchone()
            event = json.loads(payload); event['credential_checkpoint'] = ORIGIN; payload = canonical(event).decode()
            db.execute('UPDATE case_reviews SET payload=?,mac=? WHERE revision=2', (payload,mac(self.policy.key,2,previous,payload)))
        with self.assertRaisesRegex(Rejected, 'review_credential_regression'):
            self.view()

    def test_history_cannot_claim_revoked_generation(self):
        self.apply(); self.change()
        with self.store.transaction() as db:
            event = json.loads(db.execute('SELECT payload FROM case_reviews').fetchone()[0])
            event['credential_checkpoint'] = self.credential_head; payload = canonical(event).decode()
            db.execute('UPDATE case_reviews SET payload=?,mac=?', (payload,mac(self.policy.key,1,ORIGIN['head'],payload)))
        with self.assertRaisesRegex(Rejected, 'credential_history_binding'):
            self.view()

    def test_revoke_during_bundle_verification_prevents_review_commit(self):
        self.apply()
        from nqc_defense.case_evidence import verify_bundle
        def revoke_while_parsing(*args):
            result = verify_bundle(*args)
            self.change()
            return result
        with patch('nqc_defense.case_review.verify_bundle', side_effect=revoke_while_parsing):
            with self.assertRaisesRegex(Rejected, 'review_unauthorized'):
                self.apply('note')
        self.assertEqual(self.view()['review']['notes_count'], 0)

    def test_competing_administrators_have_one_winner(self):
        def worker(actor):
            try:
                return self.lifecycle.change(self.policy.key, actor, 'revoke', 'race', actor, ORIGIN)['applied']
            except Rejected as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ['ana','boris']))
        self.assertCountEqual(results, [True,'credential_checkpoint_mismatch'])
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint']['revision'], 1)

    def test_failed_insert_keeps_credential_active(self):
        with self.store.transaction() as db:
            db.execute("CREATE TRIGGER fail_lifecycle BEFORE INSERT ON review_credentials BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.change()
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'], ORIGIN)
        self.assertTrue(self.apply()['applied'])

    def test_termination_before_commit_does_not_revoke(self):
        params = self.root / 'crash-credentials.json'
        params.write_bytes(canonical({'policy_digest':self.policy.digest}))
        script = '''
from contextlib import contextmanager
import json,os,sys
from pathlib import Path
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ReviewCredentials, ORIGIN
from nqc_defense.review_policy import ReviewPolicy
root=Path(sys.argv[1]); p=json.loads((root/'crash-credentials.json').read_bytes())
store=OperationsStore(root/'ops'); policy=ReviewPolicy(root/'policy',p['policy_digest']); lifecycle=ReviewCredentials(store,policy)
original=store.transaction
@contextmanager
def transaction():
    with original() as db:
        db.create_function('terminate_test_process',0,lambda:os._exit(77))
        db.execute('CREATE TEMP TRIGGER test_death AFTER INSERT ON review_credentials BEGIN SELECT terminate_test_process(); END')
        yield db
store.transaction=transaction
lifecycle.change(policy.key,'ana','revoke','crash','crash_1',ORIGIN)
'''
        result = subprocess.run([sys.executable,'-B','-c',script,str(self.root)],
                                cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'], ORIGIN)
        self.assertTrue(self.apply()['applied'])
        self.assertTrue(self.change()['applied'])

    def test_restart_enforces_revocation(self):
        self.apply(); self.change()
        reopened = CaseReview(OperationsStore(self.store.root), ReviewPolicy(self.policy.root,self.policy.digest))
        with self.assertRaisesRegex(Rejected,'review_unauthorized'):
            reopened.view('ana',self.tokens['ana'],'tenant','host',self.case['case_id'],expected_credentials=self.credential_head)
        self.assertEqual(reopened.view('reader',self.tokens['reader'],'tenant','host',self.case['case_id'],
                                      expected_credentials=self.credential_head)['checkpoint'],self.head)

    def test_exit_after_commit_can_retry_without_duplicate_revocation(self):
        script = '''
import os,sys
from pathlib import Path
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ReviewCredentials, ORIGIN
from nqc_defense.review_policy import ReviewPolicy
root=Path(sys.argv[1]); policy=ReviewPolicy(root/'policy',sys.argv[2])
ReviewCredentials(OperationsStore(root/'ops'),policy).change(policy.key,'ana','revoke','lost response','once',ORIGIN)
os._exit(78)
'''
        result = subprocess.run([sys.executable,'-B','-c',script,str(self.root),self.policy.digest],
                                cwd=Path(__file__).resolve().parents[1],capture_output=True)
        self.assertEqual(result.returncode,78,result.stderr)
        retry = self.change(request_id='once',reason='lost response',expected=ORIGIN)
        self.assertFalse(retry['applied'])
        self.assertEqual(retry['checkpoint']['revision'],1)
        with self.assertRaisesRegex(Rejected,'review_unauthorized'):
            self.apply()

    def test_rotation_does_not_bypass_other_actor_confirmation(self):
        self.apply(); self.apply('assess',verdict='benign')
        token = secrets.token_bytes(32)
        self.change('rotate',credential=token); self.tokens['ana'] = token
        with self.assertRaisesRegex(Rejected,'review_closure_requires_other_actor'):
            self.apply('close')

    def test_revocation_serializes_after_inflight_review_commit(self):
        from contextlib import contextmanager
        from threading import Event
        inserted, release, admin_started = Event(), Event(), Event()
        original = self.store.transaction
        @contextmanager
        def transaction():
            with original() as db:
                def hold():
                    inserted.set()
                    if not release.wait(5):
                        raise RuntimeError('test transaction wait timed out')
                    return 1
                db.create_function('hold_test_review',0,hold)
                db.execute('CREATE TEMP TRIGGER hold_review AFTER INSERT ON case_reviews BEGIN SELECT hold_test_review(); END')
                yield db
        self.store.transaction = transaction
        def revoke():
            admin_started.set()
            return self.lifecycle.change(self.policy.key,'ana','revoke','concurrent','revoke_race',ORIGIN)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                writing = pool.submit(self.apply)
                self.assertTrue(inserted.wait(5))
                revoking = pool.submit(revoke)
                self.assertTrue(admin_started.wait(5))
                release.set()
                self.assertTrue(writing.result(timeout=5)['applied'])
                self.credential_head = revoking.result(timeout=5)['checkpoint']
        finally:
            release.set()
            self.store.transaction = original
        self.assertEqual(len(self.view()['history']),1)
        with self.assertRaisesRegex(Rejected,'review_unauthorized'):
            self.apply('note')

    def test_clock_regression_rejects_lifecycle_change(self):
        with patch('nqc_defense.review_credentials.time.time_ns',return_value=100):
            self.change()
        with patch('nqc_defense.review_credentials.time.time_ns',return_value=99):
            with self.assertRaisesRegex(Rejected,'credential_clock_regressed'):
                self.change(actor='reader')

    def test_logical_quotas_reject_new_change(self):
        self.change()
        for name in ('MAX_REVISIONS','MAX_TOTAL_REVISIONS'):
            with patch('nqc_defense.review_credentials.'+name,1):
                with self.assertRaisesRegex(Rejected,'credential_capacity'):
                    self.change(actor='reader')

    def test_unknown_actor_invalid_reason_and_token_shape_rejected(self):
        for kwargs in ({'actor':'missing'}, {'reason':''}, {'reason':'bad\ud800'}, {'action':'rotate','credential':b'x'},
                       {'action':'grant'}, {'credential':secrets.token_bytes(32)}):
            with self.assertRaises(Rejected):
                self.change(**kwargs)
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],ORIGIN)

    def test_history_pagination_contains_no_raw_secrets(self):
        token = secrets.token_bytes(32)
        self.change('rotate',credential=token); self.change(actor='reader')
        result = self.lifecycle.status(self.policy.key,after=1,limit=1)
        self.assertEqual([x['revision'] for x in result['history']],[2])
        encoded = canonical(result)
        for secret in (token,self.policy.key,*self.tokens.values()):
            self.assertNotIn(secret.hex().encode(),encoded)

    def test_prepared_credential_is_not_active_and_never_overwritten(self):
        path = self.root/'prepared.key'
        receipt = create_credential(path); original = path.read_bytes()
        self.assertFalse(receipt['activated']); self.assertEqual(len(original),32)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        with self.assertRaises(FileExistsError):
            create_credential(path)
        self.assertEqual(path.read_bytes(),original)
        with self.assertRaisesRegex(Rejected,'review_unauthorized'):
            self.apply(credential=original)

    def test_public_parent_directory_cannot_receive_token(self):
        directory = self.root/'public'; directory.mkdir(mode=0o755)
        with self.assertRaisesRegex(Rejected,'review_credential_directory_permissions'):
            create_credential(directory/'token.key')
        self.assertFalse((directory/'token.key').exists())

    def test_cli_rotation_and_case_review_use_retained_checkpoint(self):
        tools = Path(__file__).resolve().parents[1]/'tools'
        token_path = self.root/'next.key'
        def run(name,*args):
            result = subprocess.run([sys.executable,'-B',str(tools/name),*args],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            return json.loads(result.stdout)
        self.assertFalse(run('review_credentials.py','new-token','--credential-file',str(token_path))['activated'])
        common = ['--operations-root',str(self.store.root),'--policy-root',str(self.policy.root),'--policy-digest',self.policy.digest]
        request = self.root/'rotate.json'
        request.write_bytes(canonical({'actor':'ana','action':'rotate','reason':'CLI rotation','request_id':'cli_rotate','expected':ORIGIN}))
        changed = run('review_credentials.py','change',*common,'--admin-key-file',str(self.policy.root/'audit.key'),
                      '--request-file',str(request),'--credential-file',str(token_path))
        cp = self.root/'checkpoint.json'; cp.write_bytes(canonical(changed['checkpoint']))
        result = run('case_review.py','view',*common,'--actor','ana','--credential-file',str(token_path),
                     '--tenant','tenant','--asset','host','--case-id',self.case['case_id'],'--credential-checkpoint',str(cp))
        self.assertEqual(result['credential_checkpoint'],changed['checkpoint'])


if __name__ == '__main__':
    unittest.main()
