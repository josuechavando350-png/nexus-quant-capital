import copy
import json
from pathlib import Path
import unittest

import route_audit as audit


class RouteAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = Path(__file__).resolve().parent / 'evidence'
        rows = json.loads((cls.evidence / 'historical-receipts/rpc_original_receipts.json').read_text())
        cls.receipts = {r['result']['transactionHash']: r['result'] for r in rows[1:]}
        cls.original = cls.receipts[audit.SELECTED]
        get = lambda name: json.loads((cls.evidence / 'explorer' / name).read_text())['data']
        cls.explorer = get('transaction.json')
        cls.reserves = get('pool_at_66744161.json')['result']
        cls.market = get('market_at_66744162.json')['result']

    def replay(self, receipt=None, explorer=None, reserves=None, market=None):
        return audit.replay_selected(receipt or self.original, explorer or self.explorer,
                                     reserves or self.reserves, market or self.market)

    def test_archive_and_independent_selected_replay(self):
        result = audit.audit(self.evidence)
        self.assertEqual(result['receipt_count'], 22)
        self.assertEqual(result['selected_replay']['surplus_before_native_gas_usdg_raw'], 32060665)
        self.assertEqual(result['selected_replay']['gas_fee_wei'], 38406689180000)
        self.assertFalse(result['nqc_revenue_proven'])
        self.assertIsNone(result['aggregate_profit'])

    def test_tax_blind_quote_overstates_surplus(self):
        result = self.replay()
        self.assertEqual(result['counterfactual_no_tax_usdg_raw'], 237986092)
        self.assertEqual(result['overstatement_if_tax_omitted_usdg_raw'], 11891296)
        self.assertFalse(result['full_evm_replay'])
        self.assertFalse(result['full_calldata_available'])

    def test_forwarded_surplus_is_not_lost_when_caller_net_is_zero(self):
        case = audit.analyze_case(self.original)
        self.assertEqual(case['usdg_net_transfer_change_raw'], 0)
        self.assertEqual(case['usdg_forwarded_to_gas_payer_raw'], 32060665)
        self.assertEqual(case['usdg_exit_less_repay_raw'], 32060665)

    def test_inventory_financed_is_not_certified_as_loss_or_profit(self):
        cases = [audit.analyze_case(r) for r in self.receipts.values()]
        inventory = [c for c in cases if c['classification'] == 'no_usdg_inflow_inventory_required']
        self.assertEqual(len(inventory), 2)
        for case in inventory:
            self.assertIsNone(case['usdg_exit_less_repay_raw'])
            self.assertLess(case['usdg_net_transfer_change_raw'], 0)

    def test_complex_flows_do_not_receive_simple_margin(self):
        case = next(audit.analyze_case(r) for tx, r in self.receipts.items() if tx.startswith('0x68cea7'))
        self.assertEqual(case['classification'], 'other_or_complex_usdg_flow')
        self.assertIsNone(case['usdg_exit_less_repay_raw'])

    def test_wrong_receipt_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'receipt identity'):
            audit.validate_receipt(self.original, '0x' + '11' * 32)

    def test_removed_log_rejected(self):
        r = copy.deepcopy(self.original)
        r['logs'][3]['removed'] = True
        with self.assertRaisesRegex(ValueError, 'removed log'):
            audit.validate_receipt(r, audit.SELECTED)

    def test_duplicate_log_rejected(self):
        r = copy.deepcopy(self.original)
        r['logs'].insert(4, copy.deepcopy(r['logs'][3]))
        with self.assertRaisesRegex(ValueError, 'duplicate or unordered'):
            audit.validate_receipt(r, audit.SELECTED)

    def test_cross_block_log_rejected(self):
        r = copy.deepcopy(self.original)
        r['logs'][3]['blockHash'] = '0x' + '22' * 32
        with self.assertRaisesRegex(ValueError, 'log/receipt identity'):
            audit.validate_receipt(r, audit.SELECTED)

    def test_malformed_transfer_rejected(self):
        r = copy.deepcopy(self.original)
        r['logs'][3]['data'] = '0x01'
        with self.assertRaisesRegex(ValueError, 'wrong data size'):
            audit.analyze_case(r)

    def test_wrong_market_event_rejected(self):
        r = copy.deepcopy(self.original)
        r['logs'][2]['topics'][1] = '0x' + '33' * 32
        with self.assertRaisesRegex(ValueError, 'wrong liquidation market'):
            audit.analyze_case(r)

    def test_prior_reserve_one_unit_discrepancy_rejected(self):
        with self.assertRaisesRegex(ValueError, 'prior-block reserves mismatch'):
            self.replay(reserves=[self.reserves[0] + 1, *self.reserves[1:]])

    def test_independent_transfer_disagreement_rejected(self):
        e = copy.deepcopy(self.explorer)
        e['token_transfers'][0]['total']['value'] = str(int(e['token_transfers'][0]['total']['value']) + 1)
        with self.assertRaisesRegex(ValueError, 'independent transfer mismatch'):
            self.replay(explorer=e)

    def test_independent_fee_disagreement_rejected(self):
        e = copy.deepcopy(self.explorer)
        e['fee']['value'] = '1'
        with self.assertRaisesRegex(ValueError, 'independent fee mismatch'):
            self.replay(explorer=e)

    def test_incomplete_explorer_transfers_rejected(self):
        e = copy.deepcopy(self.explorer)
        e['token_transfers_overflow'] = True
        with self.assertRaisesRegex(ValueError, 'incomplete explorer'):
            self.replay(explorer=e)

    def test_changed_market_parameters_rejected(self):
        with self.assertRaisesRegex(ValueError, 'market state mismatch'):
            self.replay(market=[*self.market[:-1], self.market[-1] + 1])

    def test_noncanonical_address_topic_rejected(self):
        with self.assertRaisesRegex(ValueError, 'noncanonical address'):
            audit.address_topic('0x' + '11' * 32)

    def test_invalid_quote_values_rejected(self):
        for values in [(0, 1, 1), (1, 0, 1), (-1, 1, 1), (1.5, 1, 1), (True, 1, 1)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                audit.v2_out(*values)


if __name__ == '__main__':
    unittest.main()
