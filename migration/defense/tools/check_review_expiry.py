"""Exercise expiry with explicit test clock boundaries and one actual wall-clock check."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ReviewCredentials, create_credential
from nqc_defense.review_policy import ReviewPolicy, read_credential


def run(initial_lifecycle_class=ReviewCredentials, initial_review_class=CaseReview):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root/'auth.jsonl'
        log.write_bytes(b''.join(canonical({'schema':'nqc-auth-log-v1','time_ns':i*1000000000,
            'outcome':'failure','principal':'fixture-user','remote_address':'192.0.2.50'}) + b'\n' for i in range(3)))
        store = OperationsStore.create(root/'operations')
        monitor = AuthLogMonitor.register(store,'auth','evaluation','host',root,log.name,3,60)
        monitor.poll(); case = store.cases('evaluation','host')[0]; case_digest = sha256(canonical(case))
        bundle_path = root/'bundle.json'
        evidence = capture_case(store,'evaluation','host',case['case_id'],case_digest,monitor.digest,
                                [{'generation':0,'name':log.name}],bundle_path)
        grants = [{'actor':actor,'tenant':'evaluation','assets':['host'],'permissions':permissions}
                  for actor,permissions in [('analyst',['read','start','note','assess']),('observer',['read'])]]
        policy = ReviewPolicy.create(root/'policy',grants)
        keys = {g['actor']:read_credential(policy.root/'credentials'/(g['actor']+'.key')) for g in grants}
        create_credential(root/'rotated.key'); keys['analyst'] = read_credential(root/'rotated.key')
        now = [100]; rejections = {}; common = ('evaluation','host',case['case_id'])
        evidence_args = (bundle_path.read_bytes(),evidence['bundle_digest'],case_digest,monitor.digest)
        def rejected(label,fn,reason):
            try:
                fn()
            except Rejected as exc:
                if str(exc) != reason:
                    raise AssertionError('unexpected rejection') from exc
                rejections[label] = str(exc)
            else:
                raise AssertionError('expected rejection missing')
        with patch('nqc_defense.review_clock.time.time_ns',side_effect=lambda:now[0]):
            previous = initial_lifecycle_class(store,policy)
            credential_head = previous.change(policy.key,'analyst','rotate','Acceptance rotation','initial_rotate',ORIGIN,
                                              credential=keys['analyst'])['checkpoint']
            initial = initial_review_class(store,policy)
            case_head = initial.apply('analyst',keys['analyst'],*common,'start','Acceptance','start',ORIGIN,*evidence_args,
                                      expected_credentials=credential_head)['checkpoint']
            with store.transaction() as db:
                initial_credential = db.execute('SELECT payload,mac FROM review_credentials WHERE revision=1').fetchone()
                initial_case = db.execute('SELECT payload,mac FROM case_reviews WHERE revision=1').fetchone()
            review = CaseReview(store,policy); lifecycle = review.credentials
            credential_head = lifecycle.change(policy.key,'analyst','set_expiry','Bound credential','expiry',credential_head,
                                               expires_at_ns=200)['checkpoint']
            now[0] = 199
            case_head = review.apply('analyst',keys['analyst'],*common,'note','Before expiry','note',case_head,*evidence_args,
                                     expected_credentials=credential_head)['checkpoint']
            now[0] = 200
            rejected('at_deadline',lambda:review.view('analyst',keys['analyst'],*common,
                     expected_credentials=credential_head),'review_credential_expired')
            restarted = CaseReview(OperationsStore(store.root),ReviewPolicy(policy.root,policy.digest))
            now[0] = 199
            rejected('restart_clock_rollback',lambda:restarted.view('analyst',keys['analyst'],*common,
                     expected_credentials=credential_head),'credential_clock_regressed')
            now[0] = 201
            observed = restarted.view('observer',keys['observer'],*common,expected=case_head,expected_credentials=credential_head)
            create_credential(root/'replacement.key'); replacement = read_credential(root/'replacement.key')
            rejected('implicit_expiry_removal',lambda:lifecycle.change(policy.key,'analyst','rotate','Acceptance','invalid_rotate',
                     credential_head,credential=replacement),'credential_expiry_not_future')
            credential_head = lifecycle.change(policy.key,'analyst','rotate','New bounded credential','renew_lifetime',credential_head,
                                               credential=replacement,expires_at_ns=300)['checkpoint']
            keys['analyst'] = replacement
            case_head = restarted.apply('analyst',replacement,*common,'assess','Review continues','assessment',case_head,*evidence_args,
                                        verdict='inconclusive',expected_credentials=credential_head)['checkpoint']
            status = lifecycle.status(policy.key,expected=credential_head)
            with store.transaction() as db:
                retained_credential = db.execute('SELECT payload,mac FROM review_credentials WHERE revision=1').fetchone()
                retained_case = db.execute('SELECT payload,mac FROM case_reviews WHERE revision=1').fetchone()
            if initial_credential != retained_credential or initial_case != retained_case or observed['review']['notes_count'] != 1:
                raise AssertionError('migration modified previous history')
        # The deadlines above are deliberately in the past relative to the real wall clock.
        real_now = time.time_ns()
        if real_now <= 300:
            raise AssertionError('unexpected test environment wall clock')
        rejected('actual_wall_clock',lambda:restarted.view('analyst',keys['analyst'],*common,
                 expected_credentials=credential_head),'review_credential_expired')
        return {'verified':True,'fixture_origin':'authored logs, real files/SQLite and temporary credentials',
                'boundary_clock':'injected times 100, 199, 200 and 201 nanoseconds for deterministic boundary tests',
                'actual_wall_clock_checked_ns':real_now,'rejections':rejections,
                'initial_credential_schema':json.loads(initial_credential[0])['schema'],
                'initial_review_schema':json.loads(initial_case[0])['schema'],
                'previous_credential_and_case_bytes_unchanged':True,'credential_checkpoint':credential_head,
                'case_checkpoint':case_head,'replacement_expires_at_ns':status['actors']['analyst']['expires_at_ns'],
                'clock_floor_before_real_clock_check':status['clock']['observed_ns'],
                'clock_is_independently_trusted':False,'whole_database_rollback_protected':False,
                'all_legacy_credentials_automatically_expire':False,'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
