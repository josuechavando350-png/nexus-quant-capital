#!/usr/bin/env python3
"""Actual historical observations plus adversarial chronology/price checks."""
import argparse
import copy
from pathlib import Path
import unittest
import zipfile

import reconcile_oracle_chunks as r


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ARGS.archive) as z:
            cls.chunk = r.parse(z.read('drpc/chunk-25880316-25880365.json'))

    def test_historical_coverage_and_nonclaims(self):
        result = r.reconcile(ARGS.archive, ARGS.core)
        self.assertEqual(result['primary_blocks'], 215036)
        self.assertEqual(result['secondary_blocks'], 4650)
        self.assertEqual(result['secondary_missing_blocks'], 210386)
        self.assertEqual(result['recomputed_observation_digests'], 4394)
        self.assertEqual(result['liquidation_vectors_matched'], 123)
        self.assertEqual(result['liquidation_hashes_matched_to_next_parent'], 123)
        self.assertFalse(result['full_dual_provider_coverage'])
        self.assertFalse(result['available_to_nqc_before_winner_proven'])
        self.assertFalse(result['new_producer_certified'])
        ARGS.output.mkdir(parents=True, exist_ok=False)
        (ARGS.output / 'report.json').write_bytes(r.canon(result))

    def test_missing_block_rejected(self):
        doc = copy.deepcopy(self.chunk)
        doc['headers'].pop(1)
        with self.assertRaisesRegex(ValueError, 'cardinality'):
            r.observations(doc)

    def test_missing_asset_rejected(self):
        doc = copy.deepcopy(self.chunk)
        doc['changes'][0]['changed'].pop()
        with self.assertRaisesRegex(ValueError, 'incomplete checkpoint'):
            r.observations(doc)

    def test_duplicate_asset_rejected(self):
        doc = copy.deepcopy(self.chunk)
        doc['changes'][0]['changed'].append(doc['changes'][0]['changed'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate/unordered'):
            r.observations(doc)

    def test_boolean_index_rejected(self):
        doc = copy.deepcopy(self.chunk)
        doc['changes'][0]['changed'][0][0] = False
        with self.assertRaisesRegex(ValueError, 'integer bounds/type'):
            r.observations(doc)

    def test_interior_observation_digest_recomputed(self):
        doc = copy.deepcopy(self.chunk)
        doc['headers'][1][0] += 1
        doc['changes'][1]['timestamp'] += 1
        with self.assertRaisesRegex(ValueError, 'observation digest mismatch'):
            r.observations(doc)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['archive', 'core', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    ARGS, rest = p.parse_known_args()
    unittest.main(argv=['check_oracle_chunks.py', *rest])
