"""Accept revocation on a public-data receiver and preserve the signed registry prefix."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_signer_registry import fixture
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import EMPTY, RegistryMirror
from nqc_defense.signer_registry import ORIGIN


def run():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); f = fixture(root); registry = f['registry']
        data = attest_dossier(f['dossier'],sha256(f['dossier']),f['pins'],f['policy'].key,f['signing_key'],f['key_pin'])
        head = registry.change(f['authority'],'activate',f['key_pin'],'activate','Initial signer',ORIGIN,public_bytes(f['signing_key']))['receipt']
        registered = registry.record(f['authority'],data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins'],f['key_pin'],
                                     'register','Original dossier',head)['receipt']
        first_bundle = registry.export(registered)
        mirror = RegistryMirror.create(root/'mirror',registry.digest,f['authority_pin'])
        first = mirror.accept(first_bundle,sha256(first_bundle),registered,EMPTY)['receipt']
        report = mirror.verify(first,registered,data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins'])
        if not report['registry_report']['registry_accepted']: raise AssertionError('initial receipt failed')
        new_key = secrets.token_bytes(32); new_pin = sha256(public_bytes(new_key))
        head = registry.change(f['authority'],'rotate',f['key_pin'],'rotate','New signer',registered,public_bytes(new_key))['receipt']
        bundle = registry.export(head)
        second = mirror.accept(bundle,sha256(bundle),head,first)['receipt']
        historical = mirror.verify(second,registered,data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins'])
        if historical['registry_report']['signer_status_at_checkpoint'] != 'retired': raise AssertionError('history lost')
        head = registry.change(f['authority'],'revoke',f['key_pin'],'revoke','Retired signer revoked',head)['receipt']
        bundle = registry.export(head); third = mirror.accept(bundle,sha256(bundle),head,second)['receipt']
        rejected = {}
        def reject(label, call):
            try: call()
            except Rejected as exc: rejected[label] = str(exc)
            else: raise AssertionError('invalid receiver operation accepted')
        reject('revoked_signer',lambda:mirror.verify(third,registered,data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins']))
        reject('rollback_snapshot',lambda:mirror.accept(first_bundle,sha256(first_bundle),registered,third))
        reject('stale_receiver_receipt',lambda:mirror.verify(first,registered,data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins']))
        newer = attest_dossier(f['dossier'],sha256(f['dossier']),f['pins'],f['policy'].key,new_key,new_pin)
        new_registration = registry.record(f['authority'],newer,sha256(newer),f['dossier'],sha256(f['dossier']),f['pins'],new_pin,
                                           'replacement','Replacement signer dossier',head)['receipt']
        bundle = registry.export(new_registration)
        final = mirror.accept(bundle,sha256(bundle),new_registration,third)['receipt']
        if mirror.accept(bundle,sha256(bundle),new_registration,third)['advanced']: raise AssertionError('retry advanced twice')
        if mirror.export(final) != bundle: raise AssertionError('receiver changed registry bytes')
        paths = {'pins.json':canonical(f['pins']),'receiver.json':canonical(final),'receipt.json':canonical(new_registration),
                 'attestation.json':newer}
        for name,body in paths.items(): (root/name).write_bytes(body)
        for name in ('operations','policy','signer','authority','registry'): shutil.rmtree(root/name)
        f['log'].unlink(); (root/'evidence.json').unlink()
        mirror = RegistryMirror(mirror.root,registry.digest,f['authority_pin'])
        if mirror.status(final)['receipt'] != final: raise AssertionError('receiver restart failed')
        command = [sys.executable,'-B',str(Path(__file__).with_name('registry_mirror.py')),'verify',
            '--mirror-root',str(mirror.root),'--registry-digest',registry.digest,'--authority-public-digest',f['authority_pin'],
            '--expected-file',str(root/'receiver.json'),'--receipt-file',str(root/'receipt.json'),
            '--pins-file',str(root/'pins.json'),'--attestation-file',str(root/'attestation.json'),'--attestation-digest',sha256(newer),
            '--dossier-file',str(root/'dossier.json'),'--dossier-digest',sha256(f['dossier'])]
        process = subprocess.run(command,capture_output=True,text=True)
        if process.returncode or not json.loads(process.stdout)['registry_report']['registry_accepted']:
            raise AssertionError('receiver CLI failed without issuer stores')
        checks = {'received_registry_accepts_original_and_rotated_history':True,
                  'received_revocation_rejects_old_signer':rejected.get('revoked_signer')=='registry_signer_revoked',
                  'rollback_and_stale_local_receipts_rejected':len(rejected)==3,
                  'prefix_bytes_and_idempotent_update_preserved':True,
                  'reopened_receiver_cli_without_issuer_or_private_keys':True}
        return {'verified':all(checks.values()),'checks':checks,'block_criteria_completed':sum(checks.values()),
                'block_criteria_total':len(checks),'block_completion_percent':100*sum(checks.values())/len(checks),
                'fixture_origin':'authored OpenSSH-format logs; real files, signatures, SQLite and subprocess',
                'receiver_generation':final['generation'],'registry_rows':new_registration['revision'],
                'rejections':rejected,'network_delivery_implemented':False,'independent_freshness':False,
                'whole_database_rollback_requires_external_receipt':True,'production_activated':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
