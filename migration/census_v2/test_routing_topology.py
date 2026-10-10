"""Real D08/D12 reproduction and adversarial scope/identity boundaries."""
from collections import Counter, defaultdict
import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest

import audit_routing_topology as a


class RoutingTopologyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = Path(os.environ['NQC_ROUTING_READBACK'])
        cls.report = json.loads((cls.saved / 'report.json').read_bytes())
        cls.routes = [json.loads(x) for x in gzip.decompress((cls.saved / 'routes.jsonl.gz').read_bytes()).splitlines()]
        cls.candidates = [json.loads(x) for x in a.pinned(a.HERE / 'evidence/candidate-classifications.jsonl').splitlines()]
        cls.endpoints = {json.loads(x)['asset'] for x in (cls.saved / 'assets.jsonl').read_bytes().splitlines()}
        cls.example = next(r['path_examples'][0]['pools'][0] for r in cls.routes if r['direct_paths'])

    def test_complete_real_replay_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'replay'
            a.build(Path(os.environ['NQC_ORACLE_D08']), out)
            self.assertEqual({p.name for p in out.iterdir()}, {p.name for p in self.saved.iterdir()})
            for p in out.iterdir(): self.assertEqual(p.read_bytes(), (self.saved / p.name).read_bytes())

    def test_population_conservation_and_no_economic_promotion(self):
        r = self.report
        self.assertEqual(sum(r['pool_partition'].values()), 523424)
        self.assertEqual(r['distinct_directed_asset_conversions'], 67 * 66)
        self.assertEqual(len(self.routes), len({(x['collateral_asset'], x['debt_asset']) for x in self.routes}))
        self.assertEqual(sum(r['conversion_status_counts'].values()), 4422)
        self.assertEqual(sum(r['d12_topology_counts'].values()), 474)
        self.assertEqual(r['d12_classification_counts_unchanged'], {'NON_EXECUTABLE': 42, 'INSUFFICIENT_EVIDENCE': 432})
        self.assertEqual(r['aave_reserve_token_compatibility_counts'], {'BLOCKED': 67})
        self.assertEqual(r['admitted_executable_value_mxn_centavos'], 0)
        self.assertIsNone(r['complete_net_pnl'])
        self.assertFalse(r['global_route_absence_proven'])
        self.assertFalse(r['census_closed'])
        for x in self.routes:
            self.assertFalse(x['execution_admitted']); self.assertIsNone(x['complete_net_pnl'])

    def test_real_route_witnesses_are_connected_and_have_no_reused_pool(self):
        for row in self.routes:
            for path in row['path_examples']:
                t, pools = path['tokens'], path['pools']
                self.assertEqual((t[0], t[-1]), (row['collateral_asset'], row['debt_asset']))
                self.assertEqual(len(t), len(pools) + 1)
                self.assertEqual(len(pools), len({p['pair'] for p in pools}))
                for i, p in enumerate(pools):
                    self.assertEqual({t[i], t[i+1]}, {p['token0'], p['token1']})
                    self.assertGreater(int(p['reserve0']), 0); self.assertGreater(int(p['reserve1']), 0)

    def edge(self):
        x = copy.deepcopy(self.example)
        x['reserves'] = [x.pop('reserve0'), x.pop('reserve1'), 0]
        x['fee_semantics'] = {'swap_fee_bps': x.pop('swap_fee_bps')}
        x['factory_membership'] = True
        return x

    def test_duplicate_factory_pair_is_rejected(self):
        x = self.edge(); graph = defaultdict(dict); seen = set()
        a.add_edge(x, self.endpoints, graph, seen)
        changed = copy.deepcopy(x); changed['pair'] = '0x' + 'ff' * 20
        with self.assertRaisesRegex(ValueError, 'duplicate factory token pair'):
            a.add_edge(changed, self.endpoints, graph, seen)

    def test_reversed_token_identity_is_rejected(self):
        x = self.edge(); x['token0'], x['token1'] = x['token1'], x['token0']
        with self.assertRaisesRegex(ValueError, 'noncanonical token pair'):
            a.add_edge(x, self.endpoints, defaultdict(dict), set())

    def test_zero_reserve_cannot_become_a_positive_edge(self):
        x = self.edge(); x['reserves'][0] = '0'
        with self.assertRaisesRegex(ValueError, 'positive integer reserves'):
            a.add_edge(x, self.endpoints, defaultdict(dict), set())

    def test_missing_factory_membership_is_rejected(self):
        x = self.edge(); x['factory_membership'] = False
        with self.assertRaisesRegex(ValueError, 'factory membership'):
            a.add_edge(x, self.endpoints, defaultdict(dict), set())

    def test_duplicate_candidate_cannot_inflate_coverage(self):
        with self.assertRaisesRegex(ValueError, 'duplicate candidate identity'):
            a.overlay([self.candidates[0], self.candidates[0]], self.routes, self.endpoints)

    def test_positive_value_cannot_be_inherited_from_topology(self):
        x = copy.deepcopy(self.candidates[0]); x['admitted_executable_value_mxn_centavos'] = 1
        with self.assertRaisesRegex(ValueError, 'unexpected positive source value'):
            a.overlay([x], self.routes, self.endpoints)

    def test_absent_scoped_route_does_not_become_global_rejection(self):
        actual = a.overlay(self.candidates, self.routes, self.endpoints)
        unmatched = [x for x in actual if x['topology_observation']['structural_status'] == 'NO_PATH_WITHIN_DECLARED_TOPOLOGY_SCOPE']
        self.assertTrue(unmatched)
        for x in unmatched:
            self.assertEqual(x['original_classification'], x['classification_after_topology'])
            self.assertFalse(x['global_route_absence_proven'])
        same = [x for x in actual if x['collateral_asset'] == x['debt_asset']]
        self.assertEqual(len(same), 23)
        for x in same: self.assertIsNone(x['complete_net_pnl'])

    def test_changed_archive_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / 'bad.zip'; bad.write_bytes(b'not the original archive')
            with self.assertRaisesRegex(ValueError, 'D08 archive identity'):
                a.build(bad, Path(temp) / 'out')


if __name__ == '__main__':
    unittest.main()
