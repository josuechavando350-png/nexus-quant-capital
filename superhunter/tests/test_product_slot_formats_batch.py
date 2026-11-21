from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from superhunter import product_slot_formats_batch as clock
from superhunter.product_reasoning import EvidenceError


class ClockWireControls(unittest.TestCase):
    def test_default_epoch_encoding(self):
        self.assertEqual(clock.varint(0), b'\x00')

    def test_negative_int64_wire_is_ten_octets(self):
        self.assertEqual(clock.varint(-1), bytes([255]*9+[1]))

    def test_historical_timestamp(self):
        raw = clock.read_artifact(clock.ROOT, clock.HEADER)
        self.assertEqual(clock.sha(raw), clock.HEADER_SHA)
        header = clock.strict_json(raw)['block']
        self.assertEqual(int(header['timestamp'], 16), 1782906587)
        self.assertNotIn('slot', header)


@unittest.skipUnless(os.environ.get('NQC_EVM_LAYOUT_SOURCES'), 'requires the four source checkouts')
class ClockSourceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_EVM_LAYOUT_SOURCES'])
        cls.files = clock.load_sources(cls.root)

    def test_int64_vs_uint64_disagreement(self):
        files = dict(self.files)
        p = 'fuzz/fixture/proto/sysvars.proto'
        files[p] = files[p].replace(b'int64 unix_timestamp = 5;', b'uint64 unix_timestamp = 5;')
        with self.assertRaisesRegex(EvidenceError, 'signedness'):
            clock.shapes(files)

    def test_duplicate_native_field_cannot_fill_missing_field(self):
        files = dict(self.files)
        p = 'crates/node-litesvm/src/sysvar/clock.rs'
        files[p] = files[p].replace(b'bigint_to_i64(&unix_timestamp)?', b'bigint_to_i64(&epoch_start_timestamp)?')
        with self.assertRaisesRegex(EvidenceError, 'signedness'):
            clock.shapes(files)

    def test_printed_timestamp_cannot_map_to_epoch(self):
        files = dict(self.files)
        p = 'account-decoder/src/parse_sysvar.rs'
        files[p] = files[p].replace(b'unix_timestamp: clock.unix_timestamp,', b'unix_timestamp: clock.epoch_start_timestamp,')
        with self.assertRaisesRegex(EvidenceError, 'projection disagrees'):
            clock.shapes(files)

    @unittest.skipUnless(os.environ.get('NQC_SLOT_KIT'), 'requires the fixed native distributions')
    def test_reject_untrusted_package_signature(self):
        name = 'litesvm-linux-x64-gnu'
        proof = clock.strict_json(clock.read_artifact(clock.ROOT, 'superhunter/product_supply/clock-format-provenance.json'))
        proof = deepcopy(proof)
        proof['bundles'][name]['envelope']['signatures'][0]['sig'] = 'AA=='
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work/(name+'.tgz')).symlink_to(Path(os.environ['NQC_SLOT_KIT']).resolve()/(name+'.tgz'))
            with self.assertRaises(EvidenceError):
                clock.signed_package(name, work, proof, clock.UPSTREAM[clock.LITE][1])

    @unittest.skipUnless(os.environ.get('NQC_SLOT_KIT'), 'requires the fixed native distributions')
    def test_native_product_preserves_origin_and_absence(self):
        rows = clock.review(self.root)
        self.assertEqual(set(rows), set(clock.UPSTREAM))
        for result in rows.values():
            rows = result['results']
            self.assertEqual(rows['census_header']['known_fields'], ['unix_timestamp'])
            self.assertEqual(rows['census_header']['protobuf_hex'], '28dbfd93d206')
            self.assertEqual(rows['census_header']['borsh_integer_hex'], {'unix_timestamp': 'dbfe446a00000000'})
            self.assertEqual(rows['signed_and_unsafe_js_integer']['agave_fields_decimal_text']['slot'], str(2**53+1))
            self.assertEqual(rows['signed_and_unsafe_js_integer']['agave_fields_decimal_text']['unixTimestamp'], '-1')
            self.assertEqual(rows['known_zero']['protobuf_hex'], rows['unknown']['protobuf_hex'])
            self.assertNotEqual(rows['known_zero']['known_fields'], rows['unknown']['known_fields'])
            self.assertEqual(len(result['rejected_range_controls']), 3)


if __name__ == '__main__':
    unittest.main()
