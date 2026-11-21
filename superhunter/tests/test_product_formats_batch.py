"""Check object bounds, completeness and the same-count/different-identity negative."""
import json
import unittest

from superhunter import product_formats_batch as batch


class ProofObjects(unittest.TestCase):
    def test_real_cases_and_linked_receipts(self):
        rows = json.loads((batch.ROOT/'superhunter/product_supply/formats-batch.json').read_bytes())
        for name, row in rows.items():
            self.assertEqual(row['revision'], batch.PROJECTS[name][1])
        compiler = rows[batch.CAPSTONE]['result']
        layout = rows[batch.RADARE]['result']
        self.assertEqual(batch.sha(batch.canonical(layout)), compiler['radare2_sha256'])
        cases = compiler['cases']
        self.assertEqual(cases['original']['bound_labels'], ['nqc_0', 'nqc_1', 'nqc_2'])
        self.assertTrue(cases['original']['covers_reviewed_obligations'])
        self.assertFalse(cases['missing_obligation']['covers_reviewed_obligations'])
        self.assertFalse(cases['duplicate_label']['covers_reviewed_obligations'])
        self.assertEqual(cases['original']['assertion_calls'], cases['duplicate_label']['assertion_calls'])
        self.assertEqual(cases['original']['boundaries_sha256'], cases['duplicate_label']['boundaries_sha256'])
        self.assertNotEqual(layout['cases']['original']['object_sha256'], layout['cases']['duplicate_label']['object_sha256'])

    def test_current_nqc_claims_and_emitter(self):
        full = batch.c_program('cbmc', batch.claims())
        self.assertEqual(full.count('__CPROVER_assert('), 3)
        self.assertEqual(full.count('"nqc_2"'), 1)

    def test_bounds_and_unknown_format_fail_closed(self):
        with self.assertRaises(batch.EvidenceError):
            batch.read_text(b'not an ELF object', {})
        with self.assertRaises(batch.EvidenceError):
            batch.record(bytes(12), [('a', 8), ('b', 8)])
        with self.assertRaises(batch.EvidenceError):
            batch.slice_section(bytes(12), {'offset': 10, 'size': 3})
        with self.assertRaises(batch.EvidenceError):
            batch.schema_records(b'pf.elf_shdr unsupported offset\n')

    def test_instruction_or_relocation_omission_is_rejected(self):
        with self.assertRaises(batch.EvidenceError):
            batch.check_calls(bytes(5), b'', '1 5 1', '', '', 3)
        with self.assertRaises(batch.EvidenceError):
            batch.check_calls(bytes(5), b'', '0 5 1', ' 0:\te8 00 00 00 00    \tcall 5', '', 3)

    def test_native_source_subset_excludes_nonrequired_families(self):
        self.assertTrue(batch.cap_file('arch/X86/X86Mapping.c'))
        self.assertTrue(batch.cap_file('arch/ARM/ARMModule.h'))
        self.assertFalse(batch.cap_file('arch/ARM/ARMModule.c'))
        self.assertFalse(batch.cap_file('tests/integration/app.c'))
