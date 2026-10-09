"""Adversarial checks against recovered real economic archives and receipts."""
import copy
import unittest
from unittest.mock import patch

import reconcile as r


class RecoveredEconomicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents, _ = r.authenticated_inputs()
        cls.premium = r.committed_json(cls.contents[11530638026]['observed-aave-flash-premium.json'])
        cls.candidates = r.verified_candidates(
            r.committed_json(cls.contents[11530691544]['historical-weth-cashflow.json']),
            r.committed_json(cls.contents[11530582289]['rank2-preblock-weth-price.json']),
            r.committed_json(cls.contents[11527902751]['top-two-weth-prices.json']))

    def test_real_archives_receipts_and_scope(self):
        report, flashes = r.reconcile()
        receipt = report['full_receipt_log_reconciliation']
        self.assertEqual(report['recovered_previously_missing_archives'], 13)
        self.assertTrue(report['cashflow_replay_byte_identical'])
        self.assertEqual(receipt['previous_operator_witnesses_matched'], 210)
        self.assertEqual(receipt['previous_full_receipt_transactions_matched'], 123)
        self.assertEqual(receipt['complete_decoded_receipts'], 127)
        self.assertEqual(len(flashes), 22)
        self.assertEqual(len(receipt['additional_flash_events']), 2)
        self.assertEqual(receipt['transfer_and_log_counts']['erc20_shaped_transfers'], 1696)
        self.assertFalse(report['positive_nqc_value_admitted'])
        self.assertFalse(report['real_market_census_closed'])
        self.assertEqual(report['active_gas_budget_currency'], 'MXN')
        self.assertEqual(report['active_gas_budget_minor_units'], 200000)

    def test_real_half_up_rounding_cannot_be_replaced_by_ceil(self):
        changed = copy.deepcopy(self.premium)
        row = changed['network_observed_history'][1]
        self.assertNotEqual(row['conditional_original_5bps_wei'],
                            row['historical_pool_premium_wei_percentmul_half_up'])
        row['historical_pool_premium_wei_percentmul_half_up'] = row['conditional_original_5bps_wei']
        with self.assertRaisesRegex(ValueError, 'arithmetic'):
            r.premium_recalculation(self.candidates, changed)

    def test_operator_disagreement_rejected(self):
        changed = copy.deepcopy(self.premium)
        changed['two_rpc_operators'][1]['rows'][0]['premium_bps'] = 6
        with self.assertRaisesRegex(ValueError, 'observations differ'):
            r.premium_recalculation(self.candidates, changed)

    def test_fee_reference_cannot_become_available_capital(self):
        changed = copy.deepcopy(self.premium)
        changed['network_observed_history'][0]['historical_pool_liquidity_cap_verified'] = True
        with self.assertRaisesRegex(ValueError, 'available capital or profit'):
            r.premium_recalculation(self.candidates, changed)

    def test_archived_fee_reference_cannot_become_nqc_profit(self):
        changed = copy.deepcopy(self.premium)
        changed['network_observed_history'][0]['nexus_net_profit_proven'] = True
        with self.assertRaisesRegex(ValueError, 'available capital or profit'):
            r.premium_recalculation(self.candidates, changed)

    def test_changed_committed_report_rejected(self):
        changed = copy.deepcopy(self.premium)
        changed['real_market_census_closed'] = True
        with self.assertRaisesRegex(ValueError, 'commitment mismatch'):
            r.committed_json(r.canonical(changed))

    def test_changed_archived_liquidation_amount_rejected_by_actual_logs(self):
        changed = copy.deepcopy(self.contents)
        rows = [r.parse(line) for line in changed[11525823668]['decoded-liquidation-legs.jsonl'].splitlines()]
        rows[0]['debt_to_cover_raw'] = str(int(rows[0]['debt_to_cover_raw']) + 1)
        changed[11525823668]['decoded-liquidation-legs.jsonl'] = b''.join(r.canonical(x) for x in rows)
        with self.assertRaisesRegex(ValueError, '139 decoded liquidation legs differ'):
            r.complete_receipt_logs(changed)

    def test_full_semantic_log_mismatch_rejected(self):
        original = r.pinned_source
        def changed(path):
            raw = original(path)
            if path.endswith('winner-economic-ledger.jsonl'):
                rows = [r.parse(line) for line in raw.splitlines()]
                rows[0]['raw_receipt_witnesses'][0]['semantic_receipt_sha256'] = '0' * 64
                return b''.join(r.canonical(x) for x in rows)
            return raw
        with patch.object(r, 'pinned_source', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'full receipt/log historical mismatch'):
                r.complete_receipt_logs(self.contents)


if __name__ == '__main__':
    unittest.main()
