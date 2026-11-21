from copy import deepcopy
import os
import unittest

from superhunter import product_build_compatibility as comp
from superhunter.product_reasoning import EvidenceError


class BuildCompatibilityControls(unittest.TestCase):
    def test_independent_integer_packing_crosses_slot_boundary(self):
        field = lambda name, typ: {'nodeType': 'VariableDeclaration', 'stateVariable': True, 'name': name,
                                   'typeDescriptions': {'typeString': typ}}
        source = {'sources': {'State.sol': {'ast': {'nodes': [{'nodes': [field('a','uint128'),
            field('b','uint256'), field('c','uint64')]}]}}}}
        rows = [{'label': n, 'type': t, 'begin': a, 'end': b} for n,t,a,b in
                [('a','uint128',0,16),('b','uint256',32,64),('c','uint64',64,72)]]
        comp.compare_fields(rows, source)
        rows[1]['begin'] = 16
        with self.assertRaisesRegex(EvidenceError, 'independently packed'):
            comp.compare_fields(rows, source)

    def test_unsupported_types_in_static_profile_fail_closed(self):
        source = {'sources': {'State.sol': {'ast': {'nodes': [{'nodes': [
            {'nodeType': 'VariableDeclaration','stateVariable': True,'name':'x','typeDescriptions':{'typeString':'bytes'}}]}]}}}}
        with self.assertRaisesRegex(EvidenceError, 'unsupported field'):
            comp.compare_fields([], source)

    def test_same_selector_different_return_type_rejected(self):
        function = {'type': 'function', 'name': 'f', 'inputs': [], 'outputs': [{'type':'bool'}],
                    'stateMutability':'view'}
        first = {'abi':[function]}
        second = deepcopy(first)
        second['abi'][0]['outputs'][0]['type'] = 'uint8'
        with self.assertRaisesRegex(EvidenceError, 'reference ABI unavailable'):
            comp.interfaces(first,second)

    def test_source_reference_missing_function_rejected(self):
        first = {'abi':[{'type':'function','name':'f','inputs':[],'outputs':[],'stateMutability':'pure'}]}
        with self.assertRaisesRegex(EvidenceError, 'reference ABI unavailable'):
            comp.interfaces(first,{'abi':[]})

    def test_mutability_reported_even_with_identical_inputs_and_outputs(self):
        value = {'abi':[{'type':'function','name':'f','inputs':[],'outputs':[],'stateMutability':'pure'}]}
        second = deepcopy(value)
        second['abi'][0]['stateMutability']='view'
        self.assertEqual(comp.interfaces(value,second)['mutability_differences'],
                         {'f()':{'reference':'pure','owned':'view'}})

    @unittest.skipUnless(os.environ.get('NQC_BUILD_KIT') and os.environ.get('NQC_EVM_LAYOUT_SOURCES'),
                         'requires pinned compiler, wheel closure, Node and four checkouts')
    def test_compiled_positive_negative_and_independent_cases(self):
        results = comp.review(os.environ['NQC_EVM_LAYOUT_SOURCES'])
        self.assertEqual(set(results),set(comp.UPSTREAM))
        for item in results.values():
            self.assertEqual(item['source_matched_python_modules'],41)
            self.assertEqual(len(item['interface_comparison']['shared_signatures']),7)
            self.assertEqual(item['results']['reorder']['changed_existing_fields'],['credit','debit'])
            self.assertEqual(item['results']['retype']['changed_existing_fields'],['steps'])
            self.assertTrue(item['results']['append']['preserves_existing_fields'])
            self.assertEqual(item['results']['conservation']['compiler_selectors'],{'move(uint8)':'70e87aaf'})


if __name__ == '__main__':
    unittest.main()
