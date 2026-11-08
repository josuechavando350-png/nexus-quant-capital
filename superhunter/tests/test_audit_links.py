"""Regressions for internally rehashed but semantically inconsistent lab evidence."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from superhunter.audit_links import verify_audit_links
from superhunter.local_lab import execute_local, verify_local_bundle
from superhunter.native_runtime import load_components
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class AuditLinkTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.files = {k: strict_json(v) for k, v in execute_local().items()}
        self.audit = self.files['diablo-audit.json']['entries']
        self.result = self.files['lab-result.json']
        self.cases = self.files['nqc-results.json']['cases']

    def check(self):
        verify_audit_links(self.audit, self.result, self.cases)

    def test_valid_native_sequence(self):
        self.check()

    def test_input_hash_substitution_rejected_even_after_rehash(self):
        self.audit[2]['data']['input_sha256'] = '0'*64
        native = load_components()
        previous = '0'*64
        for entry in self.audit:
            entry['prev_hash'] = previous
            entry['hash'] = native.audit.compute_hash(entry['index'], entry['timestamp'],
                entry['event'], entry['data'], previous)
            previous = entry['hash']
        self.result['audit_head'] = previous
        out = self.root/'rehashed'
        write_new_bundle(out, {name: canonical(value) for name,value in self.files.items()})
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            verify_local_bundle(out)

    def test_output_commitment_must_match_actual_case(self):
        self.audit[3]['data']['output_commitment'] = '0x'+'d'*64
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_scope_must_precede_calculation(self):
        self.audit[1]['event'] = 'lab.nqc.start'
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_allows_cannot_substitute_exclusion(self):
        self.audit[-2]['data']['decision'] = 'ALLOW'
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_unrelated_scope_target_rejected(self):
        self.audit[1]['data']['target'] = 'other.lab.invalid'
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_event_swapping_rejected(self):
        self.audit[2]['data'],self.audit[5]['data'] = self.audit[5]['data'], self.audit[2]['data']
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_missing_event_rejected(self):
        self.audit.pop(4);self.result['audit_count']-=1
        with self.assertRaisesRegex(ValueError, 'event coverage'):
            self.check()

    def test_extra_event_data_rejected(self):
        self.audit[2]['data']['confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_boolean_is_not_count(self):
        self.result['schema_version'] = True
        with self.assertRaisesRegex(ValueError, 'count/schema'):
            self.check()

    def test_boolean_is_not_event_index(self):
        self.audit[1]['index'] = True
        with self.assertRaisesRegex(ValueError, 'index type'):
            self.check()

    def test_numeric_fixture_flag_not_boolean(self):
        self.audit[0]['data']['fixture_only'] = 1
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_forged_run_uuid_rejected(self):
        self.result['run_id'] = 'not-a-uuid'
        with self.assertRaises(ValueError):
            self.check()

    def test_wrong_native_function_claim_rejected(self):
        self.result['native_functions'].append('arbitrary.engine')
        with self.assertRaisesRegex(ValueError, 'execution claims'):
            self.check()

    def test_false_execution_claim_rejected(self):
        self.result['local_component_execution'] = False
        with self.assertRaisesRegex(ValueError, 'execution claims'):
            self.check()

    def test_completion_run_mismatch(self):
        self.audit[-1]['data']['run_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'semantic binding'):
            self.check()

    def test_naive_timestamp_rejected(self):
        self.audit[1]['timestamp'] = '2026-11-03T00:00:00'
        with self.assertRaisesRegex(ValueError, 'timezone'):
            self.check()

    def test_reversed_time_rejected(self):
        self.result['started_at'],self.result['completed_at'] = self.result['completed_at'],self.result['started_at']
        with self.assertRaisesRegex(ValueError, 'reversed'):
            self.check()

    def test_out_of_run_timestamp_rejected(self):
        self.audit[4]['timestamp'] = '1970-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError, 'run bounds'):
            self.check()

    def test_out_of_order_timestamp_rejected(self):
        self.audit[5]['timestamp'] = self.audit[1]['timestamp']
        with self.assertRaisesRegex(ValueError, 'out of order'):
            self.check()


if __name__ == '__main__':
    unittest.main()
