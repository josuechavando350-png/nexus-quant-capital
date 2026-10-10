"""Real third checkpoint: authenticate and reproduce the incremental delta."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import collect as c
import verify_checkpoint_delta as d


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / 'sequential-checkpoint-003-delta.zip'
PIN = '6b5691d546ee3eb4aa291a7f32ef52689826021fb791136b67fa84c8e6fbd0c0'


def delta_archive():
    raw = ARCHIVE.read_bytes()
    assert len(raw) == 4269496
    assert c.sha(raw) == PIN
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    assert len(names) == len(set(names)) == 22
    assert all(Path(name).name == name for name in names)
    manifest = json.loads(archive.read('manifest.json'))
    assert manifest['schema'] == 'nqc-oracle-continuation-delta-archive-v1'
    assert manifest['base_archive_sha256'] == d.BASE_ARCHIVE_SHA
    assert manifest['base_readback_sha256'] == d.BASE_READBACK_SHA
    assert len(manifest['members']) == 21
    for item in manifest['members']:
        member = archive.read(item['path'])
        assert (len(member), c.sha(member)) == (item['bytes'], item['sha256'])
    return archive


class DeltaCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = Path(os.environ['NQC_ORACLE_CHECKPOINT_THREE'])
        cls.primary = Path(os.environ['NQC_ORACLE_PRIMARY_DIRECTORY'])

    def test_exact_archive_and_all_new_vectors_reproduce_remote_readback(self):
        with delta_archive() as archive:
            for name in archive.namelist():
                self.assertEqual((self.evidence / name).read_bytes(), archive.read(name))
        result = d.verify(self.evidence, self.primary,
                          self.evidence / 'base-readback.json')
        self.assertEqual(c.canon(result), (self.evidence / 'readback.json').read_bytes())
        self.assertEqual(result['delta_blocks_verified'], 12000)
        self.assertEqual(result['delta_price_values_matched'], 804000)
        self.assertEqual(result['total_continuation_blocks_verified'], 55000)
        self.assertEqual(result['secondary_union_verified_blocks'], 60170)
        self.assertEqual(result['secondary_missing_blocks'], 154866)
        self.assertEqual(result['cross_operator_mismatches'], 0)
        self.assertFalse(result['full_secondary_price_coverage'])
        self.assertFalse(result['census_certified'])

    def test_delta_begins_after_exact_base_prefix_without_double_counting(self):
        base = json.loads((self.evidence / 'base-readback.json').read_bytes())
        delta = json.loads((self.evidence / 'readback.json').read_bytes())
        progress = json.loads((self.evidence / 'progress.json').read_bytes())
        self.assertEqual(progress['completed_files'][:d.BASE_CLOSED_FILES],
                         base['closed_file_commitments'])
        self.assertEqual(delta['total_continuation_blocks_verified'],
                         base['new_blocks_verified'] + delta['delta_blocks_verified'])
        self.assertEqual(delta['secondary_union_verified_blocks'],
                         5170 + delta['total_continuation_blocks_verified'])
        self.assertEqual(delta['delta_file_commitments'],
                         progress['completed_files'][d.BASE_CLOSED_FILES:])

    def test_substituted_base_readback_is_rejected_before_price_use(self):
        base = json.loads((self.evidence / 'base-readback.json').read_bytes())
        base['latest_received_at'] = '2026-10-10T00:00:00+00:00'
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / 'base.json'
            changed.write_bytes(c.canon(base))
            with self.assertRaisesRegex(ValueError, 'base readback commitment'):
                d.verify(self.evidence, self.primary, changed)


if __name__ == '__main__':
    unittest.main()
