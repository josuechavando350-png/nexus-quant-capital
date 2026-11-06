"""Real local lifecycle acceptance on authored log records; no service or production keys."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import create_credential
from nqc_defense.review_policy import ReviewPolicy, read_credential


def run(initial_review_class=CaseReview):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root / 'auth.jsonl'
        log.write_bytes(b''.join(canonical({'schema':'nqc-auth-log-v1','time_ns':i*1000000000,
            'outcome':'failure','principal':'fixture-user','remote_address':'192.0.2.50'}) + b'\n' for i in range(3)))
        store = OperationsStore.create(root / 'operations')
        monitor = AuthLogMonitor.register(store,'auth','evaluation','host',root,log.name,3,60)
        monitor.poll(); case = store.cases('evaluation','host')[0]; case_digest = sha256(canonical(case))
        bundle_path = root / 'bundle.json'
        evidence = capture_case(store,'evaluation','host',case['case_id'],case_digest,monitor.digest,
                                [{'generation':0,'name':log.name}],bundle_path)
        grants = [{'actor':a,'tenant':'evaluation','assets':['host'],'permissions':p} for a,p in
                  [('analyst',['read','start','note','assess']),('confirmer',['read','close','reopen'])]]
        policy = ReviewPolicy.create(root / 'policy',grants)
        keys = {g['actor']:read_credential(policy.root / 'credentials' / (g['actor']+'.key')) for g in grants}
        initial = initial_review_class(store,policy)
        common = ('evaluation','host',case['case_id'])
        evidence_args = (bundle_path.read_bytes(),evidence['bundle_digest'],case_digest,monitor.digest)
        first = initial.apply('analyst',keys['analyst'],*common,'start','Local acceptance','start',ORIGIN,*evidence_args)
        with store.transaction() as db:
            original_row = db.execute('SELECT payload,mac FROM case_reviews WHERE revision=1').fetchone()
        review = CaseReview(store,policy); lifecycle = review.credentials
        case_head = first['checkpoint']; credential_head = dict(ORIGIN); changes = []; rejections = {}
        def act(actor,action,request,verdict=None,token=None):
            nonlocal case_head
            result = review.apply(actor,keys[actor] if token is None else token,*common,action,'Local acceptance',request,
                                  case_head,*evidence_args,verdict=verdict,expected_credentials=credential_head)
            case_head = result['checkpoint']
            return result
        def change(action,request,token=None):
            nonlocal credential_head
            result = lifecycle.change(policy.key,'analyst',action,'Local acceptance',request,credential_head,credential=token)
            credential_head = result['checkpoint']; changes.append({'action':action,'checkpoint':credential_head})
            return result
        def reject(label,fn,reason):
            try:
                fn()
            except Rejected as exc:
                if str(exc) != reason:
                    raise AssertionError('unexpected rejection') from exc
                rejections[label] = str(exc)
            else:
                raise AssertionError('expected rejection did not occur')
        retired = keys['analyst']
        create_credential(root / 'rotated.key'); rotated = read_credential(root / 'rotated.key')
        change('rotate','rotate',rotated)
        reject('retired_token',lambda:act('analyst','note','retired'), 'review_unauthorized')
        keys['analyst'] = rotated; act('analyst','note','after_rotation')
        before_revoke = dict(credential_head)
        change('revoke','revoke')
        reject('revoked_copy',lambda:act('analyst','note','revoked_copy',token=bytes(rotated)), 'review_unauthorized')
        retry = lifecycle.change(policy.key,'analyst','revoke','Local acceptance','revoke',before_revoke)
        if retry['applied'] or retry['checkpoint'] != credential_head:
            raise AssertionError('revocation retry duplicated state')
        create_credential(root / 'renewed.key'); renewed = read_credential(root / 'renewed.key')
        change('renew','renew',renewed); keys['analyst'] = renewed
        reject('reuse_retired_token',lambda:lifecycle.change(policy.key,'analyst','rotate','Local acceptance',
               'reuse',credential_head,credential=retired), 'credential_reuse')
        act('analyst','assess','benign','benign'); act('confirmer','close','close')
        reopened = CaseReview(OperationsStore(store.root),ReviewPolicy(policy.root,policy.digest))
        result = reopened.view('confirmer',keys['confirmer'],*common,expected=case_head,expected_credentials=credential_head)
        with store.transaction() as db:
            retained_row = db.execute('SELECT payload,mac FROM case_reviews WHERE revision=1').fetchone()
        if original_row != retained_row or result['review']['stage'] != 'closed' or result['detection_status'] != 'open':
            raise AssertionError('history or review outcome changed')
        reject('stale_credential_checkpoint',lambda:reopened.view('confirmer',keys['confirmer'],*common,
               expected_credentials=ORIGIN), 'credential_checkpoint_mismatch')
        return {'verified':True,'fixture_origin':'authored authentication records, real files and SQLite, temporary keys',
                'initial_review_schema':json.loads(original_row[0])['schema'],'initial_review_bytes_unchanged':True,
                'credential_changes':changes,'rejections':rejections,'idempotent_revocation_retry':True,
                'case_checkpoint':case_head,'credential_checkpoint':credential_head,'review_stage':result['review']['stage'],
                'detection_status':result['detection_status'],'restart_verified':True,'raw_credentials_in_report':False,
                'revocation_scope':'one operations store and pinned policy','independent_anchor':False,'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
