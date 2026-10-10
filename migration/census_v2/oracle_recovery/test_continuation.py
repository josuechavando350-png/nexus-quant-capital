import copy
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

import collect as c
import verify_continuation as v


class ContinuationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = Path(os.environ['NQC_ORACLE_CHECKPOINT'])
        cls.primary = Path(os.environ['NQC_ORACLE_PRIMARY_DIRECTORY'])
        archive = Path(__file__).parent / 'sequential-checkpoint-001.zip'
        assert c.sha(archive.read_bytes()) == '4b594dbcc1e32ff8569adaa0a2cea3e374648e5c0d3d3331f0ad5f81b7e83633'
        with zipfile.ZipFile(archive) as z:
            assert len(z.namelist()) == 10
            for name in z.namelist():
                assert (cls.evidence / name).read_bytes() == z.read(name)
        cls.record = json.loads(gzip.decompress((cls.evidence / 'capture-000000.jsonl.gz').read_bytes()).splitlines()[0])
        cls.requests = json.loads(cls.record['request_body'])
        cls.batch = [q['id'] for q in cls.requests]
        cls.data = cls.requests[0]['params'][0]['data']
        cls.hashes = {q['id'] - c.START: q['params'][1]['blockHash'] for q in cls.requests}
        cls.original = c.decode_batch(cls.record['response_body'], cls.requests)

    def check(self, record):
        return v.verify_prices(record, self.batch, self.hashes, self.data, self.original.__getitem__)

    def mutate(self, field, fn):
        record = copy.deepcopy(self.record)
        doc = json.loads(record[field + '_body'])
        fn(doc)
        record[field + '_body'] = json.dumps(doc)
        record[field + '_sha256'] = c.sha(record[field + '_body'].encode())
        return record

    def test_actual_checkpoint_matches_remote_readback(self):
        result = v.verify(self.evidence, self.primary)
        self.assertEqual(c.canon(result), (self.evidence / 'readback.json').read_bytes())
        self.assertEqual(result['new_blocks_verified'], 2000)
        self.assertEqual(result['price_values_matched'], 134000)
        self.assertEqual(result['secondary_union_verified_blocks'], 7170)
        self.assertEqual(result['secondary_missing_blocks'], 207866)
        self.assertEqual(result['current_capture_counter'], 2140)
        self.assertFalse(result['full_secondary_price_coverage'])
        self.assertFalse(result['census_certified'])

    def test_altered_price_rejected(self):
        def alter(doc):
            x = doc[0]['result']
            doc[0]['result'] = x[:-64] + f'{int(x[-64:], 16) + 1:064x}'
        with self.assertRaisesRegex(ValueError, 'price vector mismatch'):
            self.check(self.mutate('response', alter))

    def test_missing_response_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cardinality'):
            self.check(self.mutate('response', lambda doc: doc.pop()))

    def test_wrong_block_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'request plan/hash'):
            self.check(self.mutate('request', lambda doc: doc[0]['params'][1].__setitem__('blockHash', c.END_HASH)))

    def test_noncanonical_request_rejected(self):
        with self.assertRaisesRegex(ValueError, 'canonicality'):
            self.check(self.mutate('request', lambda doc: doc[0]['params'][1].__setitem__('requireCanonical', False)))

    def test_duplicate_response_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.check(self.mutate('response', lambda doc: doc.__setitem__(0, doc[1])))

    def test_foreign_producer_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = json.loads((self.evidence / 'progress.json').read_bytes())
            doc['producer_commit'] = '0' * 40
            (root / 'progress.json').write_bytes(c.canon(doc))
            with self.assertRaisesRegex(ValueError, 'producer scope'):
                v.verify(root, self.primary)


if __name__ == '__main__':
    unittest.main()
