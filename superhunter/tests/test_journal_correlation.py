"""Adversarial integration tests for cross-source journal correlation; owned local data."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from superhunter import journal_correlation as c
from superhunter import journal_ingest as j
from superhunter.safe_io import canonical, strict_json


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = []
        self.bundles = []
        self.hidden = 'LAB-PRIVATE-DO-NOT-LEAK'
        self.times = [1793984400123456, 1793984402123456,
                      1793984405123456, 1793984407123456]
        for src in range(2):
            log = self.root / f'lab{src}.jsonl'
            rows = [{'__REALTIME_TIMESTAMP': str(self.times[src * 2 + idx]),
                     '__CURSOR': f'cursor={src}-{idx}',
                     'MESSAGE': self.hidden + str(src)} for idx in range(2)]
            log.write_bytes(b''.join(json.dumps(x).encode() + b'\n' for x in rows))
            bundle = self.root / f'journal{src}'
            j.ingest(log, f'lab-{src}', 0, bundle)
            self.inputs.append(log)
            self.bundles.append(bundle)
        self.first = self._event(0, 0)
        self.first_last = self._event(0, 1)
        self.second = self._event(1, 0)
        self.second_last = self._event(1, 1)
        self.hyp = self.root / 'hypotheses.json'
        self.out = self.root / 'correlation'
        self._write_links([(self.first_last, self.second)])

    def _event(self, source, index):
        old = strict_json((self.bundles[source] / 'normalized.json').read_bytes())
        return f's{source:02d}-' + old['events'][index]['event_id']

    def _write_links(self, pairs):
        value = {'schema_version': 1, 'profile': c.PROFILE,
                 'hypotheses': [{'from_event_id': a, 'to_event_id': b} for a, b in pairs]}
        self.hyp.write_bytes(canonical(value))

    def _reseal(self, name, raw):
        (self.out/name).write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def _result(self):
        return strict_json((self.out/'case.json').read_bytes())

    def test_cli_two_source_replay(self):
        cmd = [sys.executable, '-m', 'superhunter']
        first = subprocess.run(cmd + ['correlate-journals',
                                       '--bundle', str(self.bundles[0]),
                                       '--bundle', str(self.bundles[1]),
                                       '--hypotheses', str(self.hyp), '--out', str(self.out)],
                               capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = subprocess.run(cmd + ['verify-journal-correlations',
                                        '--bundle', str(self.out)], capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(json.loads(first.stdout)['status'], 'TEMPORALLY_FEASIBLE_UNVERIFIED')
        self.assertFalse(json.loads(first.stdout)['causation_established'])
        self.assertNotIn(self.hidden, first.stdout + first.stderr + second.stdout + second.stderr)
        self.assertFalse(self._result()['claims']['source_authenticated'])

    def test_raw_bytes_offsets_digests_and_originals(self):
        c.correlate(self.bundles, self.hyp, self.out)
        report = self._result()
        self.assertEqual(report['source_count'], 2)
        self.assertEqual(report['event_count'], 4)
        self.assertEqual(len(report['event_proofs']), 4)
        for idx, original in enumerate(self.inputs):
            name, _ = c.source_names(idx)
            raw = (self.out / name).read_bytes()
            self.assertEqual(raw, original.read_bytes())
            rows = [p for p in report['event_proofs'] if p['source_index'] == idx]
            self.assertEqual(sum(x['length'] for x in rows), len(raw))
            for proof in rows:
                part = raw[proof['offset']:proof['offset'] + proof['length']]
                self.assertEqual(hashlib.sha256(part).hexdigest(), proof['sha256'])
        self.assertNotIn(self.hidden, (self.out/'case.json').read_text())
        self.assertNotIn(self.hidden, (self.out/'REVIEW.md').read_text())
        self.assertEqual(c.verify(self.out), c.result_summary(report))
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)

    def test_temporal_contradiction_and_cycle(self):
        self._write_links([(self.second, self.first_last)])
        c.correlate(self.bundles, self.hyp, self.out)
        report = self._result()
        self.assertEqual(report['status'], 'DECLARED_CONSTRAINT_CONTRADICTION')
        self.assertEqual(report['hypotheses'][0]['status'], 'TEMPORALLY_CONTRADICTED')
        self.assertEqual(c.verify(self.out)['status'], report['status'])

    def test_two_opposite_cross_source_hypotheses_cycle(self):
        self._write_links([(self.first, self.second), (self.second, self.first)])
        c.correlate(self.bundles, self.hyp, self.out)
        result = self._result()
        self.assertEqual(result['status'], 'DECLARED_CONSTRAINT_CONTRADICTION')
        self.assertTrue(result['unresolved_cycle_nodes'])
        self.assertEqual(len(result['hypotheses']), 2)
        self.assertEqual(c.verify(self.out)['status'], result['status'])

    def test_cross_source_overlapping_clocks_is_inconclusive(self):
        for idx in range(2):
            meta = strict_json((self.bundles[idx]/'metadata.json').read_bytes())
            # Build a fresh, valid source bundle rather than forging the old one.
            meta['clock_uncertainty_ms'] = 5000
            new = self.root / f'alt-journal-{idx}'
            j.ingest(self.inputs[idx], f'lab-{idx}', 5000, new)
            self.bundles[idx] = new
        self._write_links([(self.first_last, self.second)])
        c.correlate(self.bundles, self.hyp, self.out)
        r = self._result()
        self.assertEqual(r['status'], 'INCONCLUSIVE_ORDER')
        self.assertEqual(r['hypotheses'][0]['status'], 'TEMPORAL_ORDER_INCONCLUSIVE')
        self.assertEqual(c.verify(self.out)['status'], r['status'])

    def test_resealed_false_result_rejected(self):
        c.correlate(self.bundles, self.hyp, self.out)
        obj = self._result()
        obj['hypotheses'][0]['causation_established'] = True
        self._reseal('case.json', canonical(obj))
        with self.assertRaisesRegex(c.CorrelationError, 'CASE_RESULT_CHANGED'):
            c.verify(self.out)

    def test_false_status_and_new_manifest_rejected(self):
        c.correlate(self.bundles, self.hyp, self.out)
        obj = self._result()
        obj['status'] = 'ALL_INCIDENTS_CONFIRMED'
        self._reseal('case.json', canonical(obj))
        with self.assertRaisesRegex(c.CorrelationError, 'CASE_RESULT_CHANGED'):
            c.verify(self.out)

    def test_source_tamper_rejected_before_ingestion(self):
        raw = (self.bundles[0] / 'journal.jsonl').read_bytes()
        (self.bundles[0] / 'journal.jsonl').write_bytes(raw.replace(b'cursor=0-0', b'cursor=0-X'))
        with self.assertRaisesRegex(c.CorrelationError, 'UNVERIFIED_JOURNAL_SOURCE'):
            c.correlate(self.bundles, self.hyp, self.out)
        self.assertFalse(self.out.exists())

    def test_original_resealed_log_change_rejected_even_if_marker_updated(self):
        receipt = self.bundles[0]/'COMPLETE.json'
        original = (self.bundles[0]/'journal.jsonl').read_bytes()
        changed = original.replace(b'cursor=0-0', b'cursor=0-X')
        (self.bundles[0]/'journal.jsonl').write_bytes(changed)
        m = strict_json(receipt.read_bytes())
        m['sha256']['journal.jsonl'] = hashlib.sha256(changed).hexdigest()
        receipt.write_bytes(canonical(m))
        with self.assertRaisesRegex(c.CorrelationError, 'UNVERIFIED_JOURNAL_SOURCE'):
            c.correlate(self.bundles, self.hyp, self.out)

    def test_resealed_case_input_rejected(self):
        c.correlate(self.bundles, self.hyp, self.out)
        raw = (self.out / 'journal-00.jsonl').read_bytes()
        self._reseal('journal-00.jsonl', raw.replace(b'cursor=0-0', b'cursor=0-X'))
        with self.assertRaisesRegex(c.CorrelationError, 'CASE_RESULT_CHANGED'):
            c.verify(self.out)

    def test_external_commitment_requires_original_marker(self):
        c.correlate(self.bundles, self.hyp, self.out)
        good = hashlib.sha256((self.out / 'COMPLETE.json').read_bytes()).hexdigest()
        self.assertEqual(c.verify(self.out, good)['sources'], 2)
        with self.assertRaisesRegex(c.CorrelationError, 'EXTERNAL_COMMITMENT_MISMATCH'):
            c.verify(self.out, '0' * 64)
        with self.assertRaisesRegex(c.CorrelationError, 'EXPECTED_COMMITMENT_FORMAT'):
            c.verify(self.out, 'NOT_A_HASH')

    def test_extra_files_and_symlinked_case_are_rejected(self):
        c.correlate(self.bundles, self.hyp, self.out)
        (self.out/'BAD').write_bytes(b'x')
        with self.assertRaisesRegex(c.CorrelationError, 'BUNDLE_FILES'):
            c.verify(self.out)
        link = self.root/'alias'
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaisesRegex(c.CorrelationError, 'BUNDLE_DIRECTORY'):
            c.verify(link)

    def test_duplicate_source_id_rejected(self):
        fresh = self.root/'same-id'
        j.ingest(self.inputs[1], 'lab-0', 0, fresh)
        with self.assertRaisesRegex(c.CorrelationError, 'DUPLICATE_SOURCE_ID'):
            c.correlate([self.bundles[0], fresh], self.hyp, self.out)
        self.assertFalse(self.out.exists())

    def test_invalid_hypothesis_or_missing_ids_rejected(self):
        for pairs in [[(self.first, 'does-not-exist')],
                      [(self.first, self.first)],
                      [(self.first, self.first_last)],
                      [(self.first_last, self.second), (self.first_last, self.second)]]:
            with self.subTest(pairs=pairs):
                self._write_links(pairs)
                with self.assertRaises(c.CorrelationError):
                    c.correlate(self.bundles, self.hyp, self.out)
                self.assertFalse(self.out.exists())

    def test_missing_hypotheses_or_extra_fields_rejected(self):
        for obj in [
                {'schema_version': 1, 'profile': c.PROFILE, 'hypotheses': []},
                {'schema_version': 1, 'profile': c.PROFILE,
                 'hypotheses': [{'from_event_id': self.first_last,
                                 'to_event_id': self.second, 'proof': True}]},
                {'schema_version': True, 'profile': c.PROFILE, 'hypotheses': []},
                {'schema_version': 1, 'profile': c.PROFILE,
                 'hypotheses': [{'from_event_id': None, 'to_event_id': self.second}]}]:
            with self.subTest(obj=obj):
                self.hyp.write_bytes(canonical(obj))
                with self.assertRaises(c.CorrelationError):
                    c.correlate(self.bundles, self.hyp, self.out)
                self.assertFalse(self.out.exists())

    def test_bool_metadata_source_index_and_out_of_range_rejected(self):
        raw = self.inputs[0].read_bytes()
        meta = canonical({'schema_version': 1, 'source_id': 'lab-0',
                          'clock_uncertainty_ms': 0})
        with self.assertRaisesRegex(c.CorrelationError, 'SOURCE_COUNT'):
            c.calculate([raw], [meta], self.hyp.read_bytes())
        with self.assertRaisesRegex(c.CorrelationError, 'SOURCE_COUNT'):
            c.calculate([raw] * 9, [meta] * 9, self.hyp.read_bytes())
        with self.assertRaisesRegex(c.CorrelationError, 'INVALID_SOURCE_EVIDENCE'):
            c.calculate([raw, self.inputs[1].read_bytes()],
                        [canonical({'schema_version': 1, 'source_id': 'lab-0',
                                    'clock_uncertainty_ms': True}),
                         canonical({'schema_version': 1, 'source_id': 'lab-1',
                                    'clock_uncertainty_ms': 0})], self.hyp.read_bytes())

    def test_duplicate_json_keys_in_hypotheses_rejected(self):
        self.hyp.write_bytes(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(c.CorrelationError, 'HYPOTHESES_JSON_INVALID'):
            c.correlate(self.bundles, self.hyp, self.out)

    def test_input_symlink_rejected(self):
        link = self.root/'symlink-source'
        link.symlink_to(self.bundles[0], target_is_directory=True)
        with self.assertRaisesRegex(c.CorrelationError, 'UNVERIFIED_JOURNAL_SOURCE'):
            c.correlate([link, self.bundles[1]], self.hyp, self.out)
        self.assertFalse(self.out.exists())

    def test_cli_sanitizes_missing_private_paths(self):
        cli = subprocess.run([sys.executable, '-m', 'superhunter', 'correlate-journals',
                              '--bundle', str(self.bundles[0]),
                              '--bundle', str(self.root/'PRIVATE-MISSING-JOURNAL'),
                              '--hypotheses', str(self.hyp), '--out', str(self.out)],
                             capture_output=True, text=True)
        self.assertEqual(cli.returncode, 2)
        self.assertNotIn('PRIVATE-MISSING-JOURNAL', cli.stderr + cli.stdout)

    def test_historical_worker_partition_ids_remain_stable(self):
        from superhunter.quality_worker import partition_ids, test_ids
        from superhunter.quality import PARTITION_COUNT
        test_root = Path(__file__).resolve().parent
        suite = unittest.TestLoader().discover(str(test_root), pattern='test*.py')
        full = sorted(test_ids(suite))
        previous = [item for item in full if not item.startswith('test_journal_correlation.')]
        full_groups = partition_ids(full, PARTITION_COUNT)
        former = partition_ids(previous, PARTITION_COUNT)
        for index in range(PARTITION_COUNT):
            keep = sorted(item for item in full_groups[index]
                          if not item.startswith('test_journal_correlation.'))
            self.assertEqual(keep, former[index], f'partition {index} moved earlier tests')
        new = [item for item in full if item.startswith('test_journal_correlation.')]
        self.assertEqual(len(new), 21)
        self.assertEqual(sorted(item for item in full_groups[0]
                                if item.startswith('test_journal_correlation.')), new)

    def test_unsupported_fake_severity_is_never_reported(self):
        c.correlate(self.bundles, self.hyp, self.out)
        report = self._result()
        self.assertFalse(report['claims']['vulnerability_confirmed'])
        self.assertFalse(report['claims']['incident_confirmed'])
        self.assertFalse(report['claims']['causation_established'])
        self.assertNotIn('severity', report)
        self.assertEqual(report['hypotheses'][0]['status'], 'TEMPORALLY_FEASIBLE_UNPROVEN')


if __name__ == '__main__':
    unittest.main()
