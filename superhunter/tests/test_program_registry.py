"""Offline policy controls with synthetic program policies, not real authorizations."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from unittest.mock import patch

from superhunter import program_registry as pr
from superhunter.safe_io import canonical, strict_json

AT='2026-11-04T15:00:00+00:00'
LATER='2026-11-06T15:00:00+00:00'


def example(platform='immunefi', number=0):
    # This text is a synthetic test artifact, not a program brief or invitation.
    content=('SYNTHETIC LOCAL TEST POLICY '+platform+' '+str(number)+'; no external authorization.').encode()
    p={'platform':platform,'program_id':'fixture-'+str(number),'scope_id':'bounty-fixture-'+platform+'-'+str(number),
       'kind':'bounty','visibility':'public','status':'active','participation':'confirmed',
       'offline_automation':'allowed','disclosure':'private',
       'policy':{'version':'v1','source_url':'https://policy.example.invalid/local-test',
                 'captured_at':'2026-11-04T00:00:00+00:00','valid_until':'2026-11-05T00:00:00+00:00',
                 'evidence_file':'policy-'+platform+'-'+str(number)+'.txt','sha256':pr.sha(content)},
       'assets':[{'id':'source','kind':'repository','locator':'example/local-test','commit':'a'*40,'chain_id':None,'effect':'include'},
                 {'id':'contract','kind':'contract','locator':'0x'+'a'*40,'commit':None,'chain_id':31337,'effect':'include'},
                 {'id':'host','kind':'hostname','locator':'qa.example.invalid','commit':None,'chain_id':None,'effect':'include'}],
       'approval':{'state':'approved','reviewer':'local-test-reviewer','reviewed_at':'2026-11-04T01:00:00+00:00','snapshot_sha256':None}}
    p['approval']['snapshot_sha256']=pr.binding(p)
    r={'id':'request-'+platform+'-'+str(number),'program_key':pr.program_key(p),'scope_id':p['scope_id'],
       'action':'offline_review','asset':{k:p['assets'][0][k] for k in ('kind','locator','commit','chain_id')}}
    return p,r,content


class ProgramRegistryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        p,r,blob=example();self.p=p;self.r=r
        self.registry={'schema_version':1,'programs':[p]};self.requests={'schema_version':1,'requests':[r]}
        self.blobs={pr.program_key(p):blob};self.evidence=self.root/'evidence';self.evidence.mkdir()
        (self.evidence/p['policy']['evidence_file']).write_bytes(blob)
        self.out=self.root/'case'

    def approve(self):
        self.p['approval']['snapshot_sha256']=pr.binding(self.p)

    def run_review(self, at=AT):
        return pr.evaluate(self.registry,self.requests,self.blobs,at=at)

    def decision(self, at=AT):
        return self.run_review(at)['decisions'][0]

    def create(self, at=AT):
        (self.root/'registry.json').write_bytes(canonical(self.registry))
        (self.root/'requests.json').write_bytes(canonical(self.requests))
        return pr.create_registry(self.root/'registry.json',self.root/'requests.json',self.evidence,self.out,at=at)

    def reseal(self,name,fn):
        path=self.out/name;value=strict_json(path.read_bytes());fn(value);raw=canonical(value);path.write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=pr.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_exact_case_eligible_only_for_offline_review(self):
        d=self.decision();self.assertEqual(d['status'],'LOCAL_SCOPE_ELIGIBLE')
        self.assertFalse(d['platform_authorization_verified']);self.assertFalse(d['network_execution_allowed'])
        self.assertTrue(d['human_review_required'])
        self.assertEqual(self.run_review()['platform_connectors_active'],0)

    def test_twenty_programs_eight_platforms_without_cross_authorization(self):
        triples=[example(pr.PLATFORMS[i%8],i) for i in range(20)]
        reg={'schema_version':1,'programs':[p for p,r,b in triples]}
        req={'schema_version':1,'requests':[r for p,r,b in triples]}
        evidence={pr.program_key(p):b for p,r,b in triples}
        result=pr.evaluate(reg,req,evidence,at=AT)
        self.assertEqual(result['program_count'],20);self.assertEqual(len(result['platforms']),8)
        self.assertEqual(result['counts'],{'LOCAL_SCOPE_ELIGIBLE':20})
        req['requests'][0]['scope_id']=triples[1][0]['scope_id']
        self.assertIn('SCOPE_ID_MISMATCH',pr.evaluate(reg,req,evidence,at=AT)['decisions'][0]['deny_reasons'])

    def test_all_eight_platform_identifiers_accepted(self):
        for plat in pr.PLATFORMS:
            with self.subTest(platform=plat):
                p,r,b=example(plat)
                d=pr.evaluate({'schema_version':1,'programs':[p]}, {'schema_version':1,'requests':[r]}, {pr.program_key(p):b},at=AT)
                self.assertEqual(d['counts'],{'LOCAL_SCOPE_ELIGIBLE':1})

    def test_unknown_platform_rejected(self):
        self.p['platform']='invented'
        with self.assertRaisesRegex(pr.RegistryError,'PLATFORM'):self.run_review()

    def test_public_does_not_imply_participation(self):
        self.p['participation']='unknown';self.approve()
        self.assertEqual(self.decision()['status'],'LOCAL_SCOPE_REVIEW_REQUIRED')

    def test_private_invitation_unknown_not_eligible(self):
        self.p['visibility']='private';self.p['participation']='unknown';self.approve()
        self.assertIn('PARTICIPATION_UNCONFIRMED',self.decision()['review_reasons'])

    def test_declined_participation_denied(self):
        self.p['participation']='declined';self.approve()
        self.assertEqual(self.decision()['status'],'LOCAL_SCOPE_DENIED')

    def test_unknown_automation_requires_review(self):
        self.p['offline_automation']='unknown';self.approve()
        self.assertIn('AUTOMATION_UNSPECIFIED',self.decision()['review_reasons'])

    def test_automation_prohibition_denied(self):
        self.p['offline_automation']='forbidden';self.approve()
        self.assertIn('OFFLINE_AUTOMATION_FORBIDDEN',self.decision()['deny_reasons'])

    def test_active_operations_always_denied(self):
        for action in ('network_scan','broadcast','submit_report'):
            with self.subTest(action=action):
                self.r['action']=action
                self.assertIn('ACTION_NOT_SUPPORTED',self.decision()['deny_reasons'])

    def test_inactive_program_denied(self):
        for status in ('paused','closed'):
            self.p['status']=status;self.approve()
            self.assertIn('PROGRAM_INACTIVE',self.decision()['deny_reasons'])

    def test_exclusion_beats_include_independent_of_order(self):
        deny={**self.p['assets'][0],'id':'excluded','effect':'exclude'}
        self.p['assets'].append(deny);self.approve()
        self.assertIn('EXCLUSION_WINS',self.decision()['deny_reasons'])
        self.p['assets'].reverse();self.approve()
        self.assertIn('EXCLUSION_WINS',self.decision()['deny_reasons'])

    def test_different_commit_not_included(self):
        self.r['asset']['commit']='b'*40
        self.assertIn('ASSET_NOT_EXPLICITLY_INCLUDED',self.decision()['deny_reasons'])

    def test_same_address_other_chain_denied(self):
        self.r['asset']={'kind':'contract','locator':'0x'+'a'*40,'commit':None,'chain_id':1}
        self.assertIn('ASSET_NOT_EXPLICITLY_INCLUDED',self.decision()['deny_reasons'])
        self.r['asset']['chain_id']=31337
        self.assertEqual(self.decision()['status'],'LOCAL_SCOPE_ELIGIBLE')

    def test_hostname_suffix_not_allowed(self):
        self.r['asset']={'kind':'hostname','locator':'qa.example.invalid.other.invalid','commit':None,'chain_id':None}
        self.assertEqual(self.decision()['status'],'LOCAL_SCOPE_DENIED')

    def test_wildcards_not_inferred(self):
        self.p['assets'][2]['locator']='*.example.invalid'
        with self.assertRaisesRegex(pr.RegistryError,'HOSTNAME_EXACT_ONLY'):self.run_review()

    def test_expiration_boundary_blocks(self):
        for at in ('2026-11-05T00:00:00Z',LATER):
            self.assertIn('SNAPSHOT_EXPIRED',self.decision(at)['review_reasons'])

    def test_future_capture_and_review_block(self):
        d=self.decision('2026-11-03T23:00:00Z')
        self.assertIn('SNAPSHOT_IN_FUTURE',d['review_reasons']);self.assertIn('REVIEW_IN_FUTURE',d['review_reasons'])

    def test_timezone_equivalence(self):
        self.assertEqual(self.run_review(AT),self.run_review('2026-11-04T09:00:00-06:00'))

    def test_naive_timestamp_rejected(self):
        with self.assertRaisesRegex(pr.RegistryError,'TIMEZONE_REQUIRED'):self.run_review('2026-11-04T15:00:00')

    def test_changed_rules_invalidate_previous_approval(self):
        before=deepcopy(self.registry)
        self.p['assets'].append({'id':'new','kind':'repository','locator':'example/new','commit':'c'*40,'chain_id':None,'effect':'include'})
        self.assertIn('REVIEW_BINDING_STALE',self.decision()['review_reasons'])
        changes=pr.changes(before,self.registry)
        self.assertEqual(changes['changed'][0]['changed_fields'],['assets'])
        self.assertTrue(changes['changed'][0]['requires_new_review'])

    def test_policy_hash_change_invalidates_approval(self):
        b=b'UPDATED SYNTHETIC POLICY';self.blobs[pr.program_key(self.p)]=b;self.p['policy']['sha256']=pr.sha(b)
        self.assertIn('REVIEW_BINDING_STALE',self.decision()['review_reasons'])

    def test_policy_bytes_tamper_rejected(self):
        self.blobs[pr.program_key(self.p)]+=b'changed'
        with self.assertRaisesRegex(pr.RegistryError,'POLICY_BYTES_MISMATCH'):self.run_review()

    def test_pending_approval_not_eligible(self):
        self.p['approval']={'state':'pending','reviewer':None,'reviewed_at':None,'snapshot_sha256':None}
        self.assertIn('REVIEW_PENDING',self.decision()['review_reasons'])

    def test_rejected_approval_denied(self):
        self.p['approval']['state']='rejected'
        self.assertIn('REVIEW_REJECTED',self.decision()['deny_reasons'])

    def test_duplicate_programs_and_scopes_rejected(self):
        self.registry['programs'].append(deepcopy(self.p))
        with self.assertRaisesRegex(pr.RegistryError,'DUPLICATE_PROGRAM_OR_SCOPE'):self.run_review()

    def test_duplicate_rules_rejected(self):
        self.p['assets'].append(deepcopy(self.p['assets'][0]))
        with self.assertRaisesRegex(pr.RegistryError,'DUPLICATE_RULE'):self.run_review()

    def test_unknown_program_denied(self):
        self.r['program_key']='immunefi:other'
        self.assertIn('PROGRAM_NOT_REGISTERED',self.decision()['deny_reasons'])

    def test_boolean_schema_and_chain_not_integers(self):
        self.registry['schema_version']=True
        with self.assertRaises(pr.RegistryError):self.run_review()
        self.registry['schema_version']=1;self.p['assets'][1]['chain_id']=True
        with self.assertRaises(pr.RegistryError):self.run_review()

    def test_secret_url_credentials_and_query_rejected(self):
        for url in ('http://example.invalid/a','https://user:secret@example.invalid/a','https://example.invalid/a?token=SECRET'):
            self.p['policy']['source_url']=url
            with self.assertRaisesRegex(pr.RegistryError,'POLICY_URL'):self.run_review()

    def test_path_traversal_rejected(self):
        self.p['policy']['evidence_file']='../secret'
        with self.assertRaisesRegex(pr.RegistryError,'EVIDENCE_PATH'):self.run_review()

    def test_empty_programs_and_oversize_rejected(self):
        for items in ([],[self.p]*(pr.MAX_PROGRAMS+1)):
            with self.assertRaises(pr.RegistryError):pr.validate_registry({'schema_version':1,'programs':items})

    def test_extra_or_missing_fields_rejected(self):
        self.p['guaranteed_bounty']=100000
        with self.assertRaisesRegex(pr.RegistryError,'PROGRAM_SCHEMA'):self.run_review()

    def test_inputs_are_not_modified(self):
        before=(deepcopy(self.registry),deepcopy(self.requests))
        self.run_review();self.assertEqual(before,(self.registry,self.requests))

    def test_diff_add_remove_and_no_change(self):
        self.assertEqual(pr.changes(self.registry,self.registry),{'added':[],'removed':[],'changed':[]})
        p,r,b=example('cantina',1)
        result=pr.changes(self.registry,{'schema_version':1,'programs':[p]})
        self.assertEqual(result['added'],['cantina:fixture-1']);self.assertEqual(result['removed'],['immunefi:fixture-0'])

    def test_native_audit_executes(self):
        native=pr.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as append:
            self.create()
        self.assertEqual(append.call_count,3)

    def test_self_contained_roundtrip(self):
        first=self.create();shutil.rmtree(self.evidence)
        self.assertEqual(pr.verify_registry(self.out,at=AT),first)

    def test_verifier_rechecks_expiry_at_current_time(self):
        self.create();r=pr.verify_registry(self.out,at=LATER)
        self.assertTrue(r['historical_evidence_consistent'])
        self.assertEqual(r['current_review']['counts'],{'LOCAL_SCOPE_REVIEW_REQUIRED':1})
        self.assertIn('SNAPSHOT_EXPIRED',r['current_review']['decisions'][0]['review_reasons'])

    def test_raw_policy_unchanged_private(self):
        self.create();self.assertEqual((self.out/'policy-000.txt').read_bytes(),self.blobs[pr.program_key(self.p)])
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_no_network_or_process(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();pr.verify_registry(self.out,at=AT)

    def test_resealed_false_approval_rejected(self):
        self.r['action']='network_scan';self.create()
        self.reseal('decision.json',lambda v:v['decisions'][0].update(status='LOCAL_SCOPE_ELIGIBLE'))
        with self.assertRaisesRegex(pr.RegistryError,'DECISION_MISMATCH'):pr.verify_registry(self.out,at=AT)

    def test_resealed_policy_changed_rejected(self):
        self.create();p=self.out/'policy-000.txt';p.write_bytes(b'changed')
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][p.name]=pr.sha(p.read_bytes())
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(pr.RegistryError,'POLICY_BYTES_MISMATCH'):pr.verify_registry(self.out,at=AT)

    def test_audit_semantics_bound_even_after_hash_reseal(self):
        self.create();self.reseal('audit.json',lambda v:v['entries'][1]['data'].update(decision_sha256='0'*64))
        with self.assertRaisesRegex(pr.RegistryError,'AUDIT_SEMANTICS'):pr.verify_registry(self.out,at=AT)

    def test_stale_code_rejected(self):
        self.create()
        with patch.object(pr,'code_identity',return_value={'old':'0'*64}),self.assertRaisesRegex(pr.RegistryError,'CODE_CHANGED'):
            pr.verify_registry(self.out,at=AT)

    def test_manifest_missing_and_extra_file_rejected(self):
        self.create();(self.out/'extra').write_text('not registered')
        with self.assertRaisesRegex(pr.RegistryError,'BUNDLE_FILES'):pr.verify_registry(self.out,at=AT)
        (self.out/'extra').unlink();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):pr.verify_registry(self.out,at=AT)

    def test_existing_output_not_overwritten(self):
        self.create();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(pr.RegistryError,'OUTPUT_EXISTS'):self.create()
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_symlink_policy_rejected(self):
        p=self.evidence/self.p['policy']['evidence_file'];p.unlink();p.symlink_to(self.root/'outside')
        (self.root/'outside').write_bytes(self.blobs[pr.program_key(self.p)])
        with self.assertRaises((ValueError,OSError)):self.create()

    def test_summary_omits_private_identifiers(self):
        r=self.run_review();text=pr.render(r).decode()
        self.assertNotIn('example/local-test',text);self.assertNotIn('local-test-reviewer',text)

    def test_cli_runs_and_verifies_separate_processes(self):
        self.create();new=self.root/'cli'
        args=['review-programs','--registry',str(self.root/'registry.json'),'--requests',str(self.root/'requests.json'),
              '--evidence',str(self.evidence),'--out',str(new),'--at',AT]
        for a in (args,['verify-programs','--bundle',str(new),'--at',AT]):
            r=subprocess.run([sys.executable,'-B','-m','superhunter',*a],cwd=pr.ROOT.parent,capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertFalse(json.loads(r.stdout)['network_execution_allowed'])
        with redirect_stdout(io.StringIO()) as stream:
            code=pr.main(['verify-programs','--bundle',str(new),'--at',LATER])
        self.assertEqual(code,1);self.assertTrue(json.loads(stream.getvalue())['explicit_replay_time'])

    def test_cli_errors_do_not_echo_inputs(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            pr.main(['verify-programs','--bundle','PRIVATE','--unknown','SENSITIVE'])
        self.assertNotIn('SENSITIVE',stream.getvalue())
        with redirect_stdout(io.StringIO()) as stream:self.assertEqual(pr.main(['verify-programs','--bundle',str(self.root/'PRIVATE')]),2)
        self.assertNotIn('PRIVATE',stream.getvalue())

    def test_candidate_adapter_checks_repo_and_all_contracts(self):
        c={'id':str(uuid.uuid4()),'scope_id':self.p['scope_id'],
           'target':{'repo':'example/local-test','commit':'a'*40,'fork_block':1},'family':'vault',
           'invariant_broken':'local_property','poc_path':'test/Local.t.sol::test_example',
           'affected_contracts':['0x'+'a'*40],'prelim_severity':'unverified','forge_evidence_sha':'0'*64}
        req=pr.requests_for_candidate(c,platform='immunefi',program_id='fixture-0',chain_id=31337)
        result=pr.evaluate(self.registry,req,self.blobs,at=AT)
        self.assertEqual(result['counts'],{'LOCAL_SCOPE_ELIGIBLE':2})
        c['affected_contracts'].append('0x'+'b'*40)
        req=pr.requests_for_candidate(c,platform='immunefi',program_id='fixture-0',chain_id=31337)
        self.assertEqual(pr.evaluate(self.registry,req,self.blobs,at=AT)['counts']['LOCAL_SCOPE_DENIED'],1)
        with self.assertRaises(pr.RegistryError):pr.requests_for_candidate(c,platform='immunefi',program_id='fixture-0',chain_id=True)


if __name__=='__main__':unittest.main()
