"""Bounded logic and tamper controls; native Geth acceptance runs separately.

Mocks in this suite isolate orchestration. They are never presented as EVM
execution; the acceptance script invokes real solc and Geth without mocks.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from superhunter import evm_coverage_guidance as g
from superhunter import evm_sequence_fuzz as f
from superhunter.safe_io import canonical, strict_json


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def minimal(self, *, pc=10, edge='7:taken'):
        return {name:{profile:{'pcs':[pc],'edges':[edge],'outcomes':{'COMMITTED':4},
                   'trace_sha256':'a'*64,'final_state':{'debit':15,'credit':0,'steps':3}}
                      for profile in f.PROFILES} for name in f.CONTROLS}

    def fake_report(self):
        return {'status':'OWNED_EVM_GUIDANCE_OBSERVED','source_digest':'0'*64,
                'seed':20261105,'candidates':2,'cases':[
                    {'case_index':0,'sequence_sha256':'1'*64,'observations':{}}],
                'runtime_calls':48,'observed_feature_count':2,'novel_features_after_baseline':0,
                'vulnerability_confirmed':False}

    def test_default_baseline_is_fixed_benign(self):
        self.assertEqual(g.BASELINE,[[0,g.evm.GAS]]*4)
        self.assertIsNot(g.BASELINE[0],g.BASELINE[1])

    def test_bounded_mutations(self):
        start=deepcopy(g.BASELINE)
        proposed,why=g.next_mutation(start,1,20261105)
        self.assertEqual(proposed[0][0],16)
        self.assertEqual(proposed[1:],start[1:])
        self.assertEqual(why['field'],'quantity')
        self.assertEqual(start,g.BASELINE)
        second,record=g.next_mutation(proposed,2,20261105)
        self.assertEqual(second[3][1],1)
        self.assertEqual(record['operation_index'],3)
        last,_=g.next_mutation(second,3,20261105)
        self.assertEqual(last[1][0],255)

    def test_feedback_seed_changes_gas_position(self):
        even,_=g.next_mutation(g.BASELINE,2,20261106)
        odd,_=g.next_mutation(g.BASELINE,2,20261105)
        self.assertEqual(even[2][1],1)
        self.assertEqual(odd[3][1],1)

    def test_parent_selection_uses_trace_novelty(self):
        history=[{'features':{'pc:a','pc:b','pc:c'},'new_features':{'pc:a','pc:b','pc:c'}},
                 {'features':{'pc:c','pc:d'},'new_features':{'pc:d'}},
                 {'features':{'pc:a'},'new_features':set()}]
        self.assertEqual(g.choose_parent(history),1)
        self.assertEqual(g.choose_parent(history[:1]),0)

    def test_more_actual_novelty_outweighs_rarity(self):
        cases=[{'features':{'a','b','c'},'new_features':{'a','b','c'}},
               {'features':{'x'},'new_features':{'x'}},
               {'features':{'y','z'},'new_features':{'y','z'}}]
        self.assertEqual(g.choose_parent(cases),2)

    def test_no_novelty_does_not_claim_progress(self):
        cases=[{'features':{'p'},'new_features':{'p'}},
               {'features':{'p'},'new_features':set()}]
        self.assertEqual(g.choose_parent(cases),0)

    def test_features_separated_by_control_and_compilation(self):
        data=self.minimal()
        output=g.case_features(data)
        self.assertEqual(len(output),8)
        self.assertIn('delayed_credit|ir_optimized|jumpi:7:taken',output)
        data['delayed_credit']['ir_optimized']['pcs']=[10,12]
        self.assertEqual(len(g.case_features(data)),9)

    def test_indeterminate_jump_not_fabricated_taken(self):
        data=self.minimal(edge='7:indeterminate')
        out=g.case_features(data)
        self.assertNotIn('conservation|legacy_unoptimized|jumpi:7:taken',out)
        self.assertIn('conservation|legacy_unoptimized|jumpi:7:indeterminate',out)

    def test_no_unverified_program_or_profile_allowed(self):
        data=self.minimal()
        data['unknown']=data['conservation']
        with self.assertRaisesRegex(g.GuidanceError,'CONTROL_INVENTORY'):g.case_features(data)
        data=self.minimal();data['conservation'].pop('ir_optimized')
        with self.assertRaisesRegex(g.GuidanceError,'PROFILE_INVENTORY'):g.case_features(data)

    def test_pc_immediates_not_fabricated(self):
        data=self.minimal();data['conservation']['legacy_unoptimized']['pcs']=[10,10]
        with self.assertRaisesRegex(g.GuidanceError,'OBSERVED_PC_SCHEMA'):g.case_features(data)

    def test_invalid_edge_not_counted(self):
        data=self.minimal();data['conservation']['legacy_unoptimized']['edges']=['7:magical']
        with self.assertRaisesRegex(g.GuidanceError,'OBSERVED_EDGE_SCHEMA'):g.case_features(data)

    def test_bounded_budget_rejects_bool_and_zero(self):
        for seed,cases in [(True,1),(0,True),(0,0),(0,4),(-1,1),(2**64,1)]:
            with self.subTest(seed=seed,cases=cases),self.assertRaises(g.GuidanceError):
                g.validate(seed,cases)

    def test_foreign_raw_case_rejected(self):
        for wrong in ([],[[255,g.evm.GAS]]*3,[[256,g.evm.GAS]]*4,
                      [[0,0]]*4,[[True,g.evm.GAS]]*4):
            with self.subTest(case=wrong),self.assertRaises(g.GuidanceError):
                g.next_mutation(wrong,1,20261105)

    def test_repeated_mutation_changes_input(self):
        candidate=deepcopy(g.BASELINE);candidate[0][0]=16
        next_case,_=g.next_mutation(candidate,1,20261105)
        self.assertEqual(next_case[0][0],15)

    def test_empty_feedback_rejected(self):
        with self.assertRaisesRegex(g.GuidanceError,'EMPTY_FEEDBACK'):g.choose_parent([])
        with self.assertRaisesRegex(g.GuidanceError,'FEEDBACK_SCHEMA'):g.choose_parent([{'features':[]}])

    def test_source_hash_gate_runs_before_binaries(self):
        with patch.object(g.compiler,'read_pinned_binary',side_effect=AssertionError('must not run')):
            with self.assertRaisesRegex(g.GuidanceError,'SOURCE_DIGEST_MISMATCH'):
                g.execute(Path('/NO_SOLC'),Path('/NO_EVM'),'0'*64)

    def test_public_cli_has_no_arbitrary_target_option(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stderr,self.assertRaises(SystemExit):
            g.main(['guide-owned-evm','--target','https://private.test','--seed','1'])
        self.assertNotIn('private.test',stderr.getvalue())

    def test_no_existing_directory_overwrite(self):
        self.root.joinpath('used').mkdir()
        with self.assertRaisesRegex(g.GuidanceError,'PRIVATE_NEW_DIRECTORY_REQUIRED'):
            g.create(self.root/'used',Path('/solc'),Path('/evm'),'0'*64)

    def test_resealed_result_cannot_pass_replay(self):
        original=self.fake_report()
        with patch.object(g,'execute',return_value=original):
            g.create(self.root/'bundle',Path('/solc'),Path('/evm'),'0'*64)
        root=self.root/'bundle'
        report=strict_json((root/'guided-observations.json').read_bytes())
        report['vulnerability_confirmed']=True
        raw=canonical(report);(root/'guided-observations.json').write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256']['guided-observations.json']=hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))
        with patch.object(g,'execute',return_value=original),self.assertRaisesRegex(g.GuidanceError,'REPLAY_DISAGREEMENT'):
            g.verify(root,Path('/solc'),Path('/evm'),'0'*64)

    def test_reseal_audit_does_not_pass(self):
        fake=self.fake_report()
        with patch.object(g,'execute',return_value=fake):
            g.create(self.root/'case',Path('/solc'),Path('/evm'),'0'*64)
        root=self.root/'case'
        x=strict_json((root/'audit.json').read_bytes());x['producer_authenticated']=True
        raw=canonical(x);(root/'audit.json').write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256']['audit.json']=g.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))
        with patch.object(g,'execute',return_value=fake),self.assertRaisesRegex(g.GuidanceError,'REPLAY_DISAGREEMENT'):
            g.verify(root,Path('/solc'),Path('/evm'),'0'*64)

    def test_originals_are_private_and_unchanged(self):
        fake=self.fake_report()
        with patch.object(g,'execute',return_value=fake):
            result=g.create(self.root/'case',Path('/solc'),Path('/evm'),'0'*64)
            self.assertEqual(g.verify(self.root/'case',Path('/solc'),Path('/evm'),'0'*64)['status'],
                             'OWNED_EVM_GUIDANCE_REPLAY_VERIFIED')
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertEqual((self.root/'case').stat().st_mode&0o777,0o700)
        for p in (self.root/'case').iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_source_report_explicitly_avoids_complete_coverage(self):
        report=self.fake_report()
        text=g._render(report).decode()
        self.assertIn('No se demuestra cobertura completa',text)
        self.assertIn('Solo contratos de prueba propios',text)


if __name__=='__main__':unittest.main()
