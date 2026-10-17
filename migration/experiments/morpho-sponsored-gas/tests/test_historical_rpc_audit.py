import copy
import unittest
from historical_rpc_audit import (audit, load, verify_header, verify_type2_hash,
                                  verify_b_movements, rlp, HASH_A, HASH_B, TX_B)


class HistoricalRpcAuditTests(unittest.TestCase):
    def test_rlp_reference_vectors_and_independent_header_hashes(self):
        self.assertEqual(rlp(b'').hex(),'80')
        self.assertEqual(rlp(0).hex(),'80')
        self.assertEqual(rlp([b'cat',b'dog']).hex(),'c88363617483646f67')
        for case,expected in (('a',HASH_A),('b',HASH_B)):
            b=load(case+'-block.json.gz')['response']['result']
            self.assertEqual(verify_header(b,expected),expected)
            b['stateRoot']='0x'+'00'*32
            with self.assertRaises(ValueError):verify_header(b,expected)

    def test_changed_signed_transaction_or_receipt_flow_is_rejected(self):
        b=load('b-block.json.gz')['response']['result']; tx=copy.deepcopy(b['transactions'][1])
        self.assertEqual(verify_type2_hash(tx,TX_B),TX_B)
        tx['value']='0x1'
        with self.assertRaises(ValueError):verify_type2_hash(tx,TX_B)
        r=load('b-receipt.json')['response']['result'];verify_b_movements(r)
        r['logs'][-1]['data']='0x'+'00'*32
        with self.assertRaises(ValueError):verify_b_movements(r)

    def test_cross_provider_reconciliation_never_becomes_a_replay(self):
        r=audit()
        self.assertIsNone(r['case_a']['sender_gas_wei'])
        self.assertEqual(r['case_a']['indexer_only_reported_sender_gas_wei'],323793004345200)
        self.assertIsNone(r['case_b_prefix']['receipt_status'])
        self.assertEqual(r['case_b']['sender_gas_wei'],198416195275125)
        self.assertEqual(r['case_b']['preceding_transactions'],1)
        self.assertEqual(len(r['selection']['api_observations']),2)
        self.assertIsNone(r['selection']['profitable_frequency'])
        self.assertFalse(r['fork_reproduced'])
        self.assertFalse(r['certified'])
