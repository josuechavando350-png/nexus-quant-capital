"""Offline holdout protocol tests. All cases, labels, and predictions are synthetic.

No detector is run or benchmark generalization claim made by these fixtures.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import holdout_protocol as h
from superhunter import quality
from superhunter.safe_io import canonical, strict_json


class HoldoutTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.input=self.root/'inputs';self.input.mkdir()
        self.public=self.root/'public';self.private=self.root/'private'
        self.frozen=self.root/'frozen';self.scored=self.root/'scored'
        rows=[]
        for i,split in enumerate(('train','test','test','test'),1):
            rows.append({'case_id':f'case{i:02d}','group_id':f'group{i:02d}',
                         'content_sha256':h.sha(f'fixture-{i}'.encode()),
                         'split':split,'family':'synthetic'})
        self.manifest={'schema_version':1,'corpus_id':'synthetic-heldout-one','provenance':'synthetic','cases':rows}
        self.labels={'schema_version':1,'corpus_id':self.manifest['corpus_id'],
                     'cases':[{'case_id':f'case{i:02d}','truth':truth,
                               'severity':'medium' if truth=='positive' else 'none'}
                              for i,truth in enumerate(('negative','positive','negative','positive'),1)]}
        self.predictions={'schema_version':1,'run_id':'offline-fixture-one',
                          'producer':{'name':'synthetic-detector','source_sha256':'a'*64},
                          'manifest_sha256':h.sha(canonical(self.manifest)),
                          'records':[{'case_id':f'case{i:02d}','decision':d,
                                      'elapsed_ms':10,'cost_micro_usd':None}
                                     for i,d in ((2,'positive'),(3,'negative'),(4,'abstain'))]}
        self.manifest_file=self.input/'manifest.json';self.labels_file=self.input/'labels.json'
        self.predictions_file=self.input/'predictions.json'
        self.write_inputs()

    def write_inputs(self):
        self.manifest_file.write_bytes(canonical(self.manifest))
        self.labels_file.write_bytes(canonical(self.labels))
        self.predictions_file.write_bytes(canonical(self.predictions))

    def prepare(self):
        self.write_inputs()
        return h.prepare(self.manifest_file,self.labels_file,self.public,self.private)

    def freeze(self):
        r=self.prepare()
        return h.freeze(self.public,self.predictions_file,self.frozen,expected_prepared_sha256=r['prepared_sha256'])

    def score(self):
        f=self.freeze();s=h.score(self.frozen,self.private,self.scored,
                                 expected_prepared=f['prepared_sha256'],expected_frozen=f['submission_sha256'])
        return f,s

    def reseal(self,dir_: Path,filename: str,edit):
        p=dir_/filename
        value=strict_json(p.read_bytes());edit(value)
        raw=canonical(value);p.write_bytes(raw)
        m=strict_json((dir_/'COMPLETE.json').read_bytes())
        m['sha256'][filename]=h.sha(raw)
        (dir_/'COMPLETE.json').write_bytes(canonical(m))

    def test_holdout_partition_is_stable_and_keeps_all_tests(self):
        from superhunter.quality_worker import partition_ids
        ids = [f'test_m{i}.Suite.test_{j}' for i in range(8) for j in range(i+1)]
        original = partition_ids(ids, 8)
        extra = [f'test_holdout_protocol.HoldoutTests.test_{j}' for j in range(35)]
        combined = partition_ids(ids+extra, 8)
        base_only = [sorted(set(group)-set(extra)) for group in combined]
        all_baseline = sorted(x for group in base_only for x in group)
        self.assertEqual(all_baseline, sorted(ids))
        self.assertEqual(sorted(x for group in combined for x in group), sorted(ids+extra))
        self.assertTrue(all(x in combined[0] for x in extra))
        self.assertTrue(all(x.split(".")[0] != "test_platform" for x in combined[7]))

    def test_public_and_submission_contain_no_truth_labels(self):
        frozen=self.freeze()
        files=list(self.public.iterdir())+list(self.frozen.iterdir())
        content=b''.join(p.read_bytes() for p in files)
        self.assertNotIn(b'"truth"',content)
        self.assertNotIn(b'"severity"',content)
        self.assertNotIn(b'"nonce"',content)
        self.assertNotIn(b'medium',content)
        self.assertFalse(frozen['label_data_in_submission'])
        self.assertFalse((self.frozen/'labels.json').exists())

    def test_private_labels_kept_separately(self):
        self.prepare()
        self.assertTrue((self.private/'nonce.json').exists())
        self.assertTrue((self.private/'labels.json').exists())
        self.assertNotEqual((self.private/'nonce.json').read_bytes(),(self.public/'commitment.json').read_bytes())
        self.assertEqual(len(strict_json((self.private/'nonce.json').read_bytes())['nonce']),64)

    def test_full_roundtrip_metrics_abstain_not_success(self):
        f,s=self.score()
        self.assertEqual(s['status'],'COMMITTED_LABEL_EVALUATION')
        counts=s['metrics']['overall']['counts']
        self.assertEqual((counts['tp'],counts['tn'],counts['abstain_positive']),(1,1,1))
        self.assertEqual(s['metrics']['overall']['recall_all_positives']['value'],0.5)
        self.assertEqual(s['metrics']['overall']['precision']['value'],1.0)
        self.assertFalse(s['metrics']['blind_evaluation_established'])
        self.assertFalse(s['labels_committed_before_submission_authenticated'])
        self.assertEqual(s,h.verify(self.scored,expected_prepared=f['prepared_sha256'],
                                    expected_frozen=f['submission_sha256']))

    def test_reveal_can_work_after_input_directories_removed(self):
        f=self.freeze()
        shutil.rmtree(self.input)
        result=h.score(self.frozen,self.private,self.scored,expected_prepared=f['prepared_sha256'],
                       expected_frozen=f['submission_sha256'])
        self.assertEqual(result['metrics']['overall']['cases'],3)

    def test_freeze_cannot_read_private_labels(self):
        r=self.prepare()
        shutil.rmtree(self.private)
        x=h.freeze(self.public,self.predictions_file,self.frozen,expected_prepared_sha256=r['prepared_sha256'])
        self.assertEqual(x['status'],'HOLDOUT_FROZEN')

    def test_rejected_extra_or_missing_predictions(self):
        for change in ('missing','extra','duplicate'):
            rows=deepcopy(self.predictions)
            if change=='missing':rows['records'].pop()
            if change=='extra':rows['records'].append({'case_id':'ghost','decision':'positive','elapsed_ms':1,'cost_micro_usd':0})
            if change=='duplicate':rows['records'][-1]['case_id']=rows['records'][0]['case_id']
            with self.subTest(change=change),self.assertRaises(h.HoldoutError):
                h.validate_predictions(rows,self.manifest)

    def test_boolean_elapsed_and_cost_denied(self):
        for field in ('elapsed_ms','cost_micro_usd'):
            rows=deepcopy(self.predictions)
            rows['records'][0][field]=True
            with self.subTest(field=field),self.assertRaises(h.HoldoutError):
                h.validate_predictions(rows,self.manifest)

    def test_wrong_manifest_in_run_denied(self):
        self.predictions['manifest_sha256']='b'*64
        with self.assertRaisesRegex(h.HoldoutError,'WRONG_MANIFEST'):
            h.validate_predictions(self.predictions,self.manifest)

    def test_split_contamination_by_related_group_rejected(self):
        self.manifest['cases'][1]['group_id']=self.manifest['cases'][0]['group_id']
        with self.assertRaisesRegex(h.HoldoutError,'RELATED_GROUP_CROSSES_SPLITS'):
            h.validate_manifest(self.manifest)

    def test_same_content_in_two_splits_rejected(self):
        self.manifest['cases'][1]['content_sha256']=self.manifest['cases'][0]['content_sha256']
        with self.assertRaisesRegex(h.HoldoutError,'DUPLICATE_CONTENT'):
            h.validate_manifest(self.manifest)

    def test_split_without_test_cases_rejected(self):
        for r in self.manifest['cases']:r['split']='development'
        with self.assertRaisesRegex(h.HoldoutError,'NO_HELD_OUT_CASES'):
            h.validate_manifest(self.manifest)

    def test_duplicate_case_rejected(self):
        self.manifest['cases'][1]['case_id']=self.manifest['cases'][0]['case_id']
        with self.assertRaisesRegex(h.HoldoutError,'DUPLICATE_CASE'):
            h.validate_manifest(self.manifest)

    def test_extra_fields_in_manifest_rejected(self):
        self.manifest['guaranteed_win']=True
        with self.assertRaisesRegex(h.HoldoutError,'MANIFEST_SCHEMA'):
            h.validate_manifest(self.manifest)

    def test_labels_missing_or_duplicate_rejected(self):
        self.labels['cases'][1]['case_id']=self.labels['cases'][0]['case_id']
        with self.assertRaisesRegex(h.HoldoutError,'DUPLICATE_LABEL'):
            h.validate_labels(self.labels,self.manifest)
        self.labels['cases']=self.labels['cases'][:-1]
        with self.assertRaises(h.HoldoutError):
            h.validate_labels(self.labels,self.manifest)

    def test_withheld_labels_change_requires_new_commitment(self):
        f=self.freeze()
        self.reseal(self.private,'labels.json',lambda v:v['cases'][1].update(truth='negative',severity='none'))
        with self.assertRaisesRegex(h.HoldoutError,'LABEL_COMMITMENT_MISMATCH'):
            h.score(self.frozen,self.private,self.scored,expected_prepared=f['prepared_sha256'],
                    expected_frozen=f['submission_sha256'])

    def test_nonce_change_requires_new_commitment(self):
        f=self.freeze()
        self.reseal(self.private,'nonce.json',lambda v:v.update(nonce='0'*64))
        with self.assertRaisesRegex(h.HoldoutError,'LABEL_COMMITMENT_MISMATCH'):
            h.score(self.frozen,self.private,self.scored,expected_prepared=f['prepared_sha256'],
                    expected_frozen=f['submission_sha256'])

    def test_external_frozen_pin_blocks_resealed_falsification(self):
        f=self.freeze()
        self.reseal(self.frozen,'predictions.json',lambda v:v['records'][1].update(decision='positive'))
        with self.assertRaisesRegex(h.HoldoutError,'FROZEN_PIN_MISMATCH'):
            h.score(self.frozen,self.private,self.scored,expected_prepared=f['prepared_sha256'],
                    expected_frozen=f['submission_sha256'])

    def test_external_prepared_pin_blocks_reseal(self):
        r=self.prepare()
        self.reseal(self.public,'manifest.json',lambda v:v['cases'][1].update(family='new'))
        with self.assertRaisesRegex(h.HoldoutError,'PREPARED_PIN_MISMATCH'):
            h.freeze(self.public,self.predictions_file,self.frozen,expected_prepared_sha256=r['prepared_sha256'])

    def test_score_cannot_reuse_another_prepared_pin(self):
        f=self.freeze()
        with self.assertRaisesRegex(h.HoldoutError,'PREPARED_BINDING'):
            h.score(self.frozen,self.private,self.scored,expected_prepared='e'*64,
                    expected_frozen=f['submission_sha256'])

    def test_report_reseal_and_metrics_lie_rejected(self):
        f,s=self.score()
        self.reseal(self.scored,'evaluation.json',lambda v:v['metrics']['overall']['counts'].update(tp=3))
        with self.assertRaisesRegex(h.HoldoutError,'REPLAY_METRIC_DISAGREEMENT'):
            h.verify(self.scored,expected_prepared=f['prepared_sha256'],expected_frozen=f['submission_sha256'])

    def test_metrics_consistent_but_audit_forged_rejected(self):
        f,s=self.score()
        self.reseal(self.scored,'audit.json',lambda v:v['entries'][1]['data'].update(case_sha256='e'*64))
        with self.assertRaises(bm.BenchmarkError if False else Exception):
            h.verify(self.scored,expected_prepared=f['prepared_sha256'],expected_frozen=f['submission_sha256'])

    def test_engine_change_blocks_existing_score(self):
        f,s=self.score()
        with patch.object(h,'_engine',return_value={'source_sha256':{'old':'0'*64}}),self.assertRaisesRegex(h.HoldoutError,'SOURCE_IDENTITY_CHANGED'):
            h.verify(self.scored,expected_prepared=f['prepared_sha256'],expected_frozen=f['submission_sha256'])

    def test_scored_bundle_extra_file_denied(self):
        f,s=self.score();(self.scored/'extra.json').write_text('{}')
        with self.assertRaisesRegex(h.HoldoutError,'EXTRA_BUNDLE_FILE'):
            h.verify(self.scored,expected_prepared=f['prepared_sha256'],expected_frozen=f['submission_sha256'])

    def test_source_files_immutable(self):
        before=[p.read_bytes() for p in (self.manifest_file,self.labels_file,self.predictions_file)]
        self.score()
        self.assertEqual(before,[p.read_bytes() for p in (self.manifest_file,self.labels_file,self.predictions_file)])

    def test_output_directory_exclusive(self):
        self.prepare()
        with self.assertRaisesRegex(h.HoldoutError,'OUTPUT_EXISTS'):
            self.prepare()

    def test_public_private_permissions(self):
        self.score()
        for base in (self.public,self.private,self.frozen,self.scored):
            self.assertEqual(base.stat().st_mode & 0o777,0o700)
            for p in base.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_symlink_in_frozen_bundle_rejected(self):
        f=self.freeze()
        p=self.frozen/'predictions.json';p.unlink();p.symlink_to(self.predictions_file)
        with self.assertRaises((OSError,ValueError)):
            h.score(self.frozen,self.private,self.scored,expected_prepared=f['prepared_sha256'],
                    expected_frozen=f['submission_sha256'])

    def test_no_network_subprocess_or_target_execution(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('subprocess.run',side_effect=AssertionError('process')):
            self.score()

    def test_cli_roundtrip_with_real_separate_processes(self):
        import os
        commands=[['prepare-holdout','--manifest',str(self.manifest_file), '--labels',str(self.labels_file),
                   '--public-out',str(self.public),'--private-out',str(self.private)]]
        def call(cmd):
            proc=subprocess.run([sys.executable,'-B','-m','superhunter',*cmd],cwd=h.ROOT.parent,
                                capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            return json.loads(proc.stdout)
        r=call(commands[0]);self.assertNotIn('truth',str(r))
        f=call(['freeze-holdout','--public',str(self.public),'--predictions',str(self.predictions_file),
                '--out',str(self.frozen),'--expected-prepared-sha256',r['prepared_sha256']])
        x=call(['score-holdout','--frozen',str(self.frozen),'--private',str(self.private),
                '--out',str(self.scored),'--expected-prepared-sha256',r['prepared_sha256'],
                '--expected-frozen-sha256',f['submission_sha256']])
        self.assertEqual(x['counts']['tp'],1)
        y=call(['verify-holdout','--bundle',str(self.scored),
                '--expected-prepared-sha256',r['prepared_sha256'],
                '--expected-frozen-sha256',f['submission_sha256']])
        self.assertEqual(x['counts'],y['counts'])

    def test_cli_wrong_pin_no_secret_echo(self):
        f=self.freeze()
        with redirect_stdout(io.StringIO()) as output:
            rc=h.main(['score-holdout','--frozen',str(self.frozen), '--private',str(self.private),
                       '--out',str(self.scored),'--expected-prepared-sha256','0'*64,
                       '--expected-frozen-sha256',f['submission_sha256']])
        self.assertEqual(rc,2)
        self.assertNotIn('synthetic-heldout',output.getvalue())
        self.assertNotIn(str(self.private),output.getvalue())

    def test_security_performance_claims_explicitly_false(self):
        f,r=self.score()
        self.assertFalse(r['labels_committed_before_submission_authenticated'])
        self.assertFalse(r['label_secrecy_authenticated'])
        self.assertFalse(r['independent_curation_authenticated'])
        self.assertFalse(r['metrics']['generalization_established'])
        self.assertFalse(r['metrics']['vulnerability_confirmed'])

    def test_wrong_nonce_format_rejected(self):
        with self.assertRaisesRegex(h.HoldoutError,'INVALID_HASH'):
            h.commitment(self.manifest,self.labels,'not-random')

    def test_independent_counting_agreement_with_benchmark(self):
        f,s=self.score()
        self.assertTrue(s['metrics']['independent_counting_agreed'])
        self.assertEqual(s['metrics']['overall']['not_detected_positives'],1)

    def test_qa_component_declared_and_mandatory(self):
        self.assertEqual(quality.COMPONENTS['holdout_protocol']['files'],['holdout_protocol.py'])
        self.assertIn('test_holdout_protocol.HoldoutTests.test_withheld_labels_change_requires_new_commitment',
                      quality.REQUIRED_TESTS)
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])

    def test_no_inplace_promotion_of_known_mutants(self):
        f,s=self.score()
        self.assertEqual(s['metrics']['corpus_provenance'],'synthetic')
        self.assertFalse(s['metrics']['labels_authenticated'])
        self.assertFalse(s['metrics']['producer_execution_authenticated'])


if __name__ == '__main__':unittest.main()
