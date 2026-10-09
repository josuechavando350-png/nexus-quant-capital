import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import resume


class PlanChecks(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent / 'resume-plan.json').read_bytes())

    def test_actual_missing_ranges_are_unique_and_conserved(self):
        numbers = resume.plan_blocks(self.plan)
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(len(numbers), 209866)
        self.assertEqual(numbers[0], 25884916)
        self.assertEqual(numbers[-1], 26095351)
        self.assertNotIn(25885016, numbers)

    def test_repeated_range_rejected(self):
        self.plan['missing_ranges'].insert(1, self.plan['missing_ranges'][0])
        with self.assertRaisesRegex(ValueError, 'overlap'):
            resume.plan_blocks(self.plan)

    def test_missing_range_rejected(self):
        self.plan['missing_ranges'].pop()
        with self.assertRaisesRegex(ValueError, 'conservation'):
            resume.plan_blocks(self.plan)

    def test_broadened_endpoint_rejected(self):
        self.plan['endpoint'] = 'https://other.invalid'
        with self.assertRaisesRegex(ValueError, 'scope/rate'):
            resume.plan_blocks(self.plan)

    def test_raised_request_rate_rejected(self):
        self.plan['interval_seconds'] = 0.125
        with self.assertRaisesRegex(ValueError, 'scope/rate'):
            resume.plan_blocks(self.plan)

    def test_parallel_workers_rejected(self):
        self.plan['workers'] = 8
        with self.assertRaisesRegex(ValueError, 'scope/rate'):
            resume.plan_blocks(self.plan)

    def test_boolean_block_rejected(self):
        self.plan['missing_ranges'][0][0] = True
        with self.assertRaisesRegex(ValueError, 'range shape'):
            resume.plan_blocks(self.plan)

    def test_retry_after_is_enforced(self):
        with self.assertRaisesRegex(ValueError, 'Retry-After'):
            resume.retry_after_elapsed(self.plan, datetime(2026, 10, 9, 22, 44, 15, tzinfo=timezone.utc))
        resume.retry_after_elapsed(self.plan, datetime(2026, 10, 9, 22, 45, 15, tzinfo=timezone.utc))

    def exercise_controller(self, fail_second_price_batch):
        ticks, starts = [0.0], []
        class FakeAcquisition:
            def __init__(self, out):
                self.http_requests = self.calls = 0
                self.price_batches = 0
            def request(self, payload, stream):
                starts.append(ticks[0])
                self.http_requests += 1
                self.calls += len(payload) if isinstance(payload, list) else 1
                if isinstance(payload, list):
                    self.price_batches += 1
                    if fail_second_price_batch and self.price_batches == 2:
                        stream.write(b'{"fixture_http_status":429}\n')
                        raise ValueError('fixture HTTP Error 429: Too Many Requests')
                    price = '0x' + ''.join(f'{v:064x}' for v in [32, 67] + [1] * 67)
                    value = [{'jsonrpc': '2.0', 'id': q['id'], 'result': price} for q in payload]
                else:
                    i = payload['id']
                    value = {'jsonrpc': '2.0', 'id': i, 'result': '0x1' if i == 0 else {
                        'number': hex(resume.c.START if i == 1 else resume.c.END),
                        'hash': resume.c.START_HASH if i == 1 else resume.c.END_HASH}}
                raw = json.dumps(value).encode()
                stream.write(raw + b'\n')
                return raw
        def pause(delay):
            ticks[0] += delay
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(Path(__file__).parent / 'oracle-pilot-evidence.zip') as z:
                (root / 'assets.json').write_bytes(z.read('assets.json'))
            args = SimpleNamespace(plan=Path(__file__).parent / 'resume-plan.json', assets=root / 'assets.json',
                                   primary=root, out=root / 'out', producer_commit='a' * 40)
            with patch.object(resume, 'plan_blocks', return_value=list(range(resume.c.START, resume.c.START + 20))), \
                 patch.object(resume.c, 'block_bindings', return_value=['0x' + '01' * 32] * 20), \
                 patch.object(resume.c, 'Acquisition', FakeAcquisition):
                code = resume.execute(args, clock=lambda: ticks[0], pause=pause)
            report = json.loads((args.out / 'acquisition.json').read_bytes())
        self.assertEqual(len(starts), 5)
        self.assertTrue(all(b - a >= 1.1 - 1e-9 for a, b in zip(starts, starts[1:])))
        return code, report

    def test_controller_spaces_requests_and_conserves_completed_blocks(self):
        code, report = self.exercise_controller(False)
        self.assertEqual(code, 0)
        self.assertEqual(report['observed_blocks'], 20)
        self.assertEqual(report['attempted_rpc_calls'], 23)
        self.assertEqual(report['status'], 'COMPLETE_REQUESTED_MISSING_BLOCKS')

    def test_controller_stops_on_429_and_preserves_prior_batch(self):
        code, report = self.exercise_controller(True)
        self.assertEqual(code, 1)
        self.assertEqual(report['observed_blocks'], 10)
        self.assertEqual(report['status'], 'STOPPED_INCOMPLETE')
        self.assertFalse(report['completed_files'][0]['complete'])
        self.assertIn('429', report['failure']['message'])


if __name__ == '__main__':
    unittest.main()
