import copy
import json
import unittest
from run_e2e import HERE, E, word
from reconcile import reconcile, bridge
from select_candidates import select

class EvidenceTests(unittest.TestCase):
    def load(self,name):return json.loads((HERE/'evidence'/name).read_text())
    def test_all_recorded_actor_assets_and_transactions_reconcile(self):
        built=self.load('build-manifest.json')['bytecode_sha256']
        self.assertEqual(built['Morpho'],'a73008812cf3c42dd17d5e7521b85b975813e430103ebb072f803a368a5113e3')
        self.assertEqual(built['UniswapV2Pair'],'c884817b0b634ee7a9c3daf1017f64b00f5574df06ee1ff27ca6f8fe7726e1d5')
        index=self.load('run-index.json')
        self.assertEqual(len(index['runs']),21)
        for item in index['runs']:
            with self.subTest(scenario=item['scenario']):reconcile(self.load(item['file']))
    def test_high_gas_refutes_sponsor_profit_despite_successful_liquidation(self):
        low=reconcile(self.load('C1_success.json'));high=reconcile(self.load('C1_high_gas.json'))
        self.assertGreater(low['sponsor']['cash_margin_wei'],0)
        self.assertLess(high['sponsor']['cash_margin_wei'],0)
        self.assertEqual(low['nqc']['final']['WETH'],high['nqc']['final']['WETH'])
        self.assertEqual(low['nqc']['initial'],{'ETH':0,'WETH':0,'COLLATERAL':0})
    def test_missing_return_is_not_counted_as_return_or_profit(self):
        r=reconcile(self.load('F03_deploy_only.json'))
        self.assertEqual(r['sponsor']['U_actually_returned_wei'],0)
        self.assertEqual(r['sponsor']['cash_margin_wei'],-30042000000000000)
        self.assertEqual(r['nqc']['liquidation_generated_WETH'],0)
        self.assertGreater(r['nqc']['native_retained_advance_wei'],0)
    def test_corrupt_balances_or_gas_are_rejected(self):
        for field in ('balance','gas'):
            r=self.load('C1_success.json')
            if field=='balance':r['transactions'][0]['after'][r['actors']['simulated_builder']]['ETH']+=1
            else:r['transactions'][0]['gas_cost_wei']+=1
            with self.assertRaises((ValueError,AssertionError)):reconcile(r)
    def test_reverted_transfers_are_not_settled_and_underpay_occurs_after_swap(self):
        r=self.load('F06_one_wei_underpay.json');last=r['transactions'][-1]
        self.assertEqual(int(last['receipt']['status'],16),0)
        self.assertEqual(last['receipt']['logs'],[])
        def visit(f):
            yield f
            for c in f.get('calls',[]):yield from visit(c)
        calls=list(visit(last['trace']))
        self.assertTrue(any(f.get('to')==r['actors']['dex_pair'] and f['input'].startswith('0x022c0d9f') for f in calls))
        self.assertEqual(reconcile(r)['nqc']['final']['WETH'],0)
    def test_one_wei_boundaries_and_uint256(self):
        s=self.load('exact-sensitivity.json');b=s['one_wei_depth_boundary']
        self.assertEqual(b['out']-b['previous_out'],1)
        self.assertGreater(s['gas_break_even_with_fixed_A_and_units']['sponsor_margin_at_boundary_wei'],0)
        self.assertLessEqual(s['gas_break_even_with_fixed_A_and_units']['sponsor_margin_next_wei'],0)
        for n in (-1,2**256,True,1.1):
            with self.assertRaises(ValueError):word(n)
    def test_trace_cannot_assert_builder_acceptance_or_mainnet_state(self):
        r=self.load('C1_success.json');b=bridge(r,reconcile(r))
        self.assertFalse(b['commercial_admission'])
        self.assertEqual(b['trace_projection']['chain_id'],31337)
        self.assertIsNone(b['trace_projection']['builder'])
        self.assertIsNone(b['trace_projection']['builder_advance_wei'])
        self.assertIsNone(b['trace_projection']['builder_receipts_verified'])
        self.assertIn('mainnet',b['reason'])
    def test_candidate_selection_is_frozen_unique_and_never_profit_ranked(self):
        a=select();self.assertEqual(a,self.load('candidates.json'))
        self.assertEqual(len({c['tx_hash'] for c in a['candidates']}),12)
        self.assertEqual(a['transactions_without_any_reported_bad_debt'],98)
        self.assertTrue(all(c['net_profit'] is None for c in a['candidates']))
    def test_dust_does_not_become_nqc_profit(self):
        clean=reconcile(self.load('C1_success.json'));dust=reconcile(self.load('F11_dust.json'))
        self.assertEqual(clean['nqc']['final'],dust['nqc']['final'])
        ex=dust['actors']['nqc_executor']
        self.assertEqual(dust['steps'][-1]['after'][ex],{'ETH':E,'WETH':E,'COLLATERAL':E})
    def test_orphaned_receipt_not_counted_or_promoted(self):
        r=self.load('F10_reorg.json');self.assertEqual(len(r['orphaned_not_counted']),1)
        self.assertEqual(int(r['orphaned_not_counted'][0]['receipt']['status'],16),1)
        ledger=reconcile(r)
        self.assertEqual(ledger['nqc']['liquidation_generated_WETH'],0)
        self.assertEqual(ledger['proposer_direct_tip_wei'],0)

if __name__=='__main__':unittest.main()
