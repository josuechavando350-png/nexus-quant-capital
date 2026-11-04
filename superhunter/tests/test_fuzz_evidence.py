"""Regression checks for contradictory, rehashed local numerical-run evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from superhunter.fuzz_lab import execute, make_case, verify_fuzz
from superhunter.native_runtime import load_components
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class FuzzEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = {name: strict_json(raw) for name, raw in execute(45, 3).items()}

    def setUp(self):
        self.files = deepcopy(self.original)
        self.meta = self.files['fuzz-result.json']
        self.entries = self.files['diablo-fuzz-audit.json']['entries']
        self.records = self.files['fuzz-cases.json']['cases']

    def verify(self, *, rehash=True):
        # Recompute integrity to isolate semantic validation, not only SHA checks.
        if rehash:
            native = load_components()
            previous = '0' * 64
            for entry in self.entries:
                entry['prev_hash'] = previous
                entry['hash'] = native.audit.compute_hash(
                    entry['index'], entry['timestamp'], entry['event'], entry['data'], previous)
                previous = entry['hash']
            self.meta['audit_head'] = previous
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'case'
            write_new_bundle(root, {name: canonical(value) for name, value in self.files.items()})
            return verify_fuzz(root)

    def test_valid_full_evidence_still_passes(self):
        self.assertEqual(self.verify()['status'], 'LOCAL_FUZZ_PASS')

    def test_counts_require_integers(self):
        for field in ('schema_version', 'tested', 'failed', 'audit_count',
                      'permutation_checks', 'scaling_checks', 'oracle_checks'):
            with self.subTest(field=field):
                original = self.meta[field]
                self.meta[field] = float(original)
                with self.assertRaises(ValueError):
                    self.verify()
                self.meta[field] = original

    def test_boolean_failed_count_rejected(self):
        self.meta['failed'] = False
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_source_claim_rejected(self):
        self.meta['source'] = 'unrelated.engine'
        with self.assertRaises(ValueError):
            self.verify()

    def test_extra_summary_claim_rejected(self):
        self.meta['production_certified'] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_reversed_summary_time_rejected(self):
        self.meta['started_at'], self.meta['completed_at'] = self.meta['completed_at'], self.meta['started_at']
        with self.assertRaises(ValueError):
            self.verify()

    def test_naive_time_rejected(self):
        self.meta['started_at'] = '2026-11-04T00:00:00'
        with self.assertRaises(ValueError):
            self.verify()

    def test_audit_timestamp_outside_run_rejected(self):
        self.entries[2]['timestamp'] = '1970-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):
            self.verify()

    def test_audit_timestamps_must_be_monotonic(self):
        self.entries[5]['timestamp'] = self.entries[1]['timestamp']
        with self.assertRaises(ValueError):
            self.verify()

    def test_noncanonical_uuid_rejected_even_when_rebound(self):
        for value in ('not-a-uuid', True):
            with self.subTest(value=value):
                self.meta['run_id'] = value
                self.entries[0]['data']['id'] = value
                self.entries[-1]['data']['id'] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def test_wrong_scope_kind_rejected(self):
        self.entries[1]['data']['kind'] = 'production'
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_scope_rule_rejected(self):
        self.entries[1]['data']['matched_rule'] = '*.external.invalid'
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_scope_reason_rejected(self):
        self.entries[1]['data']['reason'] = 'out of scope'
        with self.assertRaises(ValueError):
            self.verify()

    def test_extra_scope_claim_rejected(self):
        self.entries[1]['data']['authorized_mainnet'] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_contradictory_completion_rejected_after_rehash(self):
        self.entries[-1]['data']['vulnerability_confirmed'] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_completion_case_count_bound(self):
        self.entries[-1]['data']['cases'] = 999
        with self.assertRaises(ValueError):
            self.verify()

    def test_numeric_flag_not_boolean(self):
        self.entries[0]['data']['fixture_only'] = 1
        with self.assertRaises(ValueError):
            self.verify()

    def test_numeric_index_not_boolean(self):
        self.entries[1]['index'] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_negative_scope_kind_checked(self):
        self.entries[-2]['data']['kind'] = 'host'
        with self.assertRaises(ValueError):
            self.verify()

    def test_record_index_type_exact(self):
        self.records[0]['index'] = False
        with self.assertRaises(ValueError):
            self.verify()

    def test_seeded_values_preserve_numeric_types(self):
        row = self.records[0]['input'][0]
        row['start_order'] = float(row['start_order'])
        with self.assertRaises(ValueError):
            self.verify()

    def test_computed_output_preserves_boolean_types(self):
        self.records[0]['nqc']['global_optimum_claimed'] = 1
        with self.assertRaises(ValueError):
            self.verify()

    def test_record_extra_claim_rejected(self):
        self.records[0]['production_finding'] = True
        with self.assertRaises(ValueError):
            self.verify()

    def test_manifest_schema_boolean_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'case'
            write_new_bundle(root, {n: canonical(v) for n, v in self.files.items()})
            manifest = strict_json((root/'COMPLETE.json').read_bytes())
            manifest['schema_version'] = True
            (root/'COMPLETE.json').write_bytes(canonical(manifest))
            with self.assertRaises(ValueError):
                verify_fuzz(root)

    def test_index_outside_uint64_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            make_case(1, 2**64)


if __name__ == '__main__':
    unittest.main()
