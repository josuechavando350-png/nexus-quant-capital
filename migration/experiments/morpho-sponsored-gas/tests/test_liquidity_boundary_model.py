import gzip
import unittest
from pathlib import Path
from liquidity_boundary_model import quote, reconcile_trace, WAD

ROOT=Path(__file__).resolve().parents[1]

class LiquidityBoundaryTests(unittest.TestCase):
    def test_exact_evm_model_agreement(self):
        text=gzip.decompress((ROOT/'evidence/2026-10-17-continuation/liquidity-boundary-traces.log.gz').read_bytes()).decode()
        rows=reconcile_trace(text)
        self.assertEqual(len(rows),21)
        self.assertTrue(any(r['settled'] and r['morpho_cash_units']==0 for r in rows))
        self.assertFalse(any(r['settled'] and r['flash_route'] and r['morpho_cash_units']<8*WAD for r in rows))

    def test_altered_evm_amount_is_rejected(self):
        text=gzip.decompress((ROOT/'evidence/2026-10-17-continuation/liquidity-boundary-traces.log.gz').read_bytes()).decode()
        with self.assertRaises(ValueError):
            reconcile_trace(text.replace('dexOut: 8249365645570551238','dexOut: 8249365645570551239',1))

    def test_fee_and_price_impact_are_separate_exact_losses(self):
        r=quote(1000*WAD)
        self.assertEqual(r['spot_value_units']-r['price_impact_without_fee_units']-r['fee_effect_on_output_units'],r['executable_out_units'])
        self.assertLess(quote(100*WAD)['executable_out_units'],8*WAD)
        self.assertLess(quote(10000*WAD)['executable_out_units'],8*WAD+WAD//2)
