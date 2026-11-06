"""Independent-replay, tamper and boundary tests for joint evidence loss."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import critical_chain as cc
from superhunter import chain_path_audit as path_audit
from superhunter import evidence_ablation as ablation
from superhunter import evidence_common_mode as common
from superhunter import evidence_joint_failure as joint
from superhunter.safe_io import canonical, strict_json
from test_evidence_ablation import create_source


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class JointEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.a = create_source(self.root, 'duplicate-bundle', ['ev1', 'ev2'])
        self.b = create_source(self.root, 'independent-byte-bundle', ['ev3'])
        self.source_map = {'schema_version': 1, 'sources': [
            {'source_id': 'sourcea', 'kind': 'forensic_timeline', 'bundle_path': str(self.a)},
            {'source_id': 'sourceb', 'kind': 'forensic_timeline', 'bundle_path': str(self.a)},
            {'source_id': 'sourcec', 'kind': 'forensic_timeline', 'bundle_path': str(self.b)}]}
        ref = lambda sid, event: {'source_id': sid, 'object_id': event}
        self.spec = {
            'schema_version': 1, 'profile': cc.PROFILE,
            'scope': {'program_id': 'ownedlab', 'scope_id': 'offline',
                      'policy_sha256': sha(b'operator policy'),
                      'authorization': 'OPERATOR_DECLARED'},
            'observations': [
                {'observation_id': 'a', 'asset_id': 'asset1', 'domain': 'evm',
                 'impact_hint': 'low', 'evidence_refs': [ref('sourcea', 'ev1'), ref('sourceb', 'ev1')]},
                {'observation_id': 'b', 'asset_id': 'asset2', 'domain': 'api',
                 'impact_hint': 'medium', 'evidence_refs': [ref('sourcea', 'ev2'), ref('sourceb', 'ev2')]},
                {'observation_id': 'c', 'asset_id': 'asset3', 'domain': 'cloud',
                 'impact_hint': 'medium', 'evidence_refs': [ref('sourcec', 'ev3')]},
                {'observation_id': 'joint', 'asset_id': 'asset4', 'domain': 'identity',
                 'impact_hint': 'medium', 'evidence_refs': [ref('sourcea', 'ev1'), ref('sourcec', 'ev3')]},
            ],
            'links': [{'from': 'a', 'to': 'b', 'relation': 'enables',
                       'evidence_refs': [ref('sourcea', 'ev1'), ref('sourceb', 'ev1')]}],
            'candidates': [
                {'candidate_id': 'crit', 'observation_ids': ['a', 'b'],
                 'kind': 'chain', 'potential_impact': 'critical', 'lab_cost_units': 1},
                {'candidate_id': 'other', 'observation_ids': ['c'],
                 'kind': 'single', 'potential_impact': 'medium', 'lab_cost_units': 1},
                {'candidate_id': 'cross', 'observation_ids': ['joint'],
                 'kind': 'single', 'potential_impact': 'high', 'lab_cost_units': 1},
            ]}
        self.source_path = self.root/'sources-private.json'
        self.spec_path = self.root/'spec-private.json'
        self.triage = self.root/'triage-private'
        self.path = self.root/'path-private'
        self.ablation = self.root/'ablation-private'
        self.common = self.root/'common-private'
        self.out = self.root/'joint-private'

    def prepare(self):
        self.source_path.write_bytes(canonical(self.source_map))
        self.spec_path.write_bytes(canonical(self.spec))
        cc.review(self.spec_path, self.source_path, self.triage)
        path_audit.review(self.triage, self.source_path, self.path)
        ablation.review(self.path, self.triage, self.source_path, self.ablation)
        common.review(self.ablation, self.path, self.triage, self.source_path, self.common)

    def produce(self, order=2):
        self.prepare()
        result = joint.review(self.common, self.ablation, self.path, self.triage,
                              self.source_path, order, self.out)
        self.assertEqual(result, joint.verify(self.out, self.common, self.ablation,
                                              self.path, self.triage, self.source_path))
        return strict_json((self.out/'joint-failure.json').read_bytes())

    def repack(self, name, raw):
        (self.out/name).write_bytes(raw)
        manifest = strict_json((self.out/'COMPLETE.json').read_bytes())
        manifest['sha256'][name] = sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(manifest))

    def test_alias_group_is_one_failure_unit(self):
        x = self.produce()
        self.assertEqual(x['distinct_complete_byte_hashes'], 2)
        self.assertEqual(x['source_identities'], 3)
        self.assertEqual(x['scenarios_evaluated'], 3)
        crit = next(v for v in x['candidates'] if v['candidate_id']=='crit')
        cut = crit['minimal_new_gap_failure_sets_up_to_order']
        self.assertEqual(len(cut), 1)
        self.assertEqual(cut[0]['lost_source_ids'], ['sourcea','sourceb'])
        self.assertFalse(x['claims']['vulnerability_confirmed'])

    def test_joint_minimal_cut_requires_two_distinct_bundle_hashes(self):
        x = self.produce()
        cross = next(v for v in x['candidates'] if v['candidate_id']=='cross')
        self.assertEqual(len(cross['minimal_new_gap_failure_sets_up_to_order']), 1)
        lost = cross['minimal_new_gap_failure_sets_up_to_order'][0]
        self.assertEqual(len(lost['lost_bundle_hashes']), 2)
        self.assertEqual(lost['lost_source_ids'], ['sourcea','sourceb','sourcec'])
        self.assertTrue(x['entire_bundle_power_set_examined'])

    def test_order_one_explicitly_not_exhaustive(self):
        x = self.produce(order=1)
        self.assertEqual(x['scenarios_evaluated'], 2)
        self.assertFalse(x['entire_bundle_power_set_examined'])
        cross = next(v for v in x['candidates'] if v['candidate_id']=='cross')
        self.assertEqual(cross['minimal_new_gap_failure_sets_up_to_order'], [])
        self.assertFalse(cross['failure_order_fully_exhaustive'])

    def test_three_bundle_case_stays_bounded(self):
        third = create_source(self.root, 'third', ['ev4'])
        self.source_map['sources'].append({'source_id':'sourced', 'kind':'forensic_timeline',
                                           'bundle_path':str(third)})
        x = self.produce(order=2)
        self.assertEqual(x['distinct_complete_byte_hashes'], 3)
        self.assertEqual(x['scenarios_evaluated'], 6)
        self.assertFalse(x['entire_bundle_power_set_examined'])

    def test_bad_requested_orders_rejected(self):
        self.prepare()
        for order in [0, 4, -1, True, '2', None]:
            with self.subTest(order=order), self.assertRaisesRegex(joint.JointFailureError,
                                                                   'FAILURE_ORDER_LIMIT'):
                joint.review(self.common, self.ablation, self.path, self.triage,
                             self.source_path, order, self.out)
        self.assertFalse(self.out.exists())

    def test_cli_review_and_verify_in_separate_processes(self):
        self.prepare()
        prefix=[sys.executable, '-B', '-m', 'superhunter']
        args=['--common',str(self.common), '--ablation',str(self.ablation),
              '--path-audit',str(self.path), '--triage',str(self.triage),
              '--sources',str(self.source_path)]
        a = subprocess.run(prefix+['audit-joint-evidence']+args+
                           ['--max-failure-order','2','--out',str(self.out)],
                           capture_output=True,text=True,timeout=45)
        b = subprocess.run(prefix+['verify-joint-evidence','--bundle',str(self.out)]+args,
                           capture_output=True,text=True,timeout=45)
        self.assertEqual((a.returncode,b.returncode),(0,0),(a.stderr,b.stderr))
        self.assertEqual(json.loads(a.stdout),json.loads(b.stdout))
        self.assertNotIn(str(self.root),a.stdout+b.stdout+a.stderr+b.stderr)
        self.assertNotIn('sourcea',a.stdout+b.stdout+a.stderr+b.stderr)

    def test_forged_critical_impact_rejected_even_when_resealed(self):
        self.produce()
        result=strict_json((self.out/'joint-failure.json').read_bytes())
        result['claims']['critical_impact_confirmed']=True
        self.repack('joint-failure.json',canonical(result))
        with self.assertRaisesRegex(joint.JointFailureError,'RESULT_CHANGED'):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_forged_minimal_cut_rejected_even_when_resealed(self):
        self.produce()
        result=strict_json((self.out/'joint-failure.json').read_bytes())
        result['candidates'][0]['minimal_new_gap_failure_sets_up_to_order']=[]
        self.repack('joint-failure.json',canonical(result))
        with self.assertRaisesRegex(joint.JointFailureError,'RESULT_CHANGED'):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_reseal_exhaustive_scope_falsely_rejected(self):
        self.produce(order=1)
        result=strict_json((self.out/'joint-failure.json').read_bytes())
        result['entire_bundle_power_set_examined']=True
        self.repack('joint-failure.json',canonical(result))
        with self.assertRaisesRegex(joint.JointFailureError,'RESULT_CHANGED'):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_edited_original_source_rejected(self):
        self.produce()
        (self.a/'COMPLETE.json').write_bytes((self.a/'COMPLETE.json').read_bytes()+b' ')
        with self.assertRaises(joint.JointFailureError):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_parent_common_mode_drift_rejected(self):
        self.produce()
        (self.common/'common-mode.json').write_bytes(
            (self.common/'common-mode.json').read_bytes()+b' ')
        with self.assertRaises(joint.JointFailureError):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_missing_private_source_map_rejected(self):
        self.produce()
        self.source_path.unlink()
        with self.assertRaises(joint.JointFailureError):
            joint.verify(self.out,self.common,self.ablation,self.path,self.triage,self.source_path)

    def test_output_unchanged_when_path_exists(self):
        self.prepare()
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            joint.review(self.common,self.ablation,self.path,self.triage,self.source_path,2,self.out)

    def test_byte_hashes_do_not_certify_producers(self):
        result=self.produce()
        self.assertFalse(result['claims']['producer_independence_proved'])
        self.assertTrue(all(not x['producer_independence_proved'] for x in result['candidates']))
        self.assertFalse(result['claims']['authorization_authenticated'])
        self.assertFalse(result['claims']['causation_proved'])


if __name__=='__main__':
    unittest.main()
