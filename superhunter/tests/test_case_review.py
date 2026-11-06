"""Actual artifact integration, using declared benign/synthetic input fixtures.

No scanner, Solidity compiler, POC, RPC, account or third-party target is run.
Tests call the real existing producers/verifiers; mocks only test negative paths.
"""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from superhunter import case_review as cr
from superhunter import balance_reconciliation as ar
from superhunter import static_review as sr
from superhunter import program_registry as pr
from superhunter.safe_io import canonical, strict_json, write_new_bundle
from test_static_review import fixture as static_fixture
from test_program_registry import example as policy_fixture


class CaseReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.at = self.now.isoformat()
        self.report, self.static_context, self.sources = static_fixture()
        self.policy, _, self.policy_bytes = policy_fixture()
        self.ledger = ar.example_input()
        address = '0x' + 'a' * 40
        self.c = {'id': str(uuid.uuid4()), 'scope_id': self.policy['scope_id'],
                  'target': {'repo': self.ledger['subject']['repo'], 'commit': self.ledger['subject']['commit'], 'fork_block': 1},
                  'family': 'vault', 'invariant_broken': 'synthetic_case_only',
                  'poc_path': 'test/NotExecuted.t.sol::test_not_executed',
                  'affected_contracts': [address], 'prelim_severity': 'unverified',
                  'forge_evidence_sha': cr.sha(b'NO FORGE EXECUTION; synthetic metadata only')}
        self.static_context['repository'] = {k: self.c['target'][k] for k in ('repo', 'commit')}
        self.static_context['scope_id'] = self.c['scope_id']
        self.policy['assets'][0].update(locator=self.c['target']['repo'], commit=self.c['target']['commit'])
        self.policy['policy']['captured_at'] = (self.now - timedelta(hours=2)).isoformat()
        self.policy['policy']['valid_until'] = (self.now + timedelta(hours=12)).isoformat()
        self.policy['approval']['reviewed_at'] = (self.now - timedelta(hours=1)).isoformat()
        self.ledger['case_id'] = 'case-' + self.c['id']
        self.ctx = {'schema_version': 1, 'candidate_sha256': cr.sha(canonical(self.c)),
                    'platform': 'immunefi', 'program_id': self.policy['program_id'], 'chain_id': 31337,
                    'state_anchor': deepcopy(self.ledger['subject']['anchor']),
                    'ledger_case_id': self.ledger['case_id'], 'account_bindings': {address: 'vault'},
                    'static_fingerprint': None, 'evidence_manifests': {}}
        self.paths = {k: self.root/k for k in cr.GROUPS}
        self.refresh_policy()
        self.refresh_static()
        self.refresh_balances()
        self.out = self.root/'case'

    def store(self, name, obj):
        p = self.root/name
        p.write_bytes(canonical(obj))
        return p

    def clear(self, group):
        if self.paths[group].exists():
            shutil.rmtree(self.paths[group])

    def pin(self, group):
        self.ctx['evidence_manifests'][group] = cr.sha((self.paths[group]/'COMPLETE.json').read_bytes())

    def refresh_policy(self, requests=None, approve=True):
        self.clear('programs')
        if approve:
            self.policy['approval']['snapshot_sha256'] = pr.binding(self.policy)
        registry = {'schema_version': 1, 'programs': [self.policy]}
        requests = requests or pr.requests_for_candidate(self.c, platform=self.ctx['platform'],
                                          program_id=self.ctx['program_id'], chain_id=self.ctx['chain_id'])
        p = self.store('programs-input.json', registry)
        r = self.store('requests-input.json', requests)
        evidence = self.root/'policy-originals'
        evidence.mkdir(exist_ok=True)
        (evidence/self.policy['policy']['evidence_file']).write_bytes(self.policy_bytes)
        pr.create_registry(p, r, evidence, self.paths['programs'], at=self.at)
        self.pin('programs')

    def refresh_static(self, choose=True):
        self.clear('static')
        raw = canonical(self.report)
        self.static_context['report_sha256'] = cr.sha(raw)
        report = self.store('static-input.json', self.report)
        context = self.store('static-context.json', self.static_context)
        sources = self.root/'sources'
        for name, value in self.sources.items():
            p = sources/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(value)
        result = sr.import_report(report, context, sources, self.paths['static'])
        self.pin('static')
        if choose:
            self.ctx['static_fingerprint'] = result['alerts'][0]['fingerprint'] if result['alerts'] else None

    def refresh_balances(self):
        self.clear('balances')
        ar.create_bundle(self.ledger, self.paths['balances'])
        self.pin('balances')

    def captured(self):
        return {k: cr.capture(p) for k, p in self.paths.items()}

    def evaluate(self, at=None):
        return cr.evaluate(self.c, self.ctx, self.captured(), at=at or self.at)

    def create(self):
        c, ctx = self.store('candidate-external.json', self.c), self.store('context-external.json', self.ctx)
        return cr.create_case(c, ctx, self.paths['programs'], self.paths['static'], self.paths['balances'], self.out, at=self.at)

    def verify(self, at=None, cand=None, context=None):
        return cr.verify_case(self.out, expected_candidate=cand or self.c,
                              expected_context=context or self.ctx, at=at or self.at)

    def reseal(self, name, mutate):
        obj = strict_json((self.out/name).read_bytes());mutate(obj)
        raw = canonical(obj);(self.out/name).write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = cr.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_individually_valid_foreign_static_commit_cannot_join(self):
        self.static_context['repository']['commit'] = 'b'*40
        self.refresh_static()
        self.assertEqual(sr.verify_report(self.paths['static'])['status'], 'STATIC_REVIEW_REQUIRED')
        self.assertEqual(ar.verify_bundle(self.paths['balances'])['status'], 'ACCOUNTING_RECONCILED')
        with self.assertRaisesRegex(cr.CaseError, 'STATIC_TARGET_MISMATCH'):
            self.evaluate()

    def test_all_original_verifiers_actually_called(self):
        with patch.object(pr, 'verify_registry', wraps=pr.verify_registry) as p, \
             patch.object(sr, 'verify_report', wraps=sr.verify_report) as s, \
             patch.object(ar, 'verify_bundle', wraps=ar.verify_bundle) as a:
            result = self.evaluate()
        self.assertEqual([p.call_count, s.call_count, a.call_count], [1,1,1])
        self.assertEqual(result['status'], 'CASE_REVIEW_REQUIRED')
        for key in cr.LIMITS:
            self.assertEqual(result[key], cr.LIMITS[key])

    def test_ledger_wrong_repo_or_commit_or_chain_or_hash_rejected(self):
        original = deepcopy(self.ledger['subject'])
        for key, val in [('repo','different/repo'), ('commit','f'*40), ('chain_id',1),
                         ('anchor',{'block_number':1, 'block_hash':'0x'+'b'*64})]:
            with self.subTest(field=key):
                self.ledger['subject'] = {**original, key:val}
                self.refresh_balances()
                self.assertEqual(ar.verify_bundle(self.paths['balances'])['status'], 'ACCOUNTING_RECONCILED')
                with self.assertRaisesRegex(cr.CaseError, 'ACCOUNTING_TARGET_MISMATCH'):self.evaluate()

    def test_missing_contract_from_request_set_rejected(self):
        req = pr.requests_for_candidate(self.c, platform='immunefi', program_id=self.ctx['program_id'], chain_id=31337)
        req['requests'].pop()
        self.refresh_policy(requests=req)
        with self.assertRaisesRegex(cr.CaseError, 'CANDIDATE_REQUESTS_MISMATCH'):self.evaluate()

    def test_extra_request_cannot_be_silently_ignored(self):
        req = pr.requests_for_candidate(self.c, platform='immunefi', program_id=self.ctx['program_id'], chain_id=31337)
        req['requests'].append({**deepcopy(req['requests'][0]), 'id':'unrelated'})
        self.refresh_policy(requests=req)
        with self.assertRaisesRegex(cr.CaseError, 'CANDIDATE_REQUESTS_MISMATCH'):self.evaluate()

    def test_reordered_requests_are_same_set(self):
        req = pr.requests_for_candidate(self.c, platform='immunefi', program_id=self.ctx['program_id'], chain_id=31337)
        req['requests'].reverse();self.refresh_policy(requests=req)
        self.assertEqual(self.evaluate()['status'], 'CASE_REVIEW_REQUIRED')

    def test_unselected_static_alert_is_inconclusive(self):
        self.ctx['static_fingerprint'] = None
        r = self.evaluate()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('NO_STATIC_ALERT_SELECTED', r['incomplete_reasons'])

    def test_unknown_selected_fingerprint_rejected(self):
        self.ctx['static_fingerprint'] = 'f'*64
        with self.assertRaisesRegex(cr.CaseError, 'SELECTED_ALERT_NOT_PRESENT'):self.evaluate()

    def test_static_high_label_never_final_severity(self):
        self.report['results']['detectors'][0]['impact'] = 'High'
        self.refresh_static()
        r = self.evaluate()
        self.assertIsNone(r['final_severity']);self.assertFalse(r['vulnerability_confirmed'])

    def test_static_scope_mismatch_rejected(self):
        self.static_context['scope_id'] = 'bounty-other'
        self.refresh_static()
        with self.assertRaisesRegex(cr.CaseError, 'STATIC_SCOPE_MISMATCH'):self.evaluate()

    def test_unbound_static_observation_inconclusive(self):
        self.report['results']['detectors'][0]['elements'] = []
        self.refresh_static()
        r = self.evaluate()
        self.assertEqual(r['status'],'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('STATIC_ALERT_HAS_UNBOUND_LOCATIONS',r['incomplete_reasons'])

    def test_failed_analyzer_not_promoted(self):
        self.report = {'success':False,'error':'synthetic tool failure','results':{}}
        self.refresh_static()
        r = self.evaluate()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('STATIC_TOOL_REPORTED_ERROR',r['incomplete_reasons'])

    def test_ledger_case_id_mismatch_rejected(self):
        self.ledger['case_id'] = 'other-case'
        self.refresh_balances()
        with self.assertRaisesRegex(cr.CaseError,'LEDGER_CASE_MISMATCH'):self.evaluate()

    def test_balance_gap_is_signal_not_a_vulnerability(self):
        self.ledger['after']['usd6']['vault'] = str(int(self.ledger['after']['usd6']['vault'])+1)
        self.refresh_balances()
        r = self.evaluate()
        self.assertEqual(r['components']['balances']['unexplained_cells'],1)
        self.assertEqual(len(r['review_signals']),1)
        self.assertFalse(r['causal_impact_proven']);self.assertFalse(r['vulnerability_confirmed'])
        self.assertIsNone(r['final_severity'])

    def test_missing_quote_stays_inconclusive(self):
        self.ledger['prices'].pop('eth18');self.refresh_balances()
        r = self.evaluate()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('ACCOUNTING_VALUATION_INCOMPLETE',r['incomplete_reasons'])

    def test_incomplete_flows_stay_inconclusive(self):
        self.ledger['flow_coverage'] = 'declared_incomplete';self.refresh_balances()
        self.assertIn('ACCOUNTING_COVERAGE_INCOMPLETE', self.evaluate()['incomplete_reasons'])

    def test_policy_exclusion_blocks_even_when_other_inputs_match(self):
        self.policy['assets'].append({**deepcopy(self.policy['assets'][1]),'id':'excluded','effect':'exclude'})
        self.refresh_policy()
        r=self.evaluate()
        self.assertEqual(r['status'], 'CASE_REVIEW_BLOCKED')
        self.assertIn('EXCLUSION_WINS', r['blocked_reasons'])

    def test_changed_approval_blocks_review(self):
        self.policy['disclosure']='coordinated';self.refresh_policy(approve=False)
        self.assertIn('REVIEW_BINDING_STALE',self.evaluate()['blocked_reasons'])

    def test_expired_scope_does_not_survive_bundle_verification(self):
        self.create()
        r=self.verify(at=(self.now+timedelta(days=2)).isoformat())
        self.assertEqual(r['historical_status'],'CASE_REVIEW_REQUIRED')
        self.assertEqual(r['status'],'CASE_REVIEW_BLOCKED')
        self.assertIn('SNAPSHOT_EXPIRED',r['current_review']['blocked_reasons'])

    def test_future_receipt_rejected(self):
        with self.assertRaisesRegex(cr.CaseError,'FUTURE_POLICY_RECEIPT'):
            self.evaluate(at=(self.now-timedelta(seconds=1)).isoformat())

    def test_context_cannot_replace_candidate_commit_without_pin(self):
        self.c['target']['commit'] = 'c'*40
        with self.assertRaisesRegex(cr.CaseError, 'CANDIDATE_PIN_MISMATCH'):self.evaluate()

    def test_context_covers_all_affected_contracts(self):
        self.ctx['account_bindings'] = {}
        with self.assertRaisesRegex(cr.CaseError, 'AFFECTED_CONTRACT_SET'):self.evaluate()

    def test_account_mapping_must_exist_in_ledger(self):
        self.ctx['account_bindings']['0x'+'a'*40]='absent'
        with self.assertRaisesRegex(cr.CaseError, 'ACCOUNT_BINDING_MISSING'):self.evaluate()

    def test_bool_chain_and_block_not_integers(self):
        for key in ('chain_id','schema_version'):
            old=self.ctx[key];self.ctx[key]=True
            with self.assertRaises(cr.CaseError):self.evaluate()
            self.ctx[key]=old
        self.ctx['state_anchor']['block_number']=True
        with self.assertRaises(cr.CaseError):self.evaluate()

    def test_evidence_pins_from_other_package_block(self):
        self.ctx['evidence_manifests']['static']='0'*64
        with self.assertRaisesRegex(cr.CaseError,'EVIDENCE_PIN_MISMATCH'):self.evaluate()

    def test_untrusted_output_context_not_an_external_reference(self):
        self.create()
        new=deepcopy(self.ctx);new['ledger_case_id']='another'
        with self.assertRaisesRegex(cr.CaseError,'EXTERNAL_REFERENCE_MISMATCH'):self.verify(context=new)

    def test_candidate_same_id_with_changed_text_not_same_reference(self):
        self.create()
        c=deepcopy(self.c);c['invariant_broken']='changed'
        ctx=deepcopy(self.ctx);ctx['candidate_sha256']=cr.sha(canonical(c))
        with self.assertRaisesRegex(cr.CaseError,'EXTERNAL_REFERENCE_MISMATCH'):self.verify(cand=c,context=ctx)

    def test_self_contained_reverification_after_source_removal(self):
        first=self.create()
        for p in self.paths.values():shutil.rmtree(p)
        result=self.verify()
        self.assertEqual(result['current_review'],first)

    def test_original_sources_not_mutated(self):
        before=self.captured();self.create()
        self.assertEqual(before,self.captured())

    def test_audit_is_native_and_replayed(self):
        native=cr.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as p:
            self.create()
        self.assertGreaterEqual(p.call_count,5)
        audit=strict_json((self.out/'audit.json').read_bytes())
        self.assertEqual([e['event'] for e in audit['entries']], ['case.bind']+['case.evidence']*3+['case.review'])
        self.verify()

    def test_resealed_success_claim_rejected(self):
        self.create();self.reseal('case.json',lambda v:v.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(cr.CaseError,'CASE_REPLAY_MISMATCH'):self.verify()

    def test_resealed_audit_event_rejected(self):
        self.create();self.reseal('audit.json',lambda v:v['entries'][1]['data'].update(manifest_sha256='f'*64))
        with self.assertRaisesRegex(cr.CaseError,'CASE_REPLAY_MISMATCH'):self.verify()

    def test_report_keeps_descriptions_and_paths_private(self):
        self.report['results']['detectors'][0]['description']='UNLABELLED_PRIVATE_MARKER'
        self.refresh_static();self.create()
        self.assertNotIn('UNLABELLED_PRIVATE_MARKER',(self.out/'REVIEW.md').read_text())
        self.assertIn(b'UNLABELLED_PRIVATE_MARKER',(self.out/'static--slither.json').read_bytes())

    def test_overwrite_rejected(self):
        self.create();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(cr.CaseError,'NEW_OUTPUT_REQUIRED'):self.create()
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_extra_unmanifested_file_rejected(self):
        self.create();(self.out/'hidden.txt').write_bytes(b'extra')
        with self.assertRaises(ValueError):self.verify()

    def test_symlink_input_rejected(self):
        path=self.paths['balances']/'input.json';raw=path.read_bytes();path.unlink()
        other=self.root/'outside';other.write_bytes(raw);path.symlink_to(other)
        with self.assertRaises((OSError,ValueError)):self.evaluate()

    def test_private_modes(self):
        self.create()
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in self.out.iterdir()))

    def test_no_network_subprocess_or_poc_execution(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('subprocess.run',side_effect=AssertionError('process')):
            r=self.create();self.verify()
        self.assertFalse(r['execution_verified'])
        self.assertFalse((self.root/self.c['poc_path'].split('::')[0]).exists())

    def test_changed_engine_refuses_stale_package(self):
        self.create();original=cr.engine()
        with patch.object(cr,'engine',return_value={**original,'new':True}),self.assertRaisesRegex(cr.CaseError,'CASE_REPLAY_MISMATCH'):
            self.verify()

    def test_input_change_during_creation_aborts(self):
        original=cr.evaluate
        def modified(*args,**kwargs):
            result=original(*args,**kwargs)
            with (self.paths['static']/'slither.json').open('ab') as f:f.write(b' ')
            return result
        with patch.object(cr,'evaluate',side_effect=modified),self.assertRaises(ValueError):self.create()
        self.assertFalse((self.out/'COMPLETE.json').exists())

    def test_cli_two_real_processes(self):
        c,ctx=self.store('candidate-external.json',self.c),self.store('context-external.json',self.ctx)
        make=['review-case','--candidate',str(c),'--context',str(ctx),'--programs',str(self.paths['programs']),
              '--static',str(self.paths['static']),'--balances',str(self.paths['balances']),'--out',str(self.out)]
        verify=['verify-case','--bundle',str(self.out),'--candidate',str(c),'--context',str(ctx)]
        for args in (make,verify):
            r=subprocess.run([sys.executable,'-B','-m','superhunter',*args],cwd=cr.ROOT.parent,capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            self.assertFalse(json.loads(r.stdout)['vulnerability_confirmed'])

    def test_cli_rejects_embedded_references(self):
        self.create()
        args=['verify-case','--bundle',str(self.out),'--candidate',str(self.out/'candidate.json'),'--context',str(self.out/'context.json')]
        with redirect_stdout(io.StringIO()) as out:self.assertEqual(cr.main(args),2)
        self.assertEqual(json.loads(out.getvalue())['status'],'CASE_EVIDENCE_REJECTED')

    def test_cli_no_replay_or_target_flags(self):
        for flag in ('--at','--rpc','--target','--poc'):
            with self.subTest(flag=flag),patch('sys.stderr',new_callable=io.StringIO) as out,self.assertRaises(SystemExit):
                cr.main(['verify-case','--bundle','local','--candidate','x','--context','y',flag,'PRIVATE_MARKER'])
            self.assertNotIn('PRIVATE_MARKER',out.getvalue())

    def test_cli_error_does_not_echo_paths(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cr.main(['verify-case','--bundle',str(self.root/'PRIVATE_MARKER'),
                                     '--candidate',str(self.root/'a'),'--context',str(self.root/'b')]),2)
        self.assertNotIn('PRIVATE_MARKER',out.getvalue())

    def test_registry_includes_component_and_required_negative_controls(self):
        from superhunter import quality
        self.assertIn('case_review',quality.COMPONENTS)
        self.assertIn('programs',quality.COMPONENTS['case_review']['depends'])
        self.assertIn('test_case_review.CaseReviewTests.test_individually_valid_foreign_static_commit_cannot_join',quality.REQUIRED_TESTS)
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])


if __name__ == '__main__':unittest.main()
