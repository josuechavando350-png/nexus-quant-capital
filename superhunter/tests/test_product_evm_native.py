"""Fail-closed reconciliation controls; native executions are recorded separately."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from superhunter import product_evm_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical


class EvmSurfaceTests(unittest.TestCase):
    def test_modified_node_release_recipe_fails_before_using_any_kit(self):
        with patch('superhunter.product_census_header.read_artifact', return_value=b'{}'), \
                patch.object(native, 'source_inputs') as load_sources:
            with self.assertRaisesRegex(EvidenceError, 'evm-native-build.json'):
                native.run('/unused')
        load_sources.assert_not_called()

    def setUp(self):
        self.cases, self.evmole, self.whatsabi = {}, {}, {}
        selectors = {'aave': ['16f0115b', '1b11d0ff', '570ca735', 'df4b5c58'],
                     'backrun': ['16f0115b', '1b11d0ff', '223b035d', '570ca735', 'e4befb51'],
                     'changed': ['16f0115b', '1b11d0ff', '223b035d', '570ca735', '8e812b17'],
                     'stop': [], 'decoy': []}
        for name, rows in selectors.items():
            methods = {f'owned{i}()': s for i, s in enumerate(rows)}
            self.cases[name] = {'code': '5b00', 'methods': methods,
                                'abi': {f: {'arguments': '', 'state_mutability': 'view'} for f in methods},
                                'contract': 'Owned', 'source_sha256': 'a'*64}
            self.evmole[name] = [{'selector': s, 'offset': 0, 'dispatch': 'abi',
                                  'arguments': '', 'state_mutability': 'view'} for s in rows]
            self.whatsabi[name] = {'selectors': ['0x'+s for s in rows], 'abi_selectors': ['0x'+s for s in rows]}

    def test_complete_controls_have_stable_normalized_result(self):
        first = native.compare(self.cases, self.evmole, self.whatsabi)
        for rows in self.evmole.values():
            rows.reverse()
        for row in self.whatsabi.values():
            row['selectors'].reverse()
            row['abi_selectors'].reverse()
        second = native.compare(self.cases, self.evmole, self.whatsabi)
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(first['interface_change']['removed'], ['e4befb51'])
        self.assertEqual(first['interface_change']['added'], ['8e812b17'])

    def test_missing_case_is_not_a_success(self):
        del self.evmole['stop']
        with self.assertRaisesRegex(EvidenceError, 'incomplete bytecode controls'):
            native.compare(self.cases, self.evmole, self.whatsabi)

    def test_duplicate_selector_is_rejected(self):
        self.evmole['aave'].append(deepcopy(self.evmole['aave'][0]))
        with self.assertRaisesRegex(EvidenceError, 'EVMole surface'):
            native.compare(self.cases, self.evmole, self.whatsabi)

    def test_wrong_selector_in_either_whatsabi_interface_is_rejected(self):
        for key in ('selectors', 'abi_selectors'):
            altered = deepcopy(self.whatsabi)
            altered['backrun'][key][0] = '0xdeadbeef'
            with self.subTest(key=key), self.assertRaisesRegex(EvidenceError, 'WhatsABI surface'):
                native.compare(self.cases, self.evmole, altered)

    def test_push4_decoy_does_not_count_as_callable_function(self):
        self.whatsabi['decoy']['selectors'] = ['0xdeadbeef']
        with self.assertRaisesRegex(EvidenceError, 'WhatsABI surface'):
            native.compare(self.cases, self.evmole, self.whatsabi)

    def test_inference_disagreement_is_preserved_as_uncertainty(self):
        self.evmole['aave'][0]['arguments'] = 'uint256'
        self.evmole['aave'][0]['state_mutability'] = 'nonpayable'
        report = native.compare(self.cases, self.evmole, self.whatsabi)
        self.assertEqual(len(report['cases']['aave']['inference_differences']), 2)
        self.assertIn('not confirmed vulnerabilities', report['interpretation'])

    def test_offset_and_dispatch_must_be_valid(self):
        for key, value in [('offset', 99), ('offset', True), ('dispatch', 'fallback')]:
            altered = deepcopy(self.evmole)
            altered['aave'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(EvidenceError, 'function observation'):
                native.compare(self.cases, altered, self.whatsabi)

    def test_compiler_error_cannot_be_used_as_empty_surface(self):
        with self.assertRaisesRegex(EvidenceError, 'compilation failed'):
            native.compiler_cases({'errors': [{'severity': 'error'}]}, {})

    def test_mutation_is_bound_to_exact_owned_source_call(self):
        fixtures = {path: 'contract Owned {}' for path, _ in native.SOURCES.values()}
        with patch.object(native, 'inputs', return_value=(fixtures, {})):
            with self.assertRaisesRegex(EvidenceError, 'mutation target'):
                native.source_inputs()
