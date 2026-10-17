import unittest
from case_b_route_audit import audit, signature, cost_frontier
from historical_rpc_audit import load


class CaseBRouteTests(unittest.TestCase):
    def test_observed_bid_cost_boundary_is_strict_and_not_sponsorship(self):
        report = audit(); frontier = report['cost_frontier']
        available = report['sale_minus_debt_wei']-report['coinbase_out_wei']
        gas = frontier['gas_units_assumption']
        limit = frontier['max_total_gas_price_wei_for_strict_positive_before_unknown_costs']
        self.assertGreater(available-gas*limit,0)
        self.assertLessEqual(available-gas*(limit+1),0)
        residual = report['incremental_residual_after_known_costs_upper_bound_wei']
        self.assertEqual(frontier['max_additional_cost_wei_for_strict_positive'],residual-1)
        self.assertEqual(frontier['additional_cost_that_consumes_all_remaining_residual_wei'],residual)
        self.assertFalse(frontier['nqc_gas_or_sponsor_estimate'])
        self.assertIsNone(cost_frontier(1,2,1,1)['max_additional_cost_wei_for_strict_positive'])
        with self.assertRaises(ValueError): cost_frontier(1.0,0,1,1)

    def test_fluid_signed_movements_and_known_cost_upper_bound(self):
        result = audit()
        self.assertEqual(signature('swapIn(bool,uint256,uint256,address)')[:10], '0x2668dfaa')
        self.assertEqual(result['operations'][1]['supply_amount'], -26409680973611000000)
        self.assertEqual([x['borrow_amount'] for x in result['operations']], [0, 0])
        self.assertEqual(len(result['observed_storage_reads']), 4)
        self.assertEqual(result['sale_minus_debt_wei'], 369942447954007585)
        self.assertEqual(result['incremental_residual_after_known_costs_upper_bound_wei'], 1651296044494913)
        self.assertFalse(result['pretransaction_state_reconstructed'])
        self.assertIsNone(result['sponsor_cost'])
        self.assertFalse(result['nqc_profit_certified'])

    def test_swap_output_changed_one_wei_rejected(self):
        receipt = load('b-receipt.json')['response']['result']
        log = next(x for x in receipt['logs'] if x['address'] == '0xdd72157a021804141817d46d9852a97addfb9f59')
        raw = bytearray.fromhex(log['data'][2:]); raw[95] ^= 1
        log['data'] = '0x' + raw.hex()
        with self.assertRaisesRegex(ValueError, 'event disagrees'):
            audit(receipt=receipt)

    def test_liquidity_event_and_initial_balance_are_not_extra_income(self):
        result = audit()
        self.assertEqual(result['collateral_transfer_minus_liquidity_supply_credit'], 3042997991874121)
        self.assertIsNone(result['dex_fee_separately_verified'])
        self.assertEqual(result['initial_weth_excluded_from_income_wei'], 6392502690919791)
        self.assertEqual(result['final_weth_inferred_wei'] - result['initial_weth_excluded_from_income_wei']
                         - result['sender_gas_out_wei'], result['incremental_residual_after_known_costs_upper_bound_wei'])
        receipt = load('b-receipt.json')['response']['result']
        log = next(x for x in receipt['logs'] if x['address'] == '0x52aa899454998be5b000ad077a46bbe360f4e497')
        raw = bytearray.fromhex(log['data'][2:]); raw[63] = 1  # fabricated borrow cannot pass
        log['data'] = '0x' + raw.hex()
        with self.assertRaisesRegex(ValueError, 'event disagrees'):
            audit(receipt=receipt)
