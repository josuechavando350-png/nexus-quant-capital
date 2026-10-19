import copy
import json
import unittest
import audit


class FinancingEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = audit.sources()
        cls.ledger = json.loads(cls.raw['titan_ledger'])['scenarios']

    def case(self, name='V06_builder_funds_own_refund'):
        return json.loads(self.raw[name]), copy.deepcopy(self.ledger[name]['cashflows_and_all_asset_balances'])

    def matrix(self):
        return json.loads((audit.HERE / 'FINANCING_MATRIX.json').read_text())

    def test_positive_operator_assets_do_not_hide_financier_loss(self):
        result = audit.consolidate(*self.case('A2_C1_high_gas'))
        self.assertGreater(int(result['NQC_WETH_residue_raw']), 0)
        self.assertLess(int(result['financier_cash_delta_wei']), 0)
        self.assertEqual(result['state'], 'UNSUPPORTED_OR_ECONOMICALLY_REJECTED')

    def test_duplicate_flow_is_rejected(self):
        run, ledger = self.case(); ledger['flows'].append(copy.deepcopy(ledger['flows'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate flow'): audit.consolidate(run, ledger)

    def test_ETH_cannot_be_relabelled_WETH(self):
        run, ledger = self.case(); ledger['flows'][0]['asset'] = 'WETH'
        with self.assertRaisesRegex(ValueError, 'reconciliation'): audit.consolidate(run, ledger)

    def test_gas_cap_is_not_actual_expense(self):
        run, ledger = self.case()
        run['transactions'][0]['receipt']['effectiveGasPrice'] = run['transactions'][0]['request']['maxFeePerGas']
        with self.assertRaisesRegex(ValueError, 'gas cost'): audit.consolidate(run, ledger)

    def test_shared_labels_do_not_merge_distinct_actors(self):
        run, ledger = self.case('A2_C1_high_gas')
        ledger['actors']['sponsor_and_topup_financier'] = ledger['actors']['simulated_builder']
        with self.assertRaisesRegex(ValueError, 'actor identity'): audit.consolidate(run, ledger)

    def test_retained_advance_is_not_generated_income(self):
        result = audit.consolidate(*self.case('V07_partial_topup'))
        self.assertEqual(result['NQC_WETH_residue_raw'], '0')
        self.assertEqual(result['NQC_retained_advance_wei'], '10000000000000')
        self.assertFalse(result['complete_local_path'])
        self.assertFalse(result['real_financing_secured'])

    def test_unknown_recourse_cannot_be_silently_zeroed(self):
        matrix = self.matrix(); matrix['mechanisms'][0]['personal_recourse'] = 0
        with self.assertRaisesRegex(ValueError, 'no-recourse'): audit.validate_matrix(matrix)

    def test_public_documentation_does_not_authenticate_acceptance(self):
        matrix = self.matrix(); matrix['mechanisms'][0]['commercial_state'] = 'SPECIFIC_PROVIDER_ACCEPTANCE_VERIFIED'
        with self.assertRaisesRegex(ValueError, 'specific acceptance'): audit.validate_matrix(matrix)


if __name__ == '__main__': unittest.main()
