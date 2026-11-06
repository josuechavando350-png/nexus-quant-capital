"""Exercise a native-format case through public-key verification without retained secrets."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_log import AuthLogMonitor
from nqc_defense.case_evidence import capture_case
from nqc_defense.case_review import CaseReview, ORIGIN
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import create_signer, load_signer, publish_attestation, verify_attestation
from nqc_defense.files import sha256
from nqc_defense.operations import OperationsStore
from nqc_defense.review_dossier import capture_dossier
from nqc_defense.review_policy import ReviewPolicy, read_credential


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root/'auth.log'
        log.write_bytes(b''.join((f'2026-11-06T12:00:0{i}Z node-a sshd[417]: Failed password for analyst '
                                 'from 192.0.2.41 port 43001 ssh2\n').encode() for i in range(3)))
        store = OperationsStore.create(root/'operations')
        monitor = AuthLogMonitor.register(store, 'ssh', 'evaluation', 'host', root, log.name, 3, 60,
                                          format_name='openssh-syslog-rfc3339', expected_host='node-a')
        monitor.poll(); case = store.cases('evaluation', 'host')[0]; case_digest = sha256(canonical(case))
        evidence_path = root/'evidence.json'
        acquired = capture_case(store, 'evaluation', 'host', case['case_id'], case_digest, monitor.digest,
                                [{'generation':0, 'name':log.name}], evidence_path)
        evidence = evidence_path.read_bytes()
        grants = [{'actor':actor, 'tenant':'evaluation', 'assets':['host'], 'permissions':permissions}
                  for actor,permissions in [('analyst',['read','start','assess']), ('confirmer',['read','close'])]]
        policy = ReviewPolicy.create(root/'policy', grants); review = CaseReview(store, policy)
        checkpoint = dict(ORIGIN)
        for actor,action,verdict in [('analyst','start',None), ('analyst','assess','benign'), ('confirmer','close',None)]:
            checkpoint = review.apply(actor, read_credential(policy.root/'credentials'/(actor+'.key')),
                'evaluation', 'host', case['case_id'], action, 'Authored acceptance fixture', action, checkpoint,
                evidence, acquired['bundle_digest'], case_digest, monitor.digest, verdict=verdict)['checkpoint']
        pins = {'tenant':'evaluation', 'asset':'host', 'case_id':case['case_id'], 'case_digest':case_digest,
                'config_digest':monitor.digest, 'evidence_digest':acquired['bundle_digest'], 'policy_digest':policy.digest,
                'case_checkpoint':checkpoint, 'credential_checkpoint':ORIGIN, 'minimum_clock_ns':None}
        dossier_path = root/'dossier.json'
        capture = capture_dossier(review, policy.key, pins, evidence, dossier_path)
        dossier = dossier_path.read_bytes(); signer = root/'signer'
        key_pin = create_signer(signer)['public_key_sha256']; public_key = (signer/'verify.key').read_bytes()
        attestation_path = root/'attestation.json'; private_key = load_signer(signer, key_pin)
        arguments = (attestation_path, dossier, capture['dossier_digest'], pins, policy.key, private_key, key_pin)
        first = publish_attestation(*arguments); original = attestation_path.read_bytes()
        second = publish_attestation(*arguments)
        if first != second or original != attestation_path.read_bytes() or dossier_path.read_bytes() != dossier:
            raise AssertionError('retry changed immutable bytes')
        rejected = {}
        def reject(label, data, actual_dossier, actual_pins, pubkey=public_key):
            try:
                verify_attestation(data, sha256(data), actual_dossier, capture['dossier_digest'], actual_pins, pubkey, key_pin)
            except Rejected as exc:
                rejected[label] = str(exc)
            else:
                raise AssertionError('alteration accepted')
        changed = json.loads(original); changed['statement']['report']['facts']['review']['stage'] = 'investigating'
        reject('changed_report', canonical(changed), dossier, pins)
        reject('changed_dossier', original, dossier+b' ', pins)
        reject('different_scope', original, dossier, {**pins, 'tenant':'other'})
        reject('different_public_key', original, dossier, pins, b'\x00'*32)
        public_path = root/'public.key'; public_path.write_bytes(public_key)
        pins_path = root/'pins.json'; pins_path.write_bytes(canonical(pins))
        # The verification subprocess receives no paths or arguments containing private material.
        shutil.rmtree(store.root); shutil.rmtree(policy.root); shutil.rmtree(signer)
        log.unlink(); evidence_path.unlink()
        public_report = verify_attestation(original, first['attestation_digest'], dossier,
            capture['dossier_digest'], pins, public_key, key_pin)
        tool = Path(__file__).with_name('dossier_attestation.py')
        result = subprocess.run([sys.executable, '-B', str(tool), 'verify', '--pins-file', str(pins_path),
            '--dossier-file', str(dossier_path), '--dossier-digest', capture['dossier_digest'],
            '--public-key-file', str(public_path), '--public-key-digest', key_pin,
            '--attestation-file', str(attestation_path), '--attestation-digest', first['attestation_digest']],
            capture_output=True, text=True)
        if result.returncode or json.loads(result.stdout) != public_report:
            raise AssertionError('public CLI verification did not reproduce report')
        checks = {'full_case_evidence_review_dossier_chain':public_report['signer_report']['facts']['review']['stage']=='closed',
                  'signature_and_exact_dossier_verified':public_report['signature_verified'] and public_report['dossier_bytes_matched'],
                  'tampering_scope_and_key_substitution_rejected':len(rejected)==4,
                  'public_cli_after_private_files_removed':True,
                  'identical_retry_and_source_bytes_preserved':True}
        if not all(checks.values()):
            raise AssertionError('acceptance incomplete')
        return {'verified':True, 'fixture_origin':'authored OpenSSH RFC3339 records; real files, SQLite, generated keys and CLI; no live sshd',
                'checks':checks, 'block_criteria_completed':sum(checks.values()), 'block_criteria_total':len(checks),
                'block_completion_percent':100*sum(checks.values())/len(checks), 'algorithm':'Ed25519',
                'dossier_bytes':len(dossier), 'attestation_bytes':len(original),
                'dossier_digest':capture['dossier_digest'], 'attestation_digest':first['attestation_digest'],
                'public_key_sha256':key_pin, 'trigger_records':3, 'rejections':rejected,
                'private_key_required_for_verification':False, 'hmac_replay_by_public_verifier':False,
                'independent_custody':False, 'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
