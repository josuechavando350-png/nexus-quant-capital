import copy
import unittest
from decimal import Decimal
from retention import evaluate, bounded_loan_cashflow, morpho_blue_benchmark, uint

TOKEN = '0x' + 'a'*40
MARKET = '0x' + '1'*64

def fixture(*, sale_max='1050', sale_min=None, fee_min='10', fee_max=None,
            repay='1000', bid_min='0', bid_max=None, ts='201', maturity='200',
            debt='1000', gate='OPEN', chain=1):
    return {
        'fixture_only':True, 'candidate_id':'OFFLINE_FIXTURE_NO_ACTUAL_MARKET',
        'strategy':'MORPHO_MIDNIGHT_POST_MATURITY', 'chain_id':chain,
        'market_id':MARKET, 'loan_token_address':TOKEN,'loan_decimals':6,
        'borrower_debt_raw':debt, 'market_maturity_timestamp':maturity,
        'evaluation_timestamp':ts, 'liquidator_gate':gate,
        'canonical_market_verified':False, 'canonical_position_verified':False,
        'native_sponsor_terms_verified':False, 'competition_prospectively_measured':False,
        'loan_asset_cashflow':{
            'dex_proceeds_net_of_swap_fees':True,'cost_buckets_are_disjoint':True,
            'sale_loan_min':sale_min,'sale_loan_max':sale_max,
            'repay_loan_min':repay,'repay_loan_max':repay,
            'loan_fee_min':fee_min,'loan_fee_max':fee_max,
            'bid_loan_min':bid_min,'bid_loan_max':bid_max,
        },
    }

class RetentionTests(unittest.TestCase):
    def test_integer_strings_only(self):
        for bad in (1.0,1,-1,'-3','001','1e3','inf','NaN','1.0','',True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                uint(bad,'value')
        self.assertEqual(uint('12345678901234567890','v'),12345678901234567890)

    def test_bound_rejects_route_after_obligations(self):
        got=evaluate(fixture(sale_max='1010',fee_min='15'))
        self.assertEqual(got['economics']['upper_bound_loan_base_units_before_unpriced_native_obligations'],'-5')
        self.assertEqual(got['next_action'],'REJECT_THIS_SCOPED_ROUTE')
        self.assertFalse(got['commercial_admission'])

    def test_positive_upper_bound_not_profit(self):
        got=evaluate(fixture())
        self.assertEqual(got['economics']['upper_bound_loan_base_units_before_unpriced_native_obligations'],'40')
        self.assertIsNone(got['NQC_realized_profit'])
        self.assertEqual(got['native_gas_sponsor_terms'],'UNKNOWN')
        self.assertFalse(got['economics']['net_profit_demonstrated'])

    def test_full_lower_bound_before_native_not_gross_profit(self):
        got=evaluate(fixture(sale_max='1080',sale_min='1070',fee_min='10',fee_max='15',bid_min='3',bid_max='4'))
        self.assertEqual(got['economics']['lower_bound_loan_base_units_before_unpriced_native_obligations'],'51')
        self.assertFalse(got['commercial_admission'])
        self.assertFalse(got['no_personal_recourse_proven'])

    def test_maturity_strict_greater(self):
        self.assertEqual(evaluate(fixture(ts='200'))['protocol_gates']['eligibility'], 'NOT_POST_MATURITY_ELIGIBLE_AT_TIME')
        self.assertEqual(evaluate(fixture(ts='199'))['protocol_gates']['eligibility'], 'NOT_POST_MATURITY_ELIGIBLE_AT_TIME')
        self.assertTrue(evaluate(fixture(ts='201'))['protocol_gates']['maturity_strict_gt_checked'])

    def test_post_maturity_healthy_allowed_but_not_verified(self):
        g=evaluate(fixture())['protocol_gates']
        self.assertEqual(g['eligibility'],'MECHANISM_MAY_APPLY_NEEDS_CANONICAL_PROOF')
        self.assertFalse(g['canonical_market_and_state_proven'])
        self.assertFalse(g['health_factor_required_for_post_maturity'])

    def test_debt_zero_no_liquidation(self):
        self.assertEqual(evaluate(fixture(debt='0'))['protocol_gates']['eligibility'],'NO_UNPAID_DEBT')

    def test_liquidator_gate_must_be_known(self):
        self.assertEqual(evaluate(fixture(gate='RESTRICTED'))['protocol_gates']['eligibility'],'BLOCKED_BY_LIQUIDATOR_GATE')
        self.assertEqual(evaluate(fixture(gate='UNKNOWN'))['protocol_gates']['eligibility'],'GATE_STATE_UNKNOWN')

    def test_non_mainnet_not_titan_automatic(self):
        self.assertEqual(evaluate(fixture(chain=8453))['protocol_gates']['eligibility'],'NOT_ETHEREUM_1_TITAN_ROUTE')

    def test_cost_buckets_must_not_double_count(self):
        f=fixture();f['loan_asset_cashflow']['cost_buckets_are_disjoint']=False
        with self.assertRaises(ValueError):evaluate(f)
        f=fixture();f['loan_asset_cashflow']['dex_proceeds_net_of_swap_fees']=False
        with self.assertRaises(ValueError):evaluate(f)

    def test_invalid_sale_bounds(self):
        with self.assertRaises(ValueError):evaluate(fixture(sale_min='1200',sale_max='1100'))

    def test_unpriced_quote_never_auto_profit(self):
        f=fixture(sale_max=None,fee_min=None)
        g=evaluate(f)
        self.assertEqual(g['economics']['economic_decision'],'INSUFFICIENT_LOAN_LEDGER')
        self.assertIsNone(g['economics']['upper_bound_loan_base_units_before_unpriced_native_obligations'])
        self.assertFalse(g['commercial_admission'])

    def test_native_eth_not_silently_added(self):
        f=fixture(sale_min='1050',fee_max='10',bid_max='0')
        g=evaluate(f)
        self.assertFalse(g['economics']['native_ETH_gas_and_sponsor_funding_included'])
        self.assertFalse(g['commercial_admission'])

    def test_source_hash_format(self):
        f=fixture();f['market_id']='0xdead'
        with self.assertRaises(ValueError):evaluate(f)
        f=fixture();f['loan_token_address']='USDC'
        with self.assertRaises(ValueError):evaluate(f)

    def test_b_case_reconciliation(self):
        m=morpho_blue_benchmark()
        self.assertEqual(m['margin_before_bid_and_gas_ETH'],'0.369942447954007585')
        self.assertEqual(m['observed_residue_before_unseen_obligations_ETH'],'0.001651296044494913')
        self.assertEqual(m['scoped_net_after_full_debt_1bp_premium_ETH'],'-0.0009526778080707862415')
        self.assertTrue(Decimal(m['coinbase_share_of_sale_debt_margin_pct'])>99)
        self.assertFalse(m['profit_NQC_proven'])

if __name__=='__main__': unittest.main()
