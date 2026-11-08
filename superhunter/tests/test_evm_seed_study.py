"""Synthetic orchestration fixtures; native solc/Geth acceptance is separate."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_seed_study as st
from superhunter import evm_coverage_guidance as guidance, evm_sequence_fuzz as fuzz
from superhunter import evm_execution as evm, quality
from superhunter.safe_io import canonical, strict_json

SEEDS = [20261105,20261106]
SOURCE = 'a'*64


def fake_case(prepared, image, sequence):
    """Fake observations ONLY for fast unit tests, never labelled native runs."""
    # Stable input-dependent features, same for both arms given same sequence.
    number = int(st.sha(canonical(sequence))[:5],16) % 100000
    return {control:{profile:{'pcs':[10,number+100], 'edges':['5:fallthrough'],
             'outcomes':{'COMMITTED':fuzz.STEPS},'trace_sha256':'b'*64,
             'final_state':{'debit':15,'credit':0,'steps':fuzz.STEPS}}
             for profile in fuzz.PROFILES} for control in fuzz.CONTROLS}


class SeedStudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.bundle=self.root/'case'

    def sample(self, seeds=SEEDS):
        records=[]
        with patch.object(st,'execute_case',side_effect=fake_case):
            for seed in seeds:
                plan=st.mutation_plan(seed,2)
                records.append({'seed':seed,'plan':plan,
                    'guided':st.run_arm({},b'',plan,guided=True),
                    'fixed_parent':st.run_arm({},b'',plan,guided=False)})
        return st.summarize_study(records,SOURCE,2,{'solc_sha256':'a'*64,'evm_sha256':'b'*64},{})

    def write_mock_bundle(self, report=None):
        report=report or self.sample()
        with patch.object(st,'execute',return_value=report):
            st.create(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)
        return report

    def reseal(self,filename,fn):
        p=self.bundle/filename
        raw=strict_json(p.read_bytes())
        fn(raw)
        out=canonical(raw)
        p.write_bytes(out)
        marker=strict_json((self.bundle/'COMPLETE.json').read_bytes())
        marker['sha256'][filename]=st.sha(out)
        (self.bundle/'COMPLETE.json').write_bytes(canonical(marker))

    def test_seed_changes_full_recipe_not_parity_only(self):
        a=st.mutation_plan(20261105,3)
        b=st.mutation_plan(20261107,3)
        self.assertNotEqual(a,b)
        self.assertNotEqual(st.mutation_plan(20261105,3),st.mutation_plan(20261106,3))

    def test_recipe_deterministic_independent_of_global_random(self):
        self.assertEqual(st.mutation_plan(20261106,3),st.mutation_plan(20261106,3))

    def test_all_slots_can_be_selected_over_seed_range(self):
        observed={(r['step'],r['field']) for i in range(300) for r in st.mutation_plan(i,3)}
        self.assertEqual(len(observed),8)

    def test_no_repeated_toggle_in_one_plan(self):
        for seed in range(20):
            plan=st.mutation_plan(seed,3)
            self.assertEqual(len({(x['step'],x['field']) for x in plan}),3)

    def test_both_arms_use_exact_recipe_and_budget(self):
        report=self.sample()
        self.assertTrue(report['budget_fairness_checked'])
        self.assertEqual(report['total_runtime_calls'],2*2*3*16)
        self.assertEqual(len(report['per_seed']),2)
        for p in report['per_seed']:
            self.assertEqual(p['guided']['runtime_calls'],p['fixed_parent']['runtime_calls'])
        self.assertFalse(report['statistical_superiority_proven'])

    def test_guided_parent_is_recomputed_from_feedback(self):
        r=self.sample();a=r['paired_observation_data'][0]['guided']
        self.assertEqual(a[2]['parent_index'],1)

    def test_baseline_is_observed_in_each_arm(self):
        r=self.sample()
        for row in r['paired_observation_data']:
            self.assertEqual(row['guided'][0]['sequence'],guidance.BASELINE)
            self.assertEqual(row['fixed_parent'][0]['sequence'],guidance.BASELINE)
            self.assertEqual(row['guided'][0]['observations'],row['fixed_parent'][0]['observations'])

    def test_fixed_parent_does_not_follow_coverage(self):
        r=self.sample()
        self.assertEqual([x['parent_index'] for x in r['paired_observation_data'][0]['fixed_parent']],[None,0,0])

    def test_mutation_toggles_only_selected_field(self):
        before=deepcopy(guidance.BASELINE)
        result=st.mutate(before,{'step':2,'field':'gas'})
        self.assertEqual(before,guidance.BASELINE)
        self.assertEqual(result[2][1],1)
        self.assertEqual(st.mutate(result,{'step':2,'field':'gas'}),guidance.BASELINE)

    def test_quantity_mutation_independent_of_gas(self):
        result=st.mutate(guidance.BASELINE,{'step':0,'field':'quantity'})
        self.assertEqual(result[0],[16,evm.GAS])
        self.assertEqual(st.mutate(result,{'step':0,'field':'quantity'}),guidance.BASELINE)

    def test_seed_types_and_bounds(self):
        for bad in (True,-1,2**64,1.2,'3'):
            with self.subTest(bad=bad),self.assertRaises(st.StudyError):st.mutation_plan(bad,2)

    def test_seed_list_requires_sorted_unique(self):
        for bad in ([1,1],[2,1],[1],[0,2**64],[False,1],['1',2],list(range(5))):
            with self.subTest(bad=bad),self.assertRaises(st.StudyError):
                st.validate_parameters(bad,2,SOURCE)

    def test_budget_requires_2_or_3(self):
        for bad in (0,1,4,True,2.0):
            with self.subTest(bad=bad),self.assertRaises(st.StudyError):
                st.validate_parameters(SEEDS,bad,SOURCE)

    def test_external_source_digest_required(self):
        with self.assertRaises(st.StudyError):st.validate_parameters(SEEDS,2,'UNKNOWN')

    def test_same_parity_seeds_still_have_distinct_plans(self):
        self.assertNotEqual(st.mutation_plan(20261105,2),st.mutation_plan(20261107,2))

    def test_study_rejects_forged_guided_parent(self):
        r=self.sample();raw=deepcopy(r['paired_observation_data'])
        raw[0]['guided'][2]['parent_index']=0
        with self.assertRaises(st.StudyError):
            st.summarize_study(raw,SOURCE,2,r['engine_pins'],{})

    def test_study_rejects_forged_novelty(self):
        r=self.sample();raw=deepcopy(r['paired_observation_data'])
        raw[0]['guided'][1]['new_feature_count']=9999
        with self.assertRaises(st.StudyError):
            st.summarize_study(raw,SOURCE,2,r['engine_pins'],{})

    def test_study_rejects_unequal_budget(self):
        r=self.sample();raw=deepcopy(r['paired_observation_data']);raw[0]['fixed_parent'].pop()
        with self.assertRaises(st.StudyError):
            st.summarize_study(raw,SOURCE,2,r['engine_pins'],{})

    def test_study_rejects_forged_baseline(self):
        r=self.sample();raw=deepcopy(r['paired_observation_data']);raw[0]['fixed_parent'][0]['sequence'][0][0]=16
        with self.assertRaises(st.StudyError):
            st.summarize_study(raw,SOURCE,2,r['engine_pins'],{})

    def test_study_rejects_forged_recipe(self):
        r=self.sample();raw=deepcopy(r['paired_observation_data']);raw[0]['plan'][0]['step']=999
        with self.assertRaises(st.StudyError):
            st.summarize_study(raw,SOURCE,2,r['engine_pins'],{})

    def test_study_does_not_claim_new_vulnerability(self):
        r=self.sample()
        self.assertFalse(r['vulnerability_discovered'])
        self.assertFalse(r['full_instruction_coverage_proven'])
        self.assertFalse(r['network_used'])

    def test_created_bundle_is_private_and_self_contained(self):
        report=self.write_mock_bundle()
        self.assertEqual(self.bundle.stat().st_mode&0o777,0o700)
        for f in self.bundle.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
        with patch.object(st,'execute',return_value=report):
            out=st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                          seeds=SEEDS,mutations=2)
        self.assertEqual(out['status'],'OWNED_EVM_MULTISEED_REPLAY_VERIFIED')

    def test_resealed_superiority_claim_rejected(self):
        report=self.write_mock_bundle()
        self.reseal('study.json',lambda v:v.update(statistical_superiority_proven=True))
        with patch.object(st,'execute',return_value=report),self.assertRaisesRegex(st.StudyError,'NATIVE_MULTISEED_REPLAY_DISAGREEMENT'):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)

    def test_resealed_coverage_difference_rejected(self):
        report=self.write_mock_bundle()
        self.reseal('study.json',lambda v:v['per_seed'][0].update(coverage_delta=123))
        with patch.object(st,'execute',return_value=report),self.assertRaises(st.StudyError):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)

    def test_audit_tamper_and_reseal_rejected(self):
        report=self.write_mock_bundle()
        self.reseal('audit.json',lambda v:v['entries'][0]['data'].update(mutations=99))
        with patch.object(st,'execute',return_value=report),self.assertRaises(st.StudyError):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)

    def test_expected_seeds_cannot_be_changed_by_bundle(self):
        report=self.write_mock_bundle()
        with patch.object(st,'execute',return_value=report),self.assertRaisesRegex(st.StudyError,'EXTERNAL_CONTEXT_MISMATCH'):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=[20261105,20261107],mutations=2)

    def test_missing_file_rejected(self):
        report=self.write_mock_bundle();(self.bundle/'study.json').unlink()
        with patch.object(st,'execute',return_value=report),self.assertRaises((OSError,ValueError)):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)

    def test_extra_file_rejected(self):
        report=self.write_mock_bundle();(self.bundle/'extra').write_bytes(b'ignored')
        with patch.object(st,'execute',return_value=report),self.assertRaises(st.StudyError):
            st.verify(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,
                      seeds=SEEDS,mutations=2)

    def test_existing_output_preserved(self):
        self.write_mock_bundle(); before=(self.bundle/'COMPLETE.json').read_bytes()
        with self.assertRaises(st.StudyError):
            st.create(self.bundle,Path('/unused/solc'),Path('/unused/evm'),SOURCE,seeds=SEEDS,mutations=2)
        self.assertEqual((self.bundle/'COMPLETE.json').read_bytes(),before)

    def test_cli_fake_execute_no_network_or_child_process(self):
        r=self.sample()
        args=['study-owned-evm','--solc','unused','--evm','unused',
              '--expected-source',SOURCE,'--seeds','20261105,20261106',
              '--out',str(self.bundle)]
        with patch.object(st,'execute',return_value=r),patch.object(socket,'socket',side_effect=AssertionError),\
             patch.object(subprocess,'run',side_effect=AssertionError),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(st.main(args),0)
        self.assertEqual(json.loads(output.getvalue())['status'],'OWNED_EVM_MULTISEED_CREATED')

    def test_cli_invalid_arguments_cannot_echo_secrets(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            st.main(['study-owned-evm','--unexpected','PRIVATE_SECRET'])
        self.assertNotIn('PRIVATE_SECRET',stream.getvalue())

    def test_native_binaries_are_not_accessed_for_wrong_source_digest(self):
        with patch.object(st.compiler,'read_pinned_binary',side_effect=AssertionError):
            with self.assertRaisesRegex(st.StudyError,'SOURCE_DIGEST_MISMATCH'):
                st.execute(Path('/missing'),Path('/missing'),'0'*64,seeds=SEEDS,mutations=2)

    def test_quality_graph_registers_real_module(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])
        self.assertIn('evm_seed_study',quality.COMPONENTS)


if __name__ == '__main__':unittest.main()
