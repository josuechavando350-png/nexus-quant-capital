"""Mutation tests of captured historical fields; not invented liquidation profits."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from route_audit import analyze,expand
from keccak_reference import keccak256

class CapturedRouteTests(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((ROOT/'inputs/route_evidence.json').read_text())
        self.original=json.loads((ROOT/'reference/selected_log.json').read_text())
    def run_case(self): return analyze(self.c,self.original)
    def blocked(self):
        with self.assertRaises(ValueError): self.run_case()
    def test_historical_path_reconciles(self):
        r=self.run_case()
        self.assertEqual(r['usdc_after_debt'],'84.308093')
        self.assertEqual(r['usdc_payout'],'23.882951')
        self.assertEqual(r['observed_transfer_prefix_initial_usdc_requirement'],{'MORPHO':'3305.262344'})
        self.assertEqual(r['usdc_net_by_node']['MORPHO'],'-84.308093')
        self.assertEqual(r['usdc_net_by_node']['EXECUTOR'],'0.000000')
        self.assertIsNone(r['nqc_net_profit']); self.assertFalse(r['live_executable'])
    def test_archive_liquidation_bytes_are_identical(self):
        raw=expand(self.c['events'][2],self.c['addresses'],self.c['event_signatures'])
        self.assertEqual(raw['data'],self.original['data'])
        self.assertEqual(raw['topics'],self.original['topics'])
    def test_keccak_empty_known_vector(self):
        self.assertEqual(keccak256(b'').hex(),'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
    def test_missing_page_rejected(self):
        self.c['pages'].pop();self.blocked()
    def test_nonfinal_pagination_rejected(self):
        self.c['pagination_final']={'cursor':'not-finished'};self.blocked()
    def test_missing_event_rejected(self):
        self.c['events'].pop(20);self.blocked()
    def test_duplicate_event_rejected(self):
        self.c['events'][21]=deepcopy(self.c['events'][20]);self.blocked()
    def test_broken_intermediate_usdc_amount_rejected(self):
        self.c['events'][28]['words'][0]='c5024d09';self.blocked()
    def test_wrong_usdc_intermediate_recipient_rejected(self):
        self.c['events'][22]['indexed'][1]='EXECUTOR';self.blocked()
    def test_primary_market_substitution_rejected(self):
        self.c['events'][19]['indexed'][0]='LIQUIDATION_MARKET';self.blocked()
    def test_catalog_asset_substitution_rejected(self):
        m=self.c['market_catalog'][self.c['addresses']['WITHDRAWAL_MARKET']]
        m['collateralAsset']['address']=self.c['addresses']['PT'];self.blocked()
    def test_debt_transfer_before_redemption_rejected(self):
        self.c['events'][37],self.c['events'][42]=self.c['events'][42],self.c['events'][37];self.blocked()
    def test_weth_withdrawal_not_transfer_to_zero(self):
        self.c['events'][49]['event']='TRANSFER';self.blocked()
    def test_sweep_event_token_not_recipient(self):
        r=self.run_case()
        self.assertTrue(r['sweep_event_indexed_field_is_token_not_payout'])
        self.c['events'][52]['indexed']=['PAYOUT'];self.blocked()
    def test_no_double_count_of_payment_event(self):
        r=self.run_case()
        self.assertEqual(r['builder_paid_event_wei'],'32210448575152600')
        self.assertEqual(r['weth_increment_wei'],'225720514923773')
    def test_signed_swap_amount_rejected_if_positive(self):
        self.c['events'][47]['words'][1]='733c86207d0ed5';self.blocked()
    def test_changed_signature_rejected(self):
        self.c['event_signatures']['SY_REDEEM'][1]='0x'+'0'*64;self.blocked()
    def test_boolean_index_rejected(self):
        self.c['events'][0]['index']=False;self.blocked()
    def test_overflowing_word_rejected(self):
        self.c['events'][20]['words'][0]='1'+'0'*64;self.blocked()
    def test_changed_builder_event_amount_rejected(self):
        self.c['events'][50]['words'][0]='726f3b7960c1d9';self.blocked()
    def test_changed_cap_burn_rejected(self):
        self.c['events'][15]['words'][0]='b32daa6a7b367be7c6';self.blocked()
    def test_wrong_block_rejected(self):
        self.c['block_number']+=1;self.blocked()

if __name__=='__main__':unittest.main(verbosity=2)
