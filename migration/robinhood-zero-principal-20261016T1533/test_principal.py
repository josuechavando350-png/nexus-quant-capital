import copy
import json
import unittest

import principal_audit as p


class PrincipalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = p.replay.result(p.OLD / 'evidence/nitro-phase5/01-nqc-plain-eoa-success.json')
        cls.data = json.loads((p.OLD / 'evidence/final-simulation-input.json').read_text())

    def setUp(self):
        self.trace = copy.deepcopy(self.original)

    def find(self, name, selector):
        return next(f for f in p.replay.flatten(self.trace)
                    if p.matches(f, self.data['addresses'][name], selector))

    def test_real_principal_flow(self):
        result = p.audit_principal(self.trace, self.data)
        self.assertEqual(result['usd_surplus_before_gas_raw'], 32060665)
        self.assertEqual(result['initial_balances_observed_zero'], 6)
        self.assertFalse(result['separate_morpho_flash_loan_invoked'])
        self.assertEqual(len(result['ordered_inventory_ledgers']), 8)

    def test_each_initial_balance_must_be_zero(self):
        for which in range(6):
            with self.subTest(which=which):
                self.trace = copy.deepcopy(self.original)
                execution = self.find('executor', '0x3d47ed94')
                swap = self.find('router', '0x2948a5b4')
                checks = execution['calls'][1:3] + swap['calls'][:4]
                checks[which]['output'] = '0x' + (1).to_bytes(32, 'big').hex()
                with self.assertRaisesRegex(ValueError, 'inventory'):
                    p.audit_principal(self.trace, self.data)

    def test_repayment_before_callback_rejected(self):
        liquidation = next(f for f in p.replay.flatten(self.trace) if p.matches(f, p.replay.route.MORPHO, '0xd8eabcb8'))
        liquidation['calls'][3], liquidation['calls'][4] = liquidation['calls'][4], liquidation['calls'][3]
        with self.assertRaisesRegex(ValueError, 'order'):
            p.audit_principal(self.trace, self.data)

    def test_changed_repayment_rejected(self):
        frame = next(f for f in p.replay.flatten(self.trace) if p.matches(f, p.TOKENS['USDG'], '0x23b872dd')
                     and f['from'].lower() == p.replay.route.MORPHO)
        frame['input'] = frame['input'][:-64] + (194034132).to_bytes(32, 'big').hex()
        with self.assertRaisesRegex(ValueError, 'repayment amount'):
            p.audit_principal(self.trace, self.data)

    def test_unfunded_prefix_detected_even_with_zero_final_delta(self):
        rows = [{'ordinal': 0, 'token': 'T', 'from': 'A', 'to': 'B', 'amount_raw': 20},
                {'ordinal': 1, 'token': 'T', 'from': 'B', 'to': 'A', 'amount_raw': 20}]
        result = p.inventory_prefix(rows, 'A', 'T')
        self.assertEqual(result['final_delta_raw'], 0)
        self.assertEqual(result['minimum_initial_inventory_raw'], 20)

    def test_extra_morpho_call_rejected(self):
        self.find('executor', '0xcf7ea196')['calls'].append(
            {'to': p.replay.route.MORPHO, 'input': '0x12345678'})
        with self.assertRaisesRegex(ValueError, 'additional Morpho'):
            p.audit_principal(self.trace, self.data)

    def test_callback_authentication(self):
        self.find('executor', '0xcf7ea196')['from'] = self.data['addresses']['router']
        with self.assertRaisesRegex(ValueError, 'caller'):
            p.audit_principal(self.trace, self.data)

    def test_reverted_trace_not_a_proof(self):
        self.find('router', '0x2948a5b4')['error'] = 'execution reverted'
        with self.assertRaisesRegex(ValueError, 'reverted'):
            p.audit_principal(self.trace, self.data)

    def test_exact_approval_required(self):
        callback = self.find('executor', '0xcf7ea196')
        approval = next(f for f in callback['calls'] if p.matches(f, p.TOKENS['USDG'], '0x095ea7b3')
                        and p.args(f)[-1] == 194034131)
        approval['input'] = approval['input'][:-64] + (194034130).to_bytes(32, 'big').hex()
        with self.assertRaisesRegex(ValueError, 'approval'):
            p.audit_principal(self.trace, self.data)

    def test_full_offline_audits_and_cash_conservation(self):
        result = p.audit()
        self.assertEqual(result['new_rpc_methods'], 0)
        self.assertIsNone(result['external_funding_committed_wei'])
        self.assertFalse(result['realized_revenue'])
        for row in result['loss_attribution']:
            self.assertEqual(row['sponsor_cash_delta_wei'] + row['bundler_and_beneficiary_cash_delta_wei'],
                             row['consolidated_cash_delta_wei'])
        revert = result['loss_attribution'][2]
        self.assertEqual(revert['sponsor_cash_delta_wei'], 0)
        self.assertLess(revert['bundler_and_beneficiary_cash_delta_wei'], 0)


if __name__ == '__main__':
    unittest.main()
