import copy
import unittest

import rlp

import proof_trial as p


class WriteCoverageTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = p.key_for_slot(9), p.key_for_slot(13)
        self.records = {self.a: rlp.encode(77), self.b: rlp.encode(88)}
        self.full, self.db = p.build(self.records)
        self.root = self.full.root_hash
        self.proof = p.read_proof(self.full, self.a)

    def test_valid_read_does_not_imply_deletion_coverage(self):
        self.assertEqual(p.mpt.trie_value(self.root, self.a, self.proof), rlp.encode(77))
        result = p.trial(self.root, self.a, self.proof, 'delete')
        self.assertEqual(result['status'], 'WRITE_BLOCKED_MISSING_NODE')
        self.assertIsNone(result['new_root'])
        missing = bytes.fromhex(result['missing_node_hash'][2:])
        self.assertNotIn(missing, {p.v.k256(n) for n in self.proof})
        self.assertIn(missing, self.db)

    def test_added_sibling_matches_full_and_direct_root(self):
        result = p.demonstration()
        self.assertFalse(result['additional_node_was_in_read_proof'])
        self.assertEqual(result['delete_with_added_node']['new_root'], result['full_reference_root'])
        self.assertEqual(result['full_reference_root'], result['direct_single_leaf_root'])

    def test_replacement_does_not_need_sibling_preimage_in_this_case(self):
        result = p.trial(self.root, self.a, self.proof, 'set', rlp.encode(99))
        reference, _ = p.build({self.a: rlp.encode(99), self.b: rlp.encode(88)})
        self.assertEqual(result['new_root'], '0x' + reference.root_hash.hex())

    def test_insertion_from_noninclusion_proof(self):
        key = p.key_for_slot(17)
        proof = p.read_proof(self.full, key)
        self.assertIsNone(p.mpt.trie_value(self.root, key, proof))
        result = p.trial(self.root, key, proof, 'set', rlp.encode(33))
        reference, _ = p.build(self.records | {key: rlp.encode(33)})
        self.assertEqual(result['new_root'], '0x' + reference.root_hash.hex())

    def test_delete_sole_leaf_needs_no_extra_node(self):
        trie, _ = p.build({self.a: rlp.encode(77)})
        result = p.trial(trie.root_hash, self.a, p.read_proof(trie, self.a), 'delete')
        self.assertEqual(result['new_root'], '0x' + p.mpt.EMPTY_ROOT.hex())

    def test_delete_absent_key_is_noop(self):
        key = p.key_for_slot(17)
        result = p.trial(self.root, key, p.read_proof(self.full, key), 'delete')
        self.assertIsNone(result['old_value'])
        self.assertEqual(result['new_root'], '0x' + self.root.hex())

    def test_two_remaining_branches_do_not_require_collapse(self):
        keys = {self.a[0] >> 4: self.a}
        for slot in range(64):
            key = p.key_for_slot(slot)
            keys.setdefault(key[0] >> 4, key)
            if len(keys) == 3:
                break
        self.assertEqual(len(keys), 3)
        records = {key: rlp.encode(i + 1) for i, key in enumerate(keys.values())}
        trie, _ = p.build(records)
        result = p.trial(trie.root_hash, self.a, p.read_proof(trie, self.a), 'delete')
        reference, _ = p.build({k: v for k, v in records.items() if k != self.a})
        self.assertEqual(result['new_root'], '0x' + reference.root_hash.hex())

    def test_inline_sibling_already_carried_by_parent(self):
        # Generic short-key trie geometry, NOT Ethereum hashed storage keys.
        a, b = b'\x10', b'\x20'
        trie, _ = p.build({a: b'v', b: b'w'})
        proof = p.read_proof(trie, a)
        self.assertIsInstance(rlp.decode(proof[0])[2], list)
        result = p.trial(trie.root_hash, a, proof, 'delete')
        reference, _ = p.build({b: b'w'})
        self.assertEqual(result['new_root'], '0x' + reference.root_hash.hex())

    def test_nested_extension_also_exposes_missing_sibling(self):
        # Deliberately chosen raw keys to exercise geometry, not known preimages.
        a, b = b'\xaa' * 31 + b'\x10', b'\xaa' * 31 + b'\x20'
        trie, db = p.build({a: b'v' * 40, b: b'w' * 40})
        proof = p.read_proof(trie, a)
        self.assertEqual(len(rlp.decode(proof[0])), 2)
        blocked = p.trial(trie.root_hash, a, proof, 'delete')
        self.assertEqual(blocked['status'], 'WRITE_BLOCKED_MISSING_NODE')
        missing = bytes.fromhex(blocked['missing_node_hash'][2:])
        fixed = p.trial(trie.root_hash, a, proof, 'delete', extra_nodes=[(missing, db[missing])])
        reference, _ = p.build({b: b'w' * 40})
        self.assertEqual(fixed['new_root'], '0x' + reference.root_hash.hex())

    def test_corrupted_extra_node_rejected(self):
        blocked = p.trial(self.root, self.a, self.proof, 'delete')
        missing = bytes.fromhex(blocked['missing_node_hash'][2:])
        bad = self.db[missing][:-1] + bytes([self.db[missing][-1] ^ 1])
        with self.assertRaisesRegex(ValueError, 'Extra node hash mismatch'):
            p.trial(self.root, self.a, self.proof, 'delete', extra_nodes=[(missing, bad)])

    def test_unrelated_valid_hash_does_not_fill_gap(self):
        unrelated = rlp.encode([b'\x20' + b'\x01' * 32, b'x'])
        result = p.trial(self.root, self.a, self.proof, 'delete',
                         extra_nodes=[(p.v.k256(unrelated), unrelated)])
        self.assertEqual(result['status'], 'WRITE_BLOCKED_MISSING_NODE')
        self.assertIsNone(result['new_root'])

    def test_incomplete_read_proof_rejected_before_write(self):
        with self.assertRaisesRegex(ValueError, 'missing node'):
            p.trial(self.root, self.a, [], 'delete')

    def test_invalid_operation_or_ambiguous_zero_value_rejected(self):
        for operation, value in [('other', None), ('delete', b'x'), ('set', b''), ('set', None)]:
            with self.subTest(operation=operation, value=value), self.assertRaises(ValueError):
                p.trial(self.root, self.a, self.proof, operation, value)

    def test_disposable_attempt_does_not_mutate_inputs_or_open_gates(self):
        proof_before, db_before = copy.deepcopy(self.proof), copy.deepcopy(self.db)
        result = p.trial(self.root, self.a, self.proof, 'delete')
        self.assertEqual(self.proof, proof_before)
        self.assertEqual(self.db, db_before)
        for flag in ('historical_position_authenticated', 'nitro_replayed',
                     'complete_parent_witness', 'commercial_admission'):
            self.assertIs(result[flag], False)


if __name__ == '__main__':
    unittest.main()
