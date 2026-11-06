"""Offline real-bundle integration and adversarial tests of directed evidence audit."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import chain_path_audit as p
from superhunter import critical_chain as c
from superhunter import forensic_timeline as f
from superhunter.safe_io import canonical, strict_json


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def create_timeline(root: Path, source: str, event_ids: list[str]) -> Path:
    obj = {'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
           'sources': [{'source_id': source, 'clock_uncertainty_ms': 0}],
           'events': [{'event_id': eid, 'source_id': source, 'sequence': index,
                       'timestamp': f'2026-11-06T12:00:{index*2:02d}+00:00',
                       'kind': 'process', 'parent_event_id': None,
                       'artifact_sha256': digest(eid.encode())}
                      for index, eid in enumerate(event_ids)]}
    inp = root / (source + '.json')
    inp.write_bytes(canonical(obj))
    output = root / (source + '-bundle')
    f.review(inp, output)
    return output


class ChainPathAuditTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.s1 = create_timeline(self.root, 'forensics-a', ['event-a', 'event-c', 'event-d'])
        self.s2 = create_timeline(self.root, 'forensics-b', ['event-b'])
        self.source_map = self.root / 'sources-private.json'
        self.input = self.root / 'hypotheses-private.json'
        self.triage = self.root / 'triage-private'
        self.out = self.root / 'audit-private'
        self.sources = {'schema_version': 1, 'sources': [
            {'source_id': 'sa', 'kind': 'forensic_timeline', 'bundle_path': str(self.s1)},
            {'source_id': 'sb', 'kind': 'forensic_timeline', 'bundle_path': str(self.s2)}]}
        def ref(src, oid):
            return [{'source_id': src, 'object_id': oid}]
        self.spec = {
            'schema_version': 1, 'profile': c.PROFILE,
            'scope': {'program_id': 'owned-lab', 'scope_id': 'owned-scope',
                      'policy_sha256': digest(b'operator provided policy'),
                      'authorization': 'OPERATOR_DECLARED'},
            'observations': [
                {'observation_id': 'a', 'asset_id': 'evm1', 'domain': 'evm',
                 'impact_hint': 'low', 'evidence_refs': ref('sa', 'event-a')},
                {'observation_id': 'b', 'asset_id': 'api1', 'domain': 'api',
                 'impact_hint': 'medium', 'evidence_refs': ref('sb', 'event-b')},
                {'observation_id': 'c', 'asset_id': 'defi1', 'domain': 'defi',
                 'impact_hint': 'low', 'evidence_refs': ref('sa', 'event-c')},
                {'observation_id': 'd', 'asset_id': 'cloud1', 'domain': 'cloud',
                 'impact_hint': 'high', 'evidence_refs': ref('sa', 'event-d')}],
            'links': [
                {'from': 'a', 'to': 'b', 'relation': 'enables',
                 'evidence_refs': ref('sb', 'event-b')},
                {'from': 'b', 'to': 'c', 'relation': 'requires',
                 'evidence_refs': []},
                {'from': 'a', 'to': 'd', 'relation': 'amplifies',
                 'evidence_refs': ref('sa', 'event-a')}],
            'candidates': [
                {'candidate_id': 'critical-three', 'observation_ids': ['a', 'b', 'c'],
                 'kind': 'chain', 'potential_impact': 'critical', 'lab_cost_units': 7},
                {'candidate_id': 'fork', 'observation_ids': ['a', 'b', 'd'],
                 'kind': 'chain', 'potential_impact': 'high', 'lab_cost_units': 3},
                {'candidate_id': 'single', 'observation_ids': ['d'],
                 'kind': 'single', 'potential_impact': 'high', 'lab_cost_units': 1}]}
        self.persist()

    def persist(self):
        self.source_map.write_bytes(canonical(self.sources))
        self.input.write_bytes(canonical(self.spec))

    def setup_triage(self):
        self.persist()
        c.review(self.input, self.source_map, self.triage)
        self.assertEqual(c.verify(self.triage, self.source_map)['candidates'], 3)

    def execute(self):
        self.setup_triage()
        self.assertEqual(p.review(self.triage, self.source_map, self.out),
                         p.verify(self.out, self.triage, self.source_map))
        return strict_json((self.out / 'path-audit.json').read_bytes())

    def row(self, assessment, name):
        return next(r for r in assessment['candidates'] if r['candidate_id'] == name)

    def reseal(self, bundle: Path, file: str, raw: bytes):
        (bundle / file).write_bytes(raw)
        marker = strict_json((bundle / 'COMPLETE.json').read_bytes())
        marker['sha256'][file] = digest(raw)
        (bundle / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_longest_path_reports_unverified_link_without_false_critical(self):
        result = self.execute()
        row = self.row(result, 'critical-three')
        self.assertEqual(row['directional_witness'], ['a', 'b', 'c'])
        self.assertEqual(row['witness_node_count'], 3)
        self.assertEqual(row['uncovered_nodes'], [])
        self.assertEqual(row['unsupported_declared_links'],
                         [{'from': 'b', 'to': 'c', 'relation': 'requires'}])
        self.assertEqual(row['disposition'], 'LOCAL_EVIDENCE_GAPS')
        self.assertIn('TEST_DEPENDENCY_HYPOTHESES', row['proof_obligations'])
        self.assertFalse(row['critical_impact_confirmed'])
        self.assertFalse(row['causation_proved'])
        self.assertFalse(result['claims']['active_testing_permitted'])

    def test_branch_not_misrepresented_as_one_end_to_end_chain(self):
        result = self.execute()
        row = self.row(result, 'fork')
        self.assertEqual(row['directional_witness'], ['a', 'b'])
        self.assertEqual(row['uncovered_nodes'], ['d'])
        self.assertEqual(row['disposition'], 'BRANCHED_OR_PARTIAL_DIRECTED_WITNESS')
        self.assertIn('DESIGN_BRANCH_COVERAGE_EXPERIMENT', row['proof_obligations'])

    def test_single_is_not_converted_to_critical(self):
        result = self.execute()
        row = self.row(result, 'single')
        self.assertEqual(row['directional_witness'], ['d'])
        self.assertEqual(row['witness_edges'], [])
        self.assertFalse(row['vulnerability_confirmed'])
        self.assertIn('VERIFY_IMPACT_INDEPENDENTLY', row['proof_obligations'])

    def test_all_link_anchors_are_still_not_causation(self):
        self.spec['links'][1]['evidence_refs'] = [{'source_id':'sa', 'object_id':'event-c'}]
        result = self.execute()
        row = self.row(result, 'critical-three')
        self.assertEqual(row['disposition'], 'DIRECTED_WITNESS_ANCHORED_NOT_CAUSAL_PROOF')
        self.assertTrue(all(x['has_locally_verified_reference'] for x in row['witness_edges']))
        self.assertFalse(any(x['causation_proved'] for x in row['witness_edges']))
        self.assertFalse(row['critical_impact_confirmed'])
        self.assertFalse(result['claims']['producer_identity_authenticated'])

    def test_unanchored_observation_must_be_reported(self):
        self.spec['observations'][2]['evidence_refs'] = []
        result = self.execute()
        row = self.row(result, 'critical-three')
        self.assertEqual(row['unsupported_observations'], ['c'])
        self.assertIn('CAPTURE_OBSERVATION_SUPPORT', row['proof_obligations'])

    def test_unverified_scope_never_allows_active_testing(self):
        self.spec['scope']['authorization'] = 'UNVERIFIED'
        result = self.execute()
        self.assertTrue(all(row['upstream_status'] == 'NEEDS_SCOPE_REVIEW'
                            for row in result['candidates']))
        self.assertTrue(all(not row['active_testing_permitted']
                            for row in result['candidates']))
        self.assertFalse(result['claims']['authorization_authenticated'])

    def test_ranked_claims_are_not_probabilities(self):
        result = self.execute()
        self.assertTrue(all(type(row['upstream_priority_score']) is int
                            for row in result['candidates']))
        self.assertFalse(result['claims']['severity_confirmed'])

    def test_algorithm_prefers_longer_witness_then_fewer_gaps(self):
        result = p.longest_directed_witness(['a', 'b', 'c', 'd', 'e'],
                                           [('a', 'b', False), ('b', 'e', False),
                                            ('a', 'c', True), ('c', 'e', True),
                                            ('a', 'd', True)])
        self.assertEqual(result, ['a', 'c', 'e'])

    def test_cycle_direct_algorithm_rejected(self):
        with self.assertRaisesRegex(p.PathAuditError, 'DIRECTED_CYCLE'):
            p.longest_directed_witness(['a', 'b'], [('a', 'b', True), ('b', 'a', True)])

    def test_algorithm_stable_under_node_and_edge_permutation(self):
        a = ['a', 'b', 'c', 'd']
        edges = [('a', 'b', True), ('a', 'c', True), ('b', 'd', True), ('c', 'd', True)]
        self.assertEqual(p.longest_directed_witness(a, edges),
                         p.longest_directed_witness(a[::-1], edges[::-1]))

    def test_full_assessment_invariant_under_shuffled_spec(self):
        one = self.execute()
        self.out.rename(self.root / 'saved-audit')
        self.triage.rename(self.root / 'saved-triage')
        self.spec['observations'].reverse()
        self.spec['links'].reverse()
        self.spec['candidates'].reverse()
        two = self.execute()
        self.assertEqual(one, two)

    def test_external_source_change_invalidates_replay(self):
        self.execute()
        original = (self.s1 / 'COMPLETE.json').read_bytes()
        (self.s1 / 'COMPLETE.json').write_bytes(original + b' ')
        with self.assertRaises(p.PathAuditError):
            p.verify(self.out, self.triage, self.source_map)

    def test_modified_report_rejected_even_when_resigned_hash(self):
        self.execute()
        self.reseal(self.out, 'REVIEW.md', b'# Forged report\n')
        with self.assertRaisesRegex(p.PathAuditError, 'REPORT_CHANGED'):
            p.verify(self.out, self.triage, self.source_map)

    def test_false_severity_claim_rejected_even_when_rehashed(self):
        self.execute()
        forged = strict_json((self.out / 'path-audit.json').read_bytes())
        forged['claims']['severity_confirmed'] = True
        self.reseal(self.out, 'path-audit.json', canonical(forged))
        with self.assertRaisesRegex(p.PathAuditError, 'PATH_AUDIT_CHANGED'):
            p.verify(self.out, self.triage, self.source_map)

    def test_changed_receipt_rejected_even_when_rehashed(self):
        self.execute()
        forged = strict_json((self.out / 'receipt.json').read_bytes())
        forged['report_sha256'] = digest(b'other')
        self.reseal(self.out, 'receipt.json', canonical(forged))
        with self.assertRaisesRegex(p.PathAuditError, 'RECEIPT_MISMATCH'):
            p.verify(self.out, self.triage, self.source_map)

    def test_missing_source_map_blocks_verify(self):
        self.execute()
        self.source_map.unlink()
        with self.assertRaises(p.PathAuditError):
            p.verify(self.out, self.triage, self.source_map)

    def test_symlink_bundle_disallowed(self):
        self.execute()
        alias = self.root / 'alias'
        alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaisesRegex(p.PathAuditError, 'BUNDLE_DIRECTORY'):
            p.verify(alias, self.triage, self.source_map)

    def test_extra_artifact_blocks_verify(self):
        self.execute()
        (self.out / 'extra.txt').write_text('opaque')
        with self.assertRaisesRegex(p.PathAuditError, 'BUNDLE_FILES'):
            p.verify(self.out, self.triage, self.source_map)

    def test_current_source_identity_prevents_false_replay(self):
        self.execute()
        receipt = strict_json((self.out / 'receipt.json').read_bytes())
        receipt['snapshot']['critical_chain.py'] = digest(b'different-code')
        self.reseal(self.out, 'receipt.json', canonical(receipt))
        with self.assertRaisesRegex(p.PathAuditError, 'RECEIPT_MISMATCH'):
            p.verify(self.out, self.triage, self.source_map)

    def test_cli_two_independent_processes_private_stdout(self):
        self.setup_triage()
        base = [sys.executable, '-B', '-m', 'superhunter']
        a = subprocess.run(base + ['audit-chain-paths', '--triage', str(self.triage),
                                   '--sources', str(self.source_map), '--out', str(self.out)],
                           capture_output=True, text=True)
        b = subprocess.run(base + ['verify-chain-paths', '--bundle', str(self.out),
                                   '--triage', str(self.triage), '--sources', str(self.source_map)],
                           capture_output=True, text=True)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(json.loads(a.stdout), json.loads(b.stdout))
        self.assertNotIn(str(self.root), a.stdout + a.stderr + b.stdout + b.stderr)
        self.assertNotIn('event-a', a.stdout + a.stderr + b.stdout + b.stderr)
        self.assertNotIn('forensics-a', a.stdout + a.stderr + b.stdout + b.stderr)

    def test_private_bundle_not_world_readable(self):
        self.execute()
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        for name in p.FILES:
            self.assertEqual((self.out / name).stat().st_mode & 0o777, 0o600)

    def test_missing_external_triage_blocks_replay(self):
        self.execute()
        self.triage.rename(self.root / 'removed-triage')
        with self.assertRaises(p.PathAuditError):
            p.verify(self.out, self.triage, self.source_map)

    def test_trailing_corrupt_source_pin_rejected(self):
        self.execute()
        self.reseal(self.out, 'source-pin.json', b'not-json')
        with self.assertRaises(ValueError):
            p.verify(self.out, self.triage, self.source_map)

    def test_invalid_downstream_claims_are_never_in_response(self):
        result = self.execute()
        for row in result['candidates']:
            for key in ('critical_impact_confirmed', 'vulnerability_confirmed',
                        'active_testing_permitted', 'causation_proved'):
                self.assertIs(row[key], False)


if __name__ == '__main__':
    unittest.main()
