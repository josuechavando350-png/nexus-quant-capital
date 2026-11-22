import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from superhunter import product_evm_standards_batch as subject
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import sha
from superhunter.safe_io import canonical
from superhunter.tools.rebuild_fixed_opcode_oracle import instruction_map, rebuild


class LayoutControls(unittest.TestCase):
    def setUp(self):
        self.code = bytes.fromhex('605b5000')
        self.js = [[0, 'PUSH1', 1, 0, 1], [2, 'POP', 0, 1, -1], [3, 'STOP', 0, 0, 0]]
        self.rust = [(0, 'PUSH1', 1, 0, 1), (2, 'POP', 0, 1, 0), (3, 'STOP', 0, 0, 0)]
        self.names = {0x60: 'PUSH1', 0x50: 'POP', 0: 'STOP'}
        self.rules = {op: (name, None) for op, name in self.names.items()}
        self.oracle = sha(canonical(instruction_map('PUSH1 0x5b POP STOP', self.code)))

    def consume(self):
        return subject.views(self.code, self.js, self.rust, self.names, (self.rules, {}, {}), self.oracle)

    def test_constant_operand_is_not_jump_target(self):
        result = self.consume()
        self.assertEqual((result['instructions'], result['blocks']), (3, 1))
        self.assertEqual(result['blocks_at_maximum'], [{'start_pc': 0, 'end_pc_exclusive': 4, 'net_delta': 0}])

    def test_same_stack_delta_hides_wrong_absolute_requirement(self):
        self.rust[1] = (2, 'POP', 0, 2, 1)
        with self.assertRaisesRegex(EvidenceError, 'native readers disagree'):
            self.consume()

    def test_renamed_independent_reference_rejected(self):
        self.names[0x50] = 'ADD'
        with self.assertRaisesRegex(EvidenceError, 'HEVM'):
            self.consume()

    def test_specification_disagrees_with_both_engines(self):
        self.rules[0x60] = ('PUSH2', None)
        with self.assertRaisesRegex(EvidenceError, 'KEVM'):
            self.consume()

    def test_missing_schedule_gate(self):
        self.rules[0] = ('STOP', 'unavailable')
        with self.assertRaisesRegex(EvidenceError, 'schedule rule'):
            self.consume()

    def test_schedule_inheritance_and_explicit_override(self):
        flags = {('FORK1', 'a'): True, ('FORK2', 'a'): False}
        parents = {'FORK2': 'FORK1', 'FORK3': 'FORK2'}
        self.assertFalse(subject.gate_enabled('a', 'FORK3', flags, parents))
        self.assertTrue(subject.gate_enabled('a', 'FORK1', flags, parents))

    def test_inheritance_cycle_rejected(self):
        with self.assertRaisesRegex(EvidenceError, 'schedule rule'):
            subject.gate_enabled('a', 'A', {}, {'A': 'B', 'B': 'A'})

    def test_mutated_operand_caught_by_compiler_oracle(self):
        self.code = bytes.fromhex('60005000')
        with self.assertRaisesRegex(EvidenceError, 'solc'):
            self.consume()

    def test_corrupt_footer_rejected_before_disassembly(self):
        case = copy.deepcopy(subject.capture()['conservation'])
        output = json.loads(case['output_utf8'])
        code = output['contracts']['State.sol']['StatefulConservation']['evm']['deployedBytecode']
        code['object'] = code['object'][:-4] + '0001'
        case['output_utf8'] = json.dumps(output)
        with self.assertRaisesRegex(EvidenceError, 'metadata boundary'):
            subject.runtime(case)

    def test_exact_native_input_sizes(self):
        self.assertEqual([len(subject.runtime(case)) for case in subject.capture().values()], [768, 769, 715])

    @unittest.skipUnless(os.environ.get('NQC_EVM_LAYOUT_SOURCES'), 'requires the pinned source checkouts')
    def test_real_whatsabi_revm_accepted_by_two_references_and_compiler(self):
        rows = subject.review(Path(os.environ['NQC_EVM_LAYOUT_SOURCES']))
        self.assertEqual(set(rows), set(subject.UPSTREAM))
        for receipt in rows.values():
            cases = receipt['results']
            self.assertEqual([c['instructions'] for c in cases.values()], [510, 510, 472])
            self.assertEqual([c['blocks'] for c in cases.values()], [58, 58, 56])
            self.assertEqual(sum(c['fork_gated_instructions']['Ghaspushzero'] for c in cases.values()), 105)

    @unittest.skipUnless(os.environ.get('NQC_EVM_LAYOUT_SOLC'), 'requires pinned solc 0.8.30')
    def test_native_solc_rebuild_matches_exact_published_oracle(self):
        observed = rebuild(Path(os.environ['NQC_EVM_LAYOUT_SOLC']))
        published = subject.read_artifact(subject.ROOT, subject.SUPPLY + 'fixed-opcodes-solc.json')
        self.assertEqual(json.loads(published), observed)

    def test_unverified_compiler_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / 'solc'
            tool.write_bytes(b'wrong')
            with self.assertRaisesRegex(EvidenceError, 'compiler pin'):
                rebuild(tool)


if __name__ == '__main__':
    unittest.main()
