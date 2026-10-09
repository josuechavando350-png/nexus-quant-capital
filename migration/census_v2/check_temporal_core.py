#!/usr/bin/env python3
"""Checks with recovered ledgers and independent golden conservation totals."""
import argparse
from pathlib import Path
import tempfile
import unittest

import reconcile_temporal_core as r


class Checks(unittest.TestCase):
    def test_golden_partition_and_no_promotions(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'readback'
            result = r.verify(ARGS.core, ARGS.prior, out)
            self.assertEqual(result['candidate_accounts'], 29998)
            self.assertEqual(result['classification_counts'],
                             {'INSUFFICIENT_EVIDENCE': 29998, 'EXECUTABLE': 0, 'NON_EXECUTABLE': 0})
            self.assertEqual(result['censored_accounts'] + result['definite_accounts'], 29998)
            self.assertFalse(result['census_closed'])
            self.assertFalse(result['decision_time_observations_proven'])
            self.assertEqual(result['economics']['observed_winner_gas_wei'], '448369976498898050')
            self.assertEqual(result['economics']['observed_gross_oracle_edge_usd_wad'], '138045174690310000000000')
            self.assertEqual(result['economics']['observed_winner_gas_usd_wad'], '1144134260592713842029')
            self.assertEqual(result['economics']['after_only_gas_sign_counts'], {'positive': 83, 'nonpositive': 44})
            self.assertEqual(result['economics']['daily_rows_reconciled'], 30)
            self.assertIsNone(result['economics']['complete_net_pnl_usd_wad'])
            self.assertFalse(result['economics']['price_ledger_base_fee_used_for_gas'])

    def test_corrupted_transport_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / 'core.zip'
            raw = bytearray(ARGS.core.read_bytes())
            raw[100] ^= 1
            altered.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'transport digest'):
                r.read_core(altered)

    def test_changed_prior_cost_ledger_rejected(self):
        files = r.read_core(ARGS.core)
        _, events, _ = r.temporal(files)
        with self.assertRaisesRegex(ValueError, 'prior economic ledger pin'):
            r.economics(files, events, ARGS.prior.read_bytes() + b'\n')

    def test_different_authority_domain_rejected(self):
        files = r.read_core(ARGS.core)
        doc = r.parse(files['rmc016-capacity-authority.json'])
        with self.assertRaisesRegex(ValueError, 'authority commitment'):
            r.commitment(doc, 'NQC-RMC015-TEMPORAL-CONSERVATIVE-AUTHORITY-V1')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core', type=Path, required=True)
    p.add_argument('--prior', type=Path, required=True)
    ARGS, rest = p.parse_known_args()
    unittest.main(argv=['check_temporal_core.py', *rest])
