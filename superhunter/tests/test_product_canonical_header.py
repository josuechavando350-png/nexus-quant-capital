import unittest
from copy import deepcopy

from superhunter import product_canonical_header as header
from superhunter.product_native_capabilities import contracts
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json
from superhunter.tools.verify_review_115 import verify


class CanonicalCensusHeaderTests(unittest.TestCase):
    def setUp(self):
        self.cases, self.witness = header.header_context()

    def test_two_canonical_headers_differ_only_in_gas_used(self):
        original = self.cases['original']
        changed = self.cases['changed_gas_used']
        delta = [name for (name, _), a, b in zip(header.FIELDS, original['fields'], changed['fields'], strict=True)
                 if a != b]
        self.assertEqual(delta, ['gasUsed'])
        for name, case in self.cases.items():
            self.assertEqual(len(case['fields']), 21)
            self.assertEqual(header.sha(case['encoded']), self.witness['report']['cases'][name]['rlp_sha256'])
        self.assertNotEqual(original['hash'], changed['hash'])

    def test_template_only_instantiates_the_two_fixed_unit_tests(self):
        harness = header.owned_harness(self.cases)
        self.assertEqual(harness.count(b'function test'), 2)
        for name in header.expected_observations(self.cases):
            self.assertIn(b'function '+name.encode(), harness)
        self.assertNotIn(b'%%', harness)

    def _observed_records(self):
        # Synthetic event stream for isolated checks of the independent receipt reader.
        results = {}
        for name, pairs in header.expected_observations(self.cases).items():
            results[name] = {
                'kind': {'Unit': {'gas': 1}}, 'status': 'Success', 'reason': None, 'counterexample': None,
                'logs': [{'topics':[header.EVENT_TOPIC], 'data':'0x'+header.event_data(key, value).hex(),
                          'address':'0x'+'2'*40} for key, value in pairs],
                'decoded_logs':[key+': 0x'+value.hex() for key, value in pairs],
            }
        return {'test/Owned.t.sol:CanonicalCensusHeaderTest': {'test_results': results, 'warnings': []}}

    def test_reader_requires_exact_cases_and_observation_counts(self):
        sample = self._observed_records()
        self.assertEqual({v['observations'] for v in header.reconcile(canonical(sample), self.cases).values()}, {23})
        suite = next(iter(sample.values()))['test_results']
        suite.pop('testChangedGasUsed()')
        with self.assertRaises(EvidenceError):
            header.reconcile(canonical(sample), self.cases)

    def test_raw_and_rendered_fields_must_match(self):
        for key in ('logs', 'decoded_logs'):
            with self.subTest(key=key):
                sample = self._observed_records()
                row = next(iter(sample.values()))['test_results']['testHistoricalHeader()']
                row[key][8], row[key][14] = row[key][14], row[key][8]
                with self.assertRaises(EvidenceError):
                    header.reconcile(canonical(sample), self.cases)

    def test_result_and_historical_registry_are_bound_separately(self):
        pinned = strict_json(read_artifact(header.ROOT, 'superhunter/product_supply/canonical-header-result.json'))
        self.assertEqual(header.sha(canonical(pinned)), contracts()['canonical_header']['report_sha256'])
        nine = contracts('accounting-nine')
        self.assertEqual(len(nine), 9)
        self.assertEqual({k: v for k, v in contracts('canonical-ten').items() if k != 'canonical_header'}, nine)
        with self.assertRaisesRegex(EvidenceError, 'one exact'):
            verify(b'', require_accounting=True, require_canonical_header=True)

    def test_missing_minimal_observations_or_a_failed_test_cannot_pass(self):
        original = self._observed_records()
        for key, value in [('status','Failure'), ('counterexample', {}), ('logs', [])]:
            item = deepcopy(original)
            next(iter(item.values()))['test_results']['testHistoricalHeader()'][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                header.reconcile(canonical(item), self.cases)
