"""Actual sixth checkpoint: exact delta/prefix identity and complete price replay."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import collect as c
import prepare_checkpoint_six as p
import verify_coverage as v


class SixthCheckpointChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = Path(os.environ['NQC_COVERAGE_INPUTS'])
        cls.base = Path(os.environ['NQC_ORACLE_CHECKPOINT_FIVE'])
        cls.checkpoint = Path(os.environ['NQC_ORACLE_CHECKPOINT_SIX'])
        cls.files = p.read_delta(p.archive_bytes())

    def test_actual_full_readback_repeats_saved_report(self):
        reports = v.verify(self.inputs / 'original-oracle-evidence.zip',
                           Path(os.environ['NQC_ORACLE_D08']), self.inputs / 'pilot-bundle/pilot',
                           self.inputs / 'partial-bundle/remaining', self.checkpoint,
                           self.inputs / 'original/drpc', self.inputs / 'full-window')
        saved = Path(os.environ['NQC_ORACLE_CHECKPOINT_SIX_READBACK'])
        for name, report in reports.items():
            self.assertEqual(c.canon(report), (saved / name).read_bytes())
        r = reports['report.json']
        self.assertEqual((r['closed_continuation_blocks'], r['closed_continuation_prices_matched']), (165000, 11055000))
        self.assertEqual((r['verified_secondary_union_blocks'], r['missing_secondary_blocks']), (170170, 44866))
        self.assertEqual(r['unique_matched_price_coordinates'], 11401390)
        self.assertEqual(r['captured_but_not_verified_blocks'], 280)
        self.assertEqual((r['executed_events'], r['complete_receipts'], r['price_mismatches']), (139, 127, 0))
        self.assertEqual(reports['partition.json']['missing_ranges'], [[26050486, 26095351]])
        for field in ['milestone_10_coverage_ready', 'milestone_15_ready', 'milestone_20_ready', 'census_closed']:
            self.assertIs(r[field], False)

    def test_exact_assembled_copy_and_unchanged_base(self):
        expected = p.combined(self.base, self.files)
        self.assertEqual(set(expected), {x.name for x in self.checkpoint.iterdir()})
        for name, raw in expected.items():
            self.assertEqual((self.checkpoint / name).read_bytes(), raw)
        for i in range(139):
            name = f'capture-{i * 1000:06d}.jsonl.gz'
            self.assertEqual((self.base / name).read_bytes(), expected[name])
        self.assertEqual(len([n for n in self.files if n.startswith('capture-')]), 26)
        self.assertEqual(len([n for n in expected if n.startswith('capture-')]), 165)
        self.assertNotIn('capture-165000.jsonl.gz', expected)
        self.assertNotIn('acquisition.json', expected)

    def test_missing_base_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'progress.json').write_bytes(b'{}\n')
            with self.assertRaisesRegex(ValueError, 'base snapshot identity'):
                p.combined(base, self.files)

    def test_changed_base_readback_rejected(self):
        files = dict(self.files)
        files['base-readback.json'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'published base identity'):
            p.combined(self.base, files)

    def test_changed_new_capture_rejected(self):
        files = dict(self.files)
        files['capture-139000.jsonl.gz'] += b'x'
        with self.assertRaisesRegex(ValueError, 'closed capture identity'):
            p.combined(self.base, files)

    def test_changed_shared_anchor_rejected(self):
        files = dict(self.files)
        files['anchors.jsonl.gz'] += b'x'
        with self.assertRaisesRegex(ValueError, 'shared source or anchors changed'):
            p.combined(self.base, files)

    def test_duplicated_new_file_coordinate_rejected(self):
        files = dict(self.files)
        doc = json.loads(files['progress.json'])
        doc['completed_files'][140] = copy.deepcopy(doc['completed_files'][139])
        files['progress.json'] = c.canon(doc)
        with self.assertRaisesRegex(ValueError, 'closed capture order/completeness'):
            p.combined(self.base, files)

    def test_changed_transport_rejected(self):
        raw = bytearray(p.archive_bytes())
        raw[100] ^= 1
        with self.assertRaisesRegex(ValueError, 'delta archive digest'):
            p.read_delta(raw)


if __name__ == '__main__':
    unittest.main()
