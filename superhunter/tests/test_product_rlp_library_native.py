"""Validate captured native codec observations; these tests do not execute Forge."""
from copy import deepcopy
import unittest

from superhunter import product_rlp_library_native as product
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json


class RlpLibraryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.witness = product.header_context()
        cls.captured = strict_json(read_artifact(product.ROOT, 'superhunter/product_supply/rlp-library-native-sample.json'))

    def sample(self):
        value = deepcopy(self.captured)
        return value, value['test/Owned.t.sol:OwnedRlpLibraryTest']['test_results']

    def test_real_capture_has_two_complete_header_controls_and_negative_checks(self):
        value, _ = self.sample()
        result = product.reconcile(canonical(value), self.cases)
        self.assertEqual(len(result), 6)
        self.assertEqual(result['testHistoricalHeader()']['observations'], 23)
        self.assertEqual(result['testChangedGasUsed()']['observations'], 23)
        self.assertEqual(result['testMalformedInputsRejected()']['observations'], 7)
        self.assertEqual(result['testNoncanonicalInputsNeedOwnGuard()']['observations'], 12)
        self.assertNotEqual(self.cases['original']['hash'], self.cases['changed_gas_used']['hash'])

    def test_a_missing_header_field_cannot_hide_behind_success(self):
        value, tests = self.sample()
        row = tests['testHistoricalHeader()']
        row['logs'].pop()
        row['decoded_logs'].pop()
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_forged_hash_is_rejected_even_when_both_log_representations_agree(self):
        value, tests = self.sample()
        row = tests['testChangedGasUsed()']
        bad = b'\0'*32
        row['logs'][1]['data'] = '0x'+product.event_data('hash', bad).hex()
        row['decoded_logs'][1] = 'hash: 0x'+bad.hex()
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_noncanonical_acceptance_must_be_reported_and_guarded(self):
        value, tests = self.sample()
        row = tests['testNoncanonicalInputsNeedOwnGuard()']
        row['logs'][2]['data'] = '0x'+product.event_data('nonminimal_byte/guard', b'').hex()
        row['decoded_logs'][2] = 'nonminimal_byte/guard: 0x'
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_wrong_native_rejection_reason_is_not_equivalent(self):
        value, tests = self.sample()
        row = tests['testMalformedInputsRejected()']
        bad = product.error_bytes('some unrelated failure')
        row['logs'][0]['data'] = '0x'+product.event_data('empty_input', bad).hex()
        row['decoded_logs'][0] = 'empty_input: 0x'+bad.hex()
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_native_failure_is_rejected_despite_matching_payloads(self):
        value, tests = self.sample()
        tests['testByteBoundaries()']['status'] = 'Failure'
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_trailing_event_bytes_are_rejected(self):
        value, tests = self.sample()
        tests['testThirtyTwoItems()']['logs'][0]['data'] += '00'
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_decoded_text_alone_cannot_substitute_native_event_bytes(self):
        value, tests = self.sample()
        tests['testHistoricalHeader()']['logs'][0]['topics'] = ['0x'+'00'*32]
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(value), self.cases)

    def test_zero_quantity_and_nonce_remain_distinct_encodings(self):
        raw = strict_json(product.pinned(product.ROOT, product.FIXTURE, product.FIXTURE_SHA))
        fields = dict(zip((name for name, _ in product.FIELDS), product.field_values(raw['block'])))
        self.assertEqual(fields['difficulty'], b'')
        self.assertEqual(fields['nonce'], b'\0'*8)
        for key, replacement in (('gasUsed', '0x01'), ('nonce', '0x0')):
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                product.field_values({**raw['block'], key: replacement})


if __name__ == '__main__':
    unittest.main()
