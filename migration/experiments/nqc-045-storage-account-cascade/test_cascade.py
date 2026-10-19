import copy
import unittest
from unittest.mock import patch

import rlp

import cascade as c
import cases
from fixtures import fixture


class CascadeTests(unittest.TestCase):
    def setUp(self):
        self.records = cases.records()
        self.root, self.proof = fixture(self.records, cases.TARGET, [9])

    def test_missing_storage_sibling_yields_no_candidate_roots(self):
        result = c.apply_slot(self.root, cases.TARGET, 9, 0, self.proof)
        self.assertEqual(result['status'], 'BLOCKED_STORAGE_NODE')
        for key in ('candidate_state_root', 'candidate_storage_root', 'candidate_account_rlp'):
            self.assertIsNone(result[key])

    def test_complete_cascade_matches_full_reference_and_post_proof(self):
        result = cases.demonstration()
        self.assertNotEqual(result['input_state_root'], result['full_reference_state_root'])
        self.assertEqual(result['completed_with_sibling']['candidate_state_root'], result['full_reference_state_root'])
        values = result['post_proof_checked']['storage_values']
        self.assertEqual(int(values[c.raw.v.slot(9)]), 0)
        self.assertEqual(int(values[c.raw.v.slot(13)]), 88)

    def test_only_storage_root_account_field_changes(self):
        result = c.apply_slot(self.root, cases.TARGET, 9, 99, self.proof)
        old, new = [rlp.decode(c.raw.v.data_hex(result[k])) for k in ('old_account_rlp', 'candidate_account_rlp')]
        for index in (0, 1, 3):
            self.assertEqual(old[index], new[index])
        self.assertNotEqual(old[2], new[2])

    def test_replacement_matches_complete_state_rebuild(self):
        result = c.apply_slot(self.root, cases.TARGET, 9, 99, self.proof)
        self.records[cases.TARGET]['storage'][9] = 99
        reference, _ = fixture(self.records, cases.TARGET, [9])
        self.assertEqual(result['candidate_state_root'], reference)

    def test_unrelated_account_remains_verifiable(self):
        result = c.apply_slot(self.root, cases.TARGET, 9, 99, self.proof)
        self.records[cases.TARGET]['storage'][9] = 99
        reference, neighbor = fixture(self.records, cases.NEIGHBOR, [21])
        checked = c.facts.verify_account_facts(result['candidate_state_root'], cases.NEIGHBOR,
                                              [c.raw.v.slot(21)], neighbor)
        self.assertEqual(checked['nonce'], '5')
        self.assertEqual(checked['balance_wei'], '123')
        self.assertEqual(int(checked['storage_values'][c.raw.v.slot(21)]), 456)

    def test_storage_root_is_not_global_state_root(self):
        result = c.apply_slot(self.root, cases.TARGET, 9, 99, self.proof)
        self.assertNotEqual(result['candidate_storage_root'], result['candidate_state_root'])
        with self.assertRaises(ValueError):
            c.facts.verify_account_facts(result['candidate_storage_root'], cases.TARGET, [c.raw.v.slot(9)], self.proof)

    def test_last_slot_delete_keeps_account_and_empty_storage_root(self):
        self.records[cases.TARGET]['storage'] = {9: 77}
        root, proof = fixture(self.records, cases.TARGET, [9])
        result = c.apply_slot(root, cases.TARGET, 9, 0, proof)
        self.records[cases.TARGET]['storage'] = {}
        expected, after_proof = fixture(self.records, cases.TARGET, [9])
        self.assertEqual(result['candidate_state_root'], expected)
        self.assertEqual(result['candidate_storage_root'], '0x' + c.raw.mpt.EMPTY_ROOT.hex())
        checked = c.facts.verify_account_facts(expected, cases.TARGET, [c.raw.v.slot(9)], after_proof)
        self.assertEqual(checked['account_existence'], 'PRESENT')

    def test_zero_is_deletion_not_stored_rlp_zero(self):
        self.records[cases.TARGET]['storage'] = {9: 77}
        root, proof = fixture(self.records, cases.TARGET, [9])
        result = c.apply_slot(root, cases.TARGET, 9, 0, proof)
        wrong, _ = c.raw.build({c.raw.key_for_slot(9): rlp.encode(0)})
        self.assertNotEqual(result['candidate_storage_root'], '0x' + wrong.root_hash.hex())

    def test_zero_on_absent_slot_is_noop(self):
        root, proof = fixture(self.records, cases.TARGET, [17])
        result = c.apply_slot(root, cases.TARGET, 17, 0, proof)
        self.assertEqual(result['candidate_state_root'], root)

    def test_insert_proven_absent_slot(self):
        root, proof = fixture(self.records, cases.TARGET, [17])
        result = c.apply_slot(root, cases.TARGET, 17, 1, proof)
        self.records[cases.TARGET]['storage'][17] = 1
        expected, _ = fixture(self.records, cases.TARGET, [17])
        self.assertEqual(result['candidate_state_root'], expected)

    def test_account_creation_rejected_even_with_proven_absence(self):
        root, proof = fixture(self.records, cases.address(3), [9])
        with self.assertRaisesRegex(ValueError, 'Account creation is unsupported'):
            c.apply_slot(root, cases.address(3), 9, 1, proof)

    def test_incomplete_and_mismatched_inputs_rejected(self):
        mutations = [lambda p: p.update(accountProof=[]), lambda p: p.update(storageProof=[]),
                     lambda p: p.update(storageHash='0x' + '00' * 32),
                     lambda p: p['storageProof'][0].update(value='0x1'),
                     lambda p: p.update(nonce='0x8'), lambda p: p.update(address=cases.NEIGHBOR)]
        for mutate in mutations:
            proof = copy.deepcopy(self.proof)
            mutate(proof)
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                c.apply_slot(self.root, cases.TARGET, 9, 99, proof)

    def test_invalid_slot_and_value_rejected(self):
        for bad in (-1, 2**256, True, '9'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    c.apply_slot(self.root, cases.TARGET, bad, 99, self.proof)
                with self.assertRaises(ValueError):
                    c.apply_slot(self.root, cases.TARGET, 9, bad, self.proof)

    def test_bad_extra_node_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Extra node hash mismatch'):
            c.apply_slot(self.root, cases.TARGET, 9, 0, self.proof, [(b'\0' * 32, b'not a node')])

    def test_account_stage_failure_hides_intermediate_storage_root(self):
        # Inject a downstream failure to check output policy, not natural trie geometry.
        actual = c.raw.trial
        count = 0
        def failing_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                return {'status': 'WRITE_BLOCKED_MISSING_NODE', 'missing_node_hash': '0x' + 'ff' * 32}
            return actual(*args, **kwargs)
        with patch.object(c.raw, 'trial', side_effect=failing_second):
            result = c.apply_slot(self.root, cases.TARGET, 9, 99, self.proof)
        self.assertEqual(result['status'], 'BLOCKED_ACCOUNT_NODE')
        self.assertIsNone(result['candidate_state_root'])
        self.assertIsNone(result['candidate_storage_root'])

    def test_inputs_unchanged_and_gates_closed(self):
        before = copy.deepcopy(self.proof)
        for value in (0, 99):
            result = c.apply_slot(self.root, cases.TARGET, 9, value, self.proof)
            for key in ('historical_position_authenticated', 'nitro_replayed',
                        'complete_parent_witness', 'commercial_admission'):
                self.assertIs(result[key], False)
        self.assertEqual(before, self.proof)


if __name__ == '__main__':
    unittest.main()
