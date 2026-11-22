"""Check the minimized EVE derivative and immutable packet source."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from superhunter import product_http_report_privacy as report


class PublicHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = report.packets()
        cls.headers = [{'Server': report.MASK, 'Content-Length': str(row['content_length'])}
                       for _, row in cls.rows]

    def test_times_come_from_each_recorded_packet(self):
        times = [datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() for value, _ in self.rows]
        self.assertEqual(times, [1, 2, 3])

    def test_public_events_preserve_evidence_without_packet_bodies_or_banners(self):
        events = report.evidence(self.rows, self.headers)
        for event, (_, row) in zip(events.values(), self.rows, strict=True):
            self.assertEqual(set(event), {'event_type', 'http', 'pcap_cnt', 'timestamp'})
            self.assertEqual(event['http']['length'], row['content_length'])
            self.assertEqual(event['http']['status'], 200)
            for key in ('server', 'src', 'body_hex'):
                self.assertNotIn(row[key].encode(), report.canonical(event))

    def test_unmasked_extra_and_incorrect_headers_fail_closed(self):
        for name, value in (('Server', 'NQC-FIXTURE-RAW'), ('X-Debug', 'NQC-FIXTURE-UNKNOWN'),
                            ('Content-Length', '999')):
            headers = deepcopy(self.headers)
            headers[0][name] = value
            with self.subTest(name=name), self.assertRaises(report.EvidenceError):
                report.evidence(self.rows, headers)

    def test_missing_record_cannot_be_silently_dropped(self):
        with self.assertRaises(ValueError):
            report.evidence(self.rows, self.headers[:-1])

    def test_schema_controls_change_independent_copies(self):
        events = report.evidence(self.rows, self.headers)
        controls = report.schema_cases(events)
        self.assertIsInstance(controls['text_status']['http']['status'], str)
        self.assertEqual(controls['empty_headers']['http']['response_headers'], [])
        self.assertNotIn('timestamp', controls['absent_time'])
        self.assertNotIn('undocumented_field', events['1']['http'])
        self.assertIsInstance(events['1']['http']['status'], int)

    def test_unreviewed_capture_is_rejected(self):
        with patch.object(report, 'read_artifact', return_value=b'{}'), self.assertRaises(report.EvidenceError):
            report.packets()

    def test_missing_kit_diagnosed_without_running_a_tool(self):
        with self.assertRaisesRegex(report.EvidenceError, 'web native kit'):
            report.review(Path('/unused'), None)
