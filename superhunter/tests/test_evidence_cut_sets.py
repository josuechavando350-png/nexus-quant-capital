"""Independent exact cut-set oracle and full upstream forensic evidence replay."""
from __future__ import annotations

import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from superhunter import evidence_cut_sets as cuts
from superhunter import evidence_common_mode as common
from superhunter import critical_chain as triage
from superhunter.safe_io import canonical, strict_json
import test_evidence_common_mode as old_tests


def independent_cuts(obligations, names):
    """Brute-force 2^N oracle intentionally distinct from subset-pruning engine."""
    candidates = []
    for count in range(len(names) + 1):
        for members in combinations(sorted(names), count):
            subset = set(members)
            creates_gap = any(s and all(source in subset for source in s)
                              for s in obligations)
            if creates_gap and not any(set(previous).issubset(subset)
                                       for previous in candidates):
                candidates.append(list(members))
    return candidates


class EvidenceCutSetTests(unittest.TestCase):
    def setUp(self):
        old_tests.CommonEvidenceTests.setUp(self)
        self.common = self.base / 'common-private'
        self.cuts = self.base / 'cuts-private'

    def upstream(self):
        old_tests.CommonEvidenceTests.setup_previous(self)
        common.review(self.ablation, self.path, self.triage, self.sources, self.common)

    def produce(self):
        self.upstream()
        actual = cuts.review(self.common, self.ablation, self.path, self.triage,
                             self.sources, self.cuts)
        self.assertEqual(actual, cuts.verify(self.cuts, self.common, self.ablation,
                                              self.path, self.triage, self.sources))
        return strict_json((self.cuts / 'cut-sets.json').read_bytes())

    def test_real_verified_bundle_replay(self):
        result = self.produce()
        self.assertEqual(result['distinct_bundle_hashes'], 2)
        cases = {c['candidate_id']: c for c in result['candidates']}
        crit = cases['crit']
        self.assertEqual(crit['minimum_cut_cardinality'], 1)
        self.assertEqual(len(crit['minimal_bundle_failure_cut_sets']), 1)
        self.assertEqual(crit['minimal_bundle_failure_cut_sets'][0]['lost_distinct_bundles'], 1)
        self.assertFalse(result['claims']['vulnerability_confirmed'])
        self.assertFalse(result['claims']['causation_proved'])
        self.assertFalse(crit['critical_impact_confirmed'])

    def test_two_independent_byte_bundles_both_needed_for_one_obligation(self):
        # The source map contains two byte-identical alias IDs and an independent
        # bundle whose actual ev3 is available for a. Thus a has two distinct
        # byte-support groups, so only losing BOTH removes evidence from a.
        self.spec['observations'][0]['evidence_refs'].append(
            {'source_id':'sourcec','object_id':'ev3'})
        result = self.produce()
        crit = next(c for c in result['candidates'] if c['candidate_id']=='crit')
        # b and the link still depend on the shared bundle, which is a one-bundle
        # cut; new evidence for a remains supported after that same failure.
        one = crit['minimal_bundle_failure_cut_sets'][0]
        self.assertEqual(one['lost_distinct_bundles'], 1)
        self.assertNotIn('observation:a', one['newly_unsupported_obligations'])

    def test_genuine_two_bundle_cut_on_all_chain_obligations(self):
        # Each observation/link now has independently different BYTES to
        # satisfy it. Losing one identity or one bundle is insufficient;
        # losing both distinct original bundles creates the first new gap.
        for row in self.spec['observations'][:2] + self.spec['links']:
            row['evidence_refs'].append({'source_id':'sourcec','object_id':'ev3'})
        result = self.produce()
        case = next(x for x in result['candidates'] if x['candidate_id']=='crit')
        self.assertEqual(case['minimum_cut_cardinality'], 2)
        self.assertEqual(len(case['minimal_bundle_failure_cut_sets']), 1)
        entry = case['minimal_bundle_failure_cut_sets'][0]
        self.assertEqual(entry['lost_distinct_bundles'], 2)
        self.assertEqual(len(entry['newly_unsupported_obligations']), 3)
        self.assertTrue(entry['new_evidence_gap_in_triage'])

    def test_three_source_names_do_not_prove_three_independent_producers(self):
        r = self.produce()
        self.assertEqual(r['declared_source_ids'], 3)
        self.assertEqual(r['distinct_bundle_hashes'], 2)
        self.assertFalse(r['claims']['independent_producers_established'])

    def test_exact_cut_oracle_600(self):
        rng = random.Random(20261106)
        checked = 0
        for _ in range(600):
            labels = [f's{i}' for i in range(rng.randint(1, 8))]
            universe = set(labels)
            obligations = [set(x for x in labels if rng.getrandbits(1))
                           for __ in range(rng.randint(0, 15))]
            expected = independent_cuts(obligations, labels)
            actual = cuts.minimal_bundle_cut_sets(obligations, universe)
            self.assertEqual(actual, expected)
            checked += 1
        self.assertEqual(checked, 600)

    def test_rejected_nonset_obligation(self):
        with self.assertRaisesRegex(cuts.CutSetError, 'OBLIGATION_INPUT'):
            cuts.minimal_bundle_cut_sets([['x']], {'x'})

    def test_preexisting_empty_obligation_not_new_cut(self):
        self.assertEqual(cuts.minimal_bundle_cut_sets([set()], {'x'}), [])

    def test_one_minimum_dominates_superset(self):
        self.assertEqual(cuts.minimal_bundle_cut_sets([{'x'}, {'x','y'}, {'z','y'}],
                                                          {'x','y','z'}),
                         [['x'], ['y','z']])

    def test_cli_processes_and_privacy(self):
        self.upstream()
        cmd = [sys.executable, '-B', '-m', 'superhunter']
        paths = ['--common', str(self.common), '--ablation', str(self.ablation),
                 '--path-audit', str(self.path), '--triage', str(self.triage),
                 '--sources', str(self.sources)]
        first = subprocess.run(cmd+['audit-evidence-cuts']+paths+['--out',str(self.cuts)],
                               capture_output=True, text=True, timeout=50)
        second = subprocess.run(cmd+['verify-evidence-cuts','--bundle',str(self.cuts)]+paths,
                                capture_output=True, text=True, timeout=50)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertNotIn(str(self.base), first.stdout+first.stderr+second.stdout+second.stderr)
        self.assertNotIn('sourcea', first.stdout+first.stderr+second.stdout+second.stderr)

    def reseal(self, name, content):
        (self.cuts / name).write_bytes(content)
        marker = strict_json((self.cuts / 'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(content).hexdigest()
        (self.cuts / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_resealed_false_cut_rejected(self):
        self.produce()
        x = strict_json((self.cuts / 'cut-sets.json').read_bytes())
        x['candidates'][0]['minimum_cut_cardinality'] = 0
        self.reseal('cut-sets.json', canonical(x))
        with self.assertRaisesRegex(cuts.CutSetError, 'CUT_SET_MISMATCH'):
            cuts.verify(self.cuts, self.common, self.ablation,
                        self.path, self.triage, self.sources)

    def test_changed_original_invalidates_review(self):
        self.produce()
        marker = self.bundle / 'COMPLETE.json'
        marker.write_bytes(marker.read_bytes() + b' ')
        with self.assertRaises(cuts.CutSetError):
            cuts.verify(self.cuts, self.common, self.ablation,
                        self.path, self.triage, self.sources)

    def test_resealed_false_critical_claim_rejected(self):
        self.produce()
        x = strict_json((self.cuts / 'cut-sets.json').read_bytes())
        x['claims']['critical_impact_confirmed'] = True
        self.reseal('cut-sets.json', canonical(x))
        with self.assertRaisesRegex(cuts.CutSetError, 'CUT_SET_MISMATCH'):
            cuts.verify(self.cuts, self.common, self.ablation,
                        self.path, self.triage, self.sources)

    def test_denies_overwriting_prior_output(self):
        self.upstream()
        self.cuts.mkdir()
        with self.assertRaises(FileExistsError):
            cuts.review(self.common, self.ablation, self.path, self.triage,
                        self.sources, self.cuts)

    def test_no_external_source_or_severity_claims(self):
        r = self.produce()
        self.assertFalse(r['claims']['active_testing_permitted'])
        self.assertFalse(r['claims']['source_authenticity_established'])
        self.assertTrue(all(not c['independent_producer_identity_proved']
                            for c in r['candidates']))


if __name__ == '__main__':
    unittest.main()
