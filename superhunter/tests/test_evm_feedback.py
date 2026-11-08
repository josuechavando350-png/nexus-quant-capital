"""Synthetic feedback unit tests; native Geth+solc validation is separate.

The fabricated rows below exercise pure reduction and FAIL-CLOSED handling.
They are never presented as new EVM executions or security discoveries.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_feedback as feedback
from superhunter import evm_sequence_fuzz as fuzz
from superhunter.safe_io import canonical, strict_json


class EVMFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.out=self.root/'feedback'
        self.original=self.root/'not-a-real-native-bundle'
        self.expected='a'*64
        self.solc=self.root/'no-solc'
        self.evm=self.root/'no-evm'
        self.run=self.fixture()

    def fixture(self):
        sequences=fuzz.corpus(20261105,9)
        controls={}
        for name in fuzz.CONTROLS:
            profiles={}
            for profile in fuzz.PROFILES:
                runs=[]
                for seq in sequences:
                    state={'debit':15,'credit':0,'steps':0};steps=[]
                    for quantity,gas in seq:
                        expected=fuzz.verify_oracles(name,state,quantity,gas)
                        step={'quantity':quantity,'gas':gas,'outcome':expected['status'],
                              'state_before':dict(state),'state_after':dict(expected['state']),
                              'return_data':expected['return_data'],'error':expected['error'],
                              'observed_state_root':feedback.sha(canonical(expected['state']))}
                        steps.append(step);state=dict(expected['state'])
                    runs.append({'sequence_sha256':feedback.sha(canonical(seq)),
                                 'steps':steps,'final_state':state})
                profiles[profile]={'runs':runs}
            controls[name]={'profiles':profiles}
        return {'schema_version':1,'profile':fuzz.PROFILE,'seed':20261105,
                'cases_per_control':9,'calls_per_sequence':fuzz.STEPS,
                'executions':9*fuzz.STEPS*len(fuzz.CONTROLS)*len(fuzz.PROFILES),
                'constructor_executions':len(fuzz.CONTROLS)*len(fuzz.PROFILES),
                'source_digest':self.expected,'sequences':sequences,'controls':controls}

    def feedback(self):
        return feedback.features(self.run)

    def test_greedy_selection_retains_every_observed_feature(self):
        report=self.feedback();all_features=set(report['observed_features'])
        indices=report['selected_indices']
        selected=set().union(*(set(report['per_case_features'][i]['features']) for i in indices))
        self.assertEqual(all_features,selected)
        self.assertLessEqual(len(indices),9)
        for drop in indices:
            smaller=set().union(*(set(report['per_case_features'][i]['features']) for i in indices if i!=drop))
            self.assertNotEqual(smaller,all_features)
        self.assertFalse(report['global_minimum_corpus_proved'])

    def test_assertion_prefix_is_observed_and_reverted(self):
        report=self.feedback()
        self.assertEqual([x['control'] for x in report['witnesses']],['delayed_credit'])
        witness=report['witnesses'][0]
        self.assertEqual(witness['prefix_length'],3)
        self.assertEqual(witness['prefix'], self.run['sequences'][witness['case_index']][:3])
        self.assertTrue(witness['assertion_reverted_and_not_persisted'])
        step=self.run['controls']['delayed_credit']['profiles'][fuzz.PROFILES[0]]['runs'][witness['case_index']]['steps'][2]
        self.assertEqual(step['outcome'],'ASSERTION_REVERT')
        self.assertEqual(step['state_after'],step['state_before'])
        self.assertFalse(report['vulnerability_confirmed'])

    def test_report_marks_no_instruction_or_branch_coverage(self):
        r=self.feedback()
        self.assertFalse(r['evm_instruction_coverage_measured'])
        self.assertFalse(r['evm_branch_coverage_measured'])
        self.assertEqual(r['witness_minimality'],'shortest-observed-prefix-per-control-not-global')

    def test_observed_counts_reflect_only_one_profile(self):
        r=self.feedback()
        self.assertEqual(r['observed_step_count_one_profile'],72)
        self.assertEqual(r['observed_step_count_all_profiles'],144)
        self.assertEqual(sum(r['observed_outcome_counts_one_profile'].values()),72)

    def test_no_native_execution_from_pure_feedback(self):
        with patch.object(fuzz.evm,'_run',side_effect=AssertionError('must not execute')):
            self.assertGreater(self.feedback()['observed_feature_count'],0)

    def test_deterministic_feedback(self):
        self.assertEqual(self.feedback(),feedback.features(deepcopy(self.run)))

    def test_seeded_corpus_binding(self):
        self.run['sequences'][0][0][0]=7
        with self.assertRaisesRegex(feedback.FeedbackError,'CORPUS_NOT_CURRENT_GENERATOR'):
            self.feedback()

    def test_wrong_case_count_rejected(self):
        self.run['cases_per_control']=10
        with self.assertRaises(feedback.FeedbackError):self.feedback()

    def test_missing_control_rejected(self):
        del self.run['controls']['conservation']
        with self.assertRaisesRegex(feedback.FeedbackError,'CONTROL_INVENTORY'):self.feedback()

    def test_missing_codegen_profile_rejected(self):
        del self.run['controls']['conservation']['profiles'][fuzz.PROFILES[1]]
        with self.assertRaisesRegex(feedback.FeedbackError,'PROFILE_INVENTORY'):self.feedback()

    def test_missing_case_rejected(self):
        self.run['controls']['conservation']['profiles'][fuzz.PROFILES[0]]['runs'].pop()
        with self.assertRaisesRegex(feedback.FeedbackError,'CASE_INVENTORY'):self.feedback()

    def test_missing_step_rejected(self):
        self.run['controls']['conservation']['profiles'][fuzz.PROFILES[0]]['runs'][0]['steps'].pop()
        with self.assertRaisesRegex(feedback.FeedbackError,'STEP_INVENTORY'):self.feedback()

    def test_missing_step_field_rejected(self):
        self.run['controls']['conservation']['profiles'][fuzz.PROFILES[0]]['runs'][0]['steps'][0].pop('outcome')
        with self.assertRaises(feedback.FeedbackError):self.feedback()

    def test_false_production_panic_rejected(self):
        for profile in fuzz.PROFILES:
            row=self.run['controls']['conservation']['profiles'][profile]['runs'][0]['steps'][0]
            row['outcome']='ASSERTION_REVERT'
        with self.assertRaisesRegex(feedback.FeedbackError,'OBSERVABLE_REFERENCE_DISAGREEMENT'):
            self.feedback()

    def test_codegen_observation_mismatch_rejected(self):
        x=self.run['controls']['delayed_credit']['profiles'][fuzz.PROFILES[1]]['runs'][0]['steps'][2]
        x['state_after']['debit']+=1
        with self.assertRaisesRegex(feedback.FeedbackError,'OBSERVABLE_CODEGEN_DISAGREEMENT'):self.feedback()

    def test_wrong_sequence_sha_rejected(self):
        self.run['controls']['conservation']['profiles'][fuzz.PROFILES[0]]['runs'][0]['sequence_sha256']='0'*64
        with self.assertRaisesRegex(feedback.FeedbackError,'SEQUENCE_IDENTITY'):self.feedback()

    def test_wrong_final_state_rejected(self):
        self.run['controls']['conservation']['profiles'][fuzz.PROFILES[0]]['runs'][0]['final_state']['credit']=99
        with self.assertRaisesRegex(feedback.FeedbackError,'CASE_FINAL_STATE_DISAGREEMENT'):self.feedback()

    def test_boolean_not_a_valid_step_quantity(self):
        for p in fuzz.PROFILES:
            self.run['controls']['conservation']['profiles'][p]['runs'][0]['steps'][0]['quantity']=True
        with self.assertRaisesRegex(feedback.FeedbackError,'OBSERVABLE_STEP_SCHEMA'):self.feedback()

    def test_negative_storage_rejected(self):
        for p in fuzz.PROFILES:
            self.run['controls']['conservation']['profiles'][p]['runs'][0]['steps'][0]['state_after']['debit']=-1
        with self.assertRaisesRegex(feedback.FeedbackError,'OBSERVABLE_STEP_SCHEMA'):self.feedback()

    def test_feature_includes_qualitative_input_class(self):
        report=self.feedback();names=report['observed_features']
        self.assertTrue(any('input=forced-low-gas' in k for k in names))
        self.assertTrue(any('input=above-balance' in k for k in names))
        self.assertTrue(any('input=zero-quantity' in k for k in names))

    def test_selected_case_hashes_are_exact(self):
        r=self.feedback()
        self.assertEqual(r['selected_case_hashes'],[feedback.sha(canonical(self.run['sequences'][i]))
                                                    for i in r['selected_indices']])

    def test_created_audit_binds_features_and_native_source(self):
        r=self.feedback();b={'schema_version':1,'native_source_digest':self.expected,
                             'native_artifact_sha256':{'sequences.json':'0'*64}}
        a=strict_json(feedback._audit(r,b,'2026-11-05T00:00:00+00:00'))
        self.assertEqual(a['entries'][0]['event'],'evm.coverage.start')
        self.assertEqual(a['entries'][-1]['event'],'evm.coverage.complete')
        self.assertFalse(a['remote_producer_authenticated'])

    def test_summary_does_not_claim_security(self):
        text=feedback._render(self.feedback()).decode()
        self.assertIn('NO cobertura de PC/opcodes',text)
        self.assertIn('NO es pérdida persistente',text)

    def test_resealed_false_coverage_claim_rejected(self):
        report=self.feedback();binding={'schema_version':1,'native_source_digest':self.expected,
                                        'native_artifact_sha256':{'sequences.json':'0'*64}}
        with patch.object(feedback,'_observe',return_value=(report,binding)):
            result=feedback.create(self.original,self.solc,self.evm,self.expected,self.out)
            self.assertEqual(result['status'],'NATIVE_OBSERVABLE_FEEDBACK_VERIFIED')
            target=self.out/'feedback.json';value=strict_json(target.read_bytes())
            value['evm_instruction_coverage_measured']=True
            raw=canonical(value);target.write_bytes(raw)
            marker=strict_json((self.out/'COMPLETE.json').read_bytes())
            marker['sha256']['feedback.json']=feedback.sha(raw)
            (self.out/'COMPLETE.json').write_bytes(canonical(marker))
            with self.assertRaisesRegex(feedback.FeedbackError,'NATIVE_FEEDBACK_REPLAY_DISAGREEMENT'):
                feedback.verify(self.out,self.original,self.solc,self.evm,self.expected)

    def test_resealed_favorable_witness_rejected(self):
        report=self.feedback();b={'schema_version':1,'native_source_digest':self.expected,
                                   'native_artifact_sha256':{'result.json':'a'*64}}
        with patch.object(feedback,'_observe',return_value=(report,b)):
            feedback.create(self.original,self.solc,self.evm,self.expected,self.out)
            target=self.out/'feedback.json';data=strict_json(target.read_bytes())
            data['witnesses'][0]['prefix_length']=1
            blob=canonical(data);target.write_bytes(blob)
            marker=strict_json((self.out/'COMPLETE.json').read_bytes())
            marker['sha256']['feedback.json']=feedback.sha(blob)
            (self.out/'COMPLETE.json').write_bytes(canonical(marker))
            with self.assertRaises(feedback.FeedbackError):
                feedback.verify(self.out,self.original,self.solc,self.evm,self.expected)

    def test_existing_output_not_overwritten(self):
        self.out.mkdir()
        with self.assertRaisesRegex(feedback.FeedbackError,'OUTPUT_MUST_BE_NEW_AND_PRIVATE'):
            feedback.create(self.original,self.solc,self.evm,self.expected,self.out)

    def test_empty_external_bundle_blocks_before_output(self):
        with self.assertRaises((ValueError,OSError)):
            feedback.create(self.original,self.solc,self.evm,self.expected,self.out)
        self.assertFalse(self.out.exists())

    def test_cli_unknown_argument_sanitized(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            feedback.main(['verify-evm-feedback','--bundle','PRIVATE','--bad','SECRET'])
        self.assertNotIn('SECRET',stream.getvalue())

    def test_cli_missing_native_bundle_fails_closed(self):
        with redirect_stdout(io.StringIO()) as stream:
            code=feedback.main(['verify-evm-feedback','--bundle',str(self.root/'PRIVATE'),
                                '--native-bundle',str(self.original),'--solc',str(self.solc),
                                '--evm',str(self.evm),'--expected-source',self.expected])
        self.assertEqual(code,2)
        self.assertNotIn('PRIVATE',stream.getvalue())

    def test_cli_entrypoint_wired(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','verify-evm-feedback','--bundle',str(self.out),
                               '--native-bundle',str(self.original),'--solc',str(self.solc),
                               '--evm',str(self.evm),'--expected-source',self.expected]),redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),2)

    def test_qa_component_and_mandatory_tests_present(self):
        from superhunter import quality
        self.assertIn('evm_feedback',quality.COMPONENTS)
        self.assertIn('test_evm_feedback.EVMFeedbackTests.test_resealed_false_coverage_claim_rejected',quality.REQUIRED_TESTS)

    def test_native_mutation_during_replay_is_rejected(self):
        native=self.root/'native';native.mkdir()
        names=fuzz.FILES|{'COMPLETE.json'}
        for name in names:(native/name).write_bytes(b'before')
        def tamper(*args):
            (native/'sequences.json').write_bytes(b'after')
        with patch.object(fuzz,'replay',side_effect=tamper),self.assertRaisesRegex(
                feedback.FeedbackError,'NATIVE_ARTIFACT_CHANGED'):
            feedback._observe(native,self.solc,self.evm,self.expected)

    def test_own_program_only(self):
        r=self.feedback()
        self.assertEqual(r['controls'],list(fuzz.CONTROLS))
        self.assertFalse(r['external_target_executed'])
        self.assertFalse(r['independent_evm_used'])


if __name__=='__main__':unittest.main()
