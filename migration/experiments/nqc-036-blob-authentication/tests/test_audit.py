import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import audit
import decode_batch as decoder
import ckzg
import rlp


class RecoveredEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup = ckzg.load_trusted_setup(str(audit.ROOT/'vendor/trusted_setup.txt'),0)
        cls.blobs = [(audit.ROOT/f'evidence/blob-{i}-payload.response').read_bytes() for i in range(3)]
        cls.decoded = decoder.decode(cls.blobs)
        cls.message = cls.decoded['messages'][206]
        cls.target = audit.read('inputs/05-block.json')['result']
        cls.parent = audit.read('inputs/06-parent.json')['result']
        cls.prefix,_ = audit.prefix_transaction(cls.target,cls.parent,26008731,1789786800)
        cls.txs = [cls.prefix]+cls.message['raw_transactions']

    def test_real_full_audit_stays_closed(self):
        result = audit.audit()
        self.assertTrue(result['full_transaction_root_matches_captured_header'])
        self.assertFalse(result['canonical_l2_header_authenticated'])
        self.assertFalse(result['commercial_admission'])
        self.assertFalse(result['prefix_state_transition_executed'])
        self.assertIsNone(result['exact_prestate_root'])
        self.assertEqual(result['authenticated_priority_slots'],0)

    def test_real_blob_payload_mutation_rejected(self):
        changed = bytearray(self.blobs[0]);changed[17] ^= 1
        with self.assertRaisesRegex(ValueError,'commitment'):
            audit.verify_blob(bytes(changed),audit.read('evidence/blob-0-metadata.json'),audit.BLOB_HASHES[0],self.setup)

    def test_reordered_blobs_rejected_against_l1_hash_order(self):
        with self.assertRaisesRegex(ValueError,'hash/order'):
            audit.verify_blob(self.blobs[1],audit.read('evidence/blob-1-metadata.json'),audit.BLOB_HASHES[0],self.setup)

    def test_provider_infinity_proofs_rejected(self):
        for i,b in enumerate(self.blobs):
            m=audit.read(f'evidence/blob-{i}-metadata.json')
            self.assertFalse(ckzg.verify_blob_kzg_proof(b,audit.unhex(m['commitment']),audit.unhex(m['proof']),self.setup))

    def test_cid_metadata_mutation_rejected(self):
        m=audit.read('evidence/blob-0-metadata.json')
        m['dataStorageReferences'][0]['url']=audit.read('evidence/blob-1-metadata.json')['dataStorageReferences'][0]['url']
        with self.assertRaisesRegex(ValueError,'CID mismatch'):
            audit.verify_blob(self.blobs[0],m,audit.BLOB_HASHES[0],self.setup)

    def test_blob_truncation_rejected(self):
        with self.assertRaises(ValueError):
            decoder.decode_blobs([self.blobs[0][:-1]])

    def test_missing_blob_rejected(self):
        with self.assertRaises(ValueError):
            decoder.decode_blobs(self.blobs[:2])

    def test_invalid_nitro_field_bits_rejected(self):
        b=bytearray(self.blobs[0]);b[0] |= 128
        with self.assertRaisesRegex(ValueError,'high bits'):
            decoder.decode_blobs([bytes(b)]+self.blobs[1:])

    def test_target_message_exact_hash_order(self):
        self.assertEqual(self.message['tx_hashes'],self.target['transactions'][1:])
        self.assertEqual(self.message['tx_hashes'][0],audit.TARGET_TX)
        self.assertEqual(len(self.decoded['messages']),232)

    def test_system_prefix_hash_and_root(self):
        self.assertEqual('0x'+decoder.k256(self.prefix).hex(),audit.PREFIX_TX)
        self.assertEqual(audit.transaction_root(self.txs),self.target['transactionsRoot'])

    def test_omitting_system_prefix_changes_root(self):
        self.assertNotEqual(audit.transaction_root(self.txs[1:]),self.target['transactionsRoot'])

    def test_reordering_signed_transactions_changes_root(self):
        txs=self.txs.copy();txs[1],txs[2]=txs[2],txs[1]
        self.assertNotEqual(audit.transaction_root(txs),self.target['transactionsRoot'])

    def test_changed_prefix_context_does_not_match(self):
        prefix,_=audit.prefix_transaction(self.target,self.parent,26008732,1789786800)
        self.assertNotEqual('0x'+decoder.k256(prefix).hex(),audit.PREFIX_TX)
        with self.assertRaisesRegex(ValueError,'timestamp'):
            audit.prefix_transaction(self.target,self.parent,26008731,1789786801)

    def test_captured_state_mutation_changes_header(self):
        h=copy.deepcopy(self.target);h['stateRoot']='0x'+'11'*32
        self.assertNotEqual(audit.header_hash(h),audit.TARGET_HASH)

    def test_rlp_decoder_matches_reference_on_recovered_payload(self):
        payload,_=decoder.decode_blobs(self.blobs)
        segments,expanded=decoder.segments_from_payload(payload)
        pos=0
        for segment in segments:
            decoded,end=decoder.rlp_one(expanded,pos)
            self.assertEqual(rlp.decode(expanded[pos:end]),decoded)
            self.assertEqual(decoded,segment)
            pos=end
        self.assertEqual(pos,len(expanded))

    def test_noncanonical_rlp_rejected(self):
        for value in [b'\x81\x01',b'\xb8\x01\x01',b'\xb9\x00\x38'+b'x'*56,b'\xc1\x82\x01\x02']:
            with self.assertRaises(ValueError):
                decoder.rlp_one(value)

    def test_nested_l2_length_overrun_rejected(self):
        with self.assertRaisesRegex(ValueError,'truncated'):
            list(decoder.signed_txs(b'\x03'+(100).to_bytes(8,'big')+b'\x04\x02'))


if __name__=='__main__':
    unittest.main()
