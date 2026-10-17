import copy
import unittest
from evm_hash import keccak256
from historical_rpc_audit import load, rlp
from historical_order_audit import audit, encoded_transaction, trie_root, compact


class HistoricalOrderTests(unittest.TestCase):
    def test_all_602_transactions_match_the_pinned_header_commitment(self):
        report = audit()
        self.assertEqual(report['transaction_count'],602)
        self.assertEqual(report['target_transaction_index'],1)
        self.assertEqual(report['transaction_types'],{'0x0':115,'0x2':473,'0x3':2,'0x4':12})
        self.assertFalse(report['prefix_effects_known'])
        self.assertFalse(report['fork_reproduced'])

    def test_omission_and_reordering_with_relabelled_indices_fail_root_check(self):
        block = load('b-block.json.gz')['response']['result']
        omitted = copy.deepcopy(block); omitted['transactions'].pop()
        with self.assertRaisesRegex(ValueError,'trie root mismatch'): audit(omitted)
        block['transactions'][0],block['transactions'][1] = block['transactions'][1],block['transactions'][0]
        for i in (0,1): block['transactions'][i]['transactionIndex'] = hex(i)
        with self.assertRaisesRegex(ValueError,'trie root mismatch'): audit(block)

    def test_changed_blob_or_authorization_bytes_fail_transaction_hash(self):
        block = load('b-block.json.gz')['response']['result']
        blob = copy.deepcopy(next(t for t in block['transactions'] if t['type']=='0x3'))
        blob['blobVersionedHashes'][0] = '0x01'+'00'*31
        auth = copy.deepcopy(next(t for t in block['transactions'] if t['type']=='0x4'))
        auth['authorizationList'][0]['nonce'] = hex(int(auth['authorizationList'][0]['nonce'],16)+1)
        for tx in (blob,auth):
            with self.assertRaisesRegex(ValueError,'byte hash mismatch'): encoded_transaction(tx)

    def test_empty_and_short_embedded_trie_nodes(self):
        self.assertEqual(trie_root([]).hex(),'56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421')
        branch = [b'']*17
        branch[0] = [b'\x20',b'a']; branch[1] = [b'\x20',b'b']
        self.assertEqual(trie_root([(b'\x10',b'a'),(b'\x11',b'b')]),
                         keccak256(rlp([b'\x11',branch])))
        self.assertEqual(compact((1,2,3),True),b'\x31\x23')
        with self.assertRaises(ValueError): trie_root([(b'x',b'a'),(b'x',b'b')])
