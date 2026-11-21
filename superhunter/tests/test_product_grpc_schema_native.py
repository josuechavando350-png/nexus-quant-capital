"""Corrupt actual captured grpcurl outputs; native runs are recorded separately."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import product_grpc_schema_native as grpc
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.safe_io import strict_json


class GrpcSchemaNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins, cls.cases = grpc.inputs()
        cls.samples = strict_json((ROOT/'superhunter/product_supply/grpc-schema-native-sample.json').read_bytes())

    def case(self, name='base'):
        row = self.samples[name]
        views = {label: row[label]['stdout'].encode() for label in ('services', 'methods', 'service', 'request', 'reply')}
        return self.cases['schemas'][name].encode(), bytes.fromhex(row['descriptor_hex']), views

    def validate(self, name='base', *, descriptor=None, source=None, views=None, replay=None, pins=None):
        original, binary, printed = self.case(name)
        return grpc.validate_case(name, original if source is None else source,
                                  binary if descriptor is None else descriptor,
                                  printed if views is None else views, printed if replay is None else replay,
                                  self.pins if pins is None else pins, self.cases)

    def test_two_native_descriptors_reveal_exact_method_streaming_and_wire_type_changes(self):
        base = self.validate()['schema']
        changed = self.validate('changed')['schema']
        differences = grpc.schema_changes(base, changed)
        self.assertEqual(differences, self.cases['expected_changes'])
        self.assertEqual(differences['removed_methods'], ['nqc.owned.Ledger.Balance'])
        self.assertEqual(differences['added_methods'], ['nqc.owned.Ledger.GetBalance'])
        field, = differences['changed_fields']
        self.assertEqual((field['before']['wire_type'], field['after']['wire_type']), (0, 2))
        self.assertEqual(self.validate()['protoset_replay_views_matched'], 5)

    def test_forged_describe_text_cannot_override_decoded_message_type(self):
        _, _, views = self.case()
        views['reply'] = views['reply'].replace(b'uint64', b'string')
        with self.assertRaisesRegex(EvidenceError, 'text disagrees'):
            self.validate(views=views)

    def test_protoset_replay_cannot_silently_drop_or_replace_a_view(self):
        for label in ('services', 'methods', 'service', 'request', 'reply'):
            _, _, replay = self.case()
            replay.pop(label)
            with self.subTest(label=label), self.assertRaisesRegex(EvidenceError, 'text disagrees'):
                self.validate(replay=replay)
        with self.assertRaisesRegex(EvidenceError, 'text disagrees'):
            self.validate(replay=self.case('changed')[2])

    def test_source_or_descriptor_from_another_case_is_rejected(self):
        changed, binary, _ = self.case('changed')
        with self.assertRaisesRegex(EvidenceError, 'OWNED source differs'):
            self.validate(source=changed)
        with self.assertRaisesRegex(EvidenceError, 'descriptor or OWNED source'):
            self.validate(descriptor=binary)

    def test_resealed_type_substitution_still_fails_the_independent_schema_witness(self):
        _, binary, _ = self.case()
        self.assertEqual(binary.count(b'\x28\x04'), 1)
        forged = binary.replace(b'\x28\x04', b'\x28\x09')
        pins = copy.deepcopy(self.pins)
        pins['cases']['base']['descriptor_sha256'] = sha(forged)
        with self.assertRaisesRegex(EvidenceError, 'independent OWNED schema witness'):
            self.validate(descriptor=forged, pins=pins)

    def test_truncated_duplicate_unknown_and_noncanonical_wire_data_is_rejected(self):
        _, binary, _ = self.case()
        corruptions = [b'', binary[:-1], binary + binary, binary + b'\x10\x01',
                       b'\x8a\x00' + binary[1:], b'\x0a' + b'\xff' * 10 + b'\x01']
        for raw in corruptions:
            with self.subTest(raw=raw[:12]), self.assertRaises(EvidenceError):
                grpc.schema_from_descriptor(raw)

    def test_native_rejection_requires_expected_error_and_exact_failure_status(self):
        row = self.samples['base']['missing_symbol']
        expected = self.pins['rejections']['unknown_symbol']
        good = SimpleNamespace(returncode=1, stdout=b'', stderr=row['stderr'].encode())
        self.assertTrue(grpc.validate_rejection(good, expected)['rejected'])
        for replacement in ({'returncode': 0}, {'returncode': True}, {'stdout': b'pretend success'},
                            {'stderr': b'network failed'}, {'stderr': b''}):
            altered = SimpleNamespace(**{**vars(good), **replacement})
            with self.subTest(replacement=replacement), self.assertRaises(EvidenceError):
                grpc.validate_rejection(altered, expected)

    def test_invalid_source_controls_are_real_distinct_native_diagnostics(self):
        digests = set()
        for name in self.cases['invalid_schemas']:
            row = self.samples[name]['services']
            proc = SimpleNamespace(returncode=row['returncode'], stdout=row['stdout'].encode(), stderr=row['stderr'].encode())
            result = grpc.validate_rejection(proc, self.pins['rejections'][name])
            digests.add(result['stderr_sha256'])
        self.assertEqual(len(digests), 2)

    def test_changed_pin_manifest_is_rejected_before_producer_execution(self):
        with patch.object(grpc, 'read_artifact', return_value=b'{}\n'):
            with self.assertRaisesRegex(EvidenceError, 'producer pins differ'):
                grpc.inputs()

    def test_missing_method_is_not_inferred_to_be_a_rename_or_security_finding(self):
        before = self.validate()['schema']
        unchanged = grpc.schema_changes(before, before)
        self.assertEqual(unchanged, {'removed_methods': [], 'added_methods': [], 'changed_methods': [], 'changed_fields': []})
        changed = copy.deepcopy(before)
        del changed['services']['nqc.owned.Ledger']['Balance']
        result = grpc.schema_changes(before, changed)
        self.assertEqual(result['removed_methods'], ['nqc.owned.Ledger.Balance'])
        self.assertEqual(result['added_methods'], [])


if __name__ == '__main__':
    unittest.main()
