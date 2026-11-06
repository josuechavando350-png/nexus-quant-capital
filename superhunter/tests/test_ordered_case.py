"""Join actual local artifact producers. Fixtures are NOT blockchain execution.

The legacy test fixture is reused, not subclassed or counted a second time.
All newly asserted ordered-case behavior is executed against the v2 API.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import timedelta
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from superhunter import case_review as cr
from superhunter import ledger_sequence as ls
from superhunter import quality
from superhunter.safe_io import canonical, strict_json
import test_case_review as original


class OrderedCaseTests(unittest.TestCase):
    def setUp(self):
        f = original.CaseReviewTests('test_all_original_verifiers_actually_called')
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fx, self.root = f, f.root
        ledger, order = ls.example_input()
        ledger['case_id'] = f.ledger['case_id']
        ledger['subject'] = deepcopy(f.ledger['subject'])
        ledger['prices'] = {'usd6': deepcopy(f.ledger['prices']['usd6'])}
        f.ledger = ledger
        f.refresh_balances()
        self.order = order
        self.sequence_path = self.root/'sequence'
        self.refresh_sequence()
        self.out = self.root/'ordered-case'

    def refresh_sequence(self, foreign=None):
        if self.sequence_path.exists():
            shutil.rmtree(self.sequence_path)
        ledger = self.fx.ledger if foreign is None else foreign
        self.order['ledger_sha256'] = cr.sha(canonical(ledger))
        binding = {'ledger_sha256': cr.sha(canonical(ledger)), 'sequence_sha256': cr.sha(canonical(self.order))}
        ls.create(canonical(ledger), canonical(self.order), self.sequence_path,
                  ledger_pin=binding['ledger_sha256'], sequence_pin=binding['sequence_sha256'])
        self.ctx = deepcopy(self.fx.ctx)
        self.ctx['schema_version'] = 2
        self.ctx['sequence_binding'] = binding
        self.ctx['evidence_manifests']['sequence'] = cr.sha((self.sequence_path/'COMPLETE.json').read_bytes())

    def reverse(self):
        self.order['entries'][0]['position'], self.order['entries'][1]['position'] = 1, 0
        self.refresh_sequence()

    def inputs(self):
        return {**self.fx.captured(), 'sequence': cr.capture(self.sequence_path)}

    def result(self, at=None):
        return cr.evaluate(self.fx.c, self.ctx, self.inputs(), at=at or self.fx.at)

    def external_paths(self):
        return (self.fx.store('candidate-reference.json', self.fx.c),
                self.fx.store('ordered-context-reference.json', self.ctx))

    def create(self):
        c, ctx = self.external_paths()
        return cr.create_case(c, ctx, self.fx.paths['programs'], self.fx.paths['static'],
                              self.fx.paths['balances'], self.out, sequence_path=self.sequence_path, at=self.fx.at)

    def verify(self, at=None, context=None):
        return cr.verify_case(self.out, expected_candidate=self.fx.c, expected_context=context or self.ctx,
                              at=at or self.fx.at)

    def reseal(self, name, mutate):
        p = self.out/name
        value = strict_json(p.read_bytes()); mutate(value); raw = canonical(value); p.write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = cr.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def cli(self, args):
        return subprocess.run([sys.executable, '-B', '-m', 'superhunter', *map(str,args)],
                              cwd=cr.ROOT.parent, capture_output=True, text=True, timeout=30)

    def test_full_ordered_case_remains_a_human_review(self):
        r = self.result()
        self.assertEqual(r['schema_version'], 2)
        self.assertEqual(r['status'], 'CASE_REVIEW_REQUIRED')
        self.assertTrue(r['sequence_required'] and r['ordered_model_checked'])
        self.assertEqual(r['components']['sequence']['steps_applied'], 2)
        for key, expected in cr.LIMITS.items():
            self.assertEqual(r[key], expected)
        self.assertFalse(r['order_authenticated'])
        self.assertIn('same_canonical_ledger', r['link_checks'])

    def test_equal_totals_wrong_order_blocks_v2_not_v1(self):
        self.reverse()
        legacy = cr.evaluate(self.fx.c, self.fx.ctx, self.fx.captured(), at=self.fx.at)
        self.assertEqual(legacy['status'], 'CASE_REVIEW_REQUIRED')
        self.assertFalse(legacy['ordered_model_checked'])
        result = self.result()
        self.assertEqual(result['components']['balances']['status'], 'ACCOUNTING_RECONCILED')
        self.assertEqual(result['status'], 'CASE_REVIEW_BLOCKED')
        self.assertIn('DECLARED_SEQUENCE_CONTRADICTION', result['blocked_reasons'])
        self.assertEqual(result['components']['sequence']['steps_applied'], 0)
        self.assertFalse(result['vulnerability_confirmed'])

    def test_all_four_verifiers_really_called(self):
        with patch.object(cr.programs, 'verify_registry', wraps=cr.programs.verify_registry) as p, \
             patch.object(cr.static_review, 'verify_report', wraps=cr.static_review.verify_report) as s, \
             patch.object(cr.accounting, 'verify_bundle', wraps=cr.accounting.verify_bundle) as a, \
             patch.object(cr.ledger_sequence, 'verify', wraps=cr.ledger_sequence.verify) as seq:
            self.result()
        self.assertEqual([p.call_count,s.call_count,a.call_count,seq.call_count], [1,1,1,1])

    def test_budget_exhaustion_never_becomes_success(self):
        self.order['steps_budget'] = 1; self.refresh_sequence()
        r = self.result()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('ORDERED_LEDGER_INCOMPLETE', r['incomplete_reasons'])
        self.assertEqual(r['components']['sequence']['steps_not_attempted'], 1)

    def test_zero_budget_checks_no_movements(self):
        self.order['steps_budget'] = 0; self.refresh_sequence()
        r = self.result()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertEqual(r['components']['sequence']['steps_attempted'], 0)

    def test_unknown_order_does_not_choose_one(self):
        self.order['order_coverage'] = 'unknown'; self.refresh_sequence()
        r = self.result()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertEqual(r['components']['sequence']['steps_applied'], 0)

    def test_incomplete_flows_do_not_prove_contradiction(self):
        self.fx.ledger['flow_coverage'] = 'declared_incomplete'
        self.fx.refresh_balances(); self.reverse()
        r = self.result()
        self.assertEqual(r['status'], 'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('ACCOUNTING_COVERAGE_INCOMPLETE',r['incomplete_reasons'])
        self.assertFalse(r['vulnerability_confirmed'])

    def test_foreign_valid_ledger_is_rejected(self):
        different = deepcopy(self.fx.ledger); different['case_id'] = 'other-case'
        self.refresh_sequence(foreign=different)
        self.assertEqual(ls.verify(self.sequence_path, ledger_pin=self.ctx['sequence_binding']['ledger_sha256'],
                                  sequence_pin=self.ctx['sequence_binding']['sequence_sha256'])['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        with self.assertRaisesRegex(cr.CaseError, 'SEQUENCE_LEDGER_MISMATCH'):
            self.result()

    def test_different_block_hash_in_valid_sequence_is_rejected(self):
        different = deepcopy(self.fx.ledger); different['subject']['anchor']['block_hash'] = '0x'+'c'*64
        self.refresh_sequence(foreign=different)
        with self.assertRaisesRegex(cr.CaseError, 'SEQUENCE_LEDGER_MISMATCH'):
            self.result()

    def test_different_balances_with_same_subject_are_rejected(self):
        different = deepcopy(self.fx.ledger)
        different['before']['usd6']['vault'] = '11'; different['after']['usd6']['vault'] = '4'
        self.refresh_sequence(foreign=different)
        with self.assertRaisesRegex(cr.CaseError,'SEQUENCE_LEDGER_MISMATCH'):
            self.result()

    def test_missing_sequence_group_is_not_silently_optional(self):
        with self.assertRaisesRegex(cr.CaseError, 'CAPTURED_GROUPS'):
            cr.evaluate(self.fx.c,self.ctx,self.fx.captured(),at=self.fx.at)

    def test_legacy_profile_rejects_extra_sequence_group(self):
        with self.assertRaisesRegex(cr.CaseError, 'CAPTURED_GROUPS'):
            cr.evaluate(self.fx.c,self.fx.ctx,self.inputs(),at=self.fx.at)

    def test_v2_context_requires_both_sequence_pins(self):
        self.ctx['sequence_binding'].pop('sequence_sha256')
        with self.assertRaisesRegex(cr.CaseError, 'SEQUENCE_BINDING_SCHEMA'):
            self.result()

    def test_v2_context_requires_sequence_manifest(self):
        self.ctx['evidence_manifests'].pop('sequence')
        with self.assertRaisesRegex(cr.CaseError,'EVIDENCE_GROUPS'):
            self.result()

    def test_invalid_pin_types_and_boolean_version_rejected(self):
        for key in ('ledger_sha256','sequence_sha256'):
            old=self.ctx['sequence_binding'][key]
            self.ctx['sequence_binding'][key] = True
            with self.assertRaisesRegex(cr.CaseError, 'SEQUENCE_BINDING_HASH'): self.result()
            self.ctx['sequence_binding'][key]=old
        for bad in (True, 0, 3, 2.0, '2'):
            self.ctx['schema_version']=bad
            with self.assertRaisesRegex(cr.CaseError,'CONTEXT_VERSION'):self.result()

    def test_changed_sequence_hash_rejected(self):
        self.ctx['sequence_binding']['sequence_sha256']='0'*64
        with self.assertRaises(ValueError):self.result()

    def test_sequence_manifest_hash_rejected(self):
        self.ctx['evidence_manifests']['sequence']='0'*64
        with self.assertRaisesRegex(cr.CaseError, 'EVIDENCE_PIN_MISMATCH'):self.result()

    def test_same_ledger_other_order_is_distinct_external_context(self):
        good=cr.sha(canonical(self.ctx));self.reverse()
        self.assertNotEqual(good,cr.sha(canonical(self.ctx)))
        self.assertEqual(self.ctx['sequence_binding']['ledger_sha256'],cr.sha(canonical(self.fx.ledger)))

    def test_scope_denial_overrides_correct_sequence(self):
        self.fx.policy['status']='paused';self.fx.refresh_policy();self.refresh_sequence()
        r=self.result()
        self.assertEqual(r['components']['sequence']['status'], 'LEDGER_SEQUENCE_CONSISTENT')
        self.assertEqual(r['status'],'CASE_REVIEW_BLOCKED')
        self.assertIn('PROGRAM_INACTIVE',r['blocked_reasons'])

    def test_expiry_is_rechecked_with_the_ordered_case(self):
        self.create()
        r=self.verify(at=(self.fx.now+timedelta(hours=13)).isoformat())
        self.assertEqual(r['status'],'CASE_REVIEW_BLOCKED')
        self.assertIn('SNAPSHOT_EXPIRED',r['current_review']['blocked_reasons'])
        self.assertEqual(r['historical_status'],'CASE_REVIEW_REQUIRED')

    def test_unknown_price_stays_inconclusive_with_good_order(self):
        self.fx.ledger['prices']={};self.fx.refresh_balances();self.refresh_sequence()
        r=self.result()
        self.assertEqual(r['status'],'CASE_REVIEW_INCONCLUSIVE')
        self.assertIn('ACCOUNTING_VALUATION_INCOMPLETE',r['incomplete_reasons'])

    def test_aggregate_verifier_disagreement_blocks(self):
        original_verify=ls.verify
        def contradictory(*args, **kwargs):
            return {**original_verify(*args,**kwargs),'aggregate_status':'ACCOUNTING_INCONCLUSIVE'}
        with patch.object(ls,'verify',side_effect=contradictory),self.assertRaisesRegex(cr.CaseError,'SEQUENCE_AGGREGATE_DISAGREEMENT'):
            self.result()

    def test_unknown_sequence_verdict_rejected(self):
        original_verify=ls.verify
        with patch.object(ls,'verify',side_effect=lambda *a,**k:{**original_verify(*a,**k),'status':'PASS'}), \
             self.assertRaisesRegex(cr.CaseError,'UNKNOWN_SEQUENCE_VERDICT'):
            self.result()

    def test_false_complete_summary_rejected(self):
        original_verify=ls.verify
        with patch.object(ls,'verify',side_effect=lambda *a,**k:{**original_verify(*a,**k),'full_replay_complete':False}), \
             self.assertRaisesRegex(cr.CaseError,'SEQUENCE_COMPLETION_DISAGREEMENT'):
            self.result()

    def test_verifier_output_must_preserve_external_pin(self):
        original_verify=ls.verify
        with patch.object(ls,'verify',side_effect=lambda *a,**k:{**original_verify(*a,**k),'sequence_sha256':'f'*64}), \
             self.assertRaisesRegex(cr.CaseError,'SEQUENCE_VERIFIER_BINDING'):
            self.result()

    def test_roundtrip_retains_original_bytes(self):
        before=self.inputs();self.create();r=self.verify()
        self.assertEqual(r['status'],'CASE_REVIEW_REQUIRED')
        self.assertEqual(before,self.inputs())
        for group,data in before.items():
            for name,raw in data.items():
                self.assertEqual((self.out/(group+'--'+name)).read_bytes(),raw)

    def test_external_context_prevents_profile_downgrade(self):
        self.create()
        with self.assertRaisesRegex(cr.CaseError,'EXTERNAL_REFERENCE_MISMATCH'):
            self.verify(context=self.fx.ctx)
        self.reseal('context.json',lambda d:d.update(schema_version=1))
        with self.assertRaisesRegex(cr.CaseError,'EXTERNAL_REFERENCE_MISMATCH'):
            self.verify()

    def test_resealed_success_cannot_hide_wrong_order(self):
        self.reverse();self.create()
        self.reseal('case.json',lambda d:d.update(status='CASE_REVIEW_REQUIRED',blocked_reasons=[]))
        with self.assertRaisesRegex(cr.CaseError,'CASE_REPLAY_MISMATCH'):
            self.verify()

    def test_resealed_order_authentication_claim_rejected(self):
        self.create();self.reseal('case.json',lambda d:d.update(order_authenticated=True))
        with self.assertRaisesRegex(cr.CaseError,'CASE_REPLAY_MISMATCH'):self.verify()

    def test_audit_binds_both_ordered_inputs(self):
        r=self.create();audit=strict_json((self.out/'audit.json').read_bytes())
        links=[e for e in audit['entries'] if e['event']=='case.sequence.bind']
        self.assertEqual(len(links),1)
        self.assertEqual(links[0]['data'],self.ctx['sequence_binding'])
        groups=[e['data']['kind'] for e in audit['entries'] if e['event']=='case.evidence']
        self.assertEqual(groups,list(cr.ORDERED_GROUPS))
        self.assertEqual(r['sequence_binding'],self.ctx['sequence_binding'])

    def test_source_identity_includes_order_verifier(self):
        self.assertIn('ledger_sequence.py',cr.engine()['sources'])

    def test_v2_create_requires_sequence_argument_without_output(self):
        c,ctx=self.external_paths()
        with self.assertRaisesRegex(cr.CaseError,'SEQUENCE_ARGUMENT_PROFILE_MISMATCH'):
            cr.create_case(c,ctx,self.fx.paths['programs'],self.fx.paths['static'],self.fx.paths['balances'],self.out,at=self.fx.at)
        self.assertFalse(self.out.exists())

    def test_v1_create_forbids_ignored_sequence_argument(self):
        c=self.fx.store('legacy-c.json',self.fx.c);ctx=self.fx.store('legacy-ctx.json',self.fx.ctx)
        with self.assertRaisesRegex(cr.CaseError,'SEQUENCE_ARGUMENT_PROFILE_MISMATCH'):
            cr.create_case(c,ctx,self.fx.paths['programs'],self.fx.paths['static'],self.fx.paths['balances'],self.out,
                           at=self.fx.at,sequence_path=self.sequence_path)
        self.assertFalse(self.out.exists())

    def test_no_network_no_process_no_poc_execution(self):
        with patch('socket.socket',side_effect=AssertionError('no network')),patch('subprocess.run',side_effect=AssertionError('no process')):
            self.create();self.verify()

    def test_private_permissions_and_summary(self):
        self.create()
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        for path in self.out.iterdir():self.assertEqual(path.stat().st_mode & 0o777,0o600)
        text=(self.out/'REVIEW.md').read_text()
        self.assertIn('LEDGER_SEQUENCE_CONSISTENT',text)
        self.assertNotIn(self.fx.c['target']['repo'],text)
        self.assertNotIn(self.fx.c['poc_path'],text)

    def test_extra_artifact_and_no_overwrite(self):
        self.create()
        with self.assertRaises(cr.CaseError):self.create()
        (self.out/'untracked.txt').write_text('extra')
        with self.assertRaises(ValueError):self.verify()

    def test_cli_real_create_verify_and_blocked_variant(self):
        c,ctx=self.external_paths()
        args=['review-case','--candidate',c,'--context',ctx,'--programs',self.fx.paths['programs'],
              '--static',self.fx.paths['static'],'--balances',self.fx.paths['balances'],
              '--sequence',self.sequence_path,'--out',self.out]
        p=self.cli(args)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=self.cli(['verify-case','--bundle',self.out,'--candidate',c,'--context',ctx])
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.reverse();self.external_paths();new=self.root/'blocked-cli';args[-1]=new
        p=self.cli(args)
        self.assertEqual(p.returncode,1,p.stdout+p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'],'CASE_REVIEW_BLOCKED')

    def test_cli_missing_sequence_does_not_create_case(self):
        c,ctx=self.external_paths()
        p=self.cli(['review-case','--candidate',c,'--context',ctx,'--programs',self.fx.paths['programs'],
                    '--static',self.fx.paths['static'],'--balances',self.fx.paths['balances'],'--out',self.out])
        self.assertEqual(p.returncode,2,p.stdout+p.stderr)
        self.assertFalse(self.out.exists())

    def test_cli_embedded_reference_cannot_bypass_expected_context(self):
        self.create()
        p=self.cli(['verify-case','--bundle',self.out,'--candidate',self.out/'candidate.json','--context',self.out/'context.json'])
        self.assertEqual(p.returncode,2)

    def test_quality_requires_order_and_cross_identity_tests(self):
        self.assertIn('ledger_sequence',quality.COMPONENTS['case_review']['depends'])
        self.assertIn('test_ordered_case.',quality.COMPONENTS['case_review']['tests'])
        self.assertIn('test_ordered_case.OrderedCaseTests.test_foreign_valid_ledger_is_rejected',quality.REQUIRED_TESTS)


if __name__ == '__main__':
    unittest.main()
