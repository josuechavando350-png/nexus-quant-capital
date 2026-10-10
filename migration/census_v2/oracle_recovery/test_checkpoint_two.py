"""Real second checkpoint: reproduce all vectors and prevent prefix double counting."""
import json
import io
import os
from pathlib import Path
import unittest
import zipfile
import collect as c
import verify_continuation as v

HERE = Path(__file__).resolve().parent
PIN = '913b4c530d53207e450ff72e21ad0a0b420af0b80574faee329c161f3daca18c'


def second_archive():
    manifest = json.loads((HERE / 'sequential-checkpoint-002.parts.json').read_bytes())
    assert [x['path'] for x in manifest['parts']] == [
        'sequential-checkpoint-002.zip.part-001', 'sequential-checkpoint-002.zip.part-002']
    parts = []
    for item in manifest['parts']:
        raw = (HERE / item['path']).read_bytes()
        assert (len(raw), c.sha(raw)) == (item['bytes'], item['sha256'])
        parts.append(raw)
    raw = b''.join(parts)
    assert len(raw) == manifest['bytes'] == 15143401
    assert c.sha(raw) == manifest['sha256'] == PIN
    return zipfile.ZipFile(io.BytesIO(raw))


class SecondCheckpointTests(unittest.TestCase):
    def test_all_closed_vectors_reproduce_the_remote_readback(self):
        with second_archive() as z:
            root = Path(os.environ['NQC_ORACLE_CHECKPOINT_TWO'])
            self.assertEqual(len(z.namelist()), 50)
            self.assertEqual(len(set(z.namelist())), 50)
            for name in z.namelist():
                self.assertEqual(Path(name).name, name)
                self.assertEqual((root / name).read_bytes(), z.read(name))
            result = v.verify(root, Path(os.environ['NQC_ORACLE_PRIMARY_DIRECTORY']))
            self.assertEqual(c.canon(result), (root / 'readback.json').read_bytes())
            self.assertEqual(result['new_blocks_verified'], 43000)
            self.assertEqual(result['price_values_matched'], 2881000)
            self.assertEqual(result['secondary_union_verified_blocks'], 48170)
            self.assertEqual(result['secondary_missing_blocks'], 166866)
            self.assertEqual(result['current_capture_counter'], 43220)
            self.assertFalse(result['full_secondary_price_coverage'])
            self.assertFalse(result['census_certified'])

    def test_first_checkpoint_is_an_identical_prefix_not_additional_coverage(self):
        with zipfile.ZipFile(HERE / 'sequential-checkpoint-001.zip') as first, \
             second_archive() as second:
            old = json.loads(first.read('readback.json'))
            new = json.loads(second.read('readback.json'))
            for item in old['closed_file_commitments']:
                self.assertEqual(first.read(item['file']), second.read(item['file']))
            for name in ['anchors.jsonl.gz', 'resume.py', 'collect.py', 'resume-plan.json', 'assets.json']:
                self.assertEqual(first.read(name), second.read(name))
            self.assertEqual(new['new_blocks_verified'] - old['new_blocks_verified'], 41000)
            self.assertEqual(new['secondary_union_verified_blocks'] - old['secondary_union_verified_blocks'], 41000)


if __name__ == '__main__':
    unittest.main()
