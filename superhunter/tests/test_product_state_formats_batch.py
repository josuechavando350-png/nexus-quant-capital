import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_state_formats_batch as subject
from superhunter.product_reasoning import EvidenceError


class AmountFormatControls(unittest.TestCase):
    def test_historical_fields_are_intact(self):
        rows = subject.inputs()
        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(x == '0' for x in rows.values()), 4)
        self.assertEqual(sorted({int(s).bit_length() for s in rows.values()}), [0, 70, 77, 82])

    def test_cannot_promote_negative_unsigned_interpretation(self):
        data = {'text': '-1', 'uint': True, 'canonical': '-1', 'bits': 1, 'positive': False}
        with self.assertRaisesRegex(EvidenceError, 'normalization'):
            subject.compare('-1', data, (128, 64, 128))

    def test_falsified_positive_observation_rejected(self):
        data = {'text': '0', 'uint': True, 'canonical': '0', 'bits': 0, 'positive': True}
        with self.assertRaisesRegex(EvidenceError, 'positivity'):
            subject.compare('0', data, (128, 64, 128))

    def test_normalization_detects_wrong_quantity(self):
        data = {'text': '10', 'uint': True, 'canonical': '11', 'bits': 4, 'positive': True}
        with self.assertRaisesRegex(EvidenceError, 'normalization'):
            subject.compare('10', data, (128, 64, 128))

    def test_cairo_limb_carry_and_sui_upper_bound(self):
        text = str(2**128 + 4)
        row = subject.compare(text, {'text': text, 'uint': True, 'canonical': text, 'bits': 129,
                                     'positive': True}, (128, 64, 128))
        self.assertEqual(row['cairo_low_high'], ['4', '1'])
        self.assertFalse(row['wasm_response_uint_fits'])
        self.assertFalse(row['sui_balance_fits'])

    def test_amount_is_not_relabelled_if_superfluous_leading_zero(self):
        row = subject.compare('01', {'text': '01', 'uint': True, 'canonical': '1'}, (128, 64, 128))
        self.assertEqual(row, {'representable': False})


@unittest.skipUnless(os.environ.get('NQC_EVM_LAYOUT_SOURCES'), 'requires the five pinned source checkouts')
class UpstreamAmountFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_EVM_LAYOUT_SOURCES'])
        cls.files = subject.source_files(cls.root)

    def test_wasm_signed_schema_rejected(self):
        files = dict(self.files)
        key = next(p for p in files if '/cw_schema/' in p)
        value = json.loads(files[key])
        value['definitions'][1]['signed'] = True
        files[key] = json.dumps(value).encode()
        with self.assertRaisesRegex(EvidenceError, 'Wasm'):
            subject.shape(files)

    def test_sui_layout_width_contradiction(self):
        files = dict(self.files)
        name = next(iter(subject.UPSTREAM[subject.SUI][2]))
        files[name] = files[name].replace(b'MoveTypeLayout::U64', b'MoveTypeLayout::U128')
        with self.assertRaisesRegex(EvidenceError, 'Sui'):
            subject.shape(files)

    def test_cairo_limb_order_has_consequences(self):
        files = dict(self.files)
        name = next(iter(subject.UPSTREAM[subject.CAIRO][2]))
        files[name] = files[name].replace(b'pub low: u128,\n    pub high: u128,', b'pub high: u128,\n    pub low: u128,')
        with self.assertRaisesRegex(EvidenceError, 'Cairo'):
            subject.shape(files)

    def test_positive_amount_spec_disagrees(self):
        files = dict(self.files)
        name = next(iter(subject.UPSTREAM[subject.IBC][2]))
        files[name] = files[name].replace(b'!amount.IsPositive()', b'amount.IsNegative()')
        with self.assertRaisesRegex(EvidenceError, 'IBC'):
            subject.shape(files)

    def test_corrupt_cached_binary_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp)/'test'
            binary.write_bytes(b'corrupt')
            with patch.dict(os.environ, {'NQC_STATE_HELPER': str(binary)}):
                with self.assertRaisesRegex(EvidenceError, 'unreviewed cached'):
                    subject.review(self.root)

    @unittest.skipUnless(os.environ.get('NQC_STATE_HELPER') or os.environ.get('NQC_STATE_GO'), 'needs native reader')
    def test_authentic_product_rows_and_boundaries(self):
        rows = subject.review(self.root)
        self.assertEqual(set(rows), set(subject.UPSTREAM))
        for row in rows.values():
            self.assertEqual(len(row['results']), 7)
            self.assertEqual(len(row['controls']), 10)
            self.assertEqual(sum(x['sui_balance_fits'] for x in row['results'].values()), 4)
            self.assertEqual(sum(x['ibc_positive_amount'] for x in row['results'].values()), 3)


if __name__ == '__main__':
    unittest.main()
