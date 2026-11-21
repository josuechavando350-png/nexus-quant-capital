"""Receipt checks do not substitute for the separate native Solidity runs."""
from copy import deepcopy
import unittest

from superhunter import product_contract_properties_native as product
from superhunter.product_batches import session_operations
from superhunter.product_native_capabilities import contracts, expected_receipt
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, strict_json
from superhunter.tools.verify_review_115 import native_bindings


def sample():
    return {'test/Owned.t.sol:OwnedPropertiesReplayTest': {'warnings': [], 'test_results': {
        name: {'status': 'Success', 'reason': None, 'counterexample': None, 'kind': {'Unit': {'gas': 100}}}
        for name in set.union(*product.TESTS.values())}}}


class ContractPropertyReceiptTests(unittest.TestCase):
    def test_accounting_profile_retains_eight_contracts_and_requires_two_distinct_receipts(self):
        core = contracts(version='core-eight')
        extended = contracts()
        self.assertEqual(len(core), 8)
        self.assertEqual({key: value for key, value in extended.items() if key != 'properties'}, core)
        contract = extended['properties']
        report = strict_json((product.ROOT/'superhunter/product_supply/contract-properties-native-result.json').read_bytes())
        value = {'groups': {'properties': report}, 'repositories': sorted(product.REPOSITORIES),
                 'functional_participations': 2, 'original_vulnerabilities_confirmed': 0,
                 'scope': 'fixed_owned_controls_and_pinned_local_inputs'}
        expected = {name: expected_receipt('properties', name, contract) for name in product.REPOSITORIES}
        self.assertEqual(native_bindings({'native-capabilities': value}), expected)
        recorded = strict_json((product.ROOT/'superhunter/product_supply/contract-properties-native-acceptance.json').read_bytes())
        operations = {name: session_operations({'repository': name, 'native_capability_receipt': row})
                      for name, row in expected.items()}
        self.assertEqual(recorded, {'native-capabilities': value, 'operations': operations})
        with self.assertRaisesRegex(EvidenceError, 'group membership'):
            native_bindings({'native-capabilities': value}, version='core-eight')
        value['repositories'].pop()
        with self.assertRaisesRegex(EvidenceError, 'native totals'):
            native_bindings({'native-capabilities': value})

    def test_complete_receipt_separates_actual_source_roles(self):
        result = product.reconcile(canonical(sample()))
        self.assertEqual(len(result['crytic/properties']), 6)
        self.assertEqual(len(result['immunefi-team/forge-poc-templates']), 4)

    def test_missing_any_positive_or_negative_control_is_rejected(self):
        for name in set.union(*product.TESTS.values()):
            row = sample()
            del row['test/Owned.t.sol:OwnedPropertiesReplayTest']['test_results'][name]
            with self.subTest(name=name), self.assertRaises(EvidenceError):
                product.reconcile(canonical(row))

    def test_native_failures_and_skips_are_rejected(self):
        for value in ('Failure', 'Skipped'):
            row = sample()
            row['test/Owned.t.sol:OwnedPropertiesReplayTest']['test_results']['testCryticBalanceViolation()']['status'] = value
            with self.assertRaises(EvidenceError):
                product.reconcile(canonical(row))

    def test_unexpected_suite_or_test_is_rejected(self):
        row = sample()
        row['other'] = deepcopy(next(iter(row.values())))
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(row))
        row = sample()
        tests = row['test/Owned.t.sol:OwnedPropertiesReplayTest']['test_results']
        tests['unexpected()'] = deepcopy(next(iter(tests.values())))
        with self.assertRaises(EvidenceError):
            product.reconcile(canonical(row))

    def test_non_unit_and_boolean_gas_are_rejected(self):
        for kind in ({'Fuzz': {'runs': 0}}, {'Unit': {'gas': True}},
                     {'Unit': {'gas': 100}, 'Fuzz': {'runs': 2}}):
            row = sample()
            row['test/Owned.t.sol:OwnedPropertiesReplayTest']['test_results']['testImmunefiFeeAccounting()']['kind'] = kind
            with self.assertRaises(EvidenceError):
                product.reconcile(canonical(row))


if __name__ == '__main__':
    unittest.main()
