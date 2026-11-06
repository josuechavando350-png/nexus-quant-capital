from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import FrozenInstanceError
import copy
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_case_triage import fixture
from nqc_defense.case_triage import (MAX_INPUT_BYTES, MAX_ITEMS, MAX_POLICY, MAX_REPORT, TriagePolicy,
    load_selection, prepare_items, publish_output, rank_dossiers, verify_output)
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import DOMAIN, MAX_ATTESTATION, backend, public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import EMPTY, RegistryMirror
from nqc_defense.review_dossier import MAX_DOSSIER
from nqc_defense.signer_registry import VerifiedRegistry


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.f = fixture(self.root)
        self.mirror = self.f['mirror']; self.receipt = self.f['mirror_receipt']; self.items = self.f['items']
        self.policy = self.f['triage_policy']; self.head = self.f['registry_head']; self.counter = 0

    def rank(self, items=None, policy=None, receipt=None):
        return self.mirror.triage(self.receipt if receipt is None else receipt,
            self.policy if policy is None else policy,self.items if items is None else items)

    def policy_for(self, **changes):
        value = {**copy.deepcopy(self.f['config']),**changes}; data = canonical(value)
        return TriagePolicy(data,sha256(data))

    def sync(self):
        bundle = self.f['registry'].export(self.head)
        self.receipt = self.mirror.accept(bundle,sha256(bundle),self.head,self.receipt)['receipt']

    def revoke(self, sync=True):
        self.head = self.f['registry'].change(self.f['authority'],'revoke',self.f['key_pin'],'revoke',
            'Fixture revoke',self.head)['receipt']
        if sync: self.sync()

    def variant(self, report_change=None, dossier_change=None):
        """Sign deliberately inconsistent issuer fixtures to test consumer trust boundaries."""
        original = self.items[0]; value = json.loads(original['attestation']); dossier = json.loads(original['dossier'])
        if dossier_change: dossier_change(dossier)
        dossier = canonical(dossier); digest = sha256(dossier)
        value['statement']['dossier_digest'] = digest; value['statement']['report']['dossier_digest'] = digest
        if report_change: report_change(value['statement']['report'])
        private,_,_,_ = backend()
        value['signature_hex'] = private.from_private_bytes(self.f['signing_key']).sign(DOMAIN+canonical(value['statement'])).hex()
        data = canonical(value); self.counter += 1
        registered = self.f['registry'].record(self.f['authority'],data,sha256(data),dossier,digest,original['pins'],
            self.f['key_pin'],f'variant_{self.counter}','Explicit issuer discrepancy fixture',self.head)['receipt']
        self.head = registered; self.sync()
        return {**original,'dossier':dossier,'dossier_digest':digest,'attestation':data,'attestation_digest':sha256(data),
                'registration_receipt':registered}

    def test_pipeline_produces_explained_priority(self):
        report = self.rank(); rows = report['queue_report']['queue']
        self.assertEqual([r['score'] for r in rows],[43,25,13,0])
        for row in rows:
            self.assertEqual(sum(c['points'] for c in row['contributions']),row['score'])
            self.assertEqual(row['references']['pins']['case_id'],row['case_id'])

    def test_criticality_changes_urgency_without_hiding_evidence(self):
        before = self.rank()['queue_report']['queue']
        after = self.rank(policy=self.policy_for(asset_criticality=5,revision=2))['queue_report']['queue']
        self.assertEqual([r['score'] for r in after],[83,65,53,0])
        self.assertEqual(after[0]['urgency'],'urgent')
        self.assertEqual([r['references'] for r in before],[r['references'] for r in after])

    def test_closed_case_remains_visible_and_does_not_become_an_automatic_response(self):
        report = self.rank()['queue_report']; row = report['queue'][-1]
        self.assertEqual(row['review_stage'],'closed'); self.assertEqual(row['urgency'],'closed')
        self.assertEqual(report['selected_cases'],4); self.assertFalse(report['limits']['automatic_response'])

    def test_no_assessment_does_not_invent_a_verdict(self):
        row = next(r for r in self.rank()['queue_report']['queue'] if r['case_id']==self.items[-1]['pins']['case_id'])
        self.assertIsNone(row['analyst_verdict']); self.assertEqual(row['contributions'][2]['points'],0)

    def test_selection_order_does_not_change_report(self):
        self.assertEqual(self.rank(),self.rank(items=list(reversed(self.items))))

    def test_ties_use_case_identity_deterministically(self):
        weights = {**self.f['config']['weights'],'needs_response':0,'inconclusive':0}
        result = self.rank(policy=self.policy_for(weights=weights))['queue_report']['queue']
        ties = [r['case_id'] for r in result if r['score']==13]
        self.assertEqual(len(ties),2); self.assertEqual(ties,sorted(ties))

    def test_trigger_cap_is_explicit_and_preserves_full_record_count(self):
        weights = {**self.f['config']['weights'],'trigger_record_cap':2}
        rows = self.rank(policy=self.policy_for(weights=weights))['queue_report']['queue']
        self.assertEqual([r['score'] for r in rows],[42,22,12,0])
        self.assertEqual(next(r for r in rows if r['trigger_records']==5)['contributions'][1]['value'],5)

    def test_policy_requires_external_digest_and_canonical_bytes(self):
        data = canonical(self.f['config'])
        with self.assertRaisesRegex(Rejected,'triage_policy_digest'): TriagePolicy(data,'a'*64)
        with self.assertRaisesRegex(Rejected,'triage_policy_schema'): TriagePolicy(data+b' ',sha256(data+b' '))

    def test_policy_bounds_types_schema_and_band_order(self):
        variants = [{'asset_criticality':True},{'asset_criticality':0},{'asset_criticality':6},{'revision':0},
            {'weights':{**self.f['config']['weights'],'criticality':0}},
            {'weights':{**self.f['config']['weights'],'trigger_record_cap':101}},
            {'bands':{'normal':25,'high':25,'urgent':75}},{'schema':'other'},{'extra':True}]
        for change in variants:
            with self.subTest(change=change), self.assertRaises(Rejected): self.policy_for(**change)

    def test_policy_is_immutable_and_returns_copies(self):
        with self.assertRaises(FrozenInstanceError): self.policy.digest = 'a'*64
        value = self.policy.value; value['asset_criticality'] = 5; value['weights']['criticality'] = 999
        self.assertEqual(self.policy.value,self.f['config'])

    def test_policy_registry_authority_and_case_scope_are_enforced(self):
        for key in ('registry_digest','authority_digest'):
            with self.subTest(key=key), self.assertRaisesRegex(Rejected,'triage_registry_scope'):
                self.rank(policy=self.policy_for(**{key:'f'*64}))
        for key,value in (('tenant','other'),('asset','other'),('review_policy_digest','f'*64)):
            with self.subTest(key=key), self.assertRaisesRegex(Rejected,'triage_case_scope'):
                self.rank(policy=self.policy_for(**{key:value}))

    def test_batch_shape_and_duplicate_versions_are_rejected(self):
        for items in ([],tuple(self.items),self.items*17):
            with self.subTest(type=type(items)), self.assertRaisesRegex(Rejected,'triage_item_count'): self.rank(items=items)
        with self.assertRaisesRegex(Rejected,'triage_duplicate_case'): self.rank(items=[self.items[0],self.items[0]])

    def test_metadata_is_copied_before_use(self):
        original = copy.deepcopy(self.items); prepared = prepare_items(original)
        original[0]['pins']['case_checkpoint']['head'] = 'e'*64
        original[0]['registration_receipt']['head'] = 'e'*64
        self.assertEqual(prepared,self.items)

    def test_mutable_buffers_and_oversized_single_input_rejected(self):
        item = {**self.items[0],'dossier':bytearray(self.items[0]['dossier'])}
        with self.assertRaisesRegex(Rejected,'triage_item_bytes'): self.rank(items=[item])
        item['dossier'] = b'x'*(MAX_DOSSIER+1)
        with self.assertRaisesRegex(Rejected,'triage_item_bytes'): prepare_items([item])

    def test_actual_cumulative_byte_budget_is_checked_before_crypto(self):
        dossier = b'x'*MAX_DOSSIER; attestation = b'y'*MAX_ATTESTATION
        items = [{**item,'dossier':dossier,'attestation':attestation} for item in self.items[:2]]
        self.assertGreater(2*(len(dossier)+len(attestation)),MAX_INPUT_BYTES)
        with patch.object(VerifiedRegistry,'verify',side_effect=AssertionError('crypto before budget')):
            with self.assertRaisesRegex(Rejected,'triage_input_budget'): self.rank(items=items)

    def test_stale_receiver_reference_is_rejected(self):
        with self.assertRaisesRegex(Rejected,'mirror_receipt_mismatch'): self.rank(receipt=EMPTY)

    def test_empty_receiver_does_not_rank(self):
        mirror = RegistryMirror.create(self.root/'empty',self.f['registry'].digest,self.f['authority_pin'])
        with self.assertRaisesRegex(Rejected,'mirror_not_initialized'): mirror.triage(EMPTY,self.policy,self.items)

    def test_each_proof_is_reverified_and_no_partial_selection_is_returned(self):
        before = self.mirror.export(self.receipt)
        for field in ('attestation','dossier'):
            items = copy.deepcopy(self.items); items[-1][field] += b' '
            with self.subTest(field=field), self.assertRaises(Rejected): self.rank(items=items)
        self.assertEqual(self.mirror.export(self.receipt),before)

    def test_registration_and_pins_are_not_replaced_by_case_name(self):
        item = copy.deepcopy(self.items[0]); item['pins']['case_digest'] = 'a'*64
        with self.assertRaisesRegex(Rejected,'registry_record_binding'): self.rank(items=[item])
        item = copy.deepcopy(self.items[0]); item['registration_receipt'] = self.items[1]['registration_receipt']
        with self.assertRaisesRegex(Rejected,'registry_attestation_not_recorded'): self.rank(items=[item])

    def test_rotation_preserves_priority_of_previously_registered_dossiers(self):
        before = self.rank()['queue_report']['queue']; new_key = secrets.token_bytes(32)
        self.head = self.f['registry'].change(self.f['authority'],'rotate',self.f['key_pin'],'rotate','Fixture rotation',
            self.head,public_bytes(new_key))['receipt']; self.sync()
        self.assertEqual(self.rank()['queue_report']['queue'],before)

    def test_received_revocation_rejects_entire_batch(self):
        self.rank(); self.revoke()
        with self.assertRaisesRegex(Rejected,'registry_signer_revoked'): self.rank()

    def test_update_by_other_instance_invalidates_warm_view(self):
        self.rank(); self.revoke(sync=False); bundle = self.f['registry'].export(self.head)
        other = RegistryMirror(self.mirror.root,self.f['registry'].digest,self.f['authority_pin'])
        self.receipt = other.accept(bundle,sha256(bundle),self.head,self.receipt)['receipt']
        with self.assertRaisesRegex(Rejected,'registry_signer_revoked'): self.rank()

    def test_unreceived_revocation_remains_explicitly_a_local_historical_view(self):
        old = self.rank(); self.revoke(sync=False)
        self.assertEqual(self.rank(),old); self.assertFalse(old['queue_report']['limits']['independent_freshness'])

    def test_warm_receiver_still_rejects_storage_corruption(self):
        self.rank()
        with self.mirror.connection(write=True) as db:
            body = db.execute('SELECT bundle FROM snapshot').fetchone()[0]
            db.execute('UPDATE snapshot SET bundle=?',(body+b' ',))
        with self.assertRaises(Rejected): self.rank()

    def test_public_issuer_count_disagreement_is_rejected(self):
        item = self.variant(report_change=lambda r:r['facts']['trigger_records'].update(count=99))
        with self.assertRaisesRegex(Rejected,'triage_report_evidence_discrepancy'): self.rank(items=[item])

    def test_public_issuer_review_stage_disagreement_is_rejected(self):
        item = self.variant(report_change=lambda r:r['facts']['review'].update(stage='closed'))
        with self.assertRaisesRegex(Rejected,'triage_report_review_discrepancy'): self.rank(items=[item])

    def test_public_issuer_assessment_disagreement_is_rejected(self):
        item = self.variant(report_change=lambda r:r['assessment'].update(verdict='benign'))
        with self.assertRaisesRegex(Rejected,'triage_report_review_discrepancy'): self.rank(items=[item])

    def test_dossier_policy_must_match_review_policy_pin(self):
        item = self.variant(dossier_change=lambda d:d.update(policy={}))
        with self.assertRaisesRegex(Rejected,'triage_review_policy_binding'): self.rank(items=[item])

    def test_raw_review_change_cannot_hide_behind_old_report(self):
        def change(d):
            row = d['review_rows'][0]; event = json.loads(row[1]); event['reason'] = 'changed'; row[1] = canonical(event).decode()
        item = self.variant(dossier_change=change)
        with self.assertRaisesRegex(Rejected,'triage_report_review_discrepancy'): self.rank(items=[item])

    def test_consistent_trusted_issuer_claim_does_not_become_public_hmac_verification(self):
        def change(d):
            row = d['review_rows'][0]; event = json.loads(row[1]); event['reason'] = 'issuer claim'; row[1] = canonical(event).decode()
        item = self.variant(dossier_change=change,report_change=lambda r:r['timeline'][0].update(reason='issuer claim'))
        result = self.rank(items=[item])['queue_report']
        self.assertTrue(result['limits']['review_authorization_is_issuer_assertion'])
        self.assertFalse(result['limits']['hmac_review_history_replayed_by_this_verifier'])

    def test_review_time_and_actions_are_checked_before_scoring(self):
        for field,value in (('recorded_ns',0),('action','unknown')):
            def change(d):
                row = d['review_rows'][-1]; event = json.loads(row[1]); event[field] = value; row[1] = canonical(event).decode()
            item = self.variant(dossier_change=change)
            with self.subTest(field=field), self.assertRaises(Rejected): self.rank(items=[item])

    def test_returned_report_cannot_mutate_policy_or_next_report(self):
        before = self.rank(); value = copy.deepcopy(before)
        value['queue_report']['triage_policy']['weights']['criticality'] = 999
        value['queue_report']['queue'][0]['references']['pins']['case_checkpoint']['head'] = 'e'*64
        self.assertEqual(self.rank(),before)

    def test_pure_ranking_does_not_open_embedded_paths_database_network_or_clock(self):
        bundle = self.f['registry'].export(self.head)
        registry = VerifiedRegistry.from_bundle(bundle,sha256(bundle),self.f['registry'].digest,self.f['authority_pin'],self.head)
        expected = rank_dossiers(registry,self.policy,self.items)
        with (patch('builtins.open',side_effect=AssertionError('file access')),
              patch('sqlite3.connect',side_effect=AssertionError('database access')),
              patch('time.time_ns',side_effect=AssertionError('clock access')),
              patch('socket.create_connection',side_effect=AssertionError('network access'))):
            self.assertEqual(rank_dossiers(registry,self.policy,self.items),expected)

    def test_ranking_requires_verified_registry_and_pinned_policy(self):
        with self.assertRaisesRegex(Rejected,'triage_verified_inputs_required'): rank_dossiers({},self.policy,self.items)
        with self.assertRaisesRegex(Rejected,'triage_verified_inputs_required'): self.rank(policy=self.f['config'])

    def test_selection_loader_checks_canonical_digest_and_exact_metadata(self):
        data = canonical(self.f['selection']); self.assertEqual(load_selection(self.root,data,sha256(data)),self.items)
        with self.assertRaisesRegex(Rejected,'triage_selection_digest'): load_selection(self.root,data,'a'*64)
        with self.assertRaisesRegex(Rejected,'triage_selection_schema'): load_selection(self.root,data+b' ',sha256(data+b' '))

    def test_selection_cannot_escape_root_or_follow_a_symlink(self):
        selection = copy.deepcopy(self.f['selection']); selection['items'][0]['dossier_file'] = '../outside'
        data = canonical(selection)
        with self.assertRaisesRegex(Rejected,'unsafe_path'): load_selection(self.root,data,sha256(data))
        (self.root/'link.json').symlink_to(self.root/'dossier_0.json'); selection['items'][0]['dossier_file'] = 'link.json'
        data = canonical(selection)
        with self.assertRaisesRegex(Rejected,'file_unavailable'): load_selection(self.root,data,sha256(data))

    def test_output_can_be_recomputed_and_alteration_rejected(self):
        report = self.rank(); data = canonical(report); verified = verify_output(data,sha256(data),self.rank())
        self.assertTrue(verified['verified'])
        changed = copy.deepcopy(report); changed['queue_report']['queue'][0]['score'] += 1; body = canonical(changed)
        with self.assertRaisesRegex(Rejected,'triage_report_digest'): verify_output(body,sha256(data),report)
        with self.assertRaisesRegex(Rejected,'triage_report_discrepancy'): verify_output(body,sha256(body),report)

    def test_publication_retries_identically_and_never_replaces_content(self):
        report = self.rank(); output = self.root/'queue.json'; first = publish_output(output,report)
        self.assertEqual(publish_output(output,report),first); self.assertEqual(output.stat().st_mode & 0o777,0o600)
        with self.assertRaises(Rejected):
            publish_output(output,self.rank(policy=self.policy_for(asset_criticality=5)))
        self.assertEqual(output.read_bytes(),canonical(report))

    def test_concurrent_identical_publications_preserve_one_result(self):
        report = self.rank(); output = self.root/'queue.json'
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _:publish_output(output,report),range(2)))
        self.assertEqual(results[0],results[1]); self.assertEqual(output.read_bytes(),canonical(report))

    def test_concurrent_rankings_are_identical(self):
        expected = self.rank()
        with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(lambda _:self.rank(),range(8)))
        self.assertTrue(all(r==expected for r in results))

    def test_batch_uses_one_registry_view_while_revocation_waits(self):
        old_receipt = copy.deepcopy(self.receipt); self.revoke(sync=False); bundle = self.f['registry'].export(self.head)
        other = RegistryMirror(self.mirror.root,self.f['registry'].digest,self.f['authority_pin'])
        entered = threading.Event(); release = threading.Event(); original = VerifiedRegistry.verify
        def pause(instance,*args,**kwargs):
            if not entered.is_set():
                entered.set()
                if not release.wait(10): raise AssertionError('test release timeout')
            return original(instance,*args,**kwargs)
        with patch.object(VerifiedRegistry,'verify',new=pause), ThreadPoolExecutor(max_workers=2) as pool:
            ranking = pool.submit(self.rank); self.assertTrue(entered.wait(5))
            receiving = pool.submit(other.accept,bundle,sha256(bundle),self.head,old_receipt)
            try:
                with self.assertRaises(TimeoutError): receiving.result(timeout=0.1)
            finally: release.set()
            ranked = ranking.result(timeout=10); self.receipt = receiving.result(timeout=10)['receipt']
        self.assertEqual(ranked['mirror_receipt'],old_receipt); self.assertEqual(ranked['queue_report']['selected_cases'],4)
        with self.assertRaisesRegex(Rejected,'registry_signer_revoked'): self.rank()

    def test_cli_rank_then_verify_and_reject_changed_report(self):
        policy = canonical(self.f['config']); selection = canonical(self.f['selection'])
        for name,data in (('triage.json',policy),('selection.json',selection),('expected.json',canonical(self.receipt))):
            (self.root/name).write_bytes(data)
        shared = ['--mirror-root',str(self.mirror.root),'--registry-digest',self.f['registry'].digest,
            '--authority-public-digest',self.f['authority_pin'],'--expected-file',str(self.root/'expected.json'),
            '--policy-file',str(self.root/'triage.json'),'--policy-digest',sha256(policy),'--input-root',str(self.root),
            '--selection-file',str(self.root/'selection.json'),'--selection-digest',sha256(selection)]
        command = [sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'tools/case_triage.py')]
        output = self.root/'queue.json'
        p = subprocess.run(command+['rank']+shared+['--output',str(output)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr); result = json.loads(p.stdout)
        p = subprocess.run(command+['verify']+shared+['--report-file',str(output),'--report-digest',result['report_digest']],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr); self.assertTrue(json.loads(p.stdout)['verified'])
        output.write_bytes(output.read_bytes()+b' ')
        p = subprocess.run(command+['verify']+shared+['--report-file',str(output),'--report-digest',result['report_digest']],capture_output=True,text=True)
        self.assertEqual(p.returncode,2); self.assertNotIn('Traceback',p.stderr)

    def test_output_has_references_without_raw_log_or_reviewer_notes(self):
        body = canonical(self.rank())
        self.assertNotIn(b'Failed password',body); self.assertNotIn(b'Authored triage evaluation',body)
        self.assertNotIn(self.f['policy'].key.hex().encode(),body)

    def test_selection_is_explicitly_incomplete_for_the_whole_asset(self):
        result = self.rank(items=self.items[:1])['queue_report']
        self.assertEqual(result['selected_cases'],1); self.assertTrue(result['limits']['selected_cases_only'])

    def test_actual_maximum_batch_of_64_distinct_cases(self):
        root = self.root/'capacity'; root.mkdir(mode=0o700)
        f = fixture(root,[(2,None,False)]*MAX_ITEMS)
        report = f['mirror'].triage(f['mirror_receipt'],f['triage_policy'],f['items'])
        self.assertEqual(report['queue_report']['selected_cases'],64)
        self.assertEqual(len({r['case_id'] for r in report['queue_report']['queue']}),64)
        self.assertLess(len(canonical(report)),MAX_REPORT)


if __name__ == '__main__':
    unittest.main()
