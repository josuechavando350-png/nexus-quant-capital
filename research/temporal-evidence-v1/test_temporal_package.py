import copy, json, random, tempfile, unittest
from pathlib import Path
from temporal_common import *
import build_temporal_package as builder
import verify_temporal_package as verifier
from synthetic_fixture import make


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def build(self,**kw):
        src=make(self.root/'source',**kw); pkg=self.root/'package'
        report=builder.build(src,src.parent,pkg); return src,pkg,report
    def rehash(self,pkg):
        m=decode((pkg/'manifest.json').read_bytes())
        for rel in m['files']:
            b=(pkg/rel).read_bytes(); m['files'][rel]={'sha256':sha(b),'bytes':len(b)}
        (pkg/'manifest.json').write_bytes(canonical(m))
    def test_actual_episode_reconstruction(self):
        _,p,r=self.build(); v=verifier.verify(p)
        self.assertEqual(r['episode_count'],1); self.assertEqual(r['material_unknown_count'],0)
        e=decode((p/'episodes.jsonl').read_bytes())
        self.assertEqual(e['birth']['block'],101); self.assertEqual(e['terminal']['status'],'RECOVERED'); self.assertEqual(e['lifetime_seconds'],24)
        self.assertFalse(v['terminal_authority']); self.assertFalse(v['real_market_census_closed'])
    def test_left_censoring_keeps_full_lifetime_unknown(self):
        _,p,_=self.build(left=True); verifier.verify(p); e=decode((p/'episodes.jsonl').read_bytes())
        self.assertTrue(e['left_censored']); self.assertIsNone(e['birth']); self.assertIsNone(e['lifetime_seconds']); self.assertEqual(e['observed_duration_seconds'],36)
    def test_right_censoring_requires_end_boundary(self):
        _,p,_=self.build(right=True); verifier.verify(p); e=decode((p/'episodes.jsonl').read_bytes())
        self.assertTrue(e['right_censored']); self.assertIsNone(e['lifetime_seconds']); self.assertIsNone(e['terminal']['order'])
    def test_acquisition_hole_is_not_right_censoring(self):
        _,p,r=self.build(right=True,acquisition_hole=True); verifier.verify(p); e=decode((p/'episodes.jsonl').read_bytes())
        self.assertFalse(e['right_censored']); self.assertEqual(e['terminal']['status'],'EVIDENCE_INSUFFICIENT')
        self.assertGreater(r['material_unknown_count'],0)
    def test_missing_coverage_blocks_produce_explicit_gaps(self):
        _,p,r=self.build(coverage_gap=True); verifier.verify(p)
        gaps=[b for b in r['blockers'] if b['code']=='ACQUISITION_INCOMPLETE']
        self.assertEqual(len(gaps),12); self.assertTrue(all(g['range']==[102,103] for g in gaps))
        self.assertFalse(r['coverage_complete_for_supplied_scope'])
    def test_two_provider_ids_same_operator_does_not_pass(self):
        _,p,r=self.build(same_operator=True); verifier.verify(p)
        self.assertEqual(sum(b['code']=='DUAL_OPERATOR_AUTHORITY_MISSING' for b in r['blockers']),6)
    def test_missing_execution_remains_unknown(self):
        _,p,r=self.build(no_execution=True); verifier.verify(p)
        self.assertTrue(any(b.get('reason')=='HISTORICAL_EXECUTION_ECONOMICS_NOT_SUPPLIED' for b in r['blockers']))
    def test_invalid_historical_authority_hash_rejected(self):
        with self.assertRaisesRegex(Invalid,'SHA-256'): self.build(invalid_execution_hash=True)
    def test_future_economic_evidence_rejected(self):
        with self.assertRaisesRegex(Invalid,'look-ahead'): self.build(future_economics=True)
    def test_insufficient_disposition_not_miscounted_as_zero_unknown(self):
        _,p,r=self.build(disposition='EVIDENCE_INSUFFICIENT'); verifier.verify(p)
        self.assertGreaterEqual(r['material_unknown_count'],1); self.assertFalse(r['coverage_complete_for_supplied_scope'])
    def test_acquisition_disposition_distinct(self):
        _,p,r=self.build(disposition='ACQUISITION_INCOMPLETE'); verifier.verify(p)
        self.assertEqual(r['blockers'][0]['code'],'ACQUISITION_INCOMPLETE')
    def test_proven_zero_debt_negative_can_be_complete(self):
        _,p,r=self.build(disposition='PROVEN_REJECTION'); verifier.verify(p)
        self.assertEqual(r['episode_count'],0); self.assertEqual(r['material_unknown_count'],0); self.assertEqual(r['disposition_count'],1)
    def test_false_negative_rejected(self):
        with self.assertRaises(Invalid): self.build(disposition='PROVEN_REJECTION',false_negative=True)
    def test_relabeling_insufficient_as_proven_fails(self):
        s=make(self.root/'source',disposition='EVIDENCE_INSUFFICIENT'); d=decode(s.read_bytes())
        d['dispositions'][0]['category']='PROVEN_REJECTION'; s.write_bytes(canonical(d))
        with self.assertRaises(Invalid): builder.build(s,s.parent,self.root/'package')
    def test_byte_tampering_fails_before_row_replay(self):
        _,p,_=self.build(); (p/'episodes.jsonl').write_bytes(b'{}\n')
        with self.assertRaisesRegex(Invalid,'digest mismatch'): verifier.verify(p)
    def test_rehashed_forged_lifetime_rejected_by_independent_replay(self):
        _,p,_=self.build(left=True); e=decode((p/'episodes.jsonl').read_bytes()); e['lifetime_seconds']=36
        (p/'episodes.jsonl').write_bytes(canonical(e)); self.rehash(p)
        with self.assertRaisesRegex(Invalid,'reconstruction mismatch'): verifier.verify(p)
    def test_rehashed_forged_complete_summary_rejected(self):
        _,p,_=self.build(coverage_gap=True); r=decode((p/'report.json').read_bytes()); r['material_unknown_count']=0; r['blockers']=[]; r['coverage_complete_for_supplied_scope']=True
        (p/'report.json').write_bytes(canonical(r)); self.rehash(p)
        with self.assertRaisesRegex(Invalid,'report/count/coverage'): verifier.verify(p)
    def test_rehashed_episode_deletion_rejected(self):
        _,p,_=self.build(); (p/'episodes.jsonl').write_bytes(b''); self.rehash(p)
        with self.assertRaisesRegex(Invalid,'reconstruction mismatch'): verifier.verify(p)
    def test_unlisted_file_rejected(self):
        _,p,_=self.build(); (p/'extra.json').write_bytes(b'{}')
        with self.assertRaisesRegex(Invalid,'membership'): verifier.verify(p)
    def test_symlink_rejected(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); h=d['evidence'][0]['path']; real=s.parent/h
        copy_path=s.parent/'copy'; copy_path.write_bytes(real.read_bytes()); real.unlink(); real.symlink_to(copy_path)
        with self.assertRaisesRegex(Invalid,'symlink'): builder.build(s,s.parent,self.root/'package')
    def test_path_traversal_rejected(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); d['evidence'][0]['path']='../escape'; s.write_bytes(canonical(d))
        with self.assertRaisesRegex(Invalid,'unsafe'): builder.build(s,s.parent,self.root/'package')
    def test_boolean_count_rejected(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); d['window']['start_block']=True; s.write_bytes(canonical(d))
        with self.assertRaisesRegex(Invalid,'integer'): builder.build(s,s.parent,self.root/'package')
    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(Invalid,'duplicate JSON'): decode(b'{"x":1,"x":2}')
    def test_input_permutation_preserves_derived_rows(self):
        s,p,_=self.build(); d=decode(s.read_bytes()); rng=random.Random(1516)
        for key in ('state_refs','trigger_refs','coverage_refs','evidence'): rng.shuffle(d[key])
        s.write_bytes(canonical(d)); p2=self.root/'package2'; builder.build(s,s.parent,p2); verifier.verify(p2)
        for f in ('episodes.jsonl','dispositions.jsonl','report.json'): self.assertEqual((p/f).read_bytes(),(p2/f).read_bytes())
    def test_repeat_identical_package_bytes(self):
        s,p,_=self.build(); p2=self.root/'package2'; builder.build(s,s.parent,p2)
        self.assertEqual({x.relative_to(p).as_posix():x.read_bytes() for x in p.rglob('*') if x.is_file()},
                         {x.relative_to(p2).as_posix():x.read_bytes() for x in p2.rglob('*') if x.is_file()})
    def test_refuses_overwrite(self):
        s,p,_=self.build()
        with self.assertRaises(FileExistsError): builder.build(s,s.parent,p)
    def test_current_blocked_input_diagnosis(self):
        source=Path(__file__).resolve().parent/'real-inputs/current-d15b.json'
        r=builder.build(source,source.parent,self.root/'rejected'); self.assertEqual(r['status'],'BLOCKED_REAL_INPUT_INSUFFICIENT')
        self.assertIn('HISTORICAL_EPISODE_REPLAY_NOT_EXECUTED',r['missing_requirements'])
        self.assertFalse((self.root/'rejected'/'manifest.json').exists())
    def test_foundation_format_not_promoted(self):
        d={'schema_version':1,'trigger_universe':['t'],'episodes':[],'rejections':[{'trigger_id':'t','reason':'EVIDENCE_INSUFFICIENT'}]}
        r=diagnose_existing(d); self.assertFalse(r['terminal_authority']); self.assertIn('MISSING_IMMUTABLE_STATE_TRANSITIONS',r['missing_requirements'])
    def test_current_economic_aggregate_diagnosis(self):
        source=Path(__file__).resolve().parent/'real-inputs/current-d16.json'
        r=builder.build(source,source.parent,self.root/'rejected'); self.assertEqual(r['source_format'],'HISTORICAL_RMC016_AGGREGATE')
        self.assertTrue(any('55d5d6be' in m for m in r['missing_requirements']))
    def test_missing_population_bytes_rejected(self):
        s=make(self.root/'source'); d=decode(s.read_bytes())
        d['evidence']=[e for e in d['evidence'] if e['sha256']!=d['scope']['population_commitment']]
        s.write_bytes(canonical(d))
        with self.assertRaisesRegex(Invalid,'missing evidence bytes'): builder.build(s,s.parent,self.root/'package')
    def test_unobserved_population_not_silently_dropped(self):
        _,p,r=self.build(disposition='EVIDENCE_INSUFFICIENT'); verifier.verify(p)
        self.assertIn('UNACCOUNTED_POPULATION_LINEAGE',{b['code'] for b in r['blockers']})
        self.assertEqual(r['population_lineage_count'],1); self.assertEqual(r['observed_population_lineage_count'],0)
    def test_synthetic_source_cannot_be_relabeled_real(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); d['evidence_kind']='REAL_PREPARED_WITNESSES'; s.write_bytes(canonical(d))
        with self.assertRaisesRegex(Invalid,'synthetic evidence'): builder.build(s,s.parent,self.root/'package')
    def test_unaccounted_trigger_blocks(self):
        s=make(self.root/'source',disposition='EVIDENCE_INSUFFICIENT'); d=decode(s.read_bytes()); d['dispositions']=[]; s.write_bytes(canonical(d))
        p=self.root/'package'; r=builder.build(s,s.parent,p); verifier.verify(p)
        self.assertIn('UNACCOUNTED_TRIGGER',{b['code'] for b in r['blockers']})
    def test_fake_complete_marker_never_accepted(self):
        _,p,_=self.build(); m=decode((p/'manifest.json').read_bytes()); m['real_market_census_closed']=True
        (p/'manifest.json').write_bytes(canonical(m))
        with self.assertRaisesRegex(Invalid,'terminal'): verifier.verify(p)
    def test_source_evidence_file_tampering_rejected(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); f=s.parent/d['evidence'][0]['path']; f.write_bytes(f.read_bytes()+b' ')
        with self.assertRaisesRegex(Invalid,'byte/hash mismatch'): builder.build(s,s.parent,self.root/'package')
    def test_unknown_fields_cannot_carry_authority(self):
        s=make(self.root/'source'); d=decode(s.read_bytes()); d['real_market_census_closed']=True; s.write_bytes(canonical(d))
        with self.assertRaisesRegex(Invalid,'unknown'): builder.build(s,s.parent,self.root/'package')
    def test_derived_interest_cause_has_bound_inputs(self):
        _,p,r=self.build(derived_cause=True); verifier.verify(p)
        self.assertEqual(r['material_unknown_count'],0)
        self.assertFalse(r['chain_semantic_replay_certified'])
    def test_output_cannot_contaminate_immutable_source(self):
        s=make(self.root/'source')
        with self.assertRaisesRegex(Invalid,'outside immutable evidence root'): builder.build(s,s.parent,s.parent/'output')

if __name__=='__main__': unittest.main()
