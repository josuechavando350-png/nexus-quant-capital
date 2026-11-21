from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_infra_batch as batch
from superhunter.owned_compute_guard import rules
from superhunter.product_sources import git


class AbiChecks(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((batch.ROOT / 'superhunter/product_supply/infra_batch_abi.json').read_bytes())
        values = {k: v['result'] for k, v in self.rows.items()}
        self.tracer = values[batch.STRACE]
        self.tracee = values[batch.TRACEE]
        self.signatures = {name: [None] * self.tracer[name]['arity'] for name in batch.EXPECTED}
        for name, positions in values[batch.TETRAGON].items():
            for position, field in positions.items():
                self.signatures[name][int(position)] = field
        self.numbers = values[batch.GADGET]['numbers']
        self.reverse = dict(zip(sorted(self.numbers.values()), values[batch.GADGET]['decoded'], strict=True))

    def verify(self, policy):
        batch.verify(policy, self.tracer, self.tracee, self.signatures, self.numbers, self.reverse)

    def test_checked_policy(self):
        self.verify(rules())

    def test_changed_arity(self):
        self.tracer['write']['arity'] -= 1
        with self.assertRaisesRegex(batch.EvidenceError, 'count mismatch'):
            self.verify(rules())

    def test_disagreeing_field_names(self):
        self.signatures['read'][0] = 'buf'
        with self.assertRaisesRegex(batch.EvidenceError, 'differs across sources'):
            self.verify(rules())

    def test_out_of_bounds_position(self):
        policy = deepcopy(rules())
        next(row for row in policy if row['syscall'] == 'close')['comparisons'][0][0] = 4
        with self.assertRaisesRegex(batch.EvidenceError, 'outside'):
            self.verify(policy)

    def test_relaxed_descriptor(self):
        policy = deepcopy(rules())
        next(row for row in policy if row['syscall'] == 'read')['comparisons'] = []
        with self.assertRaisesRegex(batch.EvidenceError, 'declared intent'):
            self.verify(policy)

    def test_reversed_abi_disagrees(self):
        self.reverse[self.numbers['brk']] = 'read'
        with self.assertRaisesRegex(batch.EvidenceError, 'identity mismatch'):
            self.verify(rules())

    def test_source_changed_or_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            upstream = Path(temp)
            root = upstream / 'fixed'
            root.mkdir()
            git(root, 'init', '-q')
            source = root / 'abi.txt'
            source.write_bytes(b'selected data\n')
            git(root, 'add', 'abi.txt')
            git(root, '-c', 'user.name=NQC Test', '-c', 'user.email=local@invalid', 'commit', '-qm', 'fixed')
            pin = git(root, 'rev-parse', 'HEAD').decode().strip()
            with patch.dict(batch.SOURCES, {'test/fixture': ('fixed', pin, ('abi.txt',))}):
                self.assertEqual(batch.capture(upstream, 'test/fixture')[1]['revision'], pin)
                source.write_bytes(b'changed\n')
                with self.assertRaisesRegex(batch.EvidenceError, 'pinned Git tree'):
                    batch.capture(upstream, 'test/fixture')
                source.unlink()
                with self.assertRaises(FileNotFoundError):
                    batch.capture(upstream, 'test/fixture')
