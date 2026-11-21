import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_evaluation_batch as ev
from superhunter.product_reasoning import EvidenceError


class NumericChecks(unittest.TestCase):
    def test_table_arithmetic_uses_marginals(self):
        rows = [{'truth': a, 'answer': b} for a, b in [('x','x'), ('x','x'), ('x','y'), ('y','y')]]
        value = ev.agreement(rows)
        self.assertEqual(value['agreement'], .75)
        self.assertEqual(value['kappa'], .5)
        self.assertAlmostEqual(value['weighted_f1'], (3 * 0.8 + 2/3) / 4)
        self.assertLess(ev.fbeta(rows, 'x', 2.), ev.fbeta(rows, 'x', .5))
        self.assertGreater(ev.fbeta(rows, 'y', 2.), ev.fbeta(rows, 'y', .5))

    def test_boolean_verdicts_and_complete_cases(self):
        data = [{'id': 'a'}, {'id': 'b'}]
        for bad in ([True], [1, False], [False, True]):
            with self.assertRaises(EvidenceError):
                ev.score_record(data, bad, [True, False])
        self.assertEqual(ev.score_record(data, [True, False], [True, False])['examples_of_errors'], ['b'])

    def test_missing_mode_fails_before_promotion(self):
        with self.assertRaisesRegex(EvidenceError, 'modes'):
            ev.assess({}, {}, {})


@unittest.skipUnless(os.environ.get('NQC_TRUST_TEST_SOURCES') and os.environ.get('NQC_EVALUATION_WHEEL'),
                     'requires NQC_TRUST_TEST_SOURCES and the pinned NQC_EVALUATION_WHEEL')
class IndependentScorers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['NQC_TRUST_TEST_SOURCES'])
        cls.records = ev.review(cls.root)

    def test_measured_receipt_matches_publication(self):
        self.assertEqual(set(self.records), set(ev.PINS))
        self.assertEqual(len({v['case_matrix_sha256'] for v in self.records.values()}), 1)
        expected = (Path(ev.__file__).parent / 'product_supply/evaluation-batch-receipt.json').read_bytes()
        self.assertEqual(ev.canonical(self.records), expected)
        values = self.records[ev.PROMPT]['modes']
        self.assertEqual(values['original']['correct'], 768)
        self.assertEqual(values['without_extra_data']['correct'], 695)
        self.assertEqual(values['partial_field_mixup']['correct'], 702)

    def test_different_normalizers_have_measured_failure_bounds(self):
        for mode, gaia, whisper in [('original', 0, 0), ('upper_case_fields', 384, 384), ('punctuated_fields', 384, 0)]:
            self.assertEqual(self.records[ev.SMOL]['modes'][mode]['false_accepts_against_literal_fields'], gaia)
            self.assertEqual(self.records[ev.HF]['modes'][mode]['false_accepts_against_literal_fields'], whisper)

    def test_corrupt_wheel_never_reaches_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            wrong = workspace / 'regex.whl'
            wrong.write_bytes(b'corrupt')
            with patch.dict(os.environ, NQC_EVALUATION_WHEEL=str(wrong)):
                with self.assertRaisesRegex(EvidenceError, 'wheel differs'):
                    ev.material(workspace, self.root)
