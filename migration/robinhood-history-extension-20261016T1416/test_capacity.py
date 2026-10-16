"""Checks the real stop attribution, not a changed capture protocol."""
import json,unittest
from unittest.mock import patch
from capacity_diagnosis import HERE,diagnose

class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'));self.guard.start()
        self.result=diagnose(HERE/'evidence/pilot')
    def tearDown(self):self.guard.stop()
    def test_only_event_block_limit_was_exceeded(self):
        self.assertEqual(self.result['union_counts_not_persisted'],dict(logs=145,event_blocks=145,borrowers=54))
        self.assertEqual(self.result['limits'],dict(logs=512,event_blocks=128,borrowers=64))
        self.assertEqual(self.result['violated_limits'],['event_blocks'])
    def test_complete_history_and_original_source_retained(self):
        self.assertEqual(self.result['source_counts'],dict(logs=125,event_blocks=125,borrowers=52))
        self.assertEqual(self.result['history_counts'],dict(logs=20,event_blocks=20,borrowers=11))
        self.assertEqual(len(self.result['new_accounts_in_unmerged_history']),2)
        self.assertTrue(self.result['history_window_complete'])
        self.assertEqual(self.result['files_sha256']['source-registry.json'],self.result['files_sha256']['registry.json'])
    def test_failure_precedes_persisted_merge_and_measurement(self):
        rejection=self.result['first_merge_rejection']
        self.assertLessEqual(rejection['counts_before']['event_blocks'],128)
        self.assertGreater(rejection['proposed_counts']['event_blocks'],128)
        self.assertLessEqual(rejection['proposed_counts']['borrowers'],64)
        for field in ('merged_registry_persisted','cohort_frozen','current_coverage_measured','current_candidates_measured','limits_changed'):
            self.assertFalse(self.result[field])
        self.assertEqual(self.result['rpc_calls'],0)
    def test_saved_diagnosis_reproduces_exactly(self):
        self.assertEqual(self.result,json.loads((HERE/'evidence/capacity-diagnosis.json').read_text()))

if __name__=='__main__':unittest.main()
