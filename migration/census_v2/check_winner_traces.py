#!/usr/bin/env python3
"""Golden historical totals and malformed/reverted trace rejection."""
import argparse
from pathlib import Path
import re
import unittest
import zipfile

import reconcile_winner_traces as r


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ARGS.archive) as z:
            cls.simple = z.read('0001-26999547ac702620.cast.log')
            cls.reverted = z.read('0051-3f873abb49e69398.cast.log')

    def test_historical_totals_and_scope_mismatch(self):
        report = r.reconcile(ARGS.archive, ARGS.core, ARGS.output)
        self.assertEqual(report['winner_transactions'], 127)
        self.assertEqual(report['observed_transaction_gas_cost_wei'], '448369976498898050')
        self.assertEqual(report['counts'], {'call_frames': 15001, 'oracle_calls': 719,
            'oracle_calls_in_reverted_subtrees': 4, 'oracle_end_state_mismatches': 1,
            'rendered_value_fields': 350, 'reverted_frames': 20})
        self.assertEqual(report['outputs']['price-scope-mismatch-ledger.jsonl']['rows'], 1)
        self.assertEqual(report['outputs']['reverted-frame-ledger.jsonl']['rows'], 20)
        mismatch = r.parse((ARGS.output/'price-scope-mismatch-ledger.jsonl').read_bytes())
        self.assertEqual(mismatch['transaction_hash'], '0x8f0ab391fcf8c1454f9665460a5d675a0821b4a53e01301c17bc239ac2fcad65')
        self.assertEqual(mismatch['trace_return_units'], '7691878258344')
        self.assertEqual(mismatch['end_of_block_reference_units'], '7652143127459')
        self.assertTrue(mismatch['successful_ancestry'])
        self.assertFalse(mismatch['price_used_by_liquidation_proven'])
        ledger = [r.parse(line) for line in (ARGS.output/'winner-trace-ledger.jsonl').read_bytes().splitlines()]
        self.assertTrue(all(row['reasons'] and row['current_execution_permitted'] is False for row in ledger))
        self.assertFalse(report['complete_pnl_proven'])
        self.assertFalse(report['new_fork_replay'])
        self.assertFalse(report['raw_receipt_coverage_increased'])
        self.assertFalse(report['census_closed'])

    def test_reverted_parent_invalidates_successful_quote(self):
        _, nodes = r.parse_trace(self.reverted)
        invalid = [n for n in nodes if r.QUOTE.fullmatch(n['body']) and not n['successful_ancestry']]
        self.assertEqual(len(invalid), 2)
        self.assertTrue(all(n['outcome'] == 'Return' for n in invalid))
        for n in invalid:
            parent = n['parent']
            outcomes = []
            while parent is not None:
                outcomes.append(nodes[parent]['outcome'])
                parent = nodes[parent]['parent']
            self.assertIn('Revert', outcomes)

    def test_missing_return_fails_despite_success_footer(self):
        text = self.simple.decode()
        text = re.sub(r'^.*← \[Return\].*\n', '', text, count=1, flags=re.MULTILINE)
        with self.assertRaisesRegex(ValueError, 'tree depth|incomplete trace'):
            r.parse_trace(text.encode())

    def test_multiple_roots_rejected(self):
        text = self.simple.decode()
        text = text.replace('Transaction successfully executed.',
            '  [0] 0x0000000000000000000000000000000000000001::fallback()\n    └─ ← [Stop]\nTransaction successfully executed.')
        with self.assertRaisesRegex(ValueError, 'incomplete trace tree'):
            r.parse_trace(text.encode())

    def test_duplicate_gas_rejected(self):
        with self.assertRaisesRegex(ValueError, 'one transaction gas line'):
            r.parse_trace(self.simple + b'\nGas used: 1\n')

    def test_failed_root_rejected(self):
        text = self.simple.decode()
        text, count = re.subn(r'^    └─ ← \[(Return|Stop)\]', '    └─ ← [Revert]', text, flags=re.MULTILINE)
        self.assertEqual(count, 1)
        with self.assertRaisesRegex(ValueError, 'root reverted'):
            r.parse_trace(text.encode())


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['archive', 'core', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    ARGS, rest = p.parse_known_args()
    unittest.main(argv=['check_winner_traces.py', *rest])
