"""Schema/oracle unit tests with DECLARED SYNTHETIC EVM-shaped records.

These are NOT native executions. Native acceptance uses the actual solc/Geth
executables through score-owned-evm and verify-owned-evm-score separately.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_mutation_evaluation as score
from superhunter import evm_pause_family as pause, evm_access_family as access
from superhunter import quality
from superhunter.safe_io import canonical, strict_json


def fake_native(family: str, code_digest: str) -> dict:
    """Reconstruct test-only transitions using explicit local reference models."""
    module = pause if family == 'pause' else access
    cases,builds = {},{}
    for variant in module.VARIANTS:
        cases[variant]={};builds[variant]={}
        for compiler in module.CODEGEN:
            records=[]
            for index, scenario in enumerate(module.SEQUENCES):
                previous=({'remaining':15,'distributed':0,'paused':0} if family=='pause' else
                          {'admin':access.evm.SENDER,'remaining':10,'distributed':0})
                calls=[]
                for step, expected in enumerate(scenario):
                    if family=='pause':
                        operation,amount,gas = expected
                        ref=module.reference(variant,previous,operation,amount,gas)
                        bad=module.unauthorized_effect(previous,ref['state'],operation,amount,ref['status'])
                        row={'step':step,'operation':operation,'amount':amount,'gas':gas,
                             'paused_release_persisted':bad}
                    else:
                        caller,amount,gas = expected
                        ref=module.reference(variant,previous,caller,amount,gas)
                        bad=module.unauthorized_effect(caller,amount,ref['status'],previous,ref['state'])
                        row={'step':step,'caller':caller,'amount':amount,'gas':gas,
                             'unauthorized_effect':bad}
                    calls.append({**row,'status':ref['status'],'before':deepcopy(previous),
                                  'after':deepcopy(ref['state'])})
                    previous=ref['state']
                records.append({'case':index,'calls':calls,'final_state':deepcopy(previous)})
            cases[variant][compiler]=records
            builds[variant][compiler]={
                'source_sha256':score.sha(module.owned_source(variant).encode()),
                'runtime_sha256':score.sha((family+'-'+variant+'-'+compiler).encode())}
    return {'profile':module.PROFILE,'source_digest':code_digest,
            **({'known_intentional_fixture':True} if family=='pause' else {'known_intentional_mutation':True}),
            'vulnerability_confirmed':False,
            'solc_sha256':'1'*64,'evm_sha256':'2'*64,
            'cases':cases,'builds':builds}


class KnownMutationScoreTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.digest=score.sha(canonical(quality.source_snapshot()))
        self.pause=fake_native('pause',self.digest)
        self.access=fake_native('access',self.digest)
        self.a=self.root/'bundle'

    def assess(self):
        return score.analyze(self.pause,self.access,self.digest)

    def create(self):
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)):
            return score.create(self.a,self.root/'not-solc',self.root/'not-evm',self.digest)

    def reseal(self,name,edit):
        path=self.a/name
        value=strict_json(path.read_bytes())
        edit(value)
        raw=canonical(value);path.write_bytes(raw)
        marker=strict_json((self.a/'COMPLETE.json').read_bytes())
        marker['sha256'][name]=score.sha(raw)
        (self.a/'COMPLETE.json').write_bytes(canonical(marker))

    def test_four_cases_not_eight(self):
        x=self.assess()
        self.assertEqual(x['case_count'],4)
        self.assertEqual(len(x['observations']),4)
        self.assertEqual(len(x['corpus']['cases']),4)
        self.assertTrue(all(v['compiler_correlations']==2 for v in x['observations']))
        self.assertEqual(x['metrics']['overall']['counts']['tp'],2)
        self.assertEqual(x['metrics']['overall']['counts']['tn'],2)
        self.assertFalse(x['blind_benchmark'])
        self.assertFalse(x['generalization_established'])
        self.assertFalse(x['vulnerability_confirmed'])

    def test_observed_effect_independent_from_truth_labels(self):
        before=self.assess()
        with patch.dict(score.TRUTH,{('pause','guard_missing'):'negative'}):
            after=self.assess()
        self.assertEqual([x['status'] for x in before['observations']],
                         [x['status'] for x in after['observations']])
        self.assertEqual(after['metrics']['overall']['counts']['fp'],1)
        self.assertEqual(before['metrics']['overall']['counts']['fp'],0)

    def test_labels_are_known_not_blind(self):
        x=self.assess()
        self.assertEqual(x['metrics']['overall']['recall_all_positives']['value'],1.0)
        self.assertTrue(x['labels_known_to_developers'])
        self.assertFalse(x['negative_decision_proves_absence_of_bugs'])
        self.assertFalse(x['severity_labels_represent_real_impact'])
        self.assertFalse(x['metrics']['economic_cost_measured'])
        self.assertFalse(x['metrics']['wall_clock_benchmarked'])

    def test_known_pause_mutant_observed_persistent_effect(self):
        x=self.assess()
        positives=[r for r in x['observations'] if r['family']=='pause' and r['status']=='positive']
        self.assertEqual(len(positives),1)
        self.assertGreater(len(positives[0]['witnesses']),0)

    def test_known_access_mutant_observed_guest_effect(self):
        x=self.assess()
        positives=[r for r in x['observations'] if r['family']=='access' and r['status']=='positive']
        self.assertEqual(len(positives),1)
        self.assertGreater(len(positives[0]['witnesses']),0)

    def test_not_count_reverts_as_mutations(self):
        for family, result, variant in [('pause',self.pause,'guarded'),('access',self.access,'protected')]:
            for compilation in ('legacy','ir_optimized'):
                calls=result['cases'][variant][compilation][0]['calls']
                self.assertTrue(any(c['status']=='REVERTED' for c in calls))
        self.assertEqual(sum(o['status']=='positive' for o in self.assess()['observations']),2)

    def test_codegen_results_must_agree(self):
        calls=self.pause['cases']['guard_missing']['ir_optimized'][0]['calls']
        target=calls[1]
        target['status']='REVERTED';target['after']=deepcopy(target['before'])
        target['paused_release_persisted']=False
        with self.assertRaises(score.OwnedScoreError):self.assess()

    def test_source_mismatch_blocks(self):
        self.access['source_digest']='3'*64
        with self.assertRaisesRegex(score.OwnedScoreError,'SOURCE_DIGEST_DISAGREEMENT'):self.assess()

    def test_binary_mismatch_blocks(self):
        self.access['evm_sha256']='3'*64
        with self.assertRaisesRegex(score.OwnedScoreError,'TOOL_IDENTITY_DISAGREEMENT'):self.assess()

    def test_no_missing_scenario_silently_dropped(self):
        self.pause['cases']['guarded']['legacy'].pop()
        with self.assertRaisesRegex(score.OwnedScoreError,'SCENARIO_COVERAGE'):self.assess()

    def test_missing_compiler_corroboration_blocks(self):
        self.access['cases']['protected'].pop('legacy')
        with self.assertRaisesRegex(score.OwnedScoreError,'COMPILER_VARIANT_COVERAGE'):self.assess()

    def test_changed_build_source_blocks(self):
        self.pause['builds']['guarded']['legacy']['source_sha256']='4'*64
        with self.assertRaisesRegex(score.OwnedScoreError,'SOURCE_VARIANT_MISMATCH'):self.assess()

    def test_wrong_caller_is_not_silently_accepted(self):
        self.access['cases']['missing_auth_guard']['legacy'][0]['calls'][0]['caller']=access.evm.SENDER
        with self.assertRaisesRegex(score.OwnedScoreError,'UNEXPECTED_ACCESS_INPUT'):self.assess()

    def test_wrong_pause_operation_is_not_silently_accepted(self):
        self.pause['cases']['guard_missing']['legacy'][0]['calls'][0]['operation']='release'
        with self.assertRaisesRegex(score.OwnedScoreError,'UNEXPECTED_PAUSE_INPUT'):self.assess()

    def test_flag_forgery_detected(self):
        self.pause['cases']['guard_missing']['legacy'][0]['calls'][1]['paused_release_persisted']=False
        with self.assertRaisesRegex(score.OwnedScoreError,'FLAG_STATE_DISAGREEMENT'):self.assess()

    def test_reverted_call_cannot_count_tentative_transfer(self):
        c=self.access['cases']['protected']['legacy'][0]['calls'][0]
        c['after']['remaining']=8;c['after']['distributed']=2
        with self.assertRaisesRegex(score.OwnedScoreError,'REVERT_COMMITTED_STATE'):self.assess()

    def test_broken_chain_detected(self):
        c=self.pause['cases']['guard_missing']['legacy'][0]['calls'][2]
        c['before']['remaining']=0
        with self.assertRaisesRegex(score.OwnedScoreError,'OBSERVED_STATE_CHAIN'):self.assess()

    def test_wrong_final_state_detected(self):
        self.access['cases']['protected']['legacy'][0]['final_state']['remaining']=4
        with self.assertRaisesRegex(score.OwnedScoreError,'FINAL_STATE_MISMATCH'):self.assess()

    def test_boolean_amount_rejected(self):
        self.pause['cases']['guarded']['legacy'][0]['calls'][0]['amount']=True
        with self.assertRaises(score.OwnedScoreError):self.assess()

    def test_create_package_and_verify_requires_native_reexecution(self):
        self.create()
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)) as run:
            got=score.verify(self.a,self.root/'solc',self.root/'evm',self.digest)
        self.assertEqual(got['status'],'KNOWN_OWNED_EVM_SCORE_REPLAY_VERIFIED')
        run.assert_called_once()

    def test_resealed_favorable_report_rejected(self):
        self.create()
        self.reseal('evaluation.json',lambda x:x['metrics']['overall']['counts'].update(fp=17))
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)) as run:
            with self.assertRaisesRegex(score.OwnedScoreError,'NATIVE_SCORE_REPLAY_DISAGREEMENT'):
                score.verify(self.a,self.root/'solc',self.root/'evm',self.digest)
        run.assert_called_once()

    def test_resealed_corpus_labels_rejected(self):
        self.create()
        self.reseal('corpus.json',lambda x:x['cases'][0].update(truth='positive',severity='low'))
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)):
            with self.assertRaisesRegex(score.OwnedScoreError,'NATIVE_SCORE_REPLAY_DISAGREEMENT'):
                score.verify(self.a,self.root/'solc',self.root/'evm',self.digest)

    def test_resealed_audit_rejected(self):
        self.create()
        self.reseal('audit.json',lambda x:x['entries'][1]['data'].update(sha256='0'*64))
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)):
            with self.assertRaisesRegex(score.OwnedScoreError,'NATIVE_SCORE_REPLAY_DISAGREEMENT'):
                score.verify(self.a,self.root/'solc',self.root/'evm',self.digest)

    def test_existing_output_not_overwritten(self):
        self.create();before=(self.a/'COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(score.OwnedScoreError,'NEW_PRIVATE_OUTPUT_REQUIRED'):
            self.create()
        self.assertEqual((self.a/'COMPLETE.json').read_bytes(),before)

    def test_output_private(self):
        self.create()
        self.assertEqual(self.a.stat().st_mode & 0o777,0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in self.a.iterdir()))

    def test_entrypoint_dispatch_with_mocked_native_producers(self):
        from superhunter import __main__
        with patch.object(score,'_run_native',return_value=(self.pause,self.access)),\
             patch('sys.argv',['superhunter','score-owned-evm','--solc',str(self.root/'solc'),
                                    '--evm',str(self.root/'evm'),'--source-digest',self.digest,
                                    '--out',str(self.a)]),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(__main__.main(),0)
        self.assertEqual(json.loads(out.getvalue())['cases'],4)

    def test_no_candidate_or_network_argument(self):
        import sys
        with patch('sys.stderr',new_callable=io.StringIO) as stderr,self.assertRaises(SystemExit):
            score.main(['score-owned-evm','--solc','p','--evm','p',
                        '--source-digest',self.digest,'--out',str(self.a),'--rpc','PROD_SECRET'])
        self.assertNotIn('PROD_SECRET',stderr.getvalue())


if __name__=='__main__':
    unittest.main()
