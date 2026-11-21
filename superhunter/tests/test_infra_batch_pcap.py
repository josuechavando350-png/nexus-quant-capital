from copy import deepcopy
from pathlib import Path
import json
import struct
import unittest

from superhunter import product_infra_batch_pcap as captures
from superhunter.product_infra_batch import ROOT
from superhunter.product_review import sha
from superhunter.safe_io import canonical


class CaptureChecks(unittest.TestCase):
    def setUp(self):
        receipt = ROOT / 'superhunter/product_supply/infra_batch_captures.json'
        self.rows = json.loads(receipt.read_bytes())
        self.packets = {'dhcp': self.rows[captures.WIRESHARK]['result']['frames'],
                        'ntp': self.rows[captures.TCPDUMP]['result']['frames']}

    def test_six_events_match_stored_timeline(self):
        result = captures.timeline(self.packets)
        self.assertEqual(sha(canonical(result)), self.rows[captures.SCAPY]['timeline_sha256'])
        self.assertEqual((result['event_count'], result['declared_edges']), (6, 4))

    def test_opposite_order_detected(self):
        self.packets['ntp'].reverse()
        result = captures.timeline(self.packets)
        self.assertEqual(result['contradictions'], self.rows[captures.SCAPY]['reversed_order'])

    def test_does_not_discard_nanoseconds(self):
        self.packets['dhcp'][0]['epoch_ns'] += 1
        with self.assertRaisesRegex(captures.EvidenceError, 'submicrosecond'):
            captures.timeline(self.packets)

    def test_rejects_partial_pcap_headers(self):
        for data in [b'', b'\xd4\xc3\xb2\xa1']:
            with self.subTest(data=data), self.assertRaisesRegex(captures.EvidenceError, 'short PCAP header'):
                captures.classic(data)

    def test_rejects_bad_record_lengths_and_time(self):
        header = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
        cases = [(0, 0, 1, 5), (0, 0, 3, 3), (1, 1_000_000, 1, 1)]
        for record in cases:
            with self.subTest(record=record), self.assertRaisesRegex(captures.EvidenceError, 'invalid length/time'):
                captures.classic(header + struct.pack('<4I', *record) + b'a')

    def test_consumer_rejects_duplicate_capture_times_as_conclusive(self):
        self.packets['ntp'][1]['epoch_ns'] = self.packets['ntp'][0]['epoch_ns']
        result = captures.timeline(self.packets)
        self.assertEqual(result['status'], 'INCONCLUSIVE_ORDER')
        self.assertEqual(len(result['uncertain_edges']), 1)

    def test_bytes_are_bound_to_each_timeline_event(self):
        original = captures.timeline(self.packets)
        changed = deepcopy(self.packets)
        changed['ntp'][0]['frame_sha256'] = sha(b'altered record')
        result = captures.timeline(changed)
        self.assertNotEqual(sha(canonical(original)), sha(canonical(result)))
