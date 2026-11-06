"""Verify a native-format case dossier after removing its live sources and databases."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_credentials import ReviewCredentials, create_credential
from nqc_defense.review_dossier import capture_dossier, verify_dossier
from nqc_defense.review_policy import ReviewPolicy, read_credential


def run(initial_lifecycle_class=ReviewCredentials, initial_review_class=CaseReview):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root/'auth.log'
        def line(second):
            return (f'2026-11-06T12:00:0{second}Z node-a sshd[351]: Failed password for analyst '
                    'from 192.0.2.40 port 43000 ssh2\n').encode()
        log.write_bytes(line(0)+line(1))
        store = OperationsStore.create(root/'operations')
        monitor = AuthLogMonitor.register(store,'ssh','evaluation','host',root,log.name,3,60,
                                          format_name='openssh-syslog-rfc3339',expected_host='node-a')
        monitor.poll(); log.rename(root/'auth.old'); log.write_bytes(line(2)); monitor.rotate('auth.old'); monitor.poll()
        case = store.cases('evaluation','host')[0]; case_digest = sha256(canonical(case))
        evidence_path = root/'evidence.json'
        acquired = capture_case(store,'evaluation','host',case['case_id'],case_digest,monitor.digest,
                                [{'generation':0,'name':'auth.old'},{'generation':1,'name':'auth.log'}],evidence_path)
        evidence = evidence_path.read_bytes()
        grants = [{'actor':a,'tenant':'evaluation','assets':['host'],'permissions':p} for a,p in
                  [('analyst',['read','start','note','assess']),('confirmer',['read','close','reopen'])]]
        policy = ReviewPolicy.create(root/'policy',grants)
        tokens = {g['actor']:read_credential(policy.root/'credentials'/(g['actor']+'.key')) for g in grants}
        create_credential(root/'rotated.key'); tokens['analyst'] = read_credential(root/'rotated.key')
        lifecycle = initial_lifecycle_class(store,policy)
        credential_head = lifecycle.change(policy.key,'analyst','rotate','Local dossier acceptance','rotate',ORIGIN,
            credential=tokens['analyst'],expires_at_ns=time.time_ns()+3600_000_000_000)['checkpoint']
        review = initial_review_class(store,policy); case_head = dict(ORIGIN)
        for actor,action,verdict in [('analyst','start',None),('analyst','note',None),('analyst','assess','benign'),('confirmer','close',None)]:
            case_head = review.apply(actor,tokens[actor],'evaluation','host',case['case_id'],action,'Authored fixture review',action,
                case_head,evidence,acquired['bundle_digest'],case_digest,monitor.digest,verdict=verdict,
                expected_credentials=credential_head)['checkpoint']
        with store.transaction() as db:
            original_credentials = db.execute('SELECT revision,payload,previous,mac FROM review_credentials ORDER BY revision').fetchall()
            original_case = db.execute('SELECT revision,payload,previous,mac FROM case_reviews ORDER BY revision').fetchall()
        review = CaseReview(store,policy)
        minimum = review.credentials.status(policy.key)['clock']['observed_ns']
        pins = {'tenant':'evaluation','asset':'host','case_id':case['case_id'],'case_digest':case_digest,
                'config_digest':monitor.digest,'evidence_digest':acquired['bundle_digest'],'policy_digest':policy.digest,
                'case_checkpoint':case_head,'credential_checkpoint':credential_head,'minimum_clock_ns':minimum}
        output = root/'dossier.json'; receipt = capture_dossier(review,policy.key,pins,evidence,output)
        data = output.read_bytes(); value = json.loads(data)
        if value['credential_rows'] != [list(row) for row in original_credentials] or value['review_rows'] != [list(row) for row in original_case]:
            raise AssertionError('history payloads changed in export')
        rejected = {}
        def reject(label,body,digest,expected):
            try:
                verify_dossier(body,digest,expected,policy.key)
            except Rejected as exc:
                rejected[label] = str(exc)
            else:
                raise AssertionError('invalid dossier was accepted')
        changed = dict(value); changed['review_rows'] = value['review_rows'][:-1]; changed_data = canonical(changed)
        reject('truncated_review',changed_data,sha256(changed_data),pins)
        reject('altered_bytes',data+b' ',receipt['dossier_digest'],pins)
        stale = {**pins,'credential_checkpoint':ORIGIN}
        reject('stale_credential_pin',data,receipt['dossier_digest'],stale)
        pins_path = root/'pins.json'; pins_path.write_bytes(canonical(pins))
        key_path = root/'offline.key'; key_path.write_bytes(policy.key); os.chmod(key_path,0o600)
        shutil.rmtree(store.root); shutil.rmtree(policy.root)
        log.unlink(); (root/'auth.old').unlink(); evidence_path.unlink(); (root/'rotated.key').unlink()
        result = verify_dossier(data,receipt['dossier_digest'],pins,policy.key)
        command = subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('review_dossier.py')),'verify',
            '--pins-file',str(pins_path),'--audit-key-file',str(key_path),'--dossier-file',str(output),
            '--dossier-digest',receipt['dossier_digest']],capture_output=True,text=True)
        if command.returncode != 0 or json.loads(command.stdout) != result:
            raise AssertionError('offline CLI did not reproduce report')
        if result['facts']['review']['stage'] != 'closed' or result['assessment']['classification'] != 'analyst_claim':
            raise AssertionError('report conflated facts and assessment')
        checks = {'coherent_snapshot_and_evidence':True,'offline_replay_after_sources_removed':True,
                  'corruption_and_stale_pins_rejected':len(rejected)==3,'historical_payloads_preserved':True,
                  'cli_reproduces_offline_report':True}
        if not all(checks.values()):
            raise AssertionError('acceptance incomplete')
        return {'verified':True,'fixture_origin':'authored OpenSSH-format records; real files, SQLite, keys and CLI; no live sshd',
                'checks':checks,'block_criteria_completed':sum(checks.values()),'block_criteria_total':len(checks),
                'block_completion_percent':100*sum(checks.values())/len(checks),
                'dossier_digest':receipt['dossier_digest'],'dossier_bytes':receipt['bytes'],'source_generations':2,
                'trigger_records':result['facts']['trigger_records']['count'],'review_stage':result['facts']['review']['stage'],
                'initial_review_schema':json.loads(original_case[0][1])['schema'],
                'initial_credential_schema':json.loads(original_credentials[0][1])['schema'],
                'rejections':rejected,'independent_anchor':False,'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
