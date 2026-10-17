import json
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from prospective_observation import analyze, collect, request, temporal_order

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'evidence/2026-10-17-prospective-recovered'


class ProspectiveObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sample = Path(self.temp.name)/'sample'
        shutil.copytree(EVIDENCE/'sample-00',self.sample)

    def edit(self,name,mutate):
        path = self.sample/name; record = json.loads(path.read_text())
        mutate(record); path.write_text(json.dumps(record))

    def test_mixed_or_equal_index_heights_never_certify_state_or_profit(self):
        report = analyze(self.sample)
        self.assertFalse(report['certified']); self.assertIsNone(report['liquidation_eligible'])
        self.assertIsNone(report['morpho_aggregate_flash_cash'])
        height = report['observations']['market']['indexed_block']
        for name in ('position.json','oracle.json'):
            self.edit(name,lambda r:r['response']['data'].update(last_indexed_block=str(height)))
        altered = analyze(self.sample)
        self.assertTrue(altered['same_reported_block'])
        self.assertIsNone(altered['net_profit'])
        self.assertIn('REST_STATE_NOT_PROVED_AGAINST_HEADER_ROOT',altered['blockers'])

    def test_changed_header_wrong_position_and_lossy_amount_fail(self):
        report = analyze(self.sample); height = report['observations']['market']['indexed_block']
        header = self.sample/f'header-{height}.json'; saved = header.read_bytes()
        self.edit(header.name,lambda r:r['response']['result'].update(stateRoot='0x'+'00'*32))
        with self.assertRaisesRegex(ValueError,'header hash mismatch'): analyze(self.sample)
        header.write_bytes(saved)
        position = self.sample/'position.json'; saved = position.read_bytes()
        self.edit(position.name,lambda r:r['response']['data'].update(user_address='0x'+'00'*20))
        with self.assertRaisesRegex(ValueError,'wrong observed position'): analyze(self.sample)
        position.write_bytes(saved)
        self.edit('market.json',lambda r:r['response']['data'].update(total_borrow_assets=1.5))
        with self.assertRaises(ValueError): analyze(self.sample)

    def test_after_event_reads_cannot_be_promoted_to_temporal_capture(self):
        report = analyze(self.sample)
        self.assertFalse(temporal_order(report,1791983495,26190955))
        latest = max(r['block_timestamp'] for r in report['observations'].values())
        # A future boundary can satisfy necessary ordering only; the report still
        # withholds eligibility and economics, and no win probability is produced.
        height = max(r['indexed_block'] for r in report['observations'].values())
        self.assertTrue(temporal_order(report,latest+86400,height+7200))
        complete = int(datetime.fromisoformat(report['complete_data_received_at_utc']).timestamp())
        self.assertFalse(temporal_order(report,complete,height+1))
        self.assertIsNone(report['net_profit'])
        with self.assertRaises(ValueError): temporal_order({'observations':{}},latest,height)
        self.edit('oracle.json',lambda r:r.update(received_at_utc='2020-01-01T00:00:00+00:00'))
        with self.assertRaisesRegex(ValueError,'negative request interval'): analyze(self.sample)

    def test_collection_is_bounded_read_only_and_never_retries(self):
        with patch('urllib.request.urlopen') as network:
            with self.assertRaisesRegex(ValueError,'session limit reached'):
                collect(EVIDENCE,EVIDENCE/'selection.json')
            with self.assertRaisesRegex(ValueError,'only read-only header'):
                request(Path(self.temp.name)/'forbidden.json','https://rpc.flashbots.net/fast',
                        {'method':'eth_sendRawTransaction','params':['0x00',False]})
            network.assert_not_called()
