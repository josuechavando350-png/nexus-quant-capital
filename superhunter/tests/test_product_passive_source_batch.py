import tempfile
import unittest
from pathlib import Path

from superhunter import product_passive_source_batch as batch
from superhunter.safe_io import read_artifact, strict_json


class PassiveSourceBatchTests(unittest.TestCase):
    def test_fresh_run_reproduces_published_outputs(self):
        expected = strict_json(read_artifact(batch.ROOT, 'superhunter/product_supply/passive-source-batch-receipt.json'))
        self.assertEqual(batch.review(Path('.')), expected)
        self.assertEqual(len({r['combined_report_sha256'] for r in expected.values()}), 1)
        self.assertEqual(sorted(r['role'] for r in expected.values()), ['execution', 'execution', 'reference'])

    def test_upstream_notices_and_original_excerpts_are_bound(self):
        origins = batch.checked_origins()
        self.assertEqual([r['id'] for r in origins], [1, 10, 169])
        for row in origins:
            self.assertEqual(len(row['revision']), 40)
            self.assertTrue(row['spans'])

    def test_location_requires_a_real_file_and_exact_line_witness(self):
        valid = {'file': 'test.py', 'start_line': 1, 'snippet': 'hello'}
        records = [valid, dict(valid, file='/absent'), dict(valid, file='../unsafe'),
                   dict(valid, start_line=True), dict(valid, end_line=2),
                   dict(valid, snippet='bye'), dict(valid, file='missing.py')]
        accepted, invalid, unbound = batch.bound_locations(records, {'test.py': b'hello\nworld\n'})
        self.assertEqual((invalid, unbound), (3, 3))
        self.assertEqual(accepted, [{'uri': 'test.py', 'line': 1, 'snippet': 'hello'}])

    def test_duplicate_and_unknown_severity_conventions_are_rejected(self):
        raw = read_artifact(batch.ROOT, batch.DIRECTORY + '/dalfox-severity.txt')
        self.assertEqual(batch.severity_map(raw)['critical'], 'error')
        for altered in (raw.replace(b'"high" | "critical"', b'"high" | "high"'),
                        raw.replace(b'"note"', b'"warning-only"'),
                        raw.replace(b'"info"', b'"typo"')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                batch.severity_map(altered)

    def test_unknown_or_composite_constructor_rejected(self):
        for src in (b'def sha(raw): return run(raw)',
                    b'def sha(raw): return hashlib.md5(raw + b"x").hexdigest()',
                    b'def sha(raw):\n print(raw)\n return hashlib.md5(raw).hexdigest()'):
            with self.subTest(src=src), self.assertRaises(ValueError):
                batch.digest_source(src)

    def test_sampling_estimate_extremes(self):
        for n, c, num in [(10, 0, 0), (10, 10, 1), (1, 1, 1)]:
            for row in batch.sampled_rejection(n, c):
                self.assertEqual((row['numerator'], row['denominator']), (num, 1))
        for n, c in ((0, 0), (2, 3), (2, -1)):
            with self.assertRaises(ValueError):
                batch.sampled_rejection(n, c)

    def test_empty_checkout_cannot_authenticate_the_excerpts(self):
        from subprocess import SubprocessError
        with tempfile.TemporaryDirectory() as root, self.assertRaises((OSError, ValueError, SubprocessError)):
            batch.compare_originals(Path(root))
