"""Adversarial receipt checks; native campaign evidence is produced separately."""
from copy import deepcopy
import unittest

from superhunter import product_fuzz_native as product
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical


def echidna_sample(broken=True):
    test = {'type': 'property', 'name': 'name', 'error': None,
            'status': 'shrinking' if broken else 'fuzzing',
            'reason': 'ReturnFalse' if broken else None, 'transactions': None}
    if broken:
        test['transactions'] = [{'function': 'credit', 'arguments': [str(n)],
                                 'value': '0x0', 'gasprice': '0x0'} for n in [0, 9]]
    return {'success': True, 'error': None, 'seed': 20261121, 'coverage': {'owned': [0]}, 'tests': [test]}


def medusa_sample(broken=True):
    text = 'Initializing corpus...\n'
    if broken:
        text += ('[FAILED] Property Test: OwnedCap.echidna_total_bounded()\n'
                 '1) OwnedCap.credit(uint8)(18) (block=2)\n'
                 '2) OwnedCap.credit(uint8)(1) (block=2)\n'
                 '=> [return (false)]\nTest summary: 0 test(s) passed, 1 test(s) failed\n')
    else:
        text += ('[PASSED] Property Test: OwnedCap.echidna_total_bounded()\n'
                 'Test summary: 1 test(s) passed, 0 test(s) failed\n')
    return text.encode()


class NativeFuzzReceiptTests(unittest.TestCase):
    def test_both_echidna_polarities_preserve_native_status(self):
        a = product.echidna_result(canonical(echidna_sample()), True)
        b = product.echidna_result(canonical(echidna_sample(False)), False)
        self.assertEqual(a['counterexample'], [0, 9])
        self.assertEqual(b['native_status'], 'fuzzing')
        self.assertIsNone(b['counterexample'])

    def test_echidna_wrong_seed_or_error_is_rejected(self):
        for key, value in [('seed', 1), ('error', 'compiler failed'), ('coverage', {})]:
            row = echidna_sample()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                product.echidna_result(canonical(row), True)

    def test_echidna_false_negative_and_false_positive_are_rejected(self):
        with self.assertRaises(EvidenceError):
            product.echidna_result(canonical(echidna_sample(False)), True)
        with self.assertRaises(EvidenceError):
            product.echidna_result(canonical(echidna_sample()), False)

    def test_echidna_rejects_ambiguous_reports_and_trailing_messages(self):
        report = canonical(echidna_sample())
        for raw in (report+report, report+b'ERROR\n', b'Unknown output\n'+report):
            with self.assertRaises(EvidenceError):
                product.echidna_result(raw, True)

    def test_echidna_counterexample_must_match_exact_calls(self):
        for key, value in [('arguments', ['8']), ('function', 'total'), ('value', '0x1')]:
            row = echidna_sample()
            row['tests'][0]['transactions'][1][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                product.echidna_result(canonical(row), True)

    def test_medusa_replay_requires_native_failure_code_and_seeded_corpus(self):
        self.assertEqual(product.medusa_result(medusa_sample(), 7, True)['counterexample'], [18, 1])
        self.assertIsNone(product.medusa_result(medusa_sample(False), 0, False)['counterexample'])
        for raw, code in [(medusa_sample(), 0), (medusa_sample().replace(b'Initializing corpus...', b''), 7)]:
            with self.assertRaises(EvidenceError):
                product.medusa_result(raw, code, True)

    def test_medusa_rejects_changed_trace_and_ambiguous_summary(self):
        for raw in [medusa_sample().replace(b'(18)', b'(17)'),
                    medusa_sample()+b'Test summary: 0 test(s) passed, 1 test(s) failed\n']:
            with self.assertRaises(EvidenceError):
                product.medusa_result(raw, 7, True)

    def test_independent_replay_requires_all_four_native_tests(self):
        tests = {'test'+tool.title()+kind+'()': {'status': 'Success', 'reason': None,
                                                'kind': {'Unit': {'gas': 300000}}}
                 for tool in ('echidna', 'medusa') for kind in ('Broken', 'Fixed')}
        report = {'test/Replay.t.sol:OwnedReplayTest': {'test_results': tests}}
        self.assertEqual(len(product.forge_result(canonical(report))), 4)
        bad = deepcopy(report)
        bad['test/Replay.t.sol:OwnedReplayTest']['test_results']['testMedusaFixed()']['status'] = 'Failure'
        with self.assertRaises(EvidenceError):
            product.forge_result(canonical(bad))
        del tests['testEchidnaBroken()']
        with self.assertRaises(EvidenceError):
            product.forge_result(canonical(report))

    def test_reference_oracle_rejects_non_uint8_arguments(self):
        for value in (-1, 256, True, '9'):
            with self.assertRaises(EvidenceError):
                product.arithmetic_trace([value], False)


if __name__ == '__main__':
    unittest.main()
