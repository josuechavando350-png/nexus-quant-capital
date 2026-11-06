"""Owned synthetic Geth-format trace + real journal JSONL parser integration.

These are controlled parser tests, NOT observed blockchain executions or
blind discovery benchmarks. Tests assert both exact byte binding and limits.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_forensic_binding as f
from superhunter import journal_ingest as j
from superhunter import evm_opcode_trace as op
from superhunter.safe_io import canonical, strict_json


def trace_fixture() -> bytes:
    # Valid Geth-formatted fixture: PUSH1 05; JUMPI -> 5; JUMPDEST; STOP.
    positions = [0, 2, 5, 6]
    names = ['PUSH1', 'JUMPI', 'JUMPDEST', 'STOP']
    ops = [96, 87, 91, 0]
    lines = []
    for i, (pc, name, opcode) in enumerate(zip(positions, names, ops)):
        lines.append({'pc': pc, 'op': opcode, 'gas': hex(1000 - 10*i),
                      'gasCost': '0x3', 'memSize': 0, 'stack': None,
                      'depth': 1, 'refund': 0, 'opName': name})
    lines.append({'output': '', 'gasUsed': '0x20'})
    return b''.join(json.dumps(row).encode() + b'\n' for row in lines)


class EVMForensicBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.journal_file = self.root / 'owned.jsonl'
        self.trace_file = self.root / 'owned.trace.jsonl'
        self.context_file = self.root / 'context.json'
        self.journal_bundle = self.root / 'journal-bundle'
        self.out = self.root / 'evm-forensic'
        self.secret = 'LAB-PRIVATE-PASSWORD-DO-NOT-PRINT'
        self.trace_file.write_bytes(trace_fixture())
        self.context = {
            'schema_version': 1, 'profile': f.PROFILE,
            'bytecode_hex': '60055760005b00',
            'gas_budget': op.evm.GAS,
            'observed': {'return_data': '0x', 'error': None},
            'journal_event_id': ''}
        self._journal()

    def _journal(self, *, anchor=None, message=None, extra=None):
        anchor = f.sha(self.trace_file.read_bytes()) if anchor is None else anchor
        rows = [
            {'__REALTIME_TIMESTAMP': '1793984400123456', '__CURSOR': 'lab-0',
             'MESSAGE': self.secret if message is None else message,
             f.ANCHOR_FIELD: anchor},
            {'__REALTIME_TIMESTAMP': '1793984401123456', '__CURSOR': 'lab-1',
             'MESSAGE': 'independent background event'},
        ]
        if extra is not None: rows[0].update(extra)
        self.journal_file.write_bytes(b''.join(json.dumps(row).encode() + b'\n' for row in rows))
        if self.journal_bundle.exists():
            import shutil
            shutil.rmtree(self.journal_bundle)
        j.ingest(self.journal_file, 'owned-lab', 10, self.journal_bundle)
        normalized = strict_json((self.journal_bundle / 'normalized.json').read_bytes())
        self.context['journal_event_id'] = normalized['events'][0]['event_id']
        self.context_file.write_bytes(canonical(self.context))

    def _reseal(self, name, raw):
        target = self.out / name
        target.write_bytes(raw)
        marker = strict_json((self.out / 'COMPLETE.json').read_bytes())
        marker['sha256'][name] = f.sha(raw)
        (self.out / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_cli_separate_processes(self):
        args = [sys.executable, '-B', '-m', 'superhunter']
        a = subprocess.run(args + ['review-evm-forensic',
                                    '--journal-bundle', str(self.journal_bundle),
                                    '--trace', str(self.trace_file), '--context', str(self.context_file),
                                    '--out', str(self.out)], capture_output=True, text=True)
        self.assertEqual(a.returncode, 0, a.stderr)
        b = subprocess.run(args + ['verify-evm-forensic', '--bundle', str(self.out)],
                           capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(json.loads(a.stdout), json.loads(b.stdout))
        self.assertEqual(json.loads(b.stdout)['observed_steps'], 4)
        self.assertFalse(json.loads(b.stdout)['vulnerability_confirmed'])
        self.assertNotIn(self.secret, a.stdout + a.stderr + b.stdout + b.stderr)

    def test_raw_byte_link_record_hash_and_pc_evidence(self):
        r = f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        self.assertEqual(r, f.verify(self.out))
        value = strict_json((self.out / 'finding.json').read_bytes())
        self.assertEqual(value['journal']['record_offset'], 0)
        self.assertEqual(value['evm']['instruction_sites'], [0, 2, 5, 6])
        self.assertEqual(value['evm']['conditional_edge_set'], ['2:taken'])
        self.assertEqual(value['raw']['trace_sha256'], f.sha(trace_fixture()))
        self.assertFalse(value['claims']['evm_execution_replayed_here'])
        self.assertFalse(value['claims']['cross_source_causation_proved'])
        self.assertFalse(value['claims']['journal_producer_authenticated'])
        self.assertEqual((self.out / 'journal.jsonl').read_bytes(), self.journal_file.read_bytes())
        self.assertEqual((self.out / 'trace.jsonl').read_bytes(), trace_fixture())
        self.assertNotIn(self.secret, (self.out/'finding.json').read_text())
        self.assertNotIn(self.secret, (self.out/'REVIEW.md').read_text())
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)

    def test_anchor_mismatch_rejected(self):
        self._journal(anchor='0' * 64)
        with self.assertRaisesRegex(f.BindingError, 'TRACE_ANCHOR_MISMATCH'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        self.assertFalse(self.out.exists())

    def test_missing_anchor_rejected(self):
        self._journal(anchor='NOT_SHA256')
        with self.assertRaisesRegex(f.BindingError, 'TRACE_ANCHOR_REQUIRED'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_wrong_log_record_id_rejected(self):
        self.context['journal_event_id'] = 'not-in-export'
        self.context_file.write_bytes(canonical(self.context))
        with self.assertRaisesRegex(f.BindingError, 'JOURNAL_EVENT_NOT_FOUND'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_invalid_trace_terminal_rejected(self):
        raw = self.trace_file.read_bytes().replace(b'"output": ""', b'"output": "ff"')
        self.trace_file.write_bytes(raw)
        self._journal()
        with self.assertRaisesRegex(f.BindingError, 'EVM_TRACE_STRUCTURALLY_INVALID'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_non_instruction_pc_rejected_even_when_anchor_matches(self):
        raw = self.trace_file.read_bytes().replace(b'"pc": 0', b'"pc": 1', 1)
        self.trace_file.write_bytes(raw)
        self._journal()
        with self.assertRaisesRegex(f.BindingError, 'EVM_TRACE_STRUCTURALLY_INVALID'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_forged_opcode_rejected_even_with_consistent_journal_anchor(self):
        raw = self.trace_file.read_bytes().replace(b'"op": 96', b'"op": 97', 1)
        self.trace_file.write_bytes(raw)
        self._journal()
        with self.assertRaisesRegex(f.BindingError, 'EVM_TRACE_STRUCTURALLY_INVALID'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_duplicate_trace_json_key_rejected(self):
        raw = self.trace_file.read_bytes().replace(b'"pc": 0', b'"pc": 0, "pc": 0', 1)
        self.trace_file.write_bytes(raw)
        self._journal()
        with self.assertRaisesRegex(f.BindingError, 'EVM_TRACE_STRUCTURALLY_INVALID'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_bool_budget_rejected(self):
        self.context['gas_budget'] = True
        self.context_file.write_bytes(canonical(self.context))
        with self.assertRaisesRegex(f.BindingError, 'GAS_BUDGET'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_extra_context_key_rejected(self):
        self.context['magic'] = 'ignore'
        self.context_file.write_bytes(canonical(self.context))
        with self.assertRaisesRegex(f.BindingError, 'CONTEXT_SCHEMA'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_context_relabeling_no_fake_execution_claim(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        obj = strict_json((self.out / 'finding.json').read_bytes())
        self.assertFalse(obj['claims']['evm_execution_replayed_here'])
        self.assertFalse(obj['claims']['execution_timestamp_authenticated'])
        self.assertFalse(obj['claims']['vulnerability_confirmed'])
        self.assertFalse(obj['claims']['incident_confirmed'])

    def test_resealed_false_result_rejected(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        obj = strict_json((self.out / 'finding.json').read_bytes())
        obj['claims']['vulnerability_confirmed'] = True
        raw = canonical(obj)
        self._reseal('finding.json', raw)
        # Reseal the inner receipt and outer marker; independent reconstruction
        # still rejects the forged positive.
        receipt = strict_json((self.out / 'receipt.json').read_bytes())
        receipt['finding_sha256'] = f.sha(raw)
        self._reseal('receipt.json', canonical(receipt))
        with self.assertRaisesRegex(f.BindingError, 'FINDING_REPLAY_MISMATCH'):
            f.verify(self.out)

    def test_journal_modified_after_review_rejected(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        raw = (self.out / 'journal.jsonl').read_bytes().replace(b'lab-0', b'lab-X')
        self._reseal('journal.jsonl', raw)
        with self.assertRaises(f.BindingError):
            f.verify(self.out)

    def test_trace_modified_after_review_rejected(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        raw = (self.out / 'trace.jsonl').read_bytes().replace(b'"gasCost": "0x3"',
                                                              b'"gasCost": "0x4"', 1)
        self._reseal('trace.jsonl', raw)
        with self.assertRaisesRegex(f.BindingError, 'TRACE_ANCHOR_MISMATCH'):
            f.verify(self.out)

    def test_source_bundle_tamper_and_reseal_rejected_before_creation(self):
        (self.journal_bundle / 'journal.jsonl').write_bytes(
            (self.journal_bundle / 'journal.jsonl').read_bytes().replace(b'lab-0', b'lab-X'))
        with self.assertRaisesRegex(f.BindingError, 'JOURNAL_BUNDLE_UNVERIFIED'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_no_overwrite_existing_case(self):
        self.out.mkdir()
        with self.assertRaisesRegex(f.BindingError, 'PRIVATE_NEW_OUTPUT_REQUIRED'):
            f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)

    def test_reject_symlink_and_extra_bundle_file(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        link = self.root / 'case-link'
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaisesRegex(f.BindingError, 'BUNDLE_DIRECTORY'):
            f.verify(link)
        (self.out / 'marker.txt').write_bytes(b'unauthorized')
        with self.assertRaisesRegex(f.BindingError, 'BUNDLE_MANIFEST_INVALID'):
            f.verify(self.out)

    def test_external_commitment_blocks_resealed_bundle(self):
        f.review(self.journal_bundle, self.trace_file, self.context_file, self.out)
        good = f.sha((self.out / 'COMPLETE.json').read_bytes())
        self.assertEqual(f.verify(self.out, good)['observed_steps'], 4)
        with self.assertRaisesRegex(f.BindingError, 'EXTERNAL_SHA_MISMATCH'):
            f.verify(self.out, 'f'*64)
        with self.assertRaisesRegex(f.BindingError, 'EXTERNAL_SHA_FORMAT'):
            f.verify(self.out, 'NOT_SHA')

    def test_private_trace_input_symlink_rejected(self):
        link = self.root / 'alias.trace.jsonl'
        link.symlink_to(self.trace_file)
        with self.assertRaises((ValueError, OSError)):
            f.review(self.journal_bundle, link, self.context_file, self.out)

    def test_cli_missing_private_path_no_echo(self):
        command = [sys.executable, '-B', '-m', 'superhunter', 'review-evm-forensic',
                   '--journal-bundle', str(self.journal_bundle), '--trace', str(self.root/'SECRET'),
                   '--context', str(self.context_file), '--out', str(self.out)]
        done = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertNotIn(str(self.root), done.stdout + done.stderr)

    def test_quality_registry_and_mandatory_regressions(self):
        from superhunter import quality
        self.assertIn('evm_forensic_binding', quality.COMPONENTS)
        self.assertIn('evm_opcode_trace', quality.COMPONENTS['evm_forensic_binding']['depends'])
        self.assertIn('test_evm_forensic_binding.EVMForensicBindingTests.test_resealed_false_result_rejected',
                      quality.REQUIRED_TESTS)


if __name__ == '__main__':
    unittest.main()
