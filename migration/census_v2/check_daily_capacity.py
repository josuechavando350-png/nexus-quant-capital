#!/usr/bin/env python3
"""Real-ledger conservation and adverse-input checks for daily target analysis."""
import argparse
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_daily_capacity as a


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = a.c.read_core(ARGS.core)
        cls.tx = a.c.rows(cls.files, a.TX_FILE)
        cls.days = a.c.rows(cls.files, a.DAY_FILE)

    def test_real_source_repeats_with_no_network_or_income_admission(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
            first = a.analyze(ARGS.core)
            self.assertEqual(first, a.analyze(ARGS.core))
        r = first[1]; s = r['summary']
        self.assertEqual((s['transactions'], s['events'], s['days']), (127, 139, 30))
        self.assertEqual(s['gross_oracle_edge_usd_wad'], '138045174690310000000000')
        self.assertEqual(s['reference_after_only_observed_gas_usd_wad'], '136901040429717286157971')
        self.assertIsNone(r['complete_nqc_net_pnl_usd_wad'])
        self.assertIsNone(r['success_probability'])
        self.assertFalse(r['daily_minimum_income_proven'])
        self.assertFalse(r['census_closed'])

    def test_daily_distribution_preserves_zeros_and_concentration(self):
        rows, s = a.summarize(self.tx, self.days)
        self.assertEqual(s['zero_transaction_days'], 2)
        self.assertEqual(s['reference_negative_days'], 4)
        self.assertEqual([t['reference_days_at_least_target'] for t in s['targets']], [9, 6])
        self.assertEqual([t['reference_days_below_target'] for t in s['targets']], [21, 24])
        self.assertEqual(s['concentration_by_gross'][1]['gross_usd_wad'], '110485665624800000000000')
        self.assertEqual(s['median_daily_reference_usd_wad_fraction'],
                         {'numerator': '987632093999253233735', 'denominator': 2})
        self.assertEqual(rows[0]['start_utc'], '2026-09-01T05:23:35+00:00')
        self.assertEqual(rows[-1]['end_exclusive_utc'], '2026-10-01T05:23:35+00:00')

    def test_small_bands_cumulative_not_disjoint_or_forecasts(self):
        _, s = a.summarize(self.tx, self.days)
        band = next(b for b in s['small_reference_bands'] if b['upper_reference_usd'] == 100)
        self.assertEqual(band['transactions'], 49)
        self.assertEqual(band['subtotal_reference_usd_wad'], '1038077250722798681319')
        self.assertFalse(s['hypothetical_table_is_forecast'])
        self.assertEqual(s['hypothetical_captured_trades_required'][1],
                         {'net_usd_per_captured_trade_assumption': 50,
                          'trades_for_1500_net_usd': 30, 'trades_for_3500_net_usd': 70})

    def test_missing_zero_day_duplicate_winner_and_changed_day_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            a.summarize(self.tx, [d for d in self.days if d['day_index'] != 6])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            a.summarize(self.tx + [self.tx[0]], self.days)
        changed = copy.deepcopy(self.days); changed[0]['transaction_count'] += 1
        with self.assertRaisesRegex(ValueError, 'conservation'):
            a.summarize(self.tx, changed)

    def test_changed_gas_and_removed_unknowns_rejected(self):
        changed = copy.deepcopy(self.tx); changed[0]['observed_winner_gas_cost_usd_wad'] = '0'
        with self.assertRaisesRegex(ValueError, 'arithmetic'):
            a.summarize(changed, self.days)
        changed = copy.deepcopy(self.tx); changed[0]['omitted_costs'] = []
        with self.assertRaisesRegex(ValueError, 'authority'):
            a.summarize(changed, self.days)

    def test_corrupted_source_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'core.zip'; raw = bytearray(ARGS.core.read_bytes()); raw[10] ^= 1; p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'transport digest'):
                a.analyze(p)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--core', type=Path, required=True)
    ARGS, rest = p.parse_known_args(); unittest.main(argv=['check_daily_capacity.py', *rest])
