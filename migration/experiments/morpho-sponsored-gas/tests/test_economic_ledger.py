import dataclasses
import copy
import sys
import unittest
from fractions import Fraction
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from economic_ledger import Settlement, evaluate, expected_sponsor_margin
from test_bundle_gate import scenario as original_scenario
from bundle_gate import check

def scenario():
    return copy.deepcopy(original_scenario())


class EconomicLedgerTests(unittest.TestCase):
    def setUp(self):
        self.s = Settlement(1000,0,800,0,0,0,100,100,60,20,40,0,5,0,10,0)

    def test_callback_and_flash_route_do_not_double_count_principal(self):
        a=evaluate(self.s)
        b=evaluate(dataclasses.replace(self.s,flash_received_loan_units=800,flash_returned_loan_units=800))
        self.assertEqual(a,b)
        self.assertEqual(a["operator_loan_units"],100)
        self.assertEqual(a["operator_native_wei"],20)
        self.assertEqual(a["sponsor_margin_wei"],5)
        self.assertIsNone(a["realized_profit"])

    def test_flash_shortfall_rejected(self):
        with self.assertRaises(ValueError): evaluate(dataclasses.replace(self.s,flash_received_loan_units=800))

    def test_fee_reduces_residual(self):
        self.assertEqual(evaluate(dataclasses.replace(self.s,finance_fee_loan_units=5))["operator_loan_units"],95)

    def test_coinbase_does_not_automatically_increase_builder_margin(self):
        x=evaluate(dataclasses.replace(self.s,coinbase_payment_wei=40))
        self.assertEqual(x["sponsor_margin_wei"],5)
        self.assertEqual(x["operator_native_wei"],0)

    def test_sponsor_return_is_not_operator_profit(self):
        x=evaluate(dataclasses.replace(self.s,advance_returned_wei=5))
        self.assertEqual(x["sponsor_margin_wei"],10)
        self.assertEqual(x["operator_native_wei"],20)

    def test_negative_residual_is_blocked(self):
        self.assertFalse(evaluate(dataclasses.replace(self.s,executable_sale_loan_units=800))["balanced_positive_model"])

    def test_included_failure_can_erase_positive_margin(self):
        self.assertEqual(expected_sponsor_margin(5,100,Fraction(9,10),Fraction(1,10)),Fraction(-11,2))

    def test_unknown_probabilities_not_assumed_zero(self):
        with self.assertRaises(ValueError): expected_sponsor_margin(5,100,None,None)
        with self.assertRaises(ValueError): expected_sponsor_margin(5,100,Fraction(1),Fraction(1,10))

    def test_no_deployment_model_one_transaction(self):
        b=scenario();b["architecture"]="DEPLOYED_BUNDLER3";b["txs"]=[b["txs"][1]]
        out=check(b)
        self.assertEqual(out.transaction_count,1)
        self.assertNotIn("BUILDER_SPONSORED_DEPLOYMENT_NOT_CONFIRMED",out.blockers)
        self.assertIn("SYNTHETIC_INPUT_NOT_REAL_BUNDLE",out.blockers)
        self.assertFalse(out.certified)

    def test_adapter_deployment_must_be_counted(self):
        b=scenario();b["architecture"]="OWN_EXECUTOR_AND_ADAPTER"
        deploy=dict(b["txs"][0],purpose="DEPLOY_ADAPTER")
        for t in b["txs"]:t["nonce"]=int(t["nonce"])+1
        before=check(scenario()).required_upfront_wei
        b["txs"].insert(0,deploy)
        self.assertGreater(check(b).required_upfront_wei,before)

    def test_zero_builder_margin_not_accepted(self):
        b=scenario();b["builder_profit_minimum_wei"]=0
        b["builder_value_gross_wei"]=int(b["builder_advance_wei"])+int(b["sponsor_topup_gas_limit"])*int(b["sponsor_topup_max_fee_per_gas_wei"])
        self.assertIn("BUILDER_BALANCE_MUST_INCREASE",check(b).blockers)

    def test_noncanonical_hex_rejected(self):
        for field, value in [("sponsor_refund_recipient", "0x+"+"1"*39),
                             ("prestate_block_hash", "0x "+"1"*63)]:
            b=scenario();b[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):check(b)
