"""Real captured RPC records with adversarial coverage and identity mutations."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import reconcile as r


class FullWindowChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = Path(os.environ['NQC_FULL_WINDOW_EVIDENCE'])
        cls.receipts, cls.events, cls.ids = r.authenticated_drpc_checkpoint(
            r.V2 / 'economic_archives/inputs/11524199698.zip',
            r.V2 / 'economic_archives/inputs/11524139188.zip')
        cls.records = r.rpc_records(cls.evidence / 'drpc-full-receipts')
        raw = r.gzip.decompress((r.V2 / 'additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz').read_bytes())
        cls.tenderly = {x['params'][0]: x['result'] for x in (r.parse(line) for line in raw.splitlines())
                       if x['method'] == 'eth_getTransactionReceipt'}

    def compare(self, records):
        return r.compare_full_receipts(records, self.receipts, self.events, self.ids, self.tenderly)

    def test_real_complete_30_day_window_and_127_full_receipts(self):
        report = r.reconcile(self.evidence)
        self.assertEqual(report['scope']['covered_blocks'], 215036)
        self.assertEqual(report['executed_liquidation_events'], 139)
        self.assertEqual(report['full_semantic_receipt_log_matches'], 127)
        self.assertFalse(report['full_oracle_or_canonical_header_lineage_completed'])
        self.assertFalse(report['original_decision_time_observation_proven'])
        self.assertFalse(report['real_market_census_closed'])

    def test_missing_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete or reordered'):
            self.compare(self.records[:-1])

    def test_duplicate_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing/duplicate'):
            self.compare(self.records + self.records[:1])

    def test_reordered_receipts_rejected(self):
        records = list(self.records)
        records[0], records[1] = records[1], records[0]
        with self.assertRaisesRegex(ValueError, 'incomplete or reordered'):
            self.compare(records)

    def test_changed_full_log_rejected(self):
        records = copy.deepcopy(self.records)
        log = records[0][2]['logs'][0]
        log['data'] = ('0x' + '0' * (len(log['data']) - 2)) if log['data'] != '0x' else '0x00'
        with self.assertRaises(ValueError):
            self.compare(records)

    def test_empty_log_shard_cannot_be_omitted(self):
        original = r.records_for
        def missing(directory, provider, mode):
            report, records, identity = original(directory, provider, mode)
            if mode == 'logs':
                index = next(i for i, (_, req, response) in enumerate(records)
                             if req['method'] == 'eth_getLogs' and response == [])
                records = records[:index] + records[index+1:]
            return report, records, identity
        with patch.object(r, 'records_for', side_effect=missing):
            with self.assertRaisesRegex(ValueError, 'full historical event population'):
                r.reconcile(self.evidence)

    def test_foreign_collector_repository_rejected(self):
        original = r.parse
        def foreign(raw):
            doc = original(raw)
            if type(doc) is dict and doc.get('producer_commit') == r.BASE:
                doc['producer_repository'] = 'wrong/repository'
            return doc
        with patch.object(r, 'parse', side_effect=foreign):
            with self.assertRaisesRegex(ValueError, 'source identity'):
                r.source_identity(self.evidence)


if __name__ == '__main__':
    unittest.main()
