import copy
import unittest

import rlp
from trie import HexaryTrie

import account_facts as f
from fixtures import fixture, address, absence_shape_fixtures


class AccountFactsTests(unittest.TestCase):
    def setUp(self):
        self.address = f.FILTERED_ACCOUNT
        self.root, self.proof = fixture({self.address: {'nonce': 1, 'balance': 123,
                                        'storage': {9: 77}}}, self.address, (9, 17))

    def check(self, root=None, proof=None, slots=None, code=None):
        return f.verify_account_facts(self.root if root is None else root, self.address,
                                      [f.v.slot(9), f.v.slot(17)] if slots is None else slots,
                                      self.proof if proof is None else proof, code)

    def test_legacy_discards_validated_fields_new_layer_preserves_them(self):
        old = f.v.account_proof(self.root, self.address, [f.v.slot(9), f.v.slot(17)], self.proof)
        for field in ('account_existence', 'nonce', 'balance_wei', 'storage_root'):
            self.assertNotIn(field, old)
        result = self.check()
        self.assertEqual(result['account_existence'], 'PRESENT')
        self.assertEqual(result['nonce'], '1')
        self.assertEqual(result['balance_wei'], '123')
        self.assertEqual(result['storage_root'], self.proof['storageHash'])
        self.assertEqual(result['storage_values'], old['storage_values'])

    def test_zero_nonce_or_empty_code_does_not_mean_absence(self):
        for record in ({'nonce': 0, 'balance': 1}, {'nonce': 1, 'balance': 0}):
            root, proof = fixture({self.address: record}, self.address)
            result = self.check(root, proof, [])
            self.assertEqual(result['account_existence'], 'PRESENT')
            self.assertEqual(result['nonce'], str(record['nonce']))
            self.assertEqual(result['code_hash'], '0x' + f.mpt.EMPTY_CODE_HASH.hex())

    def test_nonempty_trie_absence_all_three_paths(self):
        for shape, (root, proof) in absence_shape_fixtures().items():
            with self.subTest(shape=shape):
                nodes = [rlp.decode(bytes.fromhex(n[2:])) for n in proof['accountProof']]
                self.assertNotEqual(bytes.fromhex(root[2:]), f.mpt.EMPTY_ROOT)
                if shape == 'empty_branch_child':
                    self.assertEqual(len(nodes[0]), 17)
                else:
                    self.assertEqual(len(nodes[0]), 2)
                    self.assertEqual(bool(nodes[0][0][0] & 0x20), shape == 'leaf_divergence')
                self.assertEqual(HexaryTrie.get_from_proof(bytes.fromhex(root[2:]),
                    f.v.k256(bytes.fromhex(self.address[2:])), nodes), b'')
                result = self.check(root, proof, [])
                self.assertEqual(result['account_existence'], 'PROVEN_ABSENT')
                self.assertEqual(result['nonce'], '0')
                self.assertEqual(result['balance_wei'], '0')
                self.assertEqual(result['storage_root'], '0x' + f.mpt.EMPTY_ROOT.hex())

    def test_empty_root_is_sufficient_for_empty_account_proof(self):
        root, proof = fixture({}, self.address, (9,))
        self.assertEqual(proof['accountProof'], [])
        result = self.check(root, proof, [f.v.slot(9)])
        self.assertEqual(result['account_existence'], 'PROVEN_ABSENT')
        self.assertEqual(result['storage_values'][f.v.slot(9)], '0')

    def test_missing_path_in_nonempty_trie_rejected_not_absent(self):
        for root, proof in absence_shape_fixtures().values():
            proof['accountProof'] = []
            with self.assertRaisesRegex(ValueError, 'missing node'):
                self.check(root, proof, [])

    def test_inclusion_path_missing_node_rejected(self):
        proof = copy.deepcopy(self.proof)
        proof['accountProof'].pop()
        with self.assertRaises(ValueError):
            self.check(proof=proof)

    def test_multilevel_account_membership_and_missing_child(self):
        records = {address(i): {'nonce': i, 'balance': i * 10} for i in range(1, 33)}
        records[self.address] = {'nonce': 99, 'balance': 1000}
        root, proof = fixture(records, self.address)
        self.assertGreater(len(proof['accountProof']), 1)
        result = self.check(root, proof, [])
        self.assertEqual((result['account_existence'], result['nonce']), ('PRESENT', '99'))
        proof['accountProof'].pop()
        with self.assertRaisesRegex(ValueError, 'missing node'):
            self.check(root, proof, [])

    def test_absence_claim_cannot_override_present_account(self):
        proof = copy.deepcopy(self.proof)
        proof.update(nonce='0x0', balance='0x0', storageHash='0x' + f.mpt.EMPTY_ROOT.hex())
        with self.assertRaises(ValueError):
            self.check(proof=proof)

    def test_proven_absence_cannot_claim_nonzero_account_fields(self):
        root, valid = absence_shape_fixtures()['leaf_divergence']
        for field in ('nonce', 'balance', 'storageHash', 'codeHash'):
            proof = copy.deepcopy(valid)
            proof[field] = '0x1' if field in ('nonce', 'balance') else '0x' + '12' * 32
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(root, proof, [])

    def test_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            self.check(proof={})
        for key in self.proof:
            proof = copy.deepcopy(self.proof)
            del proof[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(proof=proof)

    def test_missing_requested_slot_does_not_become_zero(self):
        proof = copy.deepcopy(self.proof)
        proof['storageProof'].pop()
        with self.assertRaisesRegex(ValueError, 'Missing or extra'):
            self.check(proof=proof)

    def test_changed_account_or_root_rejected(self):
        proof = copy.deepcopy(self.proof)
        proof['address'] = address(1)
        with self.assertRaises(ValueError):
            self.check(proof=proof)
        with self.assertRaises(ValueError):
            self.check(root='0x' + '12' * 32)

    def test_auxiliary_target_cannot_accept_synthetic_root(self):
        root, proof = fixture({self.address: {'nonce': 1}}, self.address)
        self.assertEqual(self.check(root, proof, [])['account_existence'], 'PRESENT')
        with self.assertRaisesRegex(ValueError, 'missing node'):
            f.verify_auxiliary_parent_account(proof)
        with self.assertRaises(TypeError):
            f.verify_auxiliary_parent_account(proof, root=root)

    def test_code_hash_is_not_claimed_as_code_bytes(self):
        self.assertFalse(self.check()['code_bytes_checked'])
        self.assertTrue(self.check(code='0x')['code_bytes_checked'])
        with self.assertRaises(ValueError):
            self.check(code='0x01')

    def test_large_values_remain_lossless_decimal_strings(self):
        root, proof = fixture({self.address: {'nonce': 2**63, 'balance': 2**255 - 1}}, self.address)
        result = self.check(root, proof, [])
        self.assertEqual(result['nonce'], str(2**63))
        self.assertEqual(result['balance_wei'], str(2**255 - 1))

    def test_noncanonical_nonce_rejected(self):
        for bad in ('0x01', '0x', True, '-1'):
            proof = copy.deepcopy(self.proof)
            proof['nonce'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.check(proof=proof)

    def test_no_input_mutation_or_admission(self):
        before = copy.deepcopy(self.proof)
        result = self.check()
        self.assertEqual(before, self.proof)
        for flag in ('canonical_root_authenticated', 'historical_position_authenticated',
                     'nitro_prefix_replayed', 'commercial_admission',
                     'complete_account_storage', 'state_transition_executed'):
            self.assertIs(result[flag], False)


if __name__ == '__main__':
    unittest.main()
