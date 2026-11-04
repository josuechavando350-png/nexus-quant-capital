"""Offline policies using synthetic examples; no real registrations or targets."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import program_registry as reg
from superhunter.safe_io import canonical, strict_json

AT='2026-11-04T12:00:00Z'


class ProgramRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.evidence=self.root/'evidence';self.evidence.mkdir()
        self.cat,self.req,self.docs=reg.example_catalog()
        self.p=self.cat['programs'][0];self.q=self.req['requests'][0]
        self.out=self.root/'bundle'

    def bind(self):
        # Fixture-only explicit review, not a production auto-approval workflow.
        self.p['review']['normalized_sha256']=reg.policy_digest(self.p)
        self.q['expected_policy_sha256']=reg.policy_digest(self.p)

    def result(self,at=AT):return reg.evaluate(self.cat,self.req,self.docs,at)
    def first(self,at=AT):return self.result(at)['decisions'][0]
    def blocked(self,reason):
        r=self.first();self.assertEqual(r['status'],'BLOCKED');self.assertIn(reason,r['reasons'])
        self.assertFalse(r['execution_authorized']);self.assertFalse(r['action_executed'])

    def create(self,at=AT):
        for name,data in self.docs.items():(self.evidence/name).write_bytes(data)
        (self.root/'catalog.json').write_bytes(canonical(self.cat));(self.root/'requests.json').write_bytes(canonical(self.req))
        return reg.create(self.root/'catalog.json',self.root/'requests.json',self.evidence,self.out,at=at)

    def reseal(self,name,fn):
        obj=strict_json((self.out/name).read_bytes());fn(obj)
        raw=canonical(obj);(self.out/name).write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=reg.digest(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_eight_platforms_separate_program_namespaces(self):
        r=self.result();self.assertEqual(r['program_count'],8)
        self.assertEqual(r['decision_counts'],{'LOCAL_REVIEW_ELIGIBLE':8})
        self.assertEqual(len({d['program_key'] for d in r['decisions']}),8)
        self.assertEqual(r['accounts_connected'],0);self.assertEqual(r['actions_executed'],0)
        self.assertFalse(r['live_scope_verified']);self.assertFalse(r['automatic_submission'])

    def test_twenty_independent_programs(self):
        template=deepcopy(self.p)
        for i in range(12):
            p=deepcopy(template);p['program_id']=f'additional-{i}';p['review']['normalized_sha256']=reg.policy_digest(p)
            self.cat['programs'].append(p)
            q=deepcopy(self.q);q.update(id=f'additional-{i}',program_id=p['program_id'],expected_policy_sha256=reg.policy_digest(p))
            self.req['requests'].append(q)
        r=self.result();self.assertEqual(r['program_count'],20)
        self.assertEqual(r['decision_counts'],{'LOCAL_REVIEW_ELIGIBLE':20})

    def test_unknown_program_does_not_borrow_another_scope(self):
        self.q['program_id']='unregistered';self.blocked('UNKNOWN_PROGRAM')

    def test_cross_platform_digest_rejected(self):
        self.q['expected_policy_sha256']=reg.policy_digest(self.cat['programs'][1]);self.blocked('POLICY_CHANGED')

    def test_same_platform_duplicate_program_rejected(self):
        self.cat['programs'].append(deepcopy(self.p))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_PROGRAM'):self.result()

    def test_exclusion_overrides_inclusion(self):
        r=deepcopy(self.p['scope'][0]);r['effect']='exclude';self.p['scope'].append(r);self.bind()
        self.blocked('EXCLUDED_ASSET')

    def test_unknown_asset_blocked(self):
        self.q['asset']['identifier']='local/other';self.blocked('ASSET_NOT_EXPLICITLY_INCLUDED')

    def test_changed_commit_is_not_same_asset(self):
        self.q['asset']['revision']='2'*40;self.blocked('ASSET_NOT_EXPLICITLY_INCLUDED')

    def test_domain_suffix_does_not_match(self):
        a={'type':'domain','identifier':'app.example.invalid','revision':None,'chain_id':None}
        self.p['scope'][0]['asset']=a;self.q['asset']={**a,'identifier':'app.example.invalid.other.invalid'};self.bind()
        self.blocked('ASSET_NOT_EXPLICITLY_INCLUDED')

    def test_wildcard_is_not_implicitly_expanded(self):
        self.q['asset']={'type':'domain','identifier':'*.example.invalid','revision':None,'chain_id':None}
        with self.assertRaisesRegex(ValueError,'EXACT_DOMAIN_REQUIRED'):self.result()

    def test_contract_chain_binding(self):
        a={'type':'contract','identifier':'0x'+'a'*40,'revision':'0x'+'c'*64,'chain_id':1}
        self.p['scope'][0]['asset']=a;self.q['asset']={**a,'chain_id':8453};self.bind()
        self.blocked('ASSET_NOT_EXPLICITLY_INCLUDED')

    def test_contract_address_case_normalized(self):
        a={'type':'contract','identifier':'0x'+'a'*40,'revision':'0x'+'c'*64,'chain_id':1}
        self.p['scope'][0]['asset']=a;self.q['asset']={**a,'identifier':'0x'+'A'*40};self.bind()
        self.assertEqual(self.first()['status'],'LOCAL_REVIEW_ELIGIBLE')

    def test_contract_boolean_chain_rejected(self):
        self.q['asset']={'type':'contract','identifier':'0x'+'a'*40,'revision':'0x'+'c'*64,'chain_id':True}
        with self.assertRaises(ValueError):self.result()

    def test_expiry_at_boundary_blocks(self):
        r=self.first('2026-11-05T00:00:00Z');self.assertEqual(r['status'],'BLOCKED');self.assertIn('POLICY_REVIEW_EXPIRED',r['reasons'])

    def test_review_from_future_blocked(self):
        self.p['review']['at']='2026-11-04T14:00:00Z';self.blocked('REVIEW_TIME_INVALID')

    def test_snapshot_from_future_blocked(self):
        self.p['policy']['retrieved_at']='2026-11-04T13:00:00Z';self.bind();self.blocked('POLICY_FROM_FUTURE')

    def test_review_cannot_predate_snapshot(self):
        self.p['review']['at']='2026-11-03T00:00:00Z';self.blocked('REVIEW_TIME_INVALID')

    def test_pending_review_is_not_eligible(self):
        self.p['review']={'state':'pending','reviewer':None,'at':None,'normalized_sha256':None}
        r=self.first();self.assertEqual(r['status'],'REVIEW_REQUIRED');self.assertIn('HUMAN_REVIEW_REQUIRED',r['reasons'])

    def test_rejected_review_blocks(self):
        self.p['review']['state']='rejected';self.blocked('REVIEW_REJECTED')

    def test_normalized_change_invalidates_review(self):
        self.p['local_actions'].remove('draft_report');self.q['expected_policy_sha256']=reg.policy_digest(self.p)
        self.blocked('REVIEW_NOT_BOUND_TO_POLICY')

    def test_policy_content_change_needs_review(self):
        file=self.p['policy']['file'];self.docs[file]+=b' revised';self.p['policy']['sha256']=reg.digest(self.docs[file])
        self.q['expected_policy_sha256']=reg.policy_digest(self.p);self.blocked('REVIEW_NOT_BOUND_TO_POLICY')

    def test_tampered_snapshot_not_accepted(self):
        self.docs[self.p['policy']['file']]+=b' altered'
        with self.assertRaisesRegex(ValueError,'POLICY_HASH_MISMATCH'):self.result()

    def test_paused_program_blocks(self):
        self.p['status']='paused';self.bind();self.blocked('PROGRAM_NOT_ACTIVE')

    def test_contest_deadline_blocks_at_boundary(self):
        self.p['mode']='contest';self.p['window']['ends_at']=AT;self.bind();self.blocked('WINDOW_ENDED')

    def test_contest_requires_deadline(self):
        self.p['mode']='contest'
        with self.assertRaisesRegex(ValueError,'CONTEST_DEADLINE_REQUIRED'):self.result()

    def test_program_not_started_blocks(self):
        self.p['window']['starts_at']='2026-11-04T13:00:00Z';self.bind();self.blocked('WINDOW_NOT_STARTED')

    def test_private_invitation_required(self):
        self.p['visibility']='private';self.bind()
        r=self.first();self.assertEqual(r['status'],'REVIEW_REQUIRED');self.assertIn('PRIVATE_INVITATION_NOT_REVIEWED',r['reasons'])

    def test_enrolment_not_assumed(self):
        self.p['participation']['enrolled']=False;self.bind()
        self.assertEqual(self.first()['status'],'REVIEW_REQUIRED')

    def test_automation_unknown_requires_review(self):
        self.p['local_automation']='unknown';self.bind();self.assertEqual(self.first()['status'],'REVIEW_REQUIRED')

    def test_automation_denied_blocks(self):
        self.p['local_automation']='denied';self.bind();self.blocked('AUTOMATION_DENIED')

    def test_live_scan_and_submission_are_never_enabled(self):
        for action in ('scan','submit_report','exploit','broadcast','deploy','fetch_live'):
            with self.subTest(action=action):
                self.q['action']=action;self.blocked('ACTIVE_OR_UNSUPPORTED_ACTION')

    def test_even_approved_external_ai_is_not_sent(self):
        self.p['external_ai']='allowed';self.q['uses_external_ai']=True;self.bind()
        self.blocked('EXTERNAL_AI_TRANSMISSION_NOT_IMPLEMENTED')

    def test_declared_bounty_is_not_a_reward_guarantee(self):
        self.p['scope'][0]['bounty_eligible']=True;self.bind()
        r=self.first();self.assertTrue(r['bounty_eligible_declared']);self.assertFalse(r['reward_guaranteed'])

    def test_unpaid_assets_can_be_reviewed_without_false_reward(self):
        self.p['scope'][0]['bounty_eligible']=False;self.bind()
        r=self.first();self.assertFalse(r['bounty_eligible_declared']);self.assertEqual(r['status'],'LOCAL_REVIEW_ELIGIBLE')

    def test_timezones_same_instant_same_result(self):
        self.assertEqual(self.result(AT),self.result('2026-11-04T06:00:00-06:00'))

    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(ValueError,'TIMEZONE_REQUIRED'):self.result('2026-11-04T12:00:00')

    def test_maximum_review_window_bounded(self):
        self.p['policy']['review_until']='2027-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'POLICY_REVIEW_WINDOW'):self.result()

    def test_boolean_schema_not_integer(self):
        self.cat['schema_version']=True
        with self.assertRaises(ValueError):self.result()

    def test_cross_platform_url_rejected(self):
        self.p['program_url']='https://hackerone.com/demo'
        with self.assertRaisesRegex(ValueError,'PLATFORM_URL_MISMATCH'):self.result()

    def test_urls_do_not_accept_credentials_or_ambiguous_hosts(self):
        for url in ('https://secret@immunefi.com/x','https://immunefi.com.other.invalid/x',
                    'https://immunefi.com/x?token=secret','http://immunefi.com/x','https://immunefi.com/a/../b'):
            with self.subTest(url=url),self.assertRaises(ValueError):
                self.p['program_url']=url;self.result()

    def test_duplicate_request_rejected(self):
        self.req['requests'].append(deepcopy(self.q))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_REQUEST'):self.result()

    def test_policy_path_traversal_rejected(self):
        self.p['policy']['file']='../private.txt'
        with self.assertRaisesRegex(ValueError,'POLICY_PATH'):self.result()

    def test_policy_symlink_rejected(self):
        self.create();path=self.evidence/self.p['policy']['file'];raw=path.read_bytes();path.unlink()
        dest=self.root/'private.txt';dest.write_bytes(raw);path.symlink_to(dest)
        with self.assertRaises((ValueError,OSError)):reg.capture_documents(self.cat,self.evidence)

    def test_limits_do_not_silently_truncate(self):
        with patch.object(reg,'MAX_PROGRAMS',2),self.assertRaisesRegex(ValueError,'PROGRAM_LIMIT'):self.result()

    def test_empty_registry_is_not_fake_onboarding(self):
        r=reg.evaluate({'schema_version':1,'programs':[]},{'schema_version':1,'requests':[]},{},AT)
        self.assertEqual(r['program_count'],0);self.assertEqual(r['decisions'],[])

    def test_inputs_never_mutated(self):
        before=deepcopy((self.cat,self.req,self.docs));self.result();self.assertEqual(before,(self.cat,self.req,self.docs))

    def test_no_network_process_or_tool_execution(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('subprocess.run',side_effect=AssertionError('process')):
            self.create();reg.verify(self.out,at=AT)

    def test_native_diablo_audit_is_called(self):
        native=reg.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as call:
            self.create()
        self.assertEqual(call.call_count,10)

    def test_self_contained_replay_preserves_inputs(self):
        r=self.create();original=(self.out/'catalog.json').read_bytes()
        import shutil;shutil.rmtree(self.evidence)
        v=reg.verify(self.out,at=AT);self.assertEqual(v['historical'],r);self.assertEqual(v['current'],r)
        self.assertEqual(original,canonical(self.cat))

    def test_historical_success_can_be_currently_expired(self):
        self.create();v=reg.verify(self.out,at='2026-11-05T00:00:00Z')
        self.assertEqual(v['historical']['decision_counts'],{'LOCAL_REVIEW_ELIGIBLE':8})
        self.assertEqual(v['current']['decision_counts'],{'BLOCKED':8})

    def test_default_verifier_rechecks_current_time(self):
        self.create()
        with patch.object(reg,'now_text',return_value='2026-11-05T01:00:00Z'):
            self.assertEqual(reg.verify(self.out)['current']['decision_counts'],{'BLOCKED':8})

    def test_resealed_false_permission_rejected(self):
        self.create();self.reseal('decision.json',lambda x:x['decisions'][0].update(execution_authorized=True))
        with self.assertRaisesRegex(ValueError,'RECOMPUTED_RESULT_MISMATCH'):reg.verify(self.out,at=AT)

    def test_resealed_audit_event_rejected(self):
        self.create();self.reseal('audit.json',lambda x:x['entries'][1]['data'].update(decision_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'AUDIT_EVENT_MISMATCH'):reg.verify(self.out,at=AT)

    def test_missing_completion_never_passes(self):
        self.create();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):reg.verify(self.out,at=AT)

    def test_private_permissions_and_summary_no_private_names(self):
        self.p['program_id']='secret-project-name';self.q['program_id']=self.p['program_id'];self.bind();self.create()
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertNotIn('secret-project-name',(self.out/'REVIEW.md').read_text())

    def test_existing_result_never_overwritten(self):
        self.create();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_extra_file_is_not_hidden_in_bundle(self):
        self.create();(self.out/'extra.txt').write_text('hidden')
        with self.assertRaisesRegex(ValueError,'BUNDLE_FILE_SET'):reg.verify(self.out,at=AT)

    def test_cli_and_entrypoint_use_real_files(self):
        self.create()
        from superhunter import __main__
        with patch('sys.argv',['superhunter','verify-programs','--bundle',str(self.out),'--at',AT]),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(__main__.main(),0)
        self.assertEqual(json.loads(output.getvalue())['accounts_connected'],0)

    def test_cli_invalid_argument_never_echoes_value(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            reg.main(['verify-programs','--bundle',str(self.out),'--token','PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE',stream.getvalue())

    def test_cli_missing_input_is_not_success(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(reg.main(['verify-programs','--bundle',str(self.out)]),2)
        self.assertEqual(json.loads(output.getvalue())['status'],'PROGRAM_POLICY_ERROR')

    def test_cli_empty_registry_never_returns_eligible(self):
        self.cat={'schema_version':1,'programs':[]};self.req={'schema_version':1,'requests':[]};self.docs={};self.create()
        with redirect_stdout(io.StringIO()):self.assertEqual(reg.main(['verify-programs','--bundle',str(self.out),'--at',AT]),1)


if __name__=='__main__':unittest.main()
