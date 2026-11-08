"""Synthetic receipt/schema regressions; these tests are not native evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_correct_evm_cases as cases
from superhunter import owned_correct_cross_evm as cross
from superhunter import owned_correct_spec_worker as eels_worker
from superhunter import owned_authority_evm_cases as old_cases
from superhunter import quality
from superhunter.safe_io import canonical


def synthetic_execution(engine, digest):
    """Fabricated observations only, with no compiler or EVM execution."""
    builds = [{'variant': 'correct', 'codegen': codegen,
        'source_sha256': cases.sha(cases.owned_source('correct').encode()),
        'input_sha256': cases.sha(canonical(cases.compile_input('correct', codegen))),
        'output_sha256': '1'*64, 'creation_sha256': '2'*64, 'runtime_sha256': '3'*64}
        for codegen in cases.CODEGEN]
    constructors, rows = [], []
    for case, codegen in cases.inventory():
        constructors.append({'case_id': case['case_id'], 'codegen': codegen,
            'initial_state': deepcopy(cases.INITIAL), 'runtime_sha256': '3'*64})
        previous = deepcopy(cases.INITIAL); expected = cases.expected_states(case)
        for index, item in enumerate(cases.schedule(case['events'])):
            following = deepcopy(previous if item['probe'] else expected[item['event_index']])
            obs = {'before': deepcopy(previous), 'after': following, 'word': item['word'], 'gas': item['gas'],
                'status': 'OUT_OF_GAS' if item['probe'] else 'COMMITTED',
                'return_data': '0x' if item['probe'] else '0x' + format(following['accepted'], '064x')}
            row = {'case_id': case['case_id'], 'codegen': codegen, 'call_index': index,
                   'event_index': item['event_index'], 'probe': item['probe'], 'observation': obs}
            if engine == 'geth': row.update(state_root='4'*64, stdout_sha256='5'*64)
            rows.append(row); previous = following
    result = {'schema_version': 1, 'profile': cases.PROFILE, 'source_digest': digest,
        'engine': engine, 'fork': 'Cancun', 'solc_sha256': cases.compiler.PIN['sha256'],
        'builds': builds, 'constructors': constructors, 'rows': rows,
        'compiler_runs': 2, 'constructor_executions': 32, 'runtime_calls': 116}
    if engine == 'geth': result['geth_sha256'] = cases.evm.PIN['sha256']
    else: result['dependencies'] = {name: {k: pin[k] for k in ('version', 'files', 'runtime_sha256')}
                                   for name, pin in cross.PINS.items()}
    return result


class CorrectNativeTests(unittest.TestCase):
    def setUp(self):
        self.digest = quality.sha(canonical(quality.source_snapshot()))
        self.geth = synthetic_execution('geth', self.digest)
        self.eels = synthetic_execution('execution-specs', self.digest)

    def test_fixed_correct_profile_has_two_builds_thirty_two_runs_and_all_probes(self):
        self.assertEqual(cases.VARIANTS, ('correct',))
        self.assertEqual(len(cases.fixed_cases()), 16)
        self.assertEqual(len(cases.inventory()), 32)
        self.assertEqual(sum(len(cases.schedule(case['events'])) for case,_ in cases.inventory()), 116)
        self.assertEqual(sum(item['probe'] for case,_ in cases.inventory()
                             for item in cases.schedule(case['events'])), 32)
        self.assertNotEqual(cases.PROFILE, old_cases.PROFILE)

    def test_only_correct_source_and_fixed_codegen_are_accepted(self):
        self.assertEqual(cases.owned_source('correct'), old_cases.owned_source('correct'))
        for variant in ('revoke_noop', 'stale_credential', '', None):
            with self.assertRaisesRegex(ValueError, 'ONLY_CORRECT_SOURCE'): cases.owned_source(variant)
            with self.assertRaisesRegex(ValueError, 'ONLY_CORRECT_SOURCE'):
                cases.compile_owned(b'not-a-compiler', variant, 'legacy')
        with self.assertRaises(ValueError): cases.compile_input('correct', 'arbitrary')

    def test_fixed_corpus_cannot_be_replaced(self):
        rows = cases.inputs.cases(); rows[0]['events'][0]['credential']['generation'] = 2
        with patch.object(cases.inputs, 'cases', return_value=rows):
            with self.assertRaisesRegex(ValueError, 'CORPUS_IDENTITY'): cases.inventory()

    def test_expected_control_storage_follows_history_and_keeps_other_keys_unchanged(self):
        case = next(c for c in cases.fixed_cases() if c['case_id'] == 'stale_grant_after_regrant_use--present')
        states = cases.expected_states(case)
        self.assertEqual([s['enabled'] for s in states], [1, 0, 1, 1])
        self.assertEqual([s['generations'][0] for s in states], [1, 2, 3, 3])
        self.assertTrue(all(s['generations'][1:] == [0]*7 for s in states))
        self.assertEqual([s['accepted'] for s in states], [1, 1, 1, 0])
        self.assertTrue(all(s['effects'] == [0]*4 for s in states))

    def test_two_decoders_agree_on_all_fixed_states(self):
        for case in cases.fixed_cases():
            for state in cases.expected_states(case):
                raw = bytes([state['phase'], state['accepted'], state['enabled'],
                             *state['generations'], *state['effects']])
                word = int.from_bytes(raw, 'little')
                self.assertEqual(cases.decode_word(word), state)
                self.assertEqual(eels_worker.decode_word(word), state)

    def test_synthetic_schema_match_has_no_detection_or_generalization_claim(self):
        report, traces = cross.compare(self.geth, self.eels, self.digest)
        self.assertEqual((report['case_count'], report['unique_event_sequences']), (16, 13))
        self.assertEqual((report['accepted_use_events'], report['rejected_use_events']), (11, 7))
        self.assertEqual(len(traces['cases']), 16)
        for key in ('detector_evaluated', 'injected_variants_executed', 'historical_detection_metrics_recomputed',
                    'generalization_established', 'independent_producers_proved', 'case_units_pooled',
                    'platform_complete', 'vulnerability_confirmed'):
            self.assertIs(report[key], False)
        self.assertIsNone(report['global_progress'])

    def test_committed_denied_use_remains_false_in_projection(self):
        _, traces = cross.compare(self.geth, self.eels, self.digest)
        row = traces['cases'][0]['trace']['observations'][0]
        self.assertIs(row['accepted'], False)
        non_probe = next(r for r in self.geth['rows'] if not r['probe'])
        self.assertEqual(non_probe['observation']['status'], 'COMMITTED')
        self.assertEqual(non_probe['observation']['return_data'], '0x'+'0'*64)

    def test_legacy_profile_cannot_be_presented_as_new_corpus(self):
        self.geth['profile'] = old_cases.PROFILE
        with self.assertRaisesRegex(ValueError, 'EXECUTION_IDENTITY'): cross.compare(self.geth, self.eels, self.digest)

    def test_wrong_source_tool_and_dependency_identity_are_rejected(self):
        for key in ('source_digest', 'solc_sha256', 'geth_sha256'):
            altered = deepcopy(self.geth); altered[key] = '0'*64
            with self.subTest(field=key):
                with self.assertRaises(ValueError): cross.compare(altered, self.eels, self.digest)
        self.eels['dependencies'] = {}
        with self.assertRaisesRegex(ValueError, 'DEPENDENCIES'): cross.compare(self.geth, self.eels, self.digest)

    def test_boolean_counts_and_short_inventories_are_rejected(self):
        for key in ('compiler_runs', 'constructor_executions', 'runtime_calls'):
            altered = deepcopy(self.geth); altered[key] = True
            with self.assertRaisesRegex(ValueError, 'COUNTS'): cross.compare(altered, self.eels, self.digest)
        self.geth['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'INVENTORY'): cross.compare(self.geth, self.eels, self.digest)

    def test_build_variant_and_source_substitution_are_rejected(self):
        for key, value in [('variant','revoke_noop'), ('source_sha256','0'*64), ('input_sha256','0'*64)]:
            altered=deepcopy(self.geth); altered['builds'][0][key]=value
            with self.assertRaisesRegex(ValueError, 'BUILD_IDENTITY'): cross.compare(altered, self.eels, self.digest)

    def test_constructor_identity_and_initial_storage_are_required(self):
        for key, value in [('case_id','other'),('runtime_sha256','0'*64),('initial_state',{})]:
            altered=deepcopy(self.geth); altered['constructors'][0][key]=value
            with self.assertRaisesRegex(ValueError, 'CONSTRUCTOR_IDENTITY'): cross.compare(altered, self.eels, self.digest)

    def test_reordered_rows_and_boolean_indices_are_rejected(self):
        altered=deepcopy(self.geth); altered['rows'][0],altered['rows'][1]=altered['rows'][1],altered['rows'][0]
        with self.assertRaisesRegex(ValueError, 'ROW_ORDER'): cross.compare(altered,self.eels,self.digest)
        self.geth['rows'][0]['event_index']=False
        with self.assertRaisesRegex(ValueError, 'ROW_ORDER'): cross.compare(self.geth,self.eels,self.digest)

    def test_fixed_word_and_gas_cannot_be_replaced(self):
        for key in ('word','gas'):
            altered=deepcopy(self.geth); altered['rows'][0]['observation'][key]+=1
            with self.assertRaisesRegex(ValueError, 'FIXED_INPUT'): cross.compare(altered,self.eels,self.digest)

    def test_one_gas_probe_cannot_persist_any_state(self):
        self.geth['rows'][0]['observation']['after']['phase']=1
        with self.assertRaisesRegex(ValueError, 'PROBE_PERSISTED'): cross.compare(self.geth,self.eels,self.digest)

    def test_one_gas_probe_cannot_claim_commit(self):
        self.geth['rows'][0]['observation']['status']='COMMITTED'
        with self.assertRaisesRegex(ValueError, 'PROBE_PERSISTED'): cross.compare(self.geth,self.eels,self.digest)

    def test_success_flag_cannot_replace_false_application_return(self):
        self.geth['rows'][1]['observation']['return_data']='0x'+format(1,'064x')
        with self.assertRaisesRegex(ValueError, 'APPLICATION_RETURN'): cross.compare(self.geth,self.eels,self.digest)

    def test_agreeing_engines_with_wrong_permission_storage_are_rejected(self):
        for execution in (self.geth,self.eels): execution['rows'][1]['observation']['after']['enabled']=1
        with self.assertRaisesRegex(ValueError, 'AUTHORED_STORAGE_DISAGREEMENT'):
            cross.compare(self.geth,self.eels,self.digest)

    def test_agreeing_engines_with_wrong_generation_are_rejected(self):
        for execution in (self.geth,self.eels): execution['rows'][1]['observation']['after']['generations'][0]=1
        with self.assertRaisesRegex(ValueError, 'AUTHORED_STORAGE_DISAGREEMENT'):
            cross.compare(self.geth,self.eels,self.digest)

    def test_agreeing_engines_with_wrong_effect_are_rejected(self):
        for execution in (self.geth,self.eels): execution['rows'][1]['observation']['after']['effects'][3]=1
        with self.assertRaisesRegex(ValueError, 'AUTHORED_STORAGE_DISAGREEMENT'):
            cross.compare(self.geth,self.eels,self.digest)

    def test_state_chain_cannot_be_broken(self):
        self.geth['rows'][1]['observation']['before']['accepted']=1
        with self.assertRaisesRegex(ValueError, 'STATE_CHAIN'): cross.compare(self.geth,self.eels,self.digest)

    def test_builds_must_agree_between_engines(self):
        self.eels['builds'][0]['output_sha256']='6'*64
        with self.assertRaisesRegex(ValueError, 'BUILD_DISAGREEMENT'): cross.compare(self.geth,self.eels,self.digest)

    def test_model_disagreement_is_not_hidden_by_native_agreement(self):
        with patch.object(cross.behavior, '_evaluate', return_value=([], [])):
            with self.assertRaisesRegex(ValueError, 'AUTHORED_MODEL_DISAGREEMENT'):
                cross.compare(self.geth,self.eels,self.digest)


class CorrectNativeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'native'
        self.digest=quality.sha(canonical(quality.source_snapshot()))
        self.solc,self.geth=Path('/unused/solc'),Path('/unused/evm')
        self.calls=[]
        def worker(engine,solc,geth,digest):
            self.calls.append(engine)
            return synthetic_execution(engine,digest)
        self.worker=patch.object(cross,'_run_worker',side_effect=worker)
        self.worker.start();self.addCleanup(self.worker.stop)

    def make(self): return cross.create(self.root,self.solc,self.geth,self.digest)
    def verify(self): return cross.verify(self.root,self.solc,self.geth,self.digest)
    def reseal(self):
        (self.root/'COMPLETE.json').write_bytes(canonical({'schema_version':1,'sha256':{
            name:quality.sha((self.root/name).read_bytes()) for name in cross.FILES}}))

    def test_verifier_requests_two_fresh_native_worker_runs(self):
        report=self.make();self.assertEqual(self.verify(),report)
        self.assertEqual(self.calls,['geth','execution-specs','geth','execution-specs'])

    def test_worker_failure_prevents_complete_bundle(self):
        with patch.object(cross,'_run_worker',side_effect=ValueError('native failed')):
            with self.assertRaisesRegex(ValueError,'native failed'):self.make()
        self.assertFalse(self.root.exists())

    def test_changed_historical_cases_block_execution(self):
        old=cross.behavior.historical.cases();old[-1]['truth']='negative'
        with patch.object(cross.behavior.historical,'cases',return_value=old):
            with self.assertRaisesRegex(ValueError,'HISTORICAL_IDENTITY'):self.make()
        self.assertEqual(self.calls,[])

    def test_resealed_false_detection_claim_is_rejected(self):
        report=self.make();report['detector_evaluated']=True
        (self.root/'comparison.json').write_bytes(canonical(report));self.reseal()
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.verify()

    def test_resealed_observation_is_rejected(self):
        self.make();data=json.loads((self.root/'geth.json').read_text())
        data['rows'][1]['observation']['after']['accepted']=1
        (self.root/'geth.json').write_bytes(canonical(data));self.reseal()
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.verify()

    def test_reexecution_failure_cannot_be_replaced_by_saved_receipt(self):
        self.make()
        with patch.object(cross,'_run_worker',side_effect=ValueError('replay unavailable')):
            with self.assertRaisesRegex(ValueError,'replay unavailable'):self.verify()

    def test_source_and_hash_mismatch_are_rejected(self):
        self.make()
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):
            cross.verify(self.root,self.solc,self.geth,'0'*64)
        (self.root/'REVIEW.md').write_text('changed')
        with self.assertRaisesRegex(ValueError,'BUNDLE_HASH'):self.verify()

    def test_missing_extra_and_symlinked_evidence_are_rejected(self):
        self.make();extra=self.root/'extra';extra.write_text('x')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.verify()
        extra.unlink();path=self.root/'geth.json';raw=path.read_bytes();path.unlink()
        outside=Path(self.temp.name)/'outside';outside.write_bytes(raw);path.symlink_to(outside)
        with self.assertRaises((OSError,ValueError)):self.verify()

    def test_marker_mutation_during_replay_is_rejected(self):
        self.make();execute=cross._execute
        def changed(*args):
            payload=execute(*args);(self.root/'COMPLETE.json').write_text('{}');return payload
        with patch.object(cross,'_execute',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'EVIDENCE_CHANGED_DURING_REPLAY'):self.verify()

    def test_existing_and_repository_output_are_rejected(self):
        self.make()
        with self.assertRaisesRegex(ValueError,'NEW_PRIVATE_OUTPUT'):self.make()
        with self.assertRaisesRegex(ValueError,'NEW_PRIVATE_OUTPUT'):
            cross.create(cross.ROOT/'unwanted',self.solc,self.geth,self.digest)

    def test_component_and_worker_registration(self):
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])
        self.assertEqual(sum('test_owned_correct_cross_evm' in group for group in QA_MODULE_GROUPS),1)
        self.assertEqual(len(quality.COMPONENTS['owned_correct_cross_evm']['files']),5)


if __name__=='__main__':unittest.main()
