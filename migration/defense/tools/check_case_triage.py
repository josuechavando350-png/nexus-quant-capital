"""Exercise prioritization on authored auth logs through real case, review, signature and registry code."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN as REVIEW_ORIGIN
from nqc_defense.case_triage import SCHEMA, TriagePolicy, load_selection, publish_output, verify_output
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, create_signer, load_signer, public_bytes
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.registry_mirror import EMPTY, RegistryMirror
from nqc_defense.review_dossier import capture_dossier
from nqc_defense.review_policy import ReviewPolicy, read_credential
from nqc_defense.signer_registry import ORIGIN, SignerRegistry


def fixture(root, specifications=None):
    """All records are explicitly authored fixtures; no daemon or remote system is contacted."""
    specifications = specifications or [(3,'needs_response',False),(5,'inconclusive',False),
                                       (2,'benign',True),(3,None,False)]
    store = OperationsStore.create(root/'operations')
    grants = [{'actor':'analyst','tenant':'evaluation','assets':['host'],'permissions':['start','assess','note','reopen']},
              {'actor':'confirmer','tenant':'evaluation','assets':['host'],'permissions':['close']}]
    policy = ReviewPolicy.create(root/'policy',grants); review = CaseReview(store,policy)
    key_pin = create_signer(root/'signer')['public_key_sha256']; key = load_signer(root/'signer',key_pin)
    authority_pin = create_signer(root/'authority')['public_key_sha256']; authority = load_signer(root/'authority',authority_pin)
    registry = SignerRegistry.create(root/'registry',public_bytes(authority),authority_pin,'evaluation','host',policy.digest)
    head = registry.change(authority,'activate',key_pin,'activate','Triage fixture signer',ORIGIN,public_bytes(key))['receipt']
    items = []; selection = []; logs = []; evidence_paths = []
    for index,(count,verdict,close) in enumerate(specifications):
        log = root/f'auth_{index}.log'; logs.append(log)
        log.write_bytes(b''.join((f'2026-11-06T12:00:{number:02d}Z node-a sshd[417]: Failed password for user{index} '
            'from 192.0.2.42 port 43002 ssh2\n').encode() for number in range(count)))
        monitor = AuthLogMonitor.register(store,f'ssh_{index}','evaluation','host',root,log.name,count,60,
                                          format_name='openssh-syslog-rfc3339',expected_host='node-a')
        monitor.poll(); case = next(c for c in store.cases('evaluation','host') if c['source_id']==f'ssh_{index}')
        case_digest = sha256(canonical(case)); evidence_path = root/f'evidence_{index}.json'; evidence_paths.append(evidence_path)
        captured = capture_case(store,'evaluation','host',case['case_id'],case_digest,monitor.digest,
                                [{'generation':0,'name':log.name}],evidence_path)
        evidence = evidence_path.read_bytes(); review_head = dict(REVIEW_ORIGIN)
        actions = [('analyst','start',None)]
        if verdict is not None: actions.append(('analyst','assess',verdict))
        if close: actions.append(('confirmer','close',None))
        for actor,action,claim in actions:
            review_head = review.apply(actor,read_credential(policy.root/'credentials'/(actor+'.key')),
                'evaluation','host',case['case_id'],action,'Authored triage evaluation',action,review_head,
                evidence,captured['bundle_digest'],case_digest,monitor.digest,verdict=claim)['checkpoint']
        pins = {'tenant':'evaluation','asset':'host','case_id':case['case_id'],'case_digest':case_digest,
                'config_digest':monitor.digest,'evidence_digest':captured['bundle_digest'],'policy_digest':policy.digest,
                'case_checkpoint':review_head,'credential_checkpoint':REVIEW_ORIGIN,'minimum_clock_ns':None}
        dossier_file = root/f'dossier_{index}.json'; capture_dossier(review,policy.key,pins,evidence,dossier_file)
        dossier = dossier_file.read_bytes(); data = attest_dossier(dossier,sha256(dossier),pins,policy.key,key,key_pin)
        attestation_file = root/f'attestation_{index}.json'; attestation_file.write_bytes(data)
        head = registry.record(authority,data,sha256(data),dossier,sha256(dossier),pins,key_pin,f'record_{index}',
                               'Triage fixture dossier',head)['receipt']
        item = {'registration_receipt':head,'attestation':data,'attestation_digest':sha256(data),'dossier':dossier,
                'dossier_digest':sha256(dossier),'pins':pins}; items.append(item)
        selection.append({key:item[key] for key in ('registration_receipt','attestation_digest','dossier_digest','pins')} |
                         {'attestation_file':attestation_file.name,'dossier_file':dossier_file.name})
    bundle = registry.export(head); mirror = RegistryMirror.create(root/'mirror',registry.digest,authority_pin)
    mirror_receipt = mirror.accept(bundle,sha256(bundle),head,EMPTY)['receipt']
    config = {'schema':SCHEMA,'policy_id':'auth_queue','revision':1,'tenant':'evaluation','asset':'host',
              'registry_digest':registry.digest,'authority_digest':authority_pin,'review_policy_digest':policy.digest,
              'asset_criticality':1,'weights':{'criticality':10,'trigger_record':1,'trigger_record_cap':20,
              'needs_response':30,'inconclusive':10},'bands':{'normal':25,'high':50,'urgent':75}}
    triage_policy = TriagePolicy(canonical(config),sha256(canonical(config)))
    return {'root':root,'store':store,'policy':policy,'review':review,'signing_key':key,'key_pin':key_pin,
            'authority':authority,'authority_pin':authority_pin,'registry':registry,'registry_head':head,
            'mirror':mirror,'mirror_receipt':mirror_receipt,'items':items,'config':config,'triage_policy':triage_policy,
            'selection':{'schema':'nqc-auth-triage-selection-v1','items':selection},'logs':logs,'evidence_paths':evidence_paths}


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); f = fixture(root); mirror = f['mirror']; items = f['items']
        first = mirror.triage(f['mirror_receipt'],f['triage_policy'],items)
        rows = first['queue_report']['queue']
        if [x['score'] for x in rows] != [43,25,13,0]: raise AssertionError('unexpected baseline ranking')
        higher = {**f['config'],'revision':2,'asset_criticality':5}; policy_bytes = canonical(higher)
        policy = TriagePolicy(policy_bytes,sha256(policy_bytes)); second = mirror.triage(f['mirror_receipt'],policy,items)
        if [x['score'] for x in second['queue_report']['queue']] != [83,65,53,0]: raise AssertionError('criticality did not change priority')
        if [x['references'] for x in rows] != [x['references'] for x in second['queue_report']['queue']]:
            raise AssertionError('criticality changed evidence')
        if second != mirror.triage(f['mirror_receipt'],policy,list(reversed(items))): raise AssertionError('order dependent queue')
        for row in second['queue_report']['queue']:
            if sum(c['points'] for c in row['contributions']) != row['score']: raise AssertionError('explanation mismatch')
        output = root/'queue.json'; published = publish_output(output,second)
        if publish_output(output,second) != published: raise AssertionError('publication retry changed')
        verify_output(output.read_bytes(),published['report_digest'],second)
        selection_bytes = canonical(f['selection']); (root/'selection.json').write_bytes(selection_bytes)
        (root/'triage_policy.json').write_bytes(policy_bytes); (root/'expected.json').write_bytes(canonical(f['mirror_receipt']))
        selected = load_selection(root,selection_bytes,sha256(selection_bytes))
        if mirror.triage(f['mirror_receipt'],policy,selected) != second: raise AssertionError('selection load changed report')
        registry = f['registry']; head = registry.change(f['authority'],'revoke',f['key_pin'],'revoke',
                            'Fixture revocation',f['registry_head'])['receipt']; bundle = registry.export(head)
        # The receiver stays at its old view until an explicit new snapshot is accepted.
        for name in ('operations','policy','signer','authority','registry'): shutil.rmtree(root/name)
        for path in f['logs']+f['evidence_paths']: path.unlink()
        command = [sys.executable,'-B',str(Path(__file__).with_name('case_triage.py')),'verify',
            '--mirror-root',str(mirror.root),'--registry-digest',registry.digest,'--authority-public-digest',f['authority_pin'],
            '--expected-file',str(root/'expected.json'),'--policy-file',str(root/'triage_policy.json'),
            '--policy-digest',policy.digest,'--input-root',str(root),'--selection-file',str(root/'selection.json'),
            '--selection-digest',sha256(selection_bytes),'--report-file',str(output),'--report-digest',published['report_digest']]
        child = subprocess.run(command,capture_output=True,text=True,check=True)
        if not json.loads(child.stdout)['verified']: raise AssertionError('public CLI failed')
        next_receipt = mirror.accept(bundle,sha256(bundle),head,f['mirror_receipt'])['receipt']
        rejected = None
        try: mirror.triage(next_receipt,policy,items)
        except Rejected as exc: rejected = str(exc)
        if rejected != 'registry_signer_revoked': raise AssertionError('received revocation not applied')
        checks = {'ingestion_review_dossier_registry_to_explained_queue':True,
                  'criticality_changes_priority_without_changing_evidence':True,
                  'closed_case_retained_and_selection_order_invariant':True,
                  'private_atomic_publication_and_recomputation':True,
                  'cli_after_original_sources_and_private_keys_removed':True,
                  'received_revocation_rejects_entire_selection':True}
        return {'verified':True,'checks':checks,'block_criteria_completed':6,'block_criteria_total':6,
                'block_completion_percent':100.0,'selected_cases':4,'baseline_scores':[43,25,13,0],
                'higher_criticality_scores':[83,65,53,0],'rejection_after_received_revocation':rejected,
                'fixture_origin':'authored OpenSSH-format logs; real files, parsers, SQLite, review, signatures and CLI',
                'cross_asset_queue':False,'production_activated':False,'empirically_calibrated_weights':False,
                'independent_freshness':False,'independent_custody':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
