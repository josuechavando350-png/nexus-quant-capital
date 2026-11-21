"""Receipt checks do not substitute for the separate native Solidity runs."""
from copy import deepcopy
import unittest

from superhunter import product_contract_properties_native as product
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical


def sample():
    return {'test/Owned.t.sol:OwnedPropertiesReplayTest': {'warnings': [], 'test_results': {
        name: {'status': 'Success', 'reason': None, 'counterexample': None, 'kind': {'Unit': {'gas': 100}}}
        for name in set.union(*product.TESTS.values())}}}


class ContractPropertyReceiptTests(unittest.TestCase):
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
        for kind in ({'Fuzz': {'runs': 0}}, {'Unit': {'gas': True}}):
            row = sample()
            row['test/Owned.t.sol:OwnedPropertiesReplayTest']['test_results']['testImmunefiFeeAccounting()']['kind'] = kind
            with self.assertRaises(EvidenceError):
                product.reconcile(canonical(row))


if __name__ == '__main__':
    unittest.main()
