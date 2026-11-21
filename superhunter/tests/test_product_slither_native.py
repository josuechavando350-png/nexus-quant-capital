"""Reconciliation negatives; synthetic data here are not native execution evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from superhunter import product_slither_native as product
from superhunter.product_slither_native_network import expected_proof
from superhunter import product_slither_native_network as network
from superhunter.product_reasoning import EvidenceError


def samples():
    native, reference = {'cases': {}, 'network': expected_proof()}, {}
    for name, source in product.controls.SOURCES.items():
        abi = [{'type': 'function', 'name': 'inspect', 'inputs': [],
                'outputs': [{'type': 'bool'}], 'stateMutability': 'view'}]
        ast = {'nodeType': 'SourceUnit', 'nodes': [{'nodeType': 'ContractDefinition', 'name': 'OwnedFixture'}]}
        contract = {'abi': abi, 'evm': {'bytecode': {'object': '600100'},
                                       'deployedBytecode': {'object': '600000'}}}
        reference[name] = {'contracts': {'Owned.sol': {'OwnedFixture': contract}},
                           'sources': {'Owned.sol': {'ast': ast}}}
        detectors = []
        if name == 'positive':
            expression = b'require(tx.origin == owner, "owner")'
            start = source.index(expression)
            detectors = [{'check': 'tx-origin', 'impact': 'Medium', 'confidence': 'Medium',
                          'description': 'Synthetic reconciliation control',
                          'elements': [{'type': 'node', 'name': 'require',
                                        'source_mapping': {'filename_relative': 'Owned.sol',
                                                           'start': start, 'length': len(expression),
                                                           'lines': [7]}}]}]
        native['cases'][name] = {'abis': {'OwnedFixture': deepcopy(abi)}, 'ast': deepcopy(ast),
                                 'runtimes': {'OwnedFixture': '600000'},
                                 'inits': {'OwnedFixture': '600100'}, 'detectors': detectors}
    return native, reference


class SlitherNativeReconciliationTests(unittest.TestCase):
    def test_complete_controls_bind_the_positive_expression(self):
        native, reference = samples()
        result = product.reconcile(native, reference)
        self.assertEqual({k: v['alert_count'] for k, v in result.items()},
                         {'positive': 1, 'clean': 0, 'comparison': 0})
        self.assertEqual(result['positive']['alerts'][0]['locations'][0]['start_byte'], 221)

    def test_missing_control_is_rejected(self):
        for missing in ('positive', 'clean', 'comparison'):
            native, reference = samples()
            del native['cases'][missing]
            with self.assertRaises(EvidenceError):
                product.reconcile(native, reference)

    def test_compiler_failure_is_not_clean_success(self):
        native, reference = samples()
        reference['clean']['errors'] = [{'severity': 'error'}]
        with self.assertRaises(EvidenceError):
            product.reconcile(native, reference)

    def test_abi_ast_or_bytecode_disagreement_is_rejected(self):
        for field in ('abis', 'ast', 'runtimes', 'inits'):
            native, reference = samples()
            native['cases']['clean'][field] = {}
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                product.reconcile(native, reference)

    def test_false_negative_is_rejected(self):
        native, reference = samples()
        native['cases']['positive']['detectors'] = []
        with self.assertRaises(EvidenceError):
            product.reconcile(native, reference)

    def test_both_negative_controls_reject_false_positives(self):
        for case in ('clean', 'comparison'):
            native, reference = samples()
            native['cases'][case]['detectors'] = deepcopy(native['cases']['positive']['detectors'])
            with self.subTest(case=case), self.assertRaises(EvidenceError):
                product.reconcile(native, reference)

    def test_valid_range_pointing_to_wrong_expression_is_rejected(self):
        native, reference = samples()
        native['cases']['positive']['detectors'][0]['elements'][0]['source_mapping']['start'] += 1
        with self.assertRaises(EvidenceError):
            product.reconcile(native, reference)

    def test_network_proof_must_match(self):
        native, reference = samples()
        native['network']['socket_controls_denied'] = 0
        with self.assertRaises(EvidenceError):
            product.reconcile(native, reference)

    def test_network_library_wrong_bytes_rejected_before_load(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'library'
            path.write_bytes(b'\0' * network.LIBRARY_BYTES)
            with self.assertRaisesRegex(ValueError, 'PRODUCT_NETWORK_LIBRARY_BYTES'):
                network.install(path)

    def test_invalid_bytecode_is_rejected_even_if_both_producers_agree(self):
        native, reference = samples()
        native['cases']['clean']['runtimes']['OwnedFixture'] = 'not-bytecode'
        reference['clean']['contracts']['Owned.sol']['OwnedFixture']['evm']['deployedBytecode']['object'] = 'not-bytecode'
        with self.assertRaises(EvidenceError):
            product.reconcile(native, reference)


if __name__ == '__main__':
    unittest.main()
