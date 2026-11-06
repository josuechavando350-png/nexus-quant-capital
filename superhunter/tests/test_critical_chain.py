"""Owned offline controlled triage; no external targets or exploit actions."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import critical_chain as c
from superhunter import forensic_timeline as ft
from superhunter import journal_ingest as journal
from superhunter import journal_correlation as corr
from superhunter.safe_io import canonical, strict_json


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def timeline(root: Path, sid: str, event_ids: list[str], uncertainty: int = 0) -> Path:
    raw = {
        'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
        'sources': [{'source_id': sid, 'clock_uncertainty_ms': uncertainty}],
        'events': [
            {'event_id': eid, 'source_id': sid, 'sequence': i,
             'timestamp': f'2026-11-06T10:00:{i * 2:02d}+00:00',
             'kind': 'process', 'parent_event_id': None,
             'artifact_sha256': sha(eid.encode())}
            for i, eid in enumerate(event_ids)]}
    file = root / f'{sid}.json'
    file.write_bytes(canonical(raw))
    out = root / f'{sid}-bundle'
    ft.review(file, out)
    self_verify = ft.verify(out)
    assert self_verify['events'] == len(event_ids)
    return out


class CriticalChainTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.t1 = timeline(self.root, 'f1', ['ev1', 'ev2', 'ev3'])
        self.t2 = timeline(self.root, 'f2', ['ev4', 'ev5'])
        self.sources = self.root / 'sources-private.json'
        self.specfile = self.root / 'hypotheses-private.json'
        self.out = self.root / 'triage-private'
        self.secret = 'PRIVATE_CASE_EXPERIMENT_DO_NOT_ECHO'
        self.source_spec = {'schema_version': 1, 'sources': [
            {'source_id': 'sourcea', 'kind': 'forensic_timeline', 'bundle_path': str(self.t1)},
            {'source_id': 'sourceb', 'kind': 'forensic_timeline', 'bundle_path': str(self.t2)}]}
        def ref(source, event):
            return {'source_id': source, 'object_id': event}
        self.spec = {
            'schema_version': 1, 'profile': c.PROFILE,
            'scope': {'program_id': 'controlled-lab', 'scope_id': 'scope-20261106',
                      'policy_sha256': sha(b'private operator-provided scope'),
                      'authorization': 'OPERATOR_DECLARED'},
            'observations': [
                {'observation_id': 'low-a', 'asset_id': 'contract-a', 'domain': 'evm',
                 'impact_hint': 'low', 'evidence_refs': [ref('sourcea', 'ev1')]},
                {'observation_id': 'medium-b', 'asset_id': 'service-b', 'domain': 'api',
                 'impact_hint': 'medium', 'evidence_refs': [ref('sourceb', 'ev4')]},
                {'observation_id': 'high-c', 'asset_id': 'contract-c', 'domain': 'evm',
                 'impact_hint': 'high', 'evidence_refs': [ref('sourcea', 'ev3')]}
            ],
            'links': [{'from': 'low-a', 'to': 'medium-b', 'relation': 'enables',
                       'evidence_refs': [ref('sourceb', 'ev5')]}],
            'candidates': [
                {'candidate_id': 'crit-chain', 'observation_ids': ['low-a', 'medium-b'],
                 'kind': 'chain', 'potential_impact': 'critical', 'lab_cost_units': 9},
                {'candidate_id': 'high-single', 'observation_ids': ['high-c'],
                 'kind': 'single', 'potential_impact': 'high', 'lab_cost_units': 1},
            ]}
        self.persist()

    def persist(self):
        self.source_spec['sources'].sort(key=lambda x: x['source_id'])
        self.sources.write_bytes(canonical(self.source_spec))
        self.specfile.write_bytes(canonical(self.spec))

    def create(self):
        self.persist()
        summary = c.review(self.specfile, self.sources, self.out)
        self.assertEqual(summary, c.verify(self.out, self.sources))
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        return strict_json((self.out/'assessment.json').read_bytes())

    def reseal(self, filename: str, raw: bytes):
        (self.out/filename).write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_cli_review_and_verify_separate_processes(self):
        self.persist()
        cmd = [sys.executable, '-B', '-m', 'superhunter']
        first = subprocess.run(cmd + ['triage-critical-chains', '--input', str(self.specfile),
                                '--sources', str(self.sources), '--out', str(self.out)],
                               capture_output=True, text=True)
        second = subprocess.run(cmd + ['verify-critical-triage', '--bundle', str(self.out),
                                 '--sources', str(self.sources)], capture_output=True,
                                text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertNotIn('sourcea', first.stdout + first.stderr + second.stdout + second.stderr)
        self.assertNotIn(str(self.root), first.stdout + first.stderr + second.stdout + second.stderr)

    def test_low_medium_chain_can_be_critical_research_without_critical_verdict(self):
        result = self.create()
        rows = result['ranked_candidates']
        self.assertEqual([x['candidate_id'] for x in rows], ['crit-chain', 'high-single'])
        self.assertEqual(rows[0]['potential_impact'], 'critical')
        self.assertEqual(rows[0]['status'], 'READY_FOR_AUTHORIZED_LAB_REVIEW')
        self.assertEqual(rows[0]['grounded_observations'], 2)
        self.assertEqual(rows[0]['evidence_backed_links_not_causation'], 1)
        self.assertFalse(rows[0]['critical_impact_confirmed'])
        self.assertFalse(rows[0]['vulnerability_confirmed'])
        self.assertFalse(result['claims']['authorization_authenticated'])
        self.assertFalse(result['claims']['active_testing_permitted'])
        self.assertFalse(result['claims']['causation_proved'])

    def test_unknown_scope_disables_authorized_review_even_with_claimed_evidence(self):
        self.spec['scope']['authorization'] = 'UNVERIFIED'
        result = self.create()
        self.assertTrue(all(row['status'] == 'NEEDS_SCOPE_REVIEW'
                            for row in result['ranked_candidates']))
        self.assertFalse(result['claims']['active_testing_permitted'])

    def test_empty_link_evidence_creates_missing_slot_not_false_chain_proof(self):
        self.spec['links'][0]['evidence_refs'] = []
        rows = self.create()['ranked_candidates']
        chain = next(x for x in rows if x['candidate_id'] == 'crit-chain')
        self.assertEqual(chain['missing_evidence_slots'], 1)
        self.assertEqual(chain['status'], 'NEEDS_EVIDENCE')

    def test_unanchored_observation_decreases_priority(self):
        self.spec['observations'][0]['evidence_refs'] = []
        chain = next(x for x in self.create()['ranked_candidates'] if x['candidate_id'] == 'crit-chain')
        self.assertEqual(chain['grounded_observations'], 1)
        self.assertEqual(chain['status'], 'NEEDS_EVIDENCE')

    def test_determinism_under_permutation_of_input_arrays(self):
        a = self.create()
        self.out.rename(self.root/'old-result')
        self.spec['observations'].reverse()
        self.spec['candidates'].reverse()
        self.source_spec['sources'].reverse()
        b = self.create()
        self.assertEqual(a, b)

    def test_duplicate_observation_rejected(self):
        self.spec['observations'].append(deepcopy(self.spec['observations'][0]))
        with self.assertRaisesRegex(c.TriageError, 'DUPLICATE_OBSERVATION'):
            self.create()
        self.assertFalse(self.out.exists())

    def test_duplicate_candidate_rejected(self):
        self.spec['candidates'].append(deepcopy(self.spec['candidates'][0]))
        with self.assertRaisesRegex(c.TriageError, 'DUPLICATE_CANDIDATE'):
            self.create()

    def test_missing_observation_rejected(self):
        self.spec['candidates'][0]['observation_ids'].append('missing')
        with self.assertRaisesRegex(c.TriageError, 'CANDIDATE_OBSERVATIONS'):
            self.create()

    def test_bad_link_endpoint_rejected(self):
        self.spec['links'][0]['to'] = 'not-here'
        with self.assertRaisesRegex(c.TriageError, 'LINK_ENDPOINT'):
            self.create()

    def test_cycle_rejected_not_scored(self):
        self.spec['links'].append({'from': 'medium-b', 'to': 'low-a',
                                   'relation': 'requires', 'evidence_refs': []})
        with self.assertRaisesRegex(c.TriageError, 'CHAIN_CYCLE'):
            self.create()

    def test_disconnected_chain_rejected(self):
        self.spec['links'] = []
        with self.assertRaisesRegex(c.TriageError, 'DISCONNECTED_CHAIN'):
            self.create()

    def test_duplicate_link_rejected(self):
        self.spec['links'].append(deepcopy(self.spec['links'][0]))
        with self.assertRaisesRegex(c.TriageError, 'DUPLICATE_LINK'):
            self.create()

    def test_nonexistent_source_object_rejected(self):
        self.spec['observations'][0]['evidence_refs'][0]['object_id'] = 'not-an-event'
        with self.assertRaisesRegex(c.TriageError, 'UNKNOWN_EVIDENCE_OBJECT'):
            self.create()

    def test_duplicate_evidence_ref_rejected(self):
        ref = self.spec['observations'][0]['evidence_refs'][0]
        self.spec['observations'][0]['evidence_refs'].append(deepcopy(ref))
        with self.assertRaisesRegex(c.TriageError, 'DUPLICATE_EVIDENCE_REF'):
            self.create()

    def test_high_claim_does_not_create_critical_severity(self):
        self.spec['candidates'][0]['potential_impact'] = 'high'
        self.assertTrue(all(not x['critical_impact_confirmed']
                            for x in self.create()['ranked_candidates']))

    def test_bool_as_cost_is_rejected(self):
        self.spec['candidates'][0]['lab_cost_units'] = True
        with self.assertRaisesRegex(c.TriageError, 'LAB_COST'):
            self.create()

    def test_illegal_authorization_approved_claim_rejected(self):
        self.spec['scope']['authorization'] = 'AUTHENTICATED'
        with self.assertRaisesRegex(c.TriageError, 'AUTHORIZATION_DECLARATION'):
            self.create()

    def test_resealed_false_critical_verdict_rejected(self):
        result = self.create()
        result['ranked_candidates'][0]['critical_impact_confirmed'] = True
        self.reseal('assessment.json', canonical(result))
        with self.assertRaisesRegex(c.TriageError, 'ASSESSMENT_CHANGED'):
            c.verify(self.out, self.sources)

    def test_input_changed_and_manifest_resealed_rejected(self):
        self.create()
        raw = strict_json((self.out/'input.json').read_bytes())
        raw['candidates'][0]['potential_impact'] = 'critical' if raw['candidates'][0]['potential_impact'] != 'critical' else 'high'
        self.reseal('input.json', canonical(raw))
        with self.assertRaisesRegex(c.TriageError, 'INPUT_CHANGED'):
            c.verify(self.out, self.sources)

    def test_external_source_changed_rejected(self):
        self.create()
        self.source_spec['sources'][0]['bundle_path'] = str(self.t2)
        self.persist()
        with self.assertRaisesRegex(c.TriageError, 'EXTERNAL_SOURCES_CHANGED'):
            c.verify(self.out, self.sources)

    def test_source_tamper_and_resealed_hash_rejected(self):
        self.create()
        raw = strict_json((self.t1/'timeline.json').read_bytes())
        raw['claims']['causation_proved'] = True
        changed = canonical(raw)
        (self.t1/'timeline.json').write_bytes(changed)
        manifest = strict_json((self.t1/'COMPLETE.json').read_bytes())
        manifest['sha256']['timeline.json'] = sha(changed)
        (self.t1/'COMPLETE.json').write_bytes(canonical(manifest))
        with self.assertRaisesRegex(c.TriageError, 'SOURCE_VERIFICATION_FAILED'):
            c.verify(self.out, self.sources)

    def test_resealed_pins_rejected(self):
        self.create()
        pins = json.loads((self.out/'source-pins.json').read_bytes())
        pins[0]['status'] = 'AUTHENTICATED_FORENSIC_SOURCE'
        self.reseal('source-pins.json', canonical(pins))
        with self.assertRaisesRegex(c.TriageError, 'EXTERNAL_SOURCES_CHANGED'):
            c.verify(self.out, self.sources)

    def test_source_symlink_rejected(self):
        symlink = self.root/'link-to-timeline'
        symlink.symlink_to(self.t1, target_is_directory=True)
        self.source_spec['sources'][0]['bundle_path'] = str(symlink)
        with self.assertRaisesRegex(c.TriageError, 'SOURCE_NOT_DIRECTORY'):
            self.create()

    def test_no_payload_exposure_in_cli_error(self):
        self.spec['scope']['program_id'] = self.secret
        self.persist()
        p = subprocess.run([sys.executable, '-B', '-m', 'superhunter',
                            'triage-critical-chains', '--input', str(self.specfile),
                            '--sources', str(self.sources), '--out', str(self.out)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(self.secret, p.stdout + p.stderr)
        self.assertFalse(self.out.exists())

    def test_existing_journal_correlation_is_really_verified(self):
        bundles = []
        for idx in range(2):
            raw = self.root / f'j{idx}.jsonl'
            raw.write_bytes((json.dumps({'__REALTIME_TIMESTAMP': str(1793984400123456 + idx*2000000),
                                         '__CURSOR': f'c{idx}', 'MESSAGE': self.secret})+'\n').encode())
            out = self.root / f'journal-{idx}'
            journal.ingest(raw, f'labsrc-{idx}', 0, out)
            bundles.append(out)
        hyp = self.root/'links.json'
        first = strict_json((bundles[0]/'normalized.json').read_bytes())['events'][0]['event_id']
        second = strict_json((bundles[1]/'normalized.json').read_bytes())['events'][0]['event_id']
        hyp.write_bytes(canonical({'schema_version':1, 'profile':corr.PROFILE,
                                   'hypotheses': [{'from_event_id': 's00-'+first,
                                                   'to_event_id': 's01-'+second}]}))
        correlated = self.root/'correlated'
        corr.correlate(bundles, hyp, correlated)
        self.source_spec['sources'][1] = {
            'source_id':'sourceb', 'kind':'journal_correlation',
            'bundle_path':str(correlated)}
        actual = strict_json((correlated/'case.json').read_bytes())
        self.spec['observations'][1]['evidence_refs'] = [
            {'source_id':'sourceb', 'object_id':actual['event_proofs'][0]['event_id']}]
        self.spec['links'][0]['evidence_refs'] = [
            {'source_id':'sourceb', 'object_id':actual['event_proofs'][1]['event_id']}]
        self.assertEqual(self.create()['source_count'],2)

    def test_evm_replay_object_sha_binding_to_real_replay(self):
        # Generate an actual byte/trace replay using existing owned tests.
        from superhunter.tests.test_evm_bounded_replay import BoundedReplayTests
        runner = BoundedReplayTests('test_taken_branch_and_every_pc_real_operand')
        runner.setUp()
        self.addCleanup(runner.doCleanups)
        runner._res()
        semantic = strict_json((runner.out/'semantic.json').read_bytes())
        self.source_spec['sources'][0] = {
            'source_id':'sourcea', 'kind':'evm_bounded_replay',
            'bundle_path':str(runner.out)}
        self.spec['observations'][0]['evidence_refs'] = [
            {'source_id':'sourcea','object_id':semantic['trace_sha256']}]
        self.spec['observations'][2]['evidence_refs'] = [
            {'source_id':'sourcea','object_id':semantic['trace_sha256']}]
        result = self.create()
        self.assertEqual(result['ranked_candidates'][0]['status'],
                         'READY_FOR_AUTHORIZED_LAB_REVIEW')
        self.assertFalse(result['claims']['vulnerability_confirmed'])


if __name__ == '__main__':
    unittest.main()
