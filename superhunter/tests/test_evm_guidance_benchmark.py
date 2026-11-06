"""Deterministic non-network comparison and tamper tests.

Synthetic observations below are fixtures for orchestration only, NOT EVM traces.
Real solc/Geth calls are executed separately by CLI acceptance.
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

from superhunter import evm_guidance_benchmark as b
from superhunter import evm_coverage_guidance as g
from superhunter import evm_sequence_fuzz as f
from superhunter.safe_io import canonical, strict_json


class GuidanceBenchmarkTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.seed=20261105
        self.digest='a'*64

    def _observation(self, pc: int) -> dict:
        return {control:{profile:{'pcs':[10,pc] if pc!=10 else [10],
                    'edges':['7:fallthrough'], 'outcomes':{'COMMITTED':f.STEPS},
                    'trace_sha256':'b'*64,
                    'final_state':{'debit':15,'credit':0,'steps':f.STEPS}}
                    for profile in f.PROFILES} for control in f.CONTROLS}

    def fixtures(self, *, guided_pcs=(10,11,12), fixed_pcs=(10,11,10)):
        guides=[];fixed=[];seen=set()
        for i,(gp,fp) in enumerate(zip(guided_pcs,fixed_pcs)):
            sequence,gm=(deepcopy(g.BASELINE),None) if i==0 else g.next_mutation(g.BASELINE,i,self.seed)
            if i==2:
                sequence,gm=g.next_mutation(g.next_mutation(g.BASELINE,1,self.seed)[0],2,self.seed)
            guides.append({'case_index':i, 'parent_index':None if i==0 else i-1,
                           'sequence':sequence,'sequence_sha256':b.digest(canonical(sequence)),
                           'mutation':gm,'observations':self._observation(gp)})
            other,meta=(deepcopy(g.BASELINE),None) if i==0 else b.fixed_parent_proposal(i,self.seed)
            fixed.append({'case_index':i,'parent_index':None if i==0 else 0,
                          'sequence':other,'sequence_sha256':b.digest(canonical(other)),
                          'mutation':meta,'observations':self._observation(fp)})
        guided_report={'profile':g.PROFILE,'status':'OWNED_EVM_GUIDANCE_OBSERVED',
                       'source_digest':self.digest,'seed':self.seed,'candidates':2,
                       'vulnerability_confirmed':False,'cases':guides,
                       'runtime_calls':48, 'observed_feature_count':len(set().union(*(
                           g.case_features(c['observations']) for c in guides))),
                       'novel_features_after_baseline':len(set().union(*(
                           g.case_features(c['observations']) for c in guides))-
                           g.case_features(guides[0]['observations']))}
        return guided_report, fixed

    def result(self):
        a,bb=self.fixtures()
        return b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_shared_baseline_and_budget(self):
        r=self.result()
        self.assertEqual(r['budget']['calls_per_arm'],48)
        self.assertEqual(r['budget']['total_calls'],96)
        self.assertTrue(all(r['fairness'].values()))
        self.assertEqual(r['guided']['summary']['baseline_features'],r['fixed_parent']['summary']['baseline_features'])
        self.assertFalse(r['statistical_superiority_proven'])

    def test_fixed_parent_ignores_feedback(self):
        first,meta=b.fixed_parent_proposal(1,self.seed)
        second,record=b.fixed_parent_proposal(2,self.seed)
        self.assertEqual(first[0][0],16)
        self.assertEqual(second[3][1],1)
        self.assertEqual(second[0][0],0)
        directed,_=g.next_mutation(first,2,self.seed)
        self.assertEqual(directed[0][0],16)
        self.assertNotEqual(directed,second)
        self.assertIn('without-feedback',record['origin'])

    def test_difference_is_counted_without_optimism(self):
        self.assertEqual(self.result()['guided_minus_fixed_features'],4)
        a,bb=self.fixtures(guided_pcs=(10,11,10),fixed_pcs=(10,11,12))
        r=b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)
        self.assertEqual(r['guided_minus_fixed_features'],-4)
        self.assertFalse(r['improved_detection_proven'])

    def test_equal_result_is_not_statistical_success(self):
        a,bb=self.fixtures(guided_pcs=(10,11,10),fixed_pcs=(10,11,10))
        r=b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)
        self.assertEqual(r['guided_minus_fixed_features'],0)
        self.assertFalse(r['statistical_superiority_proven'])

    def test_baseline_mismatch_rejected(self):
        a,bb=self.fixtures();bb[0]['observations']=self._observation(17)
        with self.assertRaisesRegex(b.ComparisonError,'BASELINE_OR_BUDGET_MISMATCH'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_missing_case_rejected(self):
        a,bb=self.fixtures();bb.pop()
        with self.assertRaisesRegex(b.ComparisonError,'UNEQUAL_CASE_BUDGET'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_wrong_call_counts_rejected(self):
        a,bb=self.fixtures();a['runtime_calls']=47
        with self.assertRaisesRegex(b.ComparisonError,'BASELINE_OR_BUDGET_MISMATCH'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_wrong_control_case_mutation_rejected(self):
        a,bb=self.fixtures();bb[2]['sequence'][1][0]=14
        with self.assertRaisesRegex(b.ComparisonError,'FIXED_CONTROL_NOT_REPRODUCIBLE'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_mismatched_recipe_rejected(self):
        a,bb=self.fixtures();bb[1]['mutation']['field']='gas'
        with self.assertRaisesRegex(b.ComparisonError,'UNEQUAL_MUTATION_RECIPES'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_ungrounded_guided_coverage_rejected(self):
        a,bb=self.fixtures();a['observed_feature_count']=987654
        with self.assertRaisesRegex(b.ComparisonError,'GUIDED_COVERAGE_MISMATCH'):
            b.compare_reports(a,bb,expected_source=self.digest,seed=self.seed,candidates=2)

    def test_wrong_source_digest_rejected(self):
        a,bb=self.fixtures()
        with self.assertRaisesRegex(b.ComparisonError,'GUIDED_EVIDENCE_PROFILE'):
            b.compare_reports(a,bb,expected_source='f'*64,seed=self.seed,candidates=2)

    def test_boolean_seed_budget_rejected(self):
        for seed,cases in [(True,2),(2,False),(-1,2),(0,0),(0,4)]:
            with self.subTest(seed=seed,cases=cases),self.assertRaises(ValueError):
                b.validate_parameters(seed,cases,self.digest)

    def test_missing_source_fails_before_solc_or_evm(self):
        with patch.object(b.guided,'execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(b.ComparisonError,'SOURCE_DIGEST_MISMATCH'):
                b.execute(Path('/no-solc'),Path('/no-evm'),'0'*64)

    def test_fake_coverage_after_hash_reseal_rejected(self):
        self._fake_tamper('guided_minus_fixed_features',999999)

    def test_resealed_favorable_claim_rejected(self):
        self._fake_tamper('statistical_superiority_proven',True)

    def _fake_tamper(self,key,value):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            b.create(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                     seed=self.seed,candidates=2)
        root=self.root/'bundle';data=strict_json((root/'comparison.json').read_bytes())
        data[key]=value
        raw=canonical(data);(root/'comparison.json').write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256']['comparison.json']=b.digest(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))
        with patch.object(b,'execute',return_value=fake),self.assertRaisesRegex(
                 b.ComparisonError,'NATIVE_REPLAY_DISAGREEMENT'):
            b.verify(root,Path('/solc'),Path('/evm'),self.digest,
                     expected_seed=self.seed,expected_candidates=2)

    def test_new_output_only(self):
        self.root.joinpath('existing').mkdir()
        with self.assertRaisesRegex(b.ComparisonError,'PRIVATE_NEW_DIRECTORY_REQUIRED'):
            b.create(self.root/'existing',Path('/solc'),Path('/evm'),self.digest)

    def test_external_parameters_required(self):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            b.create(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                     seed=self.seed,candidates=2)
        with patch.object(b,'execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(b.ComparisonError,'EXPECTED_CONTEXT_MISMATCH'):
                b.verify(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                         expected_seed=self.seed+1,expected_candidates=2)

    def test_roundtrip_verifies_same_source(self):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            b.create(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                     seed=self.seed,candidates=2)
            result=b.verify(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                            expected_seed=self.seed,expected_candidates=2)
        self.assertEqual(result['status'],'OWNED_EVM_COMPARISON_REPLAY_VERIFIED')
        self.assertEqual(result['calls'],96)

    def test_private_bundle_and_no_console_secret(self):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(b.main(['compare-owned-evm','--solc','/private/source',
                     '--evm','/private/evm','--expected-source',self.digest,
                     '--out',str(self.root/'bundle')]),0)
        self.assertNotIn('/private/',stream.getvalue())
        self.assertEqual((self.root/'bundle').stat().st_mode&0o777,0o700)
        for p in (self.root/'bundle').iterdir():
            self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_cli_rejects_foreign_target_without_echo(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            b.main(['compare-owned-evm','--target','https://private.example',
                    '--expected-source',self.digest])
        self.assertNotIn('private.example',stream.getvalue())

    def test_unexpected_extra_file_rejected(self):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            b.create(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                     seed=self.seed,candidates=2)
        (self.root/'bundle/secret').write_text('untracked')
        with patch.object(b,'execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(b.ComparisonError,'BUNDLE_FILE_SET'):
                b.verify(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                         expected_seed=self.seed,expected_candidates=2)

    def test_omit_audit_rejected_before_execution(self):
        fake=self.result()
        with patch.object(b,'execute',return_value=fake):
            b.create(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                     seed=self.seed,candidates=2)
        (self.root/'bundle/audit.json').unlink()
        with patch.object(b,'execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(b.ComparisonError,'BUNDLE_FILE_SET'):
                b.verify(self.root/'bundle',Path('/solc'),Path('/evm'),self.digest,
                         expected_seed=self.seed,expected_candidates=2)

    def test_render_does_not_claim_detected_bug(self):
        text=b._render(self.result()).decode()
        self.assertIn('NO mide recall',text)
        self.assertIn('presupuesto',text)


if __name__=='__main__':
    unittest.main()
