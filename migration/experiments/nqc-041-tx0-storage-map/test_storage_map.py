import hashlib
import json
from pathlib import Path
import unittest

import storage_map as m

HERE = Path(__file__).resolve().parent
DIAGNOSTIC = HERE.parent / 'nqc-037-historical-state/inputs/augmented-prestate.json'


class SlotTests(unittest.TestCase):
    def test_keccak_known_answer_not_sha3(self):
        self.assertEqual(m.k256(b'').hex(),
                         'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertNotEqual(m.k256(b''), hashlib.sha3_256(b'').digest())

    def test_root_matches_existing_diagnostic(self):
        self.assertEqual(m.slot((), 0),
                         '0x15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b400')
        state = json.loads(DIAGNOSTIC.read_text())['result'][m.ARBOS]['storage']
        self.assertEqual(int(state[m.slot((), 0)], 16), 61)

    def test_nested_namespace_is_not_flat_hash(self):
        self.assertEqual(m.namespace(b'\x02', b'\x00'), m.k256(m.k256(b'\x02') + b'\x00'))
        self.assertNotEqual(m.namespace(b'\x02', b'\x00'), m.k256(b'\x02\x00'))

    def test_last_byte_is_preserved(self):
        self.assertEqual(m.slot(m.QUEUE, 255)[-2:], 'ff')
        self.assertEqual(m.slot(m.QUEUE, 255)[:-2], m.slot(m.QUEUE, 0)[:-2])
        self.assertNotEqual(m.slot(m.QUEUE, 256)[:-2], m.slot(m.QUEUE, 0)[:-2])
        self.assertEqual(m.slot(m.QUEUE, 256)[-2:], '00')

    def test_vector_uses_eight_byte_big_endian_id(self):
        actual = m.constraint_slots('single', 1)['backlog']
        self.assertEqual(actual,
                         '0xb030e80be1d37b800ea9902aab7481a1eea35835f84698282506b483b7472102')
        self.assertNotEqual(actual, m.slot(m.SINGLE + ((1).to_bytes(32, 'big'),), 2))
        self.assertNotEqual(actual, m.slot(m.SINGLE + ((1).to_bytes(8, 'little'),), 2))

    def test_diagnostic_model_selection(self):
        state = json.loads(DIAGNOSTIC.read_text())['result'][m.ARBOS]['storage']
        c = m.control_slots()
        values = [int(state[c[k]], 16) for k in
                  ('arbos_version', 'single_constraints_length', 'multi_constraints_length')]
        self.assertEqual(values, [61, 2, 0])
        self.assertEqual(m.pricing_model(*values), 'single')

    def test_missing_length_is_not_zero(self):
        self.assertIsNone(m.pricing_model(61, 2, None))
        self.assertIsNone(m.pricing_model(61, None, 0))
        self.assertIsNone(m.pricing_model(50, None))

    def test_version_boundaries_and_priority(self):
        for args, expected in [((49,), 'legacy'), ((50, 0), 'legacy'),
                               ((50, 2), 'single'), ((59, 0, 2), 'legacy'),
                               ((60, 2, 1), 'multi'), ((61, None, 1), 'multi'),
                               ((61, 0, 0), 'legacy')]:
            with self.subTest(args=args):
                self.assertEqual(m.pricing_model(*args), expected)

    def test_queue_header_is_not_entry(self):
        for i in (0, 1, -1, 2 ** 64):
            with self.assertRaises(ValueError):
                m.queue_entry(i)
        self.assertEqual(m.queue_entry(2), m.slot(m.QUEUE, 2))

    def test_ticket_id_and_escrow_domains(self):
        ticket = bytes.fromhex('11' * 32)
        result = m.retryable_slots(ticket)
        self.assertEqual(len(set(result.values())), 8)
        self.assertEqual(m.escrow_address(ticket), '0x' + m.k256(b'retryable escrow' + ticket)[-20:].hex())
        self.assertNotEqual(result['calldata_length'], result['num_tries'])
        self.assertEqual(m.calldata_word_slot(ticket, 0), m.slot((b'\x02', ticket, b'\x01'), 1))
        for bad in (b'', bytes(31), bytes(33), '11' * 32):
            with self.assertRaises(ValueError):
                m.retryable_slots(bad)

    def test_blockhash_ring_wrap(self):
        self.assertEqual(m.blockhash_slot(255), m.slot(m.BLOCKHASH, 256))
        self.assertEqual(m.blockhash_slot(256), m.slot(m.BLOCKHASH, 1))
        self.assertEqual(m.blockhash_slot(26008730), m.blockhash_slot(26008730 % 256))

    def test_multigas_offsets_include_unknown(self):
        fields = m.constraint_slots('multi', 0)
        self.assertEqual(len(fields), 13)
        self.assertEqual(fields['max_weight'][-2:], '03')
        self.assertEqual(fields['weight_8'][-2:], '0c')
        fees = m.fee_slots()
        self.assertEqual(len(set(fees.values())), 18)
        self.assertEqual(fees['current_0'], m.slot(m.FEES, 9))

    def test_strict_integer_boundaries(self):
        for bad in (True, -1, 2 ** 256, '0', 1.0):
            with self.assertRaises(ValueError):
                m.slot((), bad)
        for bad in (-1, True, 2 ** 64):
            with self.assertRaises(ValueError):
                m.constraint_slots('single', bad)
        with self.assertRaises(ValueError):
            m.calldata_word_slot(bytes(32), 2 ** 64 - 1)
        with self.assertRaises(ValueError):
            m.namespace('01')
        with self.assertRaises(ValueError):
            m.constraint_slots('unknown', 0)

    def test_source_bytes_match_github_blobs(self):
        for row in json.loads((HERE / 'SOURCES.json').read_text())['sources']:
            data = (HERE / row['path']).read_bytes()
            digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            with self.subTest(path=row['path']):
                self.assertEqual(digest, row['git_blob_sha'])
                self.assertEqual(len(data), row['size_bytes'])


if __name__ == '__main__':
    unittest.main()
