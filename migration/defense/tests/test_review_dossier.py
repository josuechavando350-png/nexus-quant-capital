from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_review_credentials as fixtures
from nqc_defense.audit import mac
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256
from nqc_defense.review_dossier import capture_dossier, verify_dossier
from nqc_defense.review_credentials import ORIGIN


class DossierTests(unittest.TestCase):
    apply = fixtures.CredentialTests.apply
    view = fixtures.CredentialTests.view
    change = fixtures.CredentialTests.change

    def setUp(self):
        fixtures.CredentialTests.setUp(self)
        self.apply(); self.apply('note'); self.apply('assess',verdict='benign'); self.apply('close',actor='boris')
        self.output = self.root/'dossier.json'
        self.pins = {'tenant':'tenant','asset':'host','case_id':self.case['case_id'],'case_digest':self.case_digest,
                     'config_digest':self.monitor.digest,'evidence_digest':self.bundle_digest,'policy_digest':self.policy.digest,
                     'case_checkpoint':self.head,'credential_checkpoint':self.credential_head,'minimum_clock_ns':None}

    def capture(self, **kwargs):
        args = dict(review=self.review,admin_key=self.policy.key,pins=self.pins,evidence_bytes=self.bundle,output=self.output)
        args.update(kwargs); return capture_dossier(**args)

    def verify(self, value=None, **kwargs):
        data = self.output.read_bytes() if value is None else canonical(value)
        args = dict(data=data,digest=sha256(data),pins=self.pins,audit_key=self.policy.key)
        args.update(kwargs); return verify_dossier(**args)

    def with_deadline(self):
        import time
        self.change('set_expiry',expires_at_ns=time.time_ns()+3600_000_000_000)
        self.pins['credential_checkpoint'] = self.credential_head
        self.pins['minimum_clock_ns'] = self.lifecycle.status(self.policy.key)['clock']['observed_ns']

    def test_export_replays_state_and_labels_assessment_as_claim(self):
        receipt = self.capture(); report = self.verify()
        self.assertEqual(receipt['dossier_digest'],report['dossier_digest'])
        self.assertEqual(report['facts']['review']['stage'],'closed')
        self.assertEqual(report['assessment']['classification'],'analyst_claim')
        self.assertEqual(report['assessment']['row_head'],report['timeline'][2]['row_head'])
        self.assertEqual(report['facts']['trigger_records']['event_ids'],self.case['evidence_event_ids'])
        self.assertFalse(report['limits']['current_authorization_checked'])
        self.assertFalse(report['limits']['independent_anchor'])

    def test_private_publication_and_exact_row_bytes(self):
        self.capture(); value = json.loads(self.output.read_bytes())
        self.assertEqual(self.output.stat().st_mode & 0o777,0o600)
        with self.store.transaction() as db:
            rows = db.execute('SELECT revision,payload,previous,mac FROM case_reviews ORDER BY revision').fetchall()
        self.assertEqual(value['review_rows'],[list(row) for row in rows])
        self.assertEqual(canonical(value['evidence']),self.bundle)
        self.assertEqual(canonical(value['policy']),(self.policy.root/'policy.json').read_bytes())

    def test_verifier_opens_no_embedded_paths_database_or_clock(self):
        self.capture(); data = self.output.read_bytes(); key = self.policy.key
        with ExitStack() as stack:
            for target in ('builtins.open','os.open','sqlite3.connect','socket.socket','time.time_ns','pathlib.Path.read_bytes'):
                stack.enter_context(patch(target,side_effect=AssertionError('offline verifier performed I/O')))
            result = verify_dossier(data,sha256(data),self.pins,key)
        self.assertTrue(result['verified'])

    def test_offline_verification_after_original_store_sources_and_policy_removed(self):
        self.capture(); key = self.policy.key
        shutil.rmtree(self.store.root); shutil.rmtree(self.policy.root); self.log.unlink(); self.bundle_path.unlink()
        self.assertTrue(self.verify(audit_key=key)['verified'])

    def test_only_administrator_can_export_policy_wide_history(self):
        with self.assertRaisesRegex(Rejected,'credential_administrator_required'):
            self.capture(admin_key=self.tokens['ana'],evidence_bytes=b'invalid')
        self.assertFalse(self.output.exists())

    def test_incorrect_offline_key_rejected(self):
        self.capture()
        with self.assertRaisesRegex(Rejected,'review_audit_key_digest'):
            self.verify(audit_key=secrets.token_bytes(32))

    def test_external_digest_is_required_and_not_read_from_package(self):
        self.capture()
        with self.assertRaisesRegex(Rejected,'dossier_digest'):
            self.verify(digest='f'*64)

    def test_cross_tenant_asset_or_case_pins_rejected(self):
        self.capture()
        for changes in ({'tenant':'other'},{'asset':'other'},{'case_id':'f'*64}):
            with self.assertRaises(Rejected):
                self.verify(pins={**self.pins,**changes})

    def test_wrong_policy_case_and_source_pins_rejected(self):
        self.capture()
        for key in ('policy_digest','case_digest','config_digest','evidence_digest'):
            with self.assertRaises(Rejected):
                self.verify(pins={**self.pins,key:'f'*64})

    def test_stale_case_checkpoint_cannot_export_newer_review(self):
        self.apply('reopen',actor='boris')
        with self.assertRaisesRegex(Rejected,'dossier_case_checkpoint'):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_stale_credential_checkpoint_cannot_export_newer_policy_state(self):
        self.change()
        with self.assertRaisesRegex(Rejected,'dossier_credential_checkpoint'):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_unreviewed_checkpoint_not_accepted_as_finished_dossier(self):
        with self.assertRaisesRegex(Rejected,'dossier_review_required'):
            self.capture(pins={**self.pins,'case_checkpoint':ORIGIN})

    def test_truncated_review_chain_fails_external_checkpoint(self):
        self.capture(); value = json.loads(self.output.read_bytes()); value['review_rows'].pop()
        with self.assertRaisesRegex(Rejected,'dossier_case_checkpoint'):
            self.verify(value)

    def test_truncated_credentials_fail_external_checkpoint(self):
        self.change(); self.pins['credential_checkpoint'] = self.credential_head
        self.capture(); value = json.loads(self.output.read_bytes()); value['credential_rows'] = []
        with self.assertRaisesRegex(Rejected,'dossier_credential_checkpoint'):
            self.verify(value)

    def test_changed_review_payload_rejected_even_with_new_package_hash(self):
        self.capture(); value = json.loads(self.output.read_bytes()); value['review_rows'][0][1] = '{}'
        with self.assertRaisesRegex(Rejected,'review_history_integrity'):
            self.verify(value)

    def test_changed_credential_payload_rejected(self):
        self.change(); self.pins['credential_checkpoint'] = self.credential_head
        self.capture(); value = json.loads(self.output.read_bytes()); value['credential_rows'][0][1] = '{}'
        with self.assertRaisesRegex(Rejected,'credential_history_integrity'):
            self.verify(value)

    def test_source_record_change_rejected(self):
        self.capture(); value = json.loads(self.output.read_bytes()); value['evidence']['records'][0]['raw_base64'] = 'eA=='
        with self.assertRaisesRegex(Rejected,'evidence_bundle_digest'):
            self.verify(value)

    def test_different_valid_evidence_bundle_cannot_be_substituted(self):
        self.capture(); value = json.loads(self.output.read_bytes()); value['evidence']['captured_ns'] += 1
        changed = {**self.pins,'evidence_digest':sha256(canonical(value['evidence']))}
        with self.assertRaisesRegex(Rejected,'dossier_evidence_binding'):
            self.verify(value,pins=changed)

    def test_clock_snapshot_and_external_minimum_verified(self):
        self.with_deadline(); self.capture(); result = self.verify()
        self.assertGreaterEqual(result['facts']['clock']['observed_ns'],self.pins['minimum_clock_ns'])
        with self.assertRaisesRegex(Rejected,'dossier_clock_minimum'):
            self.verify(pins={**self.pins,'minimum_clock_ns':2**63-1})

    def test_configured_clock_cannot_be_omitted(self):
        self.with_deadline(); self.capture(); value = json.loads(self.output.read_bytes()); value['clock_row'] = None
        with self.assertRaisesRegex(Rejected,'credential_clock_missing'):
            self.verify(value)

    def test_clock_without_external_minimum_rejected(self):
        self.with_deadline(); self.capture()
        with self.assertRaisesRegex(Rejected,'dossier_clock_minimum'):
            self.verify(pins={**self.pins,'minimum_clock_ns':None})

    def test_invalid_unicode_clock_payload_returns_controlled_api_and_cli_rejection(self):
        self.with_deadline(); self.capture(); value = json.loads(self.output.read_bytes())
        value['clock_row'][0] = '\ud800'
        with self.assertRaisesRegex(Rejected,'credential_clock_size'):
            self.verify(value)
        data = canonical(value); self.output.write_bytes(data)
        pins_path = self.root/'pins.json'; pins_path.write_bytes(canonical(self.pins))
        tool = Path(__file__).resolve().parents[1]/'tools/review_dossier.py'
        result = subprocess.run([sys.executable,'-B',str(tool),'verify','--pins-file',str(pins_path),
             '--audit-key-file',str(self.policy.root/'audit.key'),'--dossier-file',str(self.output),
             '--dossier-digest',sha256(data)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'success':False,'reason':'credential_clock_size'})
        self.assertEqual(result.stderr,'')

    def test_clock_minimum_cannot_be_claimed_for_unconfigured_clock(self):
        self.capture()
        with self.assertRaisesRegex(Rejected,'dossier_clock_unavailable'):
            self.verify(pins={**self.pins,'minimum_clock_ns':0})

    def test_capture_time_before_records_rejected(self):
        self.capture(); value = json.loads(self.output.read_bytes()); value['captured_ns'] = 0
        with self.assertRaisesRegex(Rejected,'dossier_capture_time'):
            self.verify(value)

    def test_export_does_not_require_expired_reviewer_to_reauthenticate(self):
        self.change('set_expiry',expires_at_ns=1)
        self.pins['credential_checkpoint'] = self.credential_head
        self.pins['minimum_clock_ns'] = self.lifecycle.status(self.policy.key)['clock']['observed_ns']
        self.capture(); report = self.verify()
        self.assertEqual(report['facts']['review']['stage'],'closed')
        self.assertFalse(report['limits']['current_authorization_checked'])

    def test_current_changes_after_snapshot_do_not_change_historical_verification(self):
        self.capture(); data = self.output.read_bytes(); self.change()
        self.assertTrue(self.verify()['verified'])
        with self.assertRaisesRegex(Rejected,'dossier_credential_checkpoint'):
            verify_dossier(data,sha256(data),{**self.pins,'credential_checkpoint':self.credential_head},self.policy.key)

    def test_policy_change_or_live_history_corruption_prevents_export(self):
        with self.store.transaction() as db:
            db.execute("UPDATE case_reviews SET payload='{}' WHERE revision=2")
        with self.assertRaisesRegex(Rejected,'review_history_integrity'):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_public_output_directory_rejected(self):
        directory = self.root/'public'; directory.mkdir(mode=0o755)
        with self.assertRaisesRegex(Rejected,'dossier_output_directory_permissions'):
            self.capture(output=directory/'dossier.json')
        self.assertFalse((directory/'dossier.json').exists())

    def test_existing_file_never_overwritten(self):
        self.output.write_bytes(b'existing')
        with self.assertRaisesRegex(Rejected,'existing_file_differs'):
            self.capture()
        self.assertEqual(self.output.read_bytes(),b'existing')

    def test_output_symlink_never_followed(self):
        target = self.root/'target'; target.write_bytes(b'original'); self.output.symlink_to(target)
        with self.assertRaises(Rejected):
            self.capture()
        self.assertEqual(target.read_bytes(),b'original')

    def test_publication_failure_does_not_change_case_or_credential_head(self):
        before = self.view()['checkpoint']
        with patch('nqc_defense.review_dossier.publish_local',side_effect=OSError('injected')):
            with self.assertRaises(OSError):
                self.capture()
        self.assertEqual(self.view()['checkpoint'],before)
        self.assertEqual(self.lifecycle.status(self.policy.key)['checkpoint'],self.credential_head)

    def test_readback_failure_is_not_reported_as_published(self):
        with patch('nqc_defense.review_dossier.read_local',return_value=b'changed'):
            with self.assertRaisesRegex(Rejected,'dossier_publication_changed'):
                self.capture()

    def test_unknown_fields_noncanonical_json_and_bad_shapes_rejected(self):
        self.capture(); original = json.loads(self.output.read_bytes())
        for value in ({**original,'extra':True},{**original,'review_rows':{}},{**original,'credential_rows':[[]]}):
            with self.assertRaises(Rejected):
                self.verify(value)
        data = json.dumps(original,indent=2).encode()
        with self.assertRaisesRegex(Rejected,'dossier_schema'):
            self.verify(data=data,digest=sha256(data))

    def test_boolean_revision_and_invalid_unicode_payload_are_rejected(self):
        self.capture(); value = json.loads(self.output.read_bytes())
        value['review_rows'][0][0] = True
        with self.assertRaisesRegex(Rejected,'integer_range'):
            self.verify(value)
        value = json.loads(self.output.read_bytes()); value['review_rows'][0][1] = 'bad\ud800'
        with self.assertRaisesRegex(Rejected,'dossier_row_payload'):
            self.verify(value)

    def test_size_and_history_budgets_reject_without_partial_report(self):
        self.capture(); data = self.output.read_bytes()
        with patch('nqc_defense.review_dossier.MAX_DOSSIER',len(data)-1):
            with self.assertRaisesRegex(Rejected,'dossier_size'):
                self.verify()
        with patch('nqc_defense.review_dossier.MAX_HISTORY_BYTES',1):
            with self.assertRaisesRegex(Rejected,'dossier_history_budget'):
                self.verify()
        with patch('nqc_defense.review_dossier.MAX_CASE_REVISIONS',1):
            with self.assertRaisesRegex(Rejected,'dossier_row_count'):
                self.verify()

    def test_generated_keys_and_tokens_not_added_to_dossier(self):
        self.capture(); data = self.output.read_bytes()
        for secret in (self.policy.key,*self.tokens.values()):
            self.assertNotIn(secret.hex().encode(),data)
        self.assertTrue(self.verify()['limits']['source_records_and_notes_require_private_handling'])

    def test_legacy_review_v1_can_be_exported_without_rewriting_rows(self):
        with self.store.transaction() as db:
            rows = db.execute('SELECT revision,payload FROM case_reviews ORDER BY revision').fetchall()
            previous = ORIGIN['head']
            for revision,payload in rows:
                event = json.loads(payload); event.pop('credential_checkpoint'); event['schema'] = 'nqc-case-review-v1'
                payload = canonical(event).decode(); head = mac(self.policy.key,revision,previous,payload)
                db.execute('UPDATE case_reviews SET payload=?,previous=?,mac=? WHERE revision=?',(payload,previous,head,revision))
                previous = head
        self.pins['case_checkpoint'] = {'revision':4,'head':previous}
        self.capture(); report = self.verify()
        self.assertTrue(all(row['credential_checkpoint'] is None for row in report['timeline']))

    def test_cli_capture_and_offline_report_after_original_sources_removed(self):
        tool = Path(__file__).resolve().parents[1]/'tools/review_dossier.py'
        pins_path = self.root/'pins.json'; pins_path.write_bytes(canonical(self.pins))
        detached_key = self.root/'offline.key'; detached_key.write_bytes(self.policy.key); os.chmod(detached_key,0o600)
        result = subprocess.run([sys.executable,'-B',str(tool),'capture','--pins-file',str(pins_path),'--audit-key-file',str(detached_key),
             '--operations-root',str(self.store.root),'--policy-root',str(self.policy.root),'--policy-digest',self.policy.digest,
             '--evidence-file',str(self.bundle_path),'--output',str(self.output)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        receipt = json.loads(result.stdout)
        shutil.rmtree(self.store.root); shutil.rmtree(self.policy.root); self.log.unlink(); self.bundle_path.unlink()
        result = subprocess.run([sys.executable,'-B',str(tool),'verify','--pins-file',str(pins_path),'--audit-key-file',str(detached_key),
             '--dossier-file',str(self.output),'--dossier-digest',receipt['dossier_digest']],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['assessment']['classification'],'analyst_claim')


if __name__ == '__main__':
    unittest.main()
