import json
import os
from pathlib import Path
import tempfile
import unittest

from superhunter import product_evidence_codec as codec
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import sha
from superhunter.safe_io import canonical, strict_json


class EvidenceTransport(unittest.TestCase):
    def test_input_joins_200_catalog_identities_to_their_original_evidence(self):
        rows = [strict_json(record) for record in codec.catalog_records()]
        self.assertEqual(list(range(1, 201)), [row['id'] for row in rows])
        self.assertEqual(59, sum(bool(row['receipt']) for row in rows))
        self.assertEqual(59, sum(bool(row['session_evidence_sha256']) for row in rows))
        self.assertEqual(200, len({row['repository'] for row in rows}))
        self.assertTrue(any(not row['purpose'].isascii() for row in rows))

    def test_transport_gate_rejects_reserved_noninteger_and_out_of_range_ids(self):
        for ids in ([256], [0, -1], [True], [2.0], [257]):
            with self.subTest(ids=ids), self.assertRaises(EvidenceError):
                codec.labels_for(ids, {})

    def test_changed_and_truncated_input_fail_with_distinct_or_invalid_json(self):
        original = b'{"id":1}'
        self.assertTrue(codec.compatible(original, original))
        for candidate in (b'{"id":2}', b'{"id":1', b' { "id" : 1 }'):
            with self.subTest(candidate=candidate):
                self.assertFalse(codec.compatible(candidate, original))

    def test_missing_checkout_has_no_partial_result(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises((OSError, ValueError)):
                codec.review(Path(empty))


SOURCE = os.environ.get('NQC_CODEC_TEST_SOURCES') or os.environ.get('NQC_TRUST_TEST_SOURCES')


@unittest.skipUnless(SOURCE, 'requires the three pinned source checkouts')
class NativeEvidenceTransport(unittest.TestCase):
    def test_real_compiled_decoder_and_reviewed_vocabulary_restore_original_proofs(self):
        result = codec.review(Path(SOURCE))
        self.assertEqual('execution', result[codec.LLAMA]['role'])
        self.assertEqual('reference', result[codec.SGLANG]['role'])
        record = result[codec.VLLM]['result']
        self.assertEqual(200, record['admitted_records'])
        self.assertEqual(59, record['restored_receipts'])
        self.assertEqual({'broken_utf8', 'other_identity', 'truncated', 'changed_receipt'},
                         set(record['negative_controls_rejected']))
        self.assertTrue(all(record['negative_controls_rejected'].values()))
        expected = {}
        for data in codec.catalog_records():
            evidence = strict_json(data)
            if evidence['receipt']:
                expected[evidence['repository']] = evidence['session_evidence_sha256']
        self.assertEqual(sha(canonical(expected)), record['receipt_index_sha256'])

    def test_reassigned_labels_and_reserved_token_metadata_are_rejected(self):
        raw = codec.inputs(Path(SOURCE))[codec.SGLANG]
        config = json.loads(raw)
        alphabet = sorted((label for label, idx in config['model']['vocab'].items() if idx < 256),
                          key=config['model']['vocab'].get)
        codec.vocabulary(raw, alphabet)
        config['model']['vocab'][alphabet[3]] = 2
        with self.assertRaises(EvidenceError):
            codec.vocabulary(canonical(config), alphabet)
        config = json.loads(raw)
        config['added_tokens'][0]['special'] = False
        with self.assertRaises(EvidenceError):
            codec.vocabulary(canonical(config), alphabet)
