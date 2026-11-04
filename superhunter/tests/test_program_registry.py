"""Offline policy fixtures; no enrollment, platform authorization or target traffic."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import program_registry as pr
from superhunter.safe_io import canonical, strict_json

NOW = datetime(2026,11,4,18,0,tzinfo=timezone.utc)


def example(platform='immunefi', number=1, now=NOW):
    """Explicit synthetic program, not a real platform snapshot."""
    doc=b'SYNTHETIC POLICY FIXTURE. Local code review only; no real authorization.'
    program={'platform':platform,'program_id':f'fixture-{number}',
             'scope_id':f'bounty-{platform}-fixture-{number}', 'kind':'bounty','status':'active',
             'participation':'accepted','visibility':'public',
             'window':{'starts_at':(now-timedelta(days=1)).isoformat(),'ends_at':(now+timedelta(days=1)).isoformat()},
             'document':{'file':f'policy-{number}.txt','sha256':hashlib.sha256(doc).hexdigest(),
                         'source_url':'https://example.invalid/policy','captured_at':(now-timedelta(minutes=5)).isoformat()},
             'rules':{'allowed_actions':list(pr.ACTIONS),'disclosure':'manual_private_review'},
             'assets':[{'kind':'repository','repo':'own/example','commit':'a'*40},
                       {'kind':'evm_contract','chain_id':1,'address':'0x'+'b'*40},
                       {'kind':'web_origin','origin':'https://app.example.invalid'}],
             'excluded':[], 'review':{'status':'approved','reviewer':'local-fixture-operator',
                   'reviewed_at':(now-timedelta(minutes=4)).isoformat(),
                   'expires_at':(now+timedelta(hours=2)).isoformat(),'revision_sha256':'0'*64}}
    program['review']['revision_sha256']=pr.revision(program)
    case={'id':f'case-{number}','program_key':pr.program_key(program),
          'action':'offline_evidence_review','asset':deepcopy(program['assets'][0])}
    return program,doc,case


class ProgramRegistryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        p,doc,c=example();self.p=p;self.case=c
        self.registry={'schema_version':1,'programs':[p]}
        self.requests={'schema_version':1,'cases':[c]};self.documents={p['document']['file']:doc}

    def sign(self):self.p['review']['revision_sha256']=pr.revision(self.p)
    def result(self,now=NOW):return pr.evaluate(self.registry,self.documents,self.requests,now=now)[0]
    def blocked(self,reason):
        d=self.result()['decisions'][0]
        self.assertEqual(d['status'],'BLOCKED');self.assertIn(reason,d['reasons'])
    def persist(self,now=NOW):
        (self.root/'registry.json').write_bytes(canonical(self.registry))
        (self.root/'requests.json').write_bytes(canonical(self.requests))
        docs=self.root/'docs';docs.mkdir(exist_ok=True)
        for n,b in self.documents.items():(docs/n).write_bytes(b)
        return pr.create(self.root/'registry.json',self.root/'requests.json',docs,self.root/'case',now=now)

    def test_eight_platforms_are_independent_namespaces(self):
        for name in pr.PLATFORMS:
            with self.subTest(platform=name):
                p,doc,c=example(name)
                r,_=pr.evaluate({'schema_version':1,'programs':[p]},{p['document']['file']:doc},
                               {'schema_version':1,'cases':[c]},now=NOW)
                self.assertEqual(r['counts'],{'ELIGIBLE_LOCAL_REVIEW':1})
                self.assertFalse(r['authorization_authenticated'])

    def test_positive_is_not_live_permission(self):
        r=self.result();self.assertEqual(r['decisions'][0]['status'],'ELIGIBLE_LOCAL_REVIEW')
        for flag in ('platform_accounts_connected','authorization_authenticated','network_used',
                     'tests_executed_on_targets','submission_enabled','vulnerability_confirmed'):
            self.assertIs(r[flag],False)
        self.assertFalse(r['decisions'][0]['live_testing_authorized'])

    def test_unknown_program_denied(self):
        self.case['program_key']='hackerone:not-enrolled';self.blocked('PROGRAM_NOT_REGISTERED')

    def test_same_slug_different_platform_cannot_borrow_scope(self):
        self.case['program_key']='hackerone:fixture-1';self.blocked('PROGRAM_NOT_REGISTERED')

    def test_missing_platform_rejected(self):
        self.p['platform']='unsupported'
        with self.assertRaises(pr.RegistryError):self.result()

    def test_paused_program_denied(self):
        self.p['status']='paused';self.sign();self.blocked('PROGRAM_NOT_ACTIVE')

    def test_ended_program_denied(self):
        self.p['status']='ended';self.sign();self.blocked('PROGRAM_NOT_ACTIVE')

    def test_private_program_without_participation_denied(self):
        self.p['visibility']='private';self.p['participation']='unknown';self.sign()
        self.blocked('PARTICIPATION_NOT_ACCEPTED')

    def test_participation_revoked_denied(self):
        self.p['participation']='revoked';self.sign();self.blocked('PARTICIPATION_NOT_ACCEPTED')

    def test_contest_end_is_exclusive(self):
        self.p['kind']='contest';self.p['window']['ends_at']=NOW.isoformat();self.sign()
        self.blocked('PROGRAM_WINDOW_CLOSED')

    def test_not_started_denied(self):
        self.p['window']['starts_at']=(NOW+timedelta(minutes=1)).isoformat();self.sign()
        self.blocked('PROGRAM_WINDOW_CLOSED')

    def test_expired_review_denied(self):
        self.p['review']['expires_at']=NOW.isoformat();self.blocked('REVIEW_EXPIRED_OR_FUTURE')

    def test_pending_review_denied(self):
        self.p['review']['status']='pending';self.blocked('HUMAN_REVIEW_NOT_APPROVED')

    def test_revoked_review_denied(self):
        self.p['review']['status']='revoked';self.blocked('HUMAN_REVIEW_NOT_APPROVED')

    def test_scope_change_invalidates_approval(self):
        self.p['assets'].append({'kind':'repository','repo':'own/new','commit':'a'*40})
        self.blocked('POLICY_CHANGED_SINCE_REVIEW')

    def test_rule_change_invalidates_approval(self):
        self.p['rules']['allowed_actions'].remove('offline_source_review')
        self.blocked('POLICY_CHANGED_SINCE_REVIEW')

    def test_document_bytes_change_blocks(self):
        self.documents[self.p['document']['file']]+=b' changed'
        self.blocked('POLICY_DOCUMENT_CHANGED')

    def test_stale_document_at_review_blocks(self):
        self.p['document']['captured_at']=(NOW-timedelta(days=8)).isoformat();self.sign()
        self.blocked('DOCUMENT_NOT_CURRENT_AT_REVIEW')

    def test_missing_document_is_error_not_empty_permission(self):
        self.documents={}
        with self.assertRaises(pr.RegistryError):self.result()

    def test_explicit_exclusion_overrides_inclusion(self):
        self.p['excluded']=[deepcopy(self.case['asset'])];self.sign();self.blocked('EXPLICITLY_EXCLUDED')

    def test_wrong_commit_denied(self):
        self.case['asset']['commit']='c'*40;self.blocked('ASSET_NOT_EXPLICITLY_LISTED')

    def test_evm_chain_must_match(self):
        self.case['asset']={**self.p['assets'][1],'chain_id':8453}
        self.blocked('ASSET_NOT_EXPLICITLY_LISTED')

    def test_evm_case_normalized_without_changing_scope(self):
        self.case['asset']={**self.p['assets'][1],'address':'0x'+'B'*40}
        self.assertEqual(self.result()['decisions'][0]['status'],'ELIGIBLE_LOCAL_REVIEW')

    def test_boolean_chain_id_rejected(self):
        self.case['asset']={**self.p['assets'][1],'chain_id':True}
        with self.assertRaises(pr.RegistryError):self.result()

    def test_host_suffix_trick_not_included(self):
        self.case['asset']={'kind':'web_origin','origin':'https://app.example.invalid.evil.invalid'}
        self.blocked('ASSET_NOT_EXPLICITLY_LISTED')

    def test_host_wildcard_not_implicitly_expanded(self):
        self.case['asset']={'kind':'web_origin','origin':'https://*.example.invalid'}
        with self.assertRaises(pr.RegistryError):self.result()

    def test_credentials_in_origin_rejected(self):
        self.case['asset']={'kind':'web_origin','origin':'https://secret@app.example.invalid'}
        with self.assertRaises(pr.RegistryError):self.result()

    def test_action_not_declared_denied(self):
        self.p['rules']['allowed_actions']=[];self.sign();self.blocked('ACTION_NOT_DECLARED')

    def test_live_execution_and_submission_never_admitted(self):
        for a in ('network_scan','execute_poc','submit_report','bypass_waf'):
            with self.subTest(action=a):
                self.case['action']=a;self.blocked('ACTION_NOT_IMPLEMENTED_OFFLINE')

    def test_policy_cannot_enable_live_operations(self):
        self.p['rules']['allowed_actions'].append('network_scan');self.sign()
        with self.assertRaises(pr.RegistryError):self.result()

    def test_duplicate_programs_rejected(self):
        self.registry['programs'].append(deepcopy(self.p))
        with self.assertRaises(pr.RegistryError):self.result()

    def test_duplicate_cases_rejected(self):
        self.requests['cases'].append(deepcopy(self.case))
        with self.assertRaises(pr.RegistryError):self.result()

    def test_naive_times_rejected(self):
        self.p['review']['reviewed_at']='2026-11-04T17:00:00'
        with self.assertRaises(pr.RegistryError):self.result()

    def test_review_freshness_is_bounded(self):
        self.p['review']['expires_at']=(NOW+timedelta(days=30)).isoformat()
        with self.assertRaises(pr.RegistryError):self.result()

    def test_candidate_requires_repo_and_all_contracts_in_scope(self):
        c={'id':'11111111-1111-4111-8111-111111111111','scope_id':self.p['scope_id'],
           'target':{'repo':'own/example','commit':'a'*40,'fork_block':123},'family':'vault',
           'invariant_broken':'not_confirmed','poc_path':'test/Example.t.sol::test_example',
           'affected_contracts':['0x'+'b'*40],'prelim_severity':'unverified','forge_evidence_sha':'d'*64}
        r=pr.review_candidate(self.registry,self.documents,c,program=pr.program_key(self.p),chain_id=1,now=NOW)
        self.assertEqual(r['status'],'ELIGIBLE_LOCAL_REVIEW');self.assertFalse(r['poc_executed'])
        r=pr.review_candidate(self.registry,self.documents,c,program=pr.program_key(self.p),chain_id=8453,now=NOW)
        self.assertEqual(r['status'],'BLOCKED')
        c['scope_id']='bounty-other'
        with self.assertRaises(pr.RegistryError):
            pr.review_candidate(self.registry,self.documents,c,program=pr.program_key(self.p),chain_id=1,now=NOW)

    def test_audit_records_bind_every_case(self):
        r,a=pr.evaluate(self.registry,self.documents,self.requests,now=NOW)
        self.assertEqual(len(a['entries']),3)
        self.assertEqual(a['entries'][1]['data'],r['decisions'][0])

    def test_no_network_or_child_process(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.persist();pr.verify(self.root/'case',now=NOW)

    def test_bundle_roundtrip(self):
        result=self.persist()
        self.assertEqual(result,pr.verify(self.root/'case',now=NOW))
        self.assertFalse(result['authorization_authenticated'])

    def test_verification_rechecks_expiry_now(self):
        self.persist()
        r=pr.verify(self.root/'case',now=NOW+timedelta(hours=3))
        self.assertEqual(r['historical_counts'],{'ELIGIBLE_LOCAL_REVIEW':1})
        self.assertEqual(r['current_counts'],{'BLOCKED':1})

    def test_future_decision_rejected(self):
        self.persist()
        with self.assertRaises(pr.RegistryError):pr.verify(self.root/'case',now=NOW-timedelta(seconds=1))

    def test_resealed_false_permission_rejected(self):
        self.persist();p=self.root/'case';d=strict_json((p/'decision.json').read_bytes())
        d['authorization_authenticated']=True;raw=canonical(d);(p/'decision.json').write_bytes(raw)
        m=strict_json((p/'COMPLETE.json').read_bytes());m['sha256']['decision.json']=hashlib.sha256(raw).hexdigest()
        (p/'COMPLETE.json').write_bytes(canonical(m))
        with self.assertRaisesRegex(pr.RegistryError,'REPLAY_DISAGREEMENT'):pr.verify(p,now=NOW)

    def test_resealed_changed_audit_rejected(self):
        self.persist();p=self.root/'case';(p/'audit.json').write_bytes(canonical({'entries':[]}))
        m=strict_json((p/'COMPLETE.json').read_bytes());m['sha256']['audit.json']=hashlib.sha256((p/'audit.json').read_bytes()).hexdigest()
        (p/'COMPLETE.json').write_bytes(canonical(m))
        with self.assertRaises(pr.RegistryError):pr.verify(p,now=NOW)

    def test_original_registry_unchanged(self):
        before=canonical(self.registry);self.persist();self.assertEqual(before,canonical(self.registry))
        self.assertEqual((self.root/'case/registry.json').read_bytes(),before)

    def test_private_permissions_and_no_overwrite(self):
        self.persist();out=self.root/'case'
        self.assertEqual(out.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in out.iterdir()))
        with self.assertRaises(pr.RegistryError):self.persist()

    def test_symlink_document_rejected(self):
        self.persist();(self.root/'case/policy-000.txt').unlink()
        (self.root/'case/policy-000.txt').symlink_to(self.root/'docs/policy-1.txt')
        with self.assertRaises((OSError,ValueError)):pr.verify(self.root/'case',now=NOW)

    def test_console_errors_do_not_repeat_values(self):
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(pr.main(['verify-programs','--bundle',str(self.root/'PRIVATE_MARKER')]),2)
        self.assertNotIn('PRIVATE_MARKER',stdout.getvalue())
        with patch('sys.stderr',new_callable=io.StringIO) as stderr,self.assertRaises(SystemExit):
            pr.main(['program-platforms','--secret','PRIVATE_MARKER'])
        self.assertNotIn('PRIVATE_MARKER',stderr.getvalue())

    def test_platform_listing_never_claims_account_connections(self):
        with redirect_stdout(io.StringIO()) as stdout:self.assertEqual(pr.main(['program-platforms']),0)
        result=json.loads(stdout.getvalue());self.assertEqual(len(result['platforms']),8)
        self.assertFalse(result['account_connectors'])

    def test_case_batch_twenty_across_eight_platforms(self):
        programs=[];docs={};cases=[]
        for i in range(20):
            p,d,c=example(pr.PLATFORMS[i%8],i+1);programs.append(p);docs[p['document']['file']]=d;cases.append(c)
        r,a=pr.evaluate({'schema_version':1,'programs':programs},docs,{'schema_version':1,'cases':cases},now=NOW)
        self.assertEqual(r['counts'],{'ELIGIBLE_LOCAL_REVIEW':20});self.assertEqual(len(a['entries']),22)

    def test_package_route_and_quality_are_connected(self):
        from superhunter import __main__,quality
        with patch('sys.argv',['superhunter','program-platforms']),redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(__main__.main(),0)
        self.assertFalse(json.loads(stdout.getvalue())['account_connectors'])
        self.assertIn('program_registry',quality.COMPONENTS)


if __name__=='__main__':unittest.main()
