"""Real-source offline ablation, exact-set-cover oracle and adversarial replay."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from superhunter import evidence_ablation as m
from superhunter import chain_path_audit as pa
from superhunter import critical_chain as triage
from superhunter import forensic_timeline as ft
from superhunter.safe_io import canonical, strict_json


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def create_source(root: Path, name: str, events: list[str]) -> Path:
    input_path = root / (name + '.json')
    input_path.write_bytes(canonical({
        'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
        'sources': [{'source_id': name, 'clock_uncertainty_ms': 0}],
        'events': [
            {'event_id': eid, 'source_id': name, 'sequence': i,
             'timestamp': f'2026-11-06T13:00:{2*i:02d}+00:00',
             'kind': 'application', 'parent_event_id': None,
             'artifact_sha256': sha(eid.encode())}
            for i, eid in enumerate(events)]
    }))
    output = root / (name + '-source')
    ft.review(input_path, output)
    ft.verify(output)
    return output


class EvidenceAblationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src1 = create_source(self.root, 'labone', ['e1', 'e2'])
        self.src2 = create_source(self.root, 'labtwo', ['e3', 'e4'])
        self.sources = self.root / 'sources-private.json'
        self.input = self.root / 'hypotheses-private.json'
        self.triage_dir = self.root / 'triage-private'
        self.audit_dir = self.root / 'audit-private'
        self.out_dir = self.root / 'ablation-private'
        ref = lambda s,e: {'source_id': s, 'object_id': e}
        self.source_map = {'schema_version': 1, 'sources': [
            {'source_id': 'sa', 'kind': 'forensic_timeline', 'bundle_path': str(self.src1)},
            {'source_id': 'sb', 'kind': 'forensic_timeline', 'bundle_path': str(self.src2)}]}
        self.spec = {
            'schema_version': 1, 'profile': triage.PROFILE,
            'scope': {'program_id': 'local-owned', 'scope_id': 'test-scope',
                      'policy_sha256': sha(b'operator policy declaration'),
                      'authorization': 'OPERATOR_DECLARED'},
            'observations': [
                {'observation_id': 'a', 'asset_id': 'evm1', 'domain': 'evm',
                 'impact_hint': 'low', 'evidence_refs': [ref('sa','e1'),ref('sb','e3')]},
                {'observation_id': 'b', 'asset_id': 'api1', 'domain': 'api',
                 'impact_hint': 'medium', 'evidence_refs': [ref('sb','e4')]},
                {'observation_id': 'c', 'asset_id': 'cloud1', 'domain': 'cloud',
                 'impact_hint': 'high', 'evidence_refs': [ref('sa','e2')]},
            ],
            'links': [{'from': 'a', 'to': 'b', 'relation': 'requires',
                       'evidence_refs': [ref('sa','e1'),ref('sb','e3')]}],
            'candidates': [
                {'candidate_id': 'critical-chain', 'kind': 'chain',
                 'observation_ids': ['a','b'], 'potential_impact': 'critical',
                 'lab_cost_units': 7},
                {'candidate_id': 'single-c', 'kind': 'single',
                 'observation_ids': ['c'], 'potential_impact': 'high',
                 'lab_cost_units': 1},
            ]
        }

    def setup_upstream(self):
        self.sources.write_bytes(canonical(self.source_map))
        self.input.write_bytes(canonical(self.spec))
        triage.review(self.input, self.sources, self.triage_dir)
        pa.review(self.triage_dir, self.sources, self.audit_dir)
        self.assertEqual(pa.verify(self.audit_dir, self.triage_dir, self.sources)['candidates'], 2)

    def produce(self):
        self.setup_upstream()
        self.assertEqual(m.review(self.audit_dir, self.triage_dir, self.sources, self.out_dir),
                         m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources))
        return strict_json((self.out_dir / 'ablation.json').read_bytes())

    @staticmethod
    def row(result, name='critical-chain'):
        return next(row for row in result['candidates'] if row['candidate_id'] == name)

    @staticmethod
    def removed(row, sid):
        return next(r for r in row['single_source_ablations'] if r['source_id'] == sid)

    def reseal(self, bundle: Path, filename: str, data: bytes):
        (bundle / filename).write_bytes(data)
        marker = strict_json((bundle / 'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = sha(data)
        (bundle / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_shared_source_failure_and_cover(self):
        result = self.produce()
        row = self.row(result)
        self.assertEqual(row['minimum_cover_locally_verified_source_ids'], ['sb'])
        self.assertEqual(row['locally_supported_slots'], 3)
        self.assertEqual(row['unsupported_slots'], [])
        self.assertTrue(self.removed(row,'sb')['introduces_evidence_gap'])
        self.assertFalse(self.removed(row,'sa')['introduces_evidence_gap'])
        self.assertEqual(self.removed(row,'sb')['without_source_status'], 'NEEDS_EVIDENCE')
        self.assertEqual(self.removed(row,'sa')['without_source_status'],
                         'READY_FOR_AUTHORIZED_LAB_REVIEW')
        self.assertFalse(row['impact_confirmed'])
        self.assertFalse(result['claims']['source_independence_proved'])

    def test_two_sources_are_minimum_for_two_obligations(self):
        self.spec['observations'][0]['evidence_refs'] = [
            {'source_id':'sa', 'object_id':'e1'}]
        result = self.produce()
        row = self.row(result)
        self.assertEqual(row['minimum_cover_locally_verified_source_ids'], ['sa', 'sb'])
        self.assertTrue(all(x['introduces_evidence_gap']
                            for x in row['single_source_ablations']))

    def test_unanchored_edge_makes_full_cover_impossible(self):
        self.spec['links'][0]['evidence_refs'] = []
        result = self.produce()
        row = self.row(result)
        self.assertIsNone(row['minimum_cover_locally_verified_source_ids'])
        self.assertEqual(row['unsupported_slots'], ['link:a->b'])
        self.assertFalse(row['causation_proved'])

    def test_operator_declared_scope_never_entitles_active_testing(self):
        result = self.produce()
        self.assertFalse(result['claims']['authorization_authenticated'])
        self.assertFalse(result['claims']['active_testing_permitted'])
        self.assertFalse(result['claims']['vulnerability_confirmed'])

    def test_unverified_scope_does_not_promote_critical(self):
        self.spec['scope']['authorization'] = 'UNVERIFIED'
        result = self.produce()
        row = self.row(result)
        self.assertEqual(row['baseline_status'], 'NEEDS_SCOPE_REVIEW')
        self.assertTrue(all(x['without_source_status'] == 'NEEDS_SCOPE_REVIEW'
                            for x in row['single_source_ablations']))
        self.assertFalse(row['impact_confirmed'])

    def test_determinism_when_observation_and_source_order_reversed(self):
        initial = self.produce()
        self.out_dir.rename(self.root/'out-saved')
        self.triage_dir.rename(self.root/'triage-saved')
        self.audit_dir.rename(self.root/'audit-saved')
        self.spec['observations'].reverse()
        self.spec['candidates'].reverse()
        self.spec['links'].reverse()
        self.source_map['sources'].reverse()
        second = self.produce()
        self.assertEqual(initial, second)

    def test_resealed_fake_critical_claim_rejected(self):
        self.produce()
        result = strict_json((self.out_dir/'ablation.json').read_bytes())
        result['candidates'][0]['impact_confirmed'] = True
        self.reseal(self.out_dir, 'ablation.json', canonical(result))
        with self.assertRaisesRegex(m.AblationError, 'ABLATION_RESULT_CHANGED'):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_resealed_fake_source_cover_rejected(self):
        self.produce()
        result = strict_json((self.out_dir/'ablation.json').read_bytes())
        result['candidates'][0]['minimum_cover_locally_verified_source_ids'] = []
        self.reseal(self.out_dir, 'ablation.json', canonical(result))
        with self.assertRaisesRegex(m.AblationError, 'ABLATION_RESULT_CHANGED'):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_changed_original_source_rejected(self):
        self.produce()
        (self.src2/'COMPLETE.json').write_bytes(
            (self.src2/'COMPLETE.json').read_bytes() + b' ')
        with self.assertRaises(m.AblationError):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_resealed_false_upstream_path_rejected(self):
        self.produce()
        data = strict_json((self.audit_dir/'path-audit.json').read_bytes())
        data['claims']['causation_proved'] = True
        self.reseal(self.audit_dir, 'path-audit.json', canonical(data))
        with self.assertRaises(m.AblationError):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_source_snapshot_detects_local_code_change(self):
        self.produce()
        previous = m.snapshot
        m.snapshot = lambda: {'changed_code': 'deadbeef'}
        self.addCleanup(setattr, m, 'snapshot', previous)
        with self.assertRaisesRegex(m.AblationError, 'RECEIPT_MISMATCH'):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_no_existing_dir_overwrite(self):
        self.setup_upstream()
        self.out_dir.mkdir()
        with self.assertRaises(FileExistsError):
            m.review(self.audit_dir, self.triage_dir, self.sources, self.out_dir)

    def test_missing_source_file_rejected(self):
        self.produce()
        self.sources.unlink()
        with self.assertRaises(m.AblationError):
            m.verify(self.out_dir, self.audit_dir, self.triage_dir, self.sources)

    def test_cli_replay_independent_process(self):
        self.setup_upstream()
        base = [sys.executable, '-B', '-m', 'superhunter']
        commands = [base + ['audit-source-ablation', '--path-audit', str(self.audit_dir),
                            '--triage', str(self.triage_dir), '--sources', str(self.sources),
                            '--out', str(self.out_dir)],
                    base + ['verify-source-ablation', '--bundle', str(self.out_dir),
                            '--path-audit', str(self.audit_dir), '--triage', str(self.triage_dir),
                            '--sources', str(self.sources)]]
        results = [subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                   for cmd in commands]
        self.assertTrue(all(r.returncode == 0 for r in results),
                        '\n'.join(r.stderr for r in results))
        self.assertEqual(json.loads(results[0].stdout), json.loads(results[1].stdout))
        self.assertNotIn(str(self.root), ''.join(r.stdout + r.stderr for r in results))
        self.assertNotIn('critical-chain', ''.join(r.stdout + r.stderr for r in results))

    def test_exact_cover_oracle_500(self):
        rand = random.Random(20261106)
        for _ in range(500):
            n = rand.randint(1, 8)
            sources = [f's{i}' for i in range(n)]
            obligations = [
                (f'o{j}', {s for s in sources if rand.randrange(3) != 0})
                for j in range(rand.randint(1, 10))]
            actual = m.minimum_local_source_cover(obligations, list(reversed(sources)))
            # Reference enumerates all masks independently, no implementation helper.
            eligible = []
            for mask in range(1 << n):
                bits = {sources[i] for i in range(n) if mask & (1 << i)}
                if all(bits & slot for _, slot in obligations):
                    eligible.append(tuple(sorted(bits)))
            reference = list(min(eligible, key=lambda x: (len(x), x))) if eligible else None
            self.assertEqual(actual, reference)

    def test_bad_min_cover_inputs_rejected(self):
        with self.assertRaises(m.AblationError):
            m.minimum_local_source_cover([('a', {'missing'})], ['s0'])
        with self.assertRaises(m.AblationError):
            m.minimum_local_source_cover([], ['a']*2)
        with self.assertRaises(m.AblationError):
            m.minimum_local_source_cover([], ['x']*9)


if __name__ == '__main__':
    unittest.main()
