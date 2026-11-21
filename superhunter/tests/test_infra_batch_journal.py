from copy import deepcopy
import unittest

from superhunter import product_timeline_formats as clocks
from superhunter.tests import test_journal_correlation as original_suite
from superhunter.safe_io import strict_json


class ClockContracts(unittest.TestCase):
    def setUp(self):
        self.fixture = strict_json(clocks.read_artifact(clocks.ROOT, clocks.FIXTURE))

    def test_lossless_projection_from_existing_NQC_fixture(self):
        source = original_suite.CorrelationTests('test_cli_two_source_replay')
        try:
            source.setUp()
            inputs = [strict_json((bundle / 'normalized.json').read_bytes()) for bundle in source.bundles]
            self.assertEqual(self.fixture['events'], [r for val in inputs for r in val['events']])
            self.assertEqual(self.fixture['sources'], [s for val in inputs for s in val['sources']])
        finally:
            source.doCleanups()

    def test_falco_field_width_and_offset_equivalence(self):
        a = clocks.encode_falco('2026-11-06T11:00:00.123456-06:00', ('%FT%T', 9, 10**9))
        b = clocks.encode_falco(self.fixture['events'][0]['timestamp'], ('%FT%T', 9, 10**9))
        self.assertEqual(a, b)
        self.assertEqual(b, ('2026-11-06T17:00:00.123456000Z', 1793984400123456000))

    def test_unit_change_rejected(self):
        snippet = ('time_t evttime = evt->get_ts() / 1000;\n'
                   'strftime(time_sec, sizeof(time_sec), "%FT%T", &tm_buf);\n'
                   'snprintf(time_ns, sizeof(time_ns), ".%09luZ", evt->get_ts() % 1000000000);')
        with self.assertRaisesRegex(clocks.EvidenceError, 'unsupported'):
            clocks.format_rules(snippet.encode())

    def test_compound_source_sequences(self):
        rows = self.fixture['events']
        self.assertEqual(len({r['source_id'] for r in rows}), 2)
        self.assertEqual(len({r['sequence'] for r in rows}), 2)
        self.assertEqual(len({(r['source_id'], r['sequence']) for r in rows}), 4)
        same = deepcopy(self.fixture)
        same['events'][2]['source_id'] = rows[0]['source_id']
        with self.assertRaisesRegex(clocks.forensic.TimelineError, 'DUPLICATE_SOURCE_SEQUENCE'):
            clocks.forensic.analyze(same)

    def test_empty_decoder_result_rejected(self):
        with self.assertRaisesRegex(clocks.EvidenceError, 'count differs'):
            clocks.verify_times(self.fixture['events'], [], ['2026-01-01T00:00:00Z'], [])
