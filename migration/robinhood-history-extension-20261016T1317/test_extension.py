"""Offline checks on the changed policy and entry points, no reimplementation."""
import hashlib,json,unittest
from unittest.mock import patch
from continue_history import HERE,PRIOR,engine,main
import audit_extension

class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY'));self.guard.start()
        self.policy=json.loads((HERE/'policy.json').read_text())
        self.raw=(HERE.parent.parent/self.policy['source_path']).read_bytes()
    def tearDown(self):self.guard.stop()
    def test_actual_source_and_adjacent_window(self):
        state=engine.source(self.policy,self.raw)
        self.assertEqual((state['from_block'],state['through_block']),(88246281,90080877))
        self.assertEqual((self.policy['backfill_from_block'],self.policy['backfill_through_block']),(87846281,88246280))
        self.assertEqual(self.policy['source_root'],'e9dfe58703e31d07eb8a61be6ee46f62d5b13679c7e78feb286ce47e4d88ceca')
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),'8cbbeac9381cfdb0a011bd5a74a06c80b07cc755e999b50b42e920dbe0a05dba')
        self.assertEqual(len({e['borrower'] for s in state['segments'] for e in s['events']}),46)
    def test_only_source_and_window_policy_fields_changed(self):
        prior=json.loads((PRIOR/'policy.json').read_text())
        changed={k for k in prior if prior[k]!=self.policy[k]}
        self.assertEqual(changed,{'study','backfill_from_block','backfill_through_block','source_path','source_root','source_file_sha256'})
        self.assertEqual((self.policy['max_requests'],self.policy['max_run_seconds'],self.policy['max_borrowers']),(512,900,64))
    def test_previous_window_rejected_before_rpc(self):
        wrong=dict(self.policy,backfill_from_block=88246281,backfill_through_block=88646280)
        with self.assertRaisesRegex(ValueError,'FIXED_HISTORY_WINDOW'):engine.source(wrong,self.raw)
    def test_entry_point_selects_new_directory_and_restores_on_success(self):
        previous=engine.HERE
        def fake():self.assertEqual(engine.HERE,HERE);return 0
        with patch.object(engine,'main',side_effect=fake):self.assertEqual(main(),0)
        self.assertEqual(engine.HERE,previous)
    def test_entry_point_restores_on_failure_without_retry(self):
        previous=engine.HERE
        with patch.object(engine,'main',side_effect=ValueError('STOP')) as called:
            with self.assertRaisesRegex(ValueError,'STOP'):main()
            self.assertEqual(called.call_count,1)
        self.assertEqual(engine.HERE,previous)
    def test_auditor_supplies_new_policy_explicitly(self):
        with patch.object(audit_extension.replay,'audit',return_value={'status':'fixture'}) as called:
            self.assertEqual(audit_extension.audit('offline-fixture'),{'status':'fixture'})
            called.assert_called_once_with('offline-fixture',self.policy)

if __name__=='__main__':unittest.main()
