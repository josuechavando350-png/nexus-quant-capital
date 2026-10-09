"""Real V2 ledger joins: no hidden payer substitution or economic promotion."""
import copy
import gzip
from pathlib import Path
import unittest

from reconcile_additional import HERE, V2, join_v2_ledger, origin_check
from rmc016_winner_net_audit import canonical, parse_json


class AdditionalJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exchanges = [parse_json(line) for line in gzip.decompress(
            (HERE / 'recovered-rmc016/tenderly-receipts-20261009.jsonl.gz').read_bytes()).splitlines()]
        cls.ledger = (V2 / 'evidence/economics/replay/winner-economic-ledger.jsonl').read_bytes()
        cls.rows = [parse_json(line) for line in cls.ledger.splitlines()]

    def modified(self, change, expected):
        rows = copy.deepcopy(self.rows)
        change(rows)
        with self.assertRaisesRegex(ValueError, expected):
            join_v2_ledger(self.exchanges, b''.join(canonical(row) for row in rows))

    def test_real_pinned_copies_and_distinct_destination(self):
        origin = origin_check()
        self.assertEqual(origin['destination_repository'], 'josuechavando350-png/nexus-quant-capital')
        self.assertFalse(origin['source_run_identity_transferred'])

    def test_all_127_join_and_four_previously_unknown_senders_are_supplemental(self):
        before = copy.deepcopy(self.exchanges)
        report = join_v2_ledger(self.exchanges, self.ledger)
        self.assertEqual(report['transaction_count'], 127)
        self.assertEqual(report['existing_known_payers_matched'], 123)
        self.assertEqual(len(report['previously_unknown_payer_observations']), 4)
        self.assertEqual(report['whole_transaction_gas_wei'], '448369976498898050')
        self.assertEqual(report['incremental_gas_charged_wei'], '0')
        self.assertFalse(report['economic_classifications_changed'])
        self.assertEqual(self.exchanges, before)

    def test_existing_known_payer_cannot_be_substituted(self):
        self.modified(lambda rs: rs[0]['historical_gas'].update(payer='0x' + '0' * 40),
                      'known payer mismatch')

    def test_missing_v2_transaction_rejected(self):
        self.modified(lambda rs: rs.pop(), 'membership mismatch')

    def test_competitor_gas_cannot_be_charged_to_nqc(self):
        self.modified(lambda rs: rs[0]['historical_gas'].update(is_nqc_gas=True),
                      'NQC attribution')

    def test_new_receipts_cannot_promote_profit_or_admission(self):
        self.modified(lambda rs: rs[0].update(complete_realized_net_usd_wad='1'),
                      'economic promotion')


if __name__ == '__main__':
    unittest.main()
