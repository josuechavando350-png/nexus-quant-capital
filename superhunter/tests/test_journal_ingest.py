"""Journal JSONL parsing and independent verification on real bytes, never fabricated PASS."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import journal_ingest as j
from superhunter.safe_io import canonical, strict_json


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'captured.jsonl'
        self.bundle = self.root / 'bundle'
        self.secret = 'PRIVATE-MESSAGE-DO-NOT-PUBLISH'
        self.rows = [
            {'__REALTIME_TIMESTAMP': '1793984400123456', '__CURSOR': 's=cursor-1',
             '_TRANSPORT': 'stdout', '_PID': '700', 'MESSAGE': self.secret},
            {'__REALTIME_TIMESTAMP': '1793984402123456', '__CURSOR': 's=cursor-2',
             '_TRANSPORT': 'kernel', 'MESSAGE': 'second record'},
        ]
        self._write()

    def _write(self):
        self.source.write_bytes(b''.join(json.dumps(x).encode('utf-8') + b'\n' for x in self.rows))

    def _read(self, name):
        return strict_json((self.bundle / name).read_bytes())

    def _reseal(self, name, raw):
        (self.bundle / name).write_bytes(raw)
        marker = self._read('COMPLETE.json')
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (self.bundle / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_line_offsets_and_original_bytes(self):
        original = self.source.read_bytes()
        result = j.ingest(self.source, 'lab-host', 500, self.bundle)
        self.assertEqual(result['records'], 2)
        self.assertEqual((self.bundle / 'journal.jsonl').read_bytes(), original)
        self.assertEqual(j.verify(self.bundle), result)
        proof = self._read('receipt.json')['lines']
        self.assertEqual(proof[0]['offset'], 0)
        self.assertEqual(proof[1]['offset'], proof[0]['length'])
        self.assertEqual(sum(x['length'] for x in proof), len(original))
        self.assertEqual(hashlib.sha256(original[:proof[0]['length']]).hexdigest(), proof[0]['sha256'])
        self.assertEqual(self._read('timeline.json')['event_count'], 2)
        self.assertNotIn(self.secret, (self.bundle/'REVIEW.md').read_text())
        self.assertNotIn(self.secret, (self.bundle/'normalized.json').read_text())
        self.assertNotIn(self.secret, (self.bundle/'timeline.json').read_text())

    def test_timestamp_microseconds_not_float_rounded(self):
        result, offsets = j.normalized(self.source.read_bytes(), j.metadata('host', 1))
        self.assertEqual(result['events'][0]['timestamp'], '2026-11-06T17:00:00.123456+00:00')
        self.assertEqual(result['events'][1]['timestamp'], '2026-11-06T17:00:02.123456+00:00')
        self.assertEqual(len(offsets), 2)

    def test_sequences_follow_file_order_not_realtime_order(self):
        self.rows[0]['__REALTIME_TIMESTAMP'], self.rows[1]['__REALTIME_TIMESTAMP'] = (
            self.rows[1]['__REALTIME_TIMESTAMP'], self.rows[0]['__REALTIME_TIMESTAMP'])
        self._write()
        r = j.ingest(self.source, 'host', 0, self.bundle)
        self.assertEqual(r['status'], 'DECLARED_CONSTRAINT_CONTRADICTION')
        self.assertTrue(self._read('timeline.json')['contradictions'])
        self.assertEqual(j.verify(self.bundle), r)

    def test_clock_overlap_is_inconclusive(self):
        r = j.ingest(self.source, 'host', 5000, self.bundle)
        self.assertEqual(r['status'], 'INCONCLUSIVE_ORDER')
        self.assertEqual(j.verify(self.bundle)['status'], 'INCONCLUSIVE_ORDER')

    def test_cli_roundtrip_separate_processes(self):
        base = [sys.executable, '-m', 'superhunter']
        proc = subprocess.run(base + ['ingest-journal', '--input', str(self.source),
                    '--source-id', 'host', '--clock-uncertainty-ms', '0', '--out', str(self.bundle)],
                    capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verify = subprocess.run(base + ['verify-journal', '--bundle', str(self.bundle)],
                                capture_output=True, text=True)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertEqual(json.loads(proc.stdout), json.loads(verify.stdout))
        self.assertNotIn(self.secret, proc.stdout + proc.stderr + verify.stdout + verify.stderr)
        self.assertFalse(json.loads(proc.stdout)['source_authenticated'])
        self.assertFalse(json.loads(proc.stdout)['incident_confirmed'])

    def test_resealed_false_timeline_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        changed = self._read('timeline.json')
        changed['event_count'] = 999
        self._reseal('timeline.json', canonical(changed))
        with self.assertRaisesRegex(j.JournalError, 'TIMELINE_CHANGED'):
            j.verify(self.bundle)

    def test_resealed_line_receipts_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        changed = self._read('receipt.json')
        changed['lines'][1]['offset'] = 0
        self._reseal('receipt.json', canonical(changed))
        with self.assertRaisesRegex(j.JournalError, 'LINE_OFFSETS_CHANGED'):
            j.verify(self.bundle)

    def test_resealed_normalization_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        changed = self._read('normalized.json')
        changed['events'][0]['kind'] = 'network'
        self._reseal('normalized.json', canonical(changed))
        with self.assertRaisesRegex(j.JournalError, 'NORMALIZATION_CHANGED'):
            j.verify(self.bundle)

    def test_resealed_report_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        self._reseal('REVIEW.md', b'ALL INCIDENTS CONFIRMED')
        with self.assertRaisesRegex(j.JournalError, 'REPORT_CHANGED'):
            j.verify(self.bundle)

    def test_altered_source_without_resigning_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        (self.bundle/'journal.jsonl').write_bytes(b'{}\n')
        with self.assertRaisesRegex(j.JournalError, 'ARTIFACT_CHANGED'):
            j.verify(self.bundle)

    def test_resealed_original_change_not_verifiable(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        s = (self.bundle/'journal.jsonl').read_bytes().replace(b'cursor-1', b'cursor-X')
        self._reseal('journal.jsonl', s)
        with self.assertRaisesRegex(j.JournalError, 'SOURCE_CHANGED'):
            j.verify(self.bundle)

    def test_duplicate_cursor_rejected(self):
        self.rows[1]['__CURSOR'] = 's=cursor-1'
        self._write()
        with self.assertRaisesRegex(j.JournalError, 'DUPLICATE_JOURNAL_CURSOR'):
            j.ingest(self.source, 'host', 0, self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_duplicates_and_invalid_timestamps_rejected(self):
        for ts in [123, True, '1e6', '-1', '01', '', '253402300800000000', '999999999999999999999999']:
            with self.subTest(timestamp=ts):
                data = deepcopy(self.rows)
                data[0]['__REALTIME_TIMESTAMP'] = ts
                raw = b''.join(json.dumps(x).encode() + b'\n' for x in data)
                with self.assertRaises(j.JournalError):
                    j.normalized(raw, j.metadata('host', 0))
        with self.assertRaisesRegex(j.JournalError, 'JOURNAL_JSON_INVALID'):
            j.normalized(b'{"__REALTIME_TIMESTAMP":"0","__REALTIME_TIMESTAMP":"1"}\n',
                         j.metadata('host', 0))

    def test_invalid_metadata_and_boolean_as_int_rejected(self):
        with self.assertRaises(j.JournalError):
            j.metadata('host', True)
        with self.assertRaises(ValueError):
            j.metadata('INVALID SOURCE', 1)
        with self.assertRaisesRegex(j.JournalError, 'METADATA_SCHEMA'):
            j.normalized(self.source.read_bytes(), {'schema_version': 1, 'source_id': 'host'})
        with self.assertRaisesRegex(j.JournalError, 'METADATA_SCHEMA'):
            j.normalized(self.source.read_bytes(), {'schema_version': True, 'source_id': 'host', 'clock_uncertainty_ms': 0})

    def test_raw_export_contains_no_nul_or_carriage_return(self):
        for raw in (b'{}\r\n', b'{"__REALTIME_TIMESTAMP":"0"}\x00\n', b'\n', b'NOT JSON\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(j.JournalError):
                    j.normalized(raw, j.metadata('host', 0))

    def test_oversize_line_and_record_limit(self):
        huge = b'{"__REALTIME_TIMESTAMP":"1","EXTRA":"' + b'a'*33000 + b'"}\n'
        with self.assertRaisesRegex(j.JournalError, 'JOURNAL_LINE_INVALID'):
            j.normalized(huge, j.metadata('host', 0))
        good = b'{"__REALTIME_TIMESTAMP":"0"}\n'
        with self.assertRaisesRegex(j.JournalError, 'JOURNAL_EVENT_LIMIT'):
            j.normalized(good*513, j.metadata('host', 0))

    def test_symlinked_input_rejected(self):
        link = self.root/'link.jsonl'
        link.symlink_to(self.source)
        with self.assertRaises((OSError, ValueError)):
            j.ingest(link, 'host', 0, self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_private_cli_error_does_not_echo_paths(self):
        special = self.root/'PRIVATE-PATH-DO-NOT-ECHO.jsonl'
        p = subprocess.run([sys.executable, '-m', 'superhunter', 'ingest-journal',
                            '--input', str(special), '--source-id', 'host',
                            '--clock-uncertainty-ms', '0', '--out', str(self.bundle)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn('PRIVATE-PATH-DO-NOT-ECHO', p.stdout+p.stderr)

    def test_extra_bundle_files_rejected(self):
        j.ingest(self.source, 'host', 0, self.bundle)
        (self.bundle/'injected').write_bytes(b'x')
        with self.assertRaisesRegex(j.JournalError, 'BUNDLE_FILES'):
            j.verify(self.bundle)


if __name__ == '__main__':
    unittest.main()
