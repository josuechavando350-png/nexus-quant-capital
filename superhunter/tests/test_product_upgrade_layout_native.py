"""Reject malformed upgrade receipts; native execution is measured separately."""
from copy import deepcopy
import unittest

from superhunter import product_upgrade_layout_native as product
from superhunter.product_census_header import pinned
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT


def sample():
    # A small protocol fixture, not a substitute for Hardhat/OpenZeppelin execution.
    types = {typ: {'label': typ} for typ in ('address', 'uint128', 'uint256')}
    layouts = {name: {'storage': deepcopy(fields), 'types': types,
                     'flat': True, 'layoutVersion': '1.2'} for name, fields in product.EXPECTED_LAYOUTS.items()}
    output = {'contracts': {product.SOURCE_NAME: {
        name: {'storageLayout': layout, 'evm': {'deployedBytecode': {'object': '6000'}}}
        for name, layout in deepcopy(layouts).items()}},
        'sources': {product.SOURCE_NAME: {'ast': {'nodeType': 'SourceUnit', 'nodes': [
            {'name': name, 'nodeType': 'ContractDefinition'} for name in layouts]}}}}
    def compilation_input(name, source):
        return {'language': 'Solidity', 'sources': {'project/contracts/'+name: {'content': source}},
                'settings': {'evmVersion': 'paris', 'optimizer': {'enabled': False},
                    'metadata': {'bytecodeHash': 'none'}, 'remappings': [],
                    'outputSelection': {'*': {'': ['ast'], '*': ['abi', 'storageLayout', 'evm.bytecode', 'evm.deployedBytecode']}}}}
    errors = [{'type': 'ParserError', 'severity': 'error', 'code': '6933', 'message': 'Expected primary expression.'}]
    direct_invalid = {'errors': [{**row, 'errorCode': row['code']} for row in errors]}
    observed = {'compiled': {'status': 'BUILD_SUCCESS', 'output': deepcopy(output),
        'input': compilation_input('Owned.sol', pinned(ROOT, product.SOURCE, product.SOURCE_SHA).decode())},
        'invalid': {'status': 'BUILD_FAILURE', 'input': compilation_input('Invalid.sol', product.INVALID_SOURCE), 'errors': errors},
        'layouts': layouts, 'comparisons': product.expected_comparisons(),
        'incomplete_inputs': {'storage_layout': 'rejected_before_comparison', 'ast': 'rejected_before_comparison'}}
    return observed, output, direct_invalid


class UpgradeLayoutReceiptTests(unittest.TestCase):
    def test_protocol_fixture_covers_two_accepts_and_four_rejections(self):
        result = product.reconcile(*sample())
        self.assertEqual(sum(row['compatible'] for row in result['upgrade_comparisons'].values()), 2)
        self.assertEqual(len(result['upgrade_comparisons']), 6)

    def test_source_substitution_is_rejected(self):
        observed, direct, invalid = sample()
        observed['compiled']['input']['sources'][product.SOURCE_NAME]['content'] += '// replacement\n'
        with self.assertRaises(EvidenceError):
            product.reconcile(observed, direct, invalid)

    def test_hardhat_direct_compiler_disagreement_is_rejected(self):
        observed, direct, invalid = sample()
        direct['contracts'][product.SOURCE_NAME]['Base']['evm']['deployedBytecode']['object'] = '6001'
        with self.assertRaises(EvidenceError):
            product.reconcile(observed, direct, invalid)

    def test_even_matching_compilers_must_have_expected_storage_slots(self):
        observed, direct, invalid = sample()
        direct['contracts'][product.SOURCE_NAME]['Base']['storageLayout']['storage'][0]['slot'] = '9'
        observed['compiled']['output'] = deepcopy(direct)
        with self.assertRaises(EvidenceError):
            product.reconcile(observed, direct, invalid)

    def test_missing_compiler_ast_and_layout_are_rejected(self):
        for missing in ('ast', 'layout'):
            observed, direct, invalid = sample()
            if missing == 'ast':
                del direct['sources'][product.SOURCE_NAME]['ast']
            else:
                del direct['contracts'][product.SOURCE_NAME]['Base']['storageLayout']
            observed['compiled']['output'] = deepcopy(direct)
            with self.subTest(missing=missing), self.assertRaises(EvidenceError):
                product.reconcile(observed, direct, invalid)

    def test_unsafe_upgrade_false_negative_is_rejected(self):
        observed, direct, invalid = sample()
        observed['comparisons']['Narrow'] = {'compatible': True, 'operations': []}
        with self.assertRaises(EvidenceError):
            product.reconcile(observed, direct, invalid)

    def test_invalid_solidity_must_be_rejected_by_both_paths(self):
        for alter in ('status', 'direct'):
            observed, direct, invalid = sample()
            if alter == 'status':
                observed['invalid']['status'] = 'BUILD_SUCCESS'
            else:
                invalid['errors'] = []
            with self.subTest(alter=alter), self.assertRaises(EvidenceError):
                product.reconcile(observed, direct, invalid)

    def test_missing_negative_control_is_rejected(self):
        observed, direct, invalid = sample()
        del observed['incomplete_inputs']['ast']
        with self.assertRaises(EvidenceError):
            product.reconcile(observed, direct, invalid)


if __name__ == '__main__':
    unittest.main()
