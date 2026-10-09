#!/usr/bin/env python3
"""Real-input and adversarial checks for the bounded server read-back."""
import argparse
import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import verify_server_recovery as v


class Checks(unittest.TestCase):
    def test_actual_pinned_inputs_and_nonclaims(self):
        result = v.verify(ARGS.root, ARGS.d15b, ARGS.legs)
        self.assertEqual(result['event_reconciliation']['event_count'], 139)
        self.assertFalse(result['recovery_archive_complete'])
        self.assertFalse(result['real_market_census_closed'])
        self.assertIsNone(result['material_unknown_count'])

    def test_changed_summary_rejected_before_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in v.LINKS:
                dst = root / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ARGS.root / name, dst)
            path = root / next(iter(v.LINKS))
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'input binding'):
                v.verify(root, ARGS.d15b, ARGS.legs)

    def test_missing_or_duplicate_event_rejected(self):
        for rows in (SOURCE[:-1], SOURCE[:-1] + [SOURCE[0]]):
            with self.assertRaisesRegex(ValueError, 'cardinality/uniqueness'):
                v.reconcile_events(rows, LATER)

    def test_changed_amount_rejected(self):
        rows = copy.deepcopy(SOURCE)
        rows[0]['debt_to_cover'] = str(int(rows[0]['debt_to_cover']) + 1)
        with self.assertRaisesRegex(ValueError, 'field differs'):
            v.reconcile_events(rows, LATER)

    def test_changed_borrower_rejected(self):
        rows = copy.deepcopy(SOURCE)
        rows[0]['user'] = '0x' + '00' * 20
        with self.assertRaisesRegex(ValueError, 'borrower identity'):
            v.reconcile_events(rows, LATER)

    def test_integer_false_not_accepted_as_boolean(self):
        rows = copy.deepcopy(SOURCE)
        rows[0]['receive_atoken'] = 0
        with self.assertRaisesRegex(ValueError, 'boolean required'):
            v.reconcile_events(rows, LATER)

    def test_duplicate_json_fields_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            v.parse('{"gas":1,"gas":2}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'd15b', 'legs'):
        parser.add_argument('--' + name, type=Path, required=True)
    ARGS, rest = parser.parse_known_args()
    SOURCE = [v.parse(x) for x in (ARGS.root / 'liquidation-calls.jsonl').read_bytes().splitlines()]
    LATER = [v.parse(x) for x in v.archive_member(ARGS.legs, v.LEGS_SHA, 'decoded-liquidation-legs.jsonl').splitlines()]
    unittest.main(argv=['check_server_recovery.py', *rest])
