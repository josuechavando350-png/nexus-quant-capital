from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_endurance_provenance import verify

PACKAGE=Path(__file__).resolve().parents[1]
REPO=PACKAGE.parents[1]


class EnduranceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/'docs').mkdir()
        self.index=json.loads((PACKAGE/'docs/ENDURANCE_PROVENANCE.json').read_text())
        for entry in self.index['reports']:
            shutil.copyfile(PACKAGE/entry['path'],self.root/entry['path'])

    def change_report(self, action):
        entry=self.index['reports'][0]; path=self.root/entry['path']; value=json.loads(path.read_text())
        action(value); raw=json.dumps(value).encode(); path.write_bytes(raw)
        entry['sha256']=hashlib.sha256(raw).hexdigest()

    def test_recorded_sources_match_actual_immutable_git_objects(self):
        result=verify(self.index,REPO,self.root)
        self.assertTrue(result['verified']); self.assertGreaterEqual(len(result['reports']),2)
        self.assertFalse(result['independent_execution_attestation'])
        self.assertFalse(result['wall_clock_independently_certified'])
        self.assertFalse(result['reports'][0]['harness_hash_recorded_in_run'])

    def test_report_byte_change_is_rejected(self):
        path=self.root/self.index['reports'][0]['path']; path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'provenance_report_digest'): verify(self.index,REPO,self.root)

    def test_rehashed_source_claim_still_must_match_git(self):
        self.change_report(lambda r:r['source_sha256'].update({'signer_registry.py':'0'*64}))
        with self.assertRaisesRegex(ValueError,'provenance_source_digest'): verify(self.index,REPO,self.root)

    def test_report_cannot_be_assigned_to_a_different_version_label(self):
        self.index['reports'][0]['tested_runtime_version']='99.0.0'
        with self.assertRaisesRegex(ValueError,'provenance_version'): verify(self.index,REPO,self.root)

    def test_incomplete_duration_rejected_even_if_verified_flag_is_true(self):
        self.change_report(lambda r:r.update(elapsed_seconds=r['requested_seconds']-1))
        with self.assertRaisesRegex(ValueError,'provenance_incomplete_duration'): verify(self.index,REPO,self.root)

    def test_report_path_cannot_escape_docs(self):
        self.index['reports'][0]['path']='docs/../../outside.json'
        with self.assertRaisesRegex(ValueError,'provenance_report_path'): verify(self.index,REPO,self.root)

    def test_pending_runs_block_complete_mode(self):
        self.index['other_runs_in_progress']=['declared unfinished run']
        with self.assertRaisesRegex(ValueError,'provenance_runs_pending'): verify(self.index,REPO,self.root,require_complete=True)

    def test_harness_hash_must_match_its_preserved_commit(self):
        self.index['reports'][0]['harness_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'provenance_harness_digest'): verify(self.index,REPO,self.root)

    def test_empty_work_count_is_not_a_pass(self):
        self.change_report(lambda r:r.update(verified_calls=0))
        with self.assertRaisesRegex(ValueError,'provenance_operation_count'): verify(self.index,REPO,self.root)

    def test_omitted_source_cannot_pass_after_rehashing_report(self):
        self.change_report(lambda r:r['source_sha256'].pop('signer_registry.py'))
        with self.assertRaisesRegex(ValueError,'provenance_source_membership'): verify(self.index,REPO,self.root)

    def test_alias_cannot_replace_the_recorded_source_name(self):
        self.change_report(lambda r:r['source_sha256'].update({'nqc_defense/signer_registry.py':r['source_sha256'].pop('signer_registry.py')}))
        with self.assertRaisesRegex(ValueError,'provenance_source_membership'): verify(self.index,REPO,self.root)

    def test_unknown_run_schema_rejected(self):
        self.change_report(lambda r:r.update(schema='invented-schema'))
        with self.assertRaisesRegex(ValueError,'provenance_run_schema'): verify(self.index,REPO,self.root)

    def test_v2_requires_its_recorded_package_version(self):
        self.index['reports']=[self.index['reports'][1]]
        self.change_report(lambda r:r.pop('tested_package_version'))
        with self.assertRaisesRegex(ValueError,'provenance_report_version'): verify(self.index,REPO,self.root)

    def test_valid_complete_index_checks_all_three_real_reports(self):
        result=verify(self.index,REPO,self.root,require_complete=True)
        self.assertTrue(result['all_recorded_runs_complete'])
        self.assertEqual(len(result['reports']),3)


if __name__=='__main__':
    unittest.main()
