"""Identical-byte bundle alias detection and private end-to-end replay tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import evidence_common_mode as cm
from superhunter import evidence_ablation as abl
from superhunter import chain_path_audit as pa
from superhunter import critical_chain as cc
from superhunter.safe_io import canonical, strict_json
from test_evidence_ablation import create_source


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CommonEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.bundle = create_source(self.base, 'same-bundle', ['ev1','ev2'])
        self.other = create_source(self.base, 'other-bundle', ['ev3'])
        self.sources = self.base/'sources-private.json'
        self.input = self.base/'input-private.json'
        self.triage = self.base/'triage-private'
        self.path = self.base/'path-private'
        self.ablation = self.base/'ablation-private'
        self.out = self.base/'common-private'
        self.source_map = {'schema_version':1, 'sources': [
            {'source_id':'sourcea', 'kind':'forensic_timeline', 'bundle_path':str(self.bundle)},
            {'source_id':'sourceb', 'kind':'forensic_timeline', 'bundle_path':str(self.bundle)},
            {'source_id':'sourcec', 'kind':'forensic_timeline', 'bundle_path':str(self.other)},
        ]}
        refs = lambda event: [
            {'source_id':sid,'object_id':event}
            for sid in ['sourcea','sourceb']]
        self.spec = {
            'schema_version':1, 'profile':cc.PROFILE,
            'scope':{'program_id':'owned-test','scope_id':'bounded',
                     'policy_sha256':sha(b'operator provided text'),
                     'authorization':'OPERATOR_DECLARED'},
            'observations': [
                {'observation_id':'a','asset_id':'p1','domain':'evm',
                 'impact_hint':'low','evidence_refs':refs('ev1')},
                {'observation_id':'b','asset_id':'p2','domain':'api',
                 'impact_hint':'medium','evidence_refs':refs('ev2')},
                {'observation_id':'c','asset_id':'p3','domain':'cloud',
                 'impact_hint':'high','evidence_refs':[{'source_id':'sourcec','object_id':'ev3'}]},
            ],
            'links': [{'from':'a','to':'b','relation':'enables',
                       'evidence_refs':refs('ev1')}],
            'candidates': [
                {'candidate_id':'crit', 'observation_ids':['a','b'],'kind':'chain',
                 'potential_impact':'critical','lab_cost_units':1},
                {'candidate_id':'single', 'observation_ids':['c'],'kind':'single',
                 'potential_impact':'high','lab_cost_units':1},
            ],
        }

    def setup_previous(self):
        self.sources.write_bytes(canonical(self.source_map))
        self.input.write_bytes(canonical(self.spec))
        cc.review(self.input, self.sources, self.triage)
        pa.review(self.triage, self.sources, self.path)
        abl.review(self.path, self.triage, self.sources, self.ablation)
        self.assertEqual(abl.verify(self.ablation, self.path, self.triage, self.sources)['candidates'],2)

    def produce(self):
        self.setup_previous()
        self.assertEqual(cm.review(self.ablation, self.path, self.triage,
                                   self.sources, self.out),
                         cm.verify(self.out, self.ablation, self.path,
                                   self.triage, self.sources))
        return strict_json((self.out/'common-mode.json').read_bytes())

    def reseal(self, folder:Path, name:str, raw:bytes):
        (folder/name).write_bytes(raw)
        manifest = strict_json((folder/'COMPLETE.json').read_bytes())
        manifest['sha256'][name] = sha(raw)
        (folder/'COMPLETE.json').write_bytes(canonical(manifest))

    def test_identical_bundle_aliases_not_fake_independence(self):
        report = self.produce()
        self.assertEqual(report['source_identities'],3)
        self.assertEqual(report['unique_complete_byte_hashes'],2)
        self.assertEqual(report['identical_bundle_alias_groups'], [['sourcea','sourceb']])
        group = next(g for g in report['group_ablations']
                     if g['source_ids']==['sourcea','sourceb'])
        crit = next(c for c in group['cases'] if c['candidate_id']=='crit')
        self.assertTrue(crit['new_evidence_gap'])
        self.assertTrue(crit['single_alias_tests_were_insufficient'])
        self.assertFalse(crit['vulnerability_confirmed'])
        self.assertFalse(report['claims']['independent_producers_established'])

    def test_unrelated_source_loss_does_not_create_fake_gap(self):
        report = self.produce()
        group = next(g for g in report['group_ablations'] if g['source_ids']==['sourcec'])
        crit = next(c for c in group['cases'] if c['candidate_id']=='crit')
        self.assertFalse(crit['new_evidence_gap'])
        self.assertEqual(crit['priority_delta'],0)
        self.assertFalse(crit['single_alias_tests_were_insufficient'])

    def test_all_distinct_bundles_have_no_duplicate_groups(self):
        # Replace the second alias with the other provenance bundle, referencing
        # actual objects, while keeping candidate structure unchanged.
        self.source_map['sources'] = self.source_map['sources'][:2]
        self.source_map['sources'][1]['bundle_path'] = str(self.other)
        for row in self.spec['observations'] + self.spec['links']:
            row['evidence_refs'] = [r for r in row['evidence_refs']
                                    if r['source_id']=='sourcea']
        self.spec['observations'][2]['evidence_refs'] = []
        report = self.produce()
        self.assertEqual(report['identical_bundle_alias_groups'],[])
        self.assertEqual(report['source_identities'],report['unique_complete_byte_hashes'])
        self.assertFalse(report['claims']['independent_producers_established'])

    def test_cli_independent_replay(self):
        self.setup_previous()
        cmd = [sys.executable,'-B','-m','superhunter']
        args = ['--ablation',str(self.ablation),'--path-audit',str(self.path),
                '--triage',str(self.triage),'--sources',str(self.sources)]
        first = subprocess.run(cmd + ['audit-common-evidence'] + args +
                               ['--out',str(self.out)],capture_output=True,text=True,timeout=40)
        second = subprocess.run(cmd + ['verify-common-evidence','--bundle',str(self.out)] +
                                args,capture_output=True,text=True,timeout=40)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertEqual(json.loads(first.stdout),json.loads(second.stdout))
        self.assertNotIn(str(self.base),first.stdout+first.stderr+second.stdout+second.stderr)
        self.assertNotIn('sourcea',first.stdout+first.stderr+second.stdout+second.stderr)

    def test_resealed_false_diversity_rejected(self):
        self.produce()
        data = strict_json((self.out/'common-mode.json').read_bytes())
        data['claims']['independent_producers_established'] = True
        self.reseal(self.out,'common-mode.json',canonical(data))
        with self.assertRaisesRegex(cm.CommonModeError,'RESULT_CHANGED'):
            cm.verify(self.out,self.ablation,self.path,self.triage,self.sources)

    def test_resealed_false_group_loss_rejected(self):
        self.produce()
        data = strict_json((self.out/'common-mode.json').read_bytes())
        data['group_ablations'][0]['cases'][0]['priority_delta'] = 0
        self.reseal(self.out,'common-mode.json',canonical(data))
        with self.assertRaises(cm.CommonModeError):
            cm.verify(self.out,self.ablation,self.path,self.triage,self.sources)

    def test_upstream_original_change_rejected(self):
        self.produce()
        (self.bundle/'COMPLETE.json').write_bytes((self.bundle/'COMPLETE.json').read_bytes()+b' ')
        with self.assertRaises(cm.CommonModeError):
            cm.verify(self.out,self.ablation,self.path,self.triage,self.sources)

    def test_upstream_ablation_reseal_rejected(self):
        self.produce()
        data = strict_json((self.ablation/'ablation.json').read_bytes())
        data['claims']['causation_proved'] = True
        self.reseal(self.ablation,'ablation.json',canonical(data))
        with self.assertRaises(cm.CommonModeError):
            cm.verify(self.out,self.ablation,self.path,self.triage,self.sources)

    def test_changed_source_map_rejected(self):
        self.produce()
        self.sources.unlink()
        with self.assertRaises(cm.CommonModeError):
            cm.verify(self.out,self.ablation,self.path,self.triage,self.sources)

    def test_exact_bundle_grouping_stable_under_permutation(self):
        pins = [{'source_id':sid,'complete_sha256':value} for sid,value in
                [('z','a'*64),('b','b'*64),('y','a'*64),('a','b'*64)]]
        self.assertEqual(cm.group_exact_bundles(pins),cm.group_exact_bundles(pins[::-1]))
        groups = cm.group_exact_bundles(pins)
        self.assertEqual([g['source_ids'] for g in groups],[['a','b'],['y','z']])

    def test_duplicate_source_ids_rejected(self):
        with self.assertRaisesRegex(cm.CommonModeError,'DUPLICATE_SOURCE_ID'):
            cm.group_exact_bundles([
                {'source_id':'x','complete_sha256':'a'*64},
                {'source_id':'x','complete_sha256':'b'*64}])

    def test_outputs_deny_overwrite(self):
        self.setup_previous()
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            cm.review(self.ablation,self.path,self.triage,self.sources,self.out)

    def test_no_source_producer_authentication_claim(self):
        report=self.produce()
        self.assertTrue(all(not r['verified_producer_independence']
                            for g in report['group_ablations'] for r in g['cases']))
        self.assertFalse(report['claims']['source_authenticity_established'])
        self.assertFalse(report['claims']['authorization_authenticated'])
        self.assertFalse(report['claims']['vulnerability_confirmed'])


if __name__=='__main__':
    unittest.main()
