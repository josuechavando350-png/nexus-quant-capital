"""Exercise real local key lifecycle against an authored authentication case and public proofs."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN as REVIEW_ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, create_signer, load_signer, public_bytes
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_dossier import capture_dossier
from nqc_defense.review_policy import ReviewPolicy, read_credential
from nqc_defense.signer_registry import ORIGIN, SignerRegistry, verify_registered


def fixture(root):
    """Explicit synthetic log content, with real parsers, SQLite, private files and signatures."""
    log = root/'auth.log'
    log.write_bytes(b''.join((f'2026-11-06T12:00:0{i}Z node-a sshd[417]: Failed password for analyst '
                             'from 192.0.2.42 port 43002 ssh2\n').encode() for i in range(3)))
    store = OperationsStore.create(root/'operations')
    monitor = AuthLogMonitor.register(store, 'ssh', 'evaluation', 'host', root, log.name, 3, 60,
                                      format_name='openssh-syslog-rfc3339', expected_host='node-a')
    monitor.poll(); case = store.cases('evaluation', 'host')[0]; case_digest = sha256(canonical(case))
    evidence_path = root/'evidence.json'
    captured = capture_case(store, 'evaluation', 'host', case['case_id'], case_digest, monitor.digest,
                            [{'generation':0, 'name':log.name}], evidence_path)
    evidence = evidence_path.read_bytes()
    grants = [{'actor':actor, 'tenant':'evaluation', 'assets':['host'], 'permissions':permissions}
              for actor, permissions in [('analyst',['start','assess']), ('confirmer',['close'])]]
    policy = ReviewPolicy.create(root/'policy', grants); review = CaseReview(store, policy); head = dict(REVIEW_ORIGIN)
    for actor,action,verdict in [('analyst','start',None), ('analyst','assess','benign'), ('confirmer','close',None)]:
        head = review.apply(actor, read_credential(policy.root/'credentials'/(actor+'.key')), 'evaluation', 'host', case['case_id'],
            action, 'Authored validation fixture', action, head, evidence, captured['bundle_digest'], case_digest,
            monitor.digest, verdict=verdict)['checkpoint']
    pins = {'tenant':'evaluation', 'asset':'host', 'case_id':case['case_id'], 'case_digest':case_digest,
            'config_digest':monitor.digest, 'evidence_digest':captured['bundle_digest'], 'policy_digest':policy.digest,
            'case_checkpoint':head, 'credential_checkpoint':REVIEW_ORIGIN, 'minimum_clock_ns':None}
    dossier_path = root/'dossier.json'; capture_dossier(review, policy.key, pins, evidence, dossier_path)
    signer_root = root/'signer'; key_pin = create_signer(signer_root)['public_key_sha256']; signing_key = load_signer(signer_root, key_pin)
    authority_root = root/'authority'; authority_pin = create_signer(authority_root)['public_key_sha256']
    authority_key = load_signer(authority_root, authority_pin)
    registry = SignerRegistry.create(root/'registry', public_bytes(authority_key), authority_pin, 'evaluation', 'host', policy.digest)
    return {'root':root, 'log':log, 'store':store, 'policy':policy, 'pins':pins, 'dossier':dossier_path.read_bytes(),
            'signing_key':signing_key, 'key_pin':key_pin, 'authority':authority_key, 'authority_pin':authority_pin,
            'registry':registry}


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); f = fixture(root); registry = f['registry']; key_pin = f['key_pin']
        data = attest_dossier(f['dossier'], sha256(f['dossier']), f['pins'], f['policy'].key, f['signing_key'], key_pin)
        activated = registry.change(f['authority'], 'activate', key_pin, 'activate', 'Initial key', ORIGIN, public_bytes(f['signing_key']))['receipt']
        old_receipt = registry.record(f['authority'], data, sha256(data), f['dossier'], sha256(f['dossier']),
            f['pins'], key_pin, 'old_record', 'Register original dossier', activated)['receipt']
        replacement = secrets.token_bytes(32); replacement_pin = sha256(public_bytes(replacement))
        rotated = registry.change(f['authority'], 'rotate', key_pin, 'rotate', 'Replace key', old_receipt, public_bytes(replacement))['receipt']
        old_bundle = registry.export(rotated)
        historical = verify_registered(old_bundle, sha256(old_bundle), registry.digest, f['authority_pin'], rotated, old_receipt,
            data, sha256(data), f['dossier'], sha256(f['dossier']), f['pins'])
        if historical['signer_status_at_checkpoint'] != 'retired':
            raise AssertionError('rotation lost historical verification')
        newer = attest_dossier(f['dossier'], sha256(f['dossier']), f['pins'], f['policy'].key, replacement, replacement_pin)
        new_receipt = registry.record(f['authority'], newer, sha256(newer), f['dossier'], sha256(f['dossier']), f['pins'],
            replacement_pin, 'new_record', 'Record replacement signer', rotated)['receipt']
        rejected = {}
        def reject(label, call):
            try:
                call()
            except Rejected as exc:
                rejected[label] = str(exc)
            else:
                raise AssertionError('invalid registry state accepted')
        changed = json.loads(f['dossier']); changed['captured_ns'] += 1; changed = canonical(changed)
        late = attest_dossier(changed, sha256(changed), f['pins'], f['policy'].key, f['signing_key'], key_pin)
        reject('new_record_from_retired_key', lambda:registry.record(f['authority'], late, sha256(late), changed, sha256(changed),
            f['pins'], key_pin, 'late', 'Retired key attempt', new_receipt))
        final = registry.change(f['authority'], 'revoke', key_pin, 'revoke', 'Revoke retired key', new_receipt)['receipt']
        bundle = registry.export(final)
        reject('revoked_historical_signer', lambda:verify_registered(bundle, sha256(bundle), registry.digest, f['authority_pin'],
            final, old_receipt, data, sha256(data), f['dossier'], sha256(f['dossier']), f['pins']))
        reject('stale_bundle', lambda:verify_registered(old_bundle, sha256(old_bundle), registry.digest, f['authority_pin'],
            final, old_receipt, data, sha256(data), f['dossier'], sha256(f['dossier']), f['pins']))
        retry = registry.record(f['authority'], data, sha256(data), f['dossier'], sha256(f['dossier']), f['pins'],
            key_pin, 'old_record', 'Register original dossier', activated)
        if retry['applied'] or retry['receipt'] != old_receipt or retry['current_checkpoint'] != final:
            raise AssertionError('idempotent recovery failed')
        outputs = {'pins.json':canonical(f['pins']), 'head.json':canonical(final), 'receipt.json':canonical(new_receipt),
                   'bundle.json':bundle, 'attestation.json':newer}
        for name, body in outputs.items():
            (root/name).write_bytes(body)
        for directory in ('operations', 'policy', 'signer', 'authority', 'registry'):
            shutil.rmtree(root/directory)
        f['log'].unlink(); (root/'evidence.json').unlink()
        command = [sys.executable, '-B', str(Path(__file__).with_name('signer_registry.py')), 'verify',
            '--registry-digest',registry.digest,'--authority-public-digest',f['authority_pin'],
            '--expected-file',str(root/'head.json'),'--receipt-file',str(root/'receipt.json'),
            '--bundle-file',str(root/'bundle.json'),'--bundle-digest',sha256(bundle),
            '--pins-file',str(root/'pins.json'),'--attestation-file',str(root/'attestation.json'),'--attestation-digest',sha256(newer),
            '--dossier-file',str(root/'dossier.json'),'--dossier-digest',sha256(f['dossier'])]
        process = subprocess.run(command, capture_output=True, text=True)
        if process.returncode or not json.loads(process.stdout)['registry_accepted']:
            raise AssertionError('public registry CLI failed')
        checks = {'registered_history_survives_rotation':historical['registry_accepted'],
                  'new_retired_key_registration_rejected':'new_record_from_retired_key' in rejected,
                  'revocation_and_stale_bundle_rejected':len(rejected)==3,
                  'idempotent_receipt_recovery_after_revocation':not retry['applied'],
                  'public_cli_without_private_material':True}
        return {'verified':all(checks.values()), 'checks':checks, 'block_criteria_completed':sum(checks.values()),
                'block_criteria_total':len(checks),'block_completion_percent':100*sum(checks.values())/len(checks),
                'fixture_origin':'authored OpenSSH-format logs; real files, SQLite, signatures and subprocess; no live sshd',
                'registry_rows':final['revision'], 'registered_attestations':2, 'public_bundle_bytes':len(bundle),
                'rejections':rejected, 'root_authority_rotation':False, 'independent_freshness':False,
                'independent_custody':False, 'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
