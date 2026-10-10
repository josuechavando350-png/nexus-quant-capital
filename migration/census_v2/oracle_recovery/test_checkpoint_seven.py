"""Actual final oracle delta: parity, preserved prefix and terminal integrity."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import collect as c
import prepare_checkpoint_seven as p
import verify_coverage as v

class TerminalCheckpointChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=Path(os.environ['NQC_COVERAGE_INPUTS'])
        cls.base=Path(os.environ['NQC_ORACLE_CHECKPOINT_SIX'])
        cls.checkpoint=Path(os.environ['NQC_ORACLE_CHECKPOINT_SEVEN'])
        cls.files=p.read_delta(p.archive_bytes())

    def test_actual_full_replay_matches_saved_outputs(self):
        reports=v.verify(self.inputs/'original-oracle-evidence.zip',Path(os.environ['NQC_ORACLE_D08']),
            self.inputs/'pilot-bundle/pilot',self.inputs/'partial-bundle/remaining',self.checkpoint,
            self.inputs/'original/drpc',self.inputs/'full-window')
        saved=Path(os.environ['NQC_ORACLE_CHECKPOINT_SEVEN_READBACK'])
        for name,report in reports.items():self.assertEqual(c.canon(report),(saved/name).read_bytes())
        r=reports['report.json']
        self.assertEqual((r['closed_continuation_blocks'],r['closed_continuation_prices_matched']),(209866,14061022))
        self.assertEqual((r['verified_secondary_union_blocks'],r['missing_secondary_blocks']),(215036,0))
        self.assertEqual(r['unique_matched_price_coordinates'],14407412)
        self.assertEqual(r['captured_but_not_verified_blocks'],0)
        self.assertEqual((r['executed_events'],r['complete_receipts'],r['price_mismatches']),(139,127,0))
        self.assertEqual(reports['partition.json']['missing_ranges'],[])
        self.assertEqual(r['status'],'HISTORICAL_COVERAGE_READY_FOR_REVIEW')
        self.assertTrue(r['terminal_acquisition_exact_file_present'])
        self.assertTrue(r['milestone_10_coverage_ready']) # legacy field, no numerical notice
        for k in ['milestone_15_ready','milestone_20_ready','census_closed','capture_or_profit_admitted',
                  'independent_authority_acceptance','original_decision_time_observation_proven',
                  'independent_underlying_nodes_proven','notification_sent']:
            self.assertIs(r[k],False)
        self.assertEqual(r['earlier_failure_records_preserved'][0]['http_status'],429)

    def test_exact_terminal_assembly_and_short_final_file(self):
        expected=p.combined(self.base,self.files)
        self.assertEqual(set(expected),{x.name for x in self.checkpoint.iterdir()})
        for n,raw in expected.items():self.assertEqual((self.checkpoint/n).read_bytes(),raw)
        doc=json.loads(expected['progress.json'])
        self.assertEqual(doc['completed_files'][-1]['observed_blocks'],866)
        self.assertEqual(expected['progress.json'],expected['acquisition.json'])
        for i in range(165):
            n=f'capture-{i*1000:06d}.jsonl.gz'
            self.assertEqual(expected[n],(self.base/n).read_bytes())

    def altered(self,mutator,both=True):
        files=dict(self.files);doc=json.loads(files['progress.json']);mutator(doc)
        files['progress.json']=c.canon(doc)
        if both:files['acquisition.json']=files['progress.json']
        return files

    def test_terminal_disagreement_rejected(self):
        files=dict(self.files);files['acquisition.json']+=b'\n'
        with self.assertRaisesRegex(ValueError,'terminal files'):p.combined(self.base,files)

    def test_false_complete_counter_rejected(self):
        files=self.altered(lambda d:d.update(observed_blocks=209865))
        with self.assertRaisesRegex(ValueError,'terminal completeness'):p.combined(self.base,files)

    def test_failed_state_cannot_be_promoted(self):
        files=self.altered(lambda d:d.update(failure={'http_status':429}))
        with self.assertRaisesRegex(ValueError,'terminal completeness'):p.combined(self.base,files)

    def test_running_state_rejected(self):
        files=self.altered(lambda d:d.update(status='RUNNING'))
        with self.assertRaisesRegex(ValueError,'terminal completeness'):p.combined(self.base,files)

    def test_last_file_count_not_padded(self):
        def change(d):d['completed_files'][-1]['observed_blocks']=1000
        with self.assertRaisesRegex(ValueError,'coordinate/count'):p.combined(self.base,self.altered(change))

    def test_changed_capture_rejected(self):
        files=dict(self.files);files['capture-209000.jsonl.gz']+=b'x'
        with self.assertRaisesRegex(ValueError,'capture identity'):p.combined(self.base,files)

    def test_duplicate_new_coordinate_rejected(self):
        def change(d):d['completed_files'][166]=copy.deepcopy(d['completed_files'][165])
        with self.assertRaisesRegex(ValueError,'coordinate/count'):p.combined(self.base,self.altered(change))

    def test_changed_base_rejected(self):
        files=dict(self.files);files['base-readback.json']+=b'\n'
        with self.assertRaisesRegex(ValueError,'published base'):p.combined(self.base,files)

    def test_changed_shared_source_rejected(self):
        files=dict(self.files);files['resume.py']+=b'\n'
        with self.assertRaisesRegex(ValueError,'shared source'):p.combined(self.base,files)

    def test_transport_corruption_rejected(self):
        raw=bytearray(p.archive_bytes());raw[100]^=1
        with self.assertRaisesRegex(ValueError,'archive identity'):p.read_delta(raw)

if __name__=='__main__':unittest.main()
