"""Real offline normalized forensic timeline tests: no live targets or fabricated incident claims."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import forensic_timeline as ft
from superhunter.safe_io import canonical, strict_json


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'events.json'
        self.bundle = self.root / 'result'
        self.sample = {'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
                       'sources': [{'source_id': 'host-a', 'clock_uncertainty_ms': 0},
                                   {'source_id': 'service-b', 'clock_uncertainty_ms': 0}],
                       'events': [
                           {'event_id': 'a1', 'source_id': 'host-a', 'sequence': 1,
                            'timestamp': '2026-11-06T11:00:00-06:00', 'kind': 'process',
                            'parent_event_id': None, 'artifact_sha256': 'a'*64},
                           {'event_id': 'b1', 'source_id': 'service-b', 'sequence': 1,
                            'timestamp': '2026-11-06T17:00:02Z', 'kind': 'network',
                            'parent_event_id': 'a1', 'artifact_sha256': 'b'*64},
                           {'event_id': 'a2', 'source_id': 'host-a', 'sequence': 2,
                            'timestamp': '2026-11-06T17:00:04+00:00', 'kind': 'file',
                            'parent_event_id': 'b1', 'artifact_sha256': 'c'*64},
                       ]}
        self.input.write_text(json.dumps(self.sample, ensure_ascii=False, indent=2))

    def test_normalized_timeline_preserves_offset_and_declarations(self):
        value = ft.analyze(self.sample)
        self.assertEqual(value['status'], 'DECLARED_ORDER_CONSISTENT')
        self.assertEqual(value['source_count'], 2)
        self.assertEqual(value['event_count'], 3)
        self.assertEqual(value['declared_edges'], 3)
        self.assertEqual(value['timeline'][0]['timestamp_utc'], '2026-11-06T17:00:00+00:00')
        self.assertFalse(value['claims']['evidence_authenticated'])
        self.assertFalse(value['claims']['causation_proved'])
        self.assertFalse(value['claims']['raw_disk_ram_pcap_parsed'])

    def test_cycle_and_temporal_inversion_not_pass(self):
        data = deepcopy(self.sample)
        data['events'][0]['parent_event_id'] = 'a2'
        r = ft.analyze(data)
        self.assertEqual(r['status'], 'DECLARED_CONSTRAINT_CONTRADICTION')
        self.assertTrue(r['topologically_unresolved_nodes'])
        self.assertTrue(r['contradictions'])

    def test_overlapping_error_bounds_are_not_pass(self):
        data = deepcopy(self.sample)
        for src in data['sources']:
            src['clock_uncertainty_ms'] = 4000
        r = ft.analyze(data)
        self.assertEqual(r['status'], 'INCONCLUSIVE_ORDER')
        self.assertTrue(r['uncertain_edges'])

    def test_backward_declared_sequence_is_contradiction(self):
        data = deepcopy(self.sample)
        data['events'][2]['timestamp'] = '2026-11-06T16:59:00Z'
        r = ft.analyze(data)
        self.assertEqual(r['status'], 'DECLARED_CONSTRAINT_CONTRADICTION')
        self.assertTrue(any(x['relation'] == 'declared_source_sequence' for x in r['contradictions']))

    def test_duplicate_json_key_rejected(self):
        self.input.write_bytes(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            ft.review(self.input, self.bundle)

    def test_duplicate_event_and_source_rejected(self):
        data = deepcopy(self.sample)
        data['events'].append(deepcopy(data['events'][0]))
        with self.assertRaisesRegex(ft.TimelineError, 'DUPLICATE_EVENT'):
            ft.analyze(data)
        data = deepcopy(self.sample)
        data['sources'].append(deepcopy(data['sources'][0]))
        with self.assertRaisesRegex(ft.TimelineError, 'DUPLICATE_SOURCE'):
            ft.analyze(data)

    def test_duplicate_sequence_and_bool_rejected(self):
        data = deepcopy(self.sample)
        data['events'][2]['sequence'] = 1
        with self.assertRaisesRegex(ft.TimelineError, 'DUPLICATE_SOURCE_SEQUENCE'):
            ft.analyze(data)
        data = deepcopy(self.sample)
        data['events'][0]['sequence'] = True
        with self.assertRaisesRegex(ft.TimelineError, 'SEQUENCE_TYPE'):
            ft.analyze(data)

    def test_unregistered_parent_or_source_rejected(self):
        data = deepcopy(self.sample)
        data['events'][0]['source_id'] = 'missing'
        with self.assertRaisesRegex(ft.TimelineError, 'UNREGISTERED_SOURCE'):
            ft.analyze(data)
        data = deepcopy(self.sample)
        data['events'][1]['parent_event_id'] = 'missing'
        with self.assertRaisesRegex(ft.TimelineError, 'MISSING_PARENT'):
            ft.analyze(data)

    def test_unbounded_data_or_missing_timezone_rejected(self):
        data = deepcopy(self.sample)
        data['events'][0]['timestamp'] = '2026-11-06T17:00:00'
        with self.assertRaisesRegex(ft.TimelineError, 'TIMEZONE_REQUIRED'):
            ft.analyze(data)
        data = deepcopy(self.sample)
        data['sources'][0]['clock_uncertainty_ms'] = 2**80
        with self.assertRaisesRegex(ft.TimelineError, 'CLOCK_UNCERTAINTY'):
            ft.analyze(data)

    def test_non_string_kind_is_rejected_not_crashed(self):
        data = deepcopy(self.sample)
        data['events'][0]['kind'] = {}
        with self.assertRaisesRegex(ft.TimelineError, 'EVENT_KIND'):
            ft.analyze(data)

    def test_original_json_bytes_retained_and_verified(self):
        original = self.input.read_bytes()
        ft.review(self.input, self.bundle)
        self.assertEqual((self.bundle / 'input.json').read_bytes(), original)
        self.assertEqual(ft.verify(self.bundle)['status'], 'DECLARED_ORDER_CONSISTENT')
        self.assertEqual((self.bundle / 'receipt.json').read_bytes(), canonical(strict_json((self.bundle / 'receipt.json').read_bytes())))

    def test_resealed_false_result_rejected(self):
        ft.review(self.input, self.bundle)
        timeline = strict_json((self.bundle/'timeline.json').read_bytes())
        timeline['status'] = 'DECLARED_ORDER_CONSISTENT' # simulate a false alteration to a report after events change
        timeline['event_count'] = 987
        self._reseal('timeline.json', canonical(timeline))
        with self.assertRaisesRegex(ft.TimelineError, 'DERIVED_TIMELINE_MISMATCH'):
            ft.verify(self.bundle)

    def test_resealed_event_bytes_are_not_authenticated(self):
        ft.review(self.input, self.bundle)
        raw = (self.bundle / 'input.json').read_bytes().replace(b'"a1"', b'"z1"')
        self._reseal('input.json', raw)
        with self.assertRaises(ft.TimelineError):
            ft.verify(self.bundle)

    def test_missing_artifact_is_rejected(self):
        ft.review(self.input, self.bundle)
        (self.bundle / 'REVIEW.md').unlink()
        with self.assertRaisesRegex(ft.TimelineError, 'BUNDLE_FILE_SET'):
            ft.verify(self.bundle)

    def test_symlink_input_rejected(self):
        link = self.root / 'link.json'
        link.symlink_to(self.input)
        with self.assertRaises((ValueError, OSError)):
            ft.review(link, self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_cli_end_to_end_and_replay(self):
        cmd = [sys.executable, '-m', 'superhunter']
        first = subprocess.run(cmd + ['review-forensic-timeline', '--input', str(self.input),
                                      '--out', str(self.bundle)], capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertFalse(json.loads(first.stdout)['incident_confirmed'])
        second = subprocess.run(cmd + ['verify-forensic-timeline', '--bundle', str(self.bundle)],
                                capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))

    def test_cli_private_error_does_not_echo_path(self):
        special = self.root / 'secret-marker-alpha.json'
        result = subprocess.run([sys.executable, '-m', 'superhunter', 'review-forensic-timeline',
                                 '--input', str(special), '--out', str(self.bundle)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('secret-marker-alpha', result.stderr)

    def _reseal(self, name, raw):
        (self.bundle / name).write_bytes(raw)
        manifest = strict_json((self.bundle / 'COMPLETE.json').read_bytes())
        manifest['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (self.bundle / 'COMPLETE.json').write_bytes(canonical(manifest))


if __name__ == '__main__':
    unittest.main()
