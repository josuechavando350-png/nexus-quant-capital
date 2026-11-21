"""Verifier controls; native executions are recorded separately in static-native evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import product_static_native as native
from superhunter.product_reasoning import EvidenceError


class StaticNativeTests(unittest.TestCase):
    def setUp(self):
        self.pins, self.cases = native.inputs()

    def report(self, rows=''):
        return ('<results version="2"><cppcheck version="2.23 dev"/><errors>' + rows +
                '</errors></results>').encode()

    def test_clean_native_report_is_accepted_only_for_clean_control(self):
        result = native.cppcheck_result(self.report(), 'clean.c', self.cases['c']['clean.c'])
        self.assertEqual(result['diagnostics'], [])
        for name in ('null.c', 'bounds.c'):
            with self.subTest(case=name), self.assertRaises(EvidenceError):
                native.cppcheck_result(self.report(), name, self.cases['c'][name])

    def test_positive_locations_and_cwe_are_validated(self):
        row = '<error id="nullPointer" severity="error" cwe="476"><location file="null.c" line="3" column="13"/></error>'
        self.assertEqual(native.cppcheck_result(self.report(row), 'null.c', self.cases['c']['null.c'])['diagnostics'][0]['cwe'], 476)
        for changed in (row.replace('476', '0'), row.replace('line="3"', 'line="2"'),
                        row.replace('file="null.c"', 'file="clean.c"'), row + row,
                        row.replace('severity="error"', 'severity="warning"')):
            with self.subTest(row=changed), self.assertRaises(EvidenceError):
                native.cppcheck_result(self.report(changed), 'null.c', self.cases['c']['null.c'])

    def test_wrong_version_or_missing_xml_sections_cannot_succeed(self):
        for raw in (self.report().replace(b'2.23 dev', b'0.0'), b'<results/>',
                    b'<!DOCTYPE results><results/>', b'<broken'):
            with self.subTest(report=raw), self.assertRaises(EvidenceError):
                native.cppcheck_result(raw, 'clean.c', self.cases['c']['clean.c'])

    def test_relative_targets_use_signed_displacement(self):
        self.assertEqual(native.relative_target(bytes.fromhex('e9fbffffff'), 0x1000), 0x1000)
        self.assertEqual(native.relative_target(bytes.fromhex('74fe'), 0x1000), 0x1000)
        self.assertEqual(native.relative_target(bytes.fromhex('0f84faffffff'), 0x1000), 0x1000)
        self.assertIsNone(native.relative_target(b'\x90', 0x1000))

    def decoder(self):
        return {'api_version': [6, 0], 'input_bytes': 4, 'decoded_bytes': 4, 'instructions': [
            {'address': 4096, 'size': 2, 'bytes': '7401', 'mnemonic': 'je', 'direct_target': 4099},
            {'address': 4098, 'size': 2, 'bytes': 'ffc0', 'mnemonic': 'inc', 'direct_target': None}]}

    def test_internal_branch_to_instruction_middle_is_reported(self):
        result = native.decoder_result(self.decoder(), bytes.fromhex('7401ffc0'), 4096)
        self.assertEqual(result['misaligned_internal_targets'], [4099])

    def test_substituted_instruction_or_branch_is_rejected(self):
        changes = [('bytes', '7402'), ('direct_target', 4098), ('address', 4097), ('size', 3)]
        for field, value in changes:
            report = self.decoder()
            report['instructions'][0][field] = value
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                native.decoder_result(report, bytes.fromhex('7401ffc0'), 4096)

    def test_truncated_instruction_bytes_are_retained_explicitly(self):
        report = {'api_version': [6, 0], 'input_bytes': 3, 'decoded_bytes': 1, 'instructions': [
            {'address': 4096, 'size': 1, 'bytes': '90', 'mnemonic': 'nop', 'direct_target': None}]}
        result = native.decoder_result(report, bytes.fromhex('90e901'), 4096)
        self.assertEqual(result['undecoded_suffix'], 'e901')
        report['decoded_bytes'] = 3
        with self.assertRaises(EvidenceError):
            native.decoder_result(report, bytes.fromhex('90e901'), 4096)

    def test_objdump_parsing_keeps_instruction_bytes_and_offsets(self):
        text = '\n00001000 <.data>:\n  1000:\t74 01                \tje 0x1003\n  1002:\tff c0                \tinc eax\n'
        self.assertEqual(native.objdump_spans(text), [(4096, '7401'), (4098, 'ffc0')])

    def test_image_mapping_rejects_overlap_and_file_overrun(self):
        raw = bytes(range(16))
        self.assertEqual(native.image_bytes(raw, [(4096, 0, 16)], 4098, 3), bytes([2, 3, 4]))
        for spans in ([], [(4096, 0, 2)], [(4096, 0, 16), (4096, 0, 16)]):
            with self.subTest(spans=spans), self.assertRaises(EvidenceError):
                native.image_bytes(raw, spans, 4098, 3)
        with self.assertRaises(EvidenceError):
            native.executable_spans(b'not an ELF')

    def test_pin_substitution_is_rejected_before_tool_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'producer pins'):
                native.run(Path('/unused'))
        execute.assert_not_called()

    def test_modified_tool_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            # Pin file order starts with cppcheck; a mismatching binary never runs.
            (kit/'cppcheck').write_bytes(b'not the compiled scanner')
            with patch.object(native.subprocess, 'run') as execute:
                with self.assertRaisesRegex(EvidenceError, 'release digest mismatch'):
                    native.run(kit)
            execute.assert_not_called()
