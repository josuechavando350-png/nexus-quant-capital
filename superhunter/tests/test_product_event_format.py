"""Check layout ambiguity and structural acceptance using only fixed unsigned data words."""
import unittest

from superhunter import product_event_format as event
from superhunter.safe_io import canonical

TOPIC = '0x' + 'cd' * 32
TOKEN_STANDARDS = {'IERC20': (True, True, False), 'IERC721': (True, True, True)}


def word(n):
    return '0x' + n.to_bytes(32, 'big').hex()


def log(topics, *data):
    return {'topics': [TOPIC, *[word(value) for value in topics]],
            'data': '0x' + ''.join(word(value)[2:] for value in data)}


def doc(row, mask):
    return {'logs': [row], 'signature': event.SIGNATURE, 'expectedIndexed': mask,
            'transactionHash': 'MUST_NOT_BE_PUBLISHED'}


class EventFormatTests(unittest.TestCase):
    def test_single_record_can_match_three_wire_layouts(self):
        record = log((3, 5), 7)
        out = event.check_fixture(doc(record, None), TOPIC, TOKEN_STANDARDS)
        self.assertTrue(out['unlabelled_layout_ambiguous'])
        self.assertEqual(out['plausible_index_masks'], 3)
        self.assertEqual(out['compatible_declared_interfaces'], ['IERC20'])
        self.assertNotIn(b'MUST_NOT_BE_PUBLISHED', canonical(out))

    def test_unknown_layout_cannot_promote_to_proven(self):
        with self.assertRaisesRegex(ValueError, 'unique'):
            event.check_fixture(doc(log((3, 5), 7), [True, True, False]), TOPIC, TOKEN_STANDARDS)

    def test_three_indexed_words_and_zero_uint_are_valid(self):
        out = event.check_fixture(doc(log((0, 0, 0)), [True]*3), TOPIC, TOKEN_STANDARDS)
        self.assertEqual(out['compatible_declared_interfaces'], ['IERC721'])
        self.assertEqual(out['plausible_index_masks'], 1)

    def test_bad_topic_data_alignment_or_word_count_fails(self):
        good = log((1, 2), 3)
        for row in ({**good, 'topics': [word(5), *good['topics'][1:]]}, {**good, 'data': '0x01'},
                    {**good, 'data': '0x'}, {**good, 'topics': [TOPIC, '0x01']}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                event.placements(row, TOPIC)

    def test_overwidth_address_and_false_ambiguity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            event.check_fixture(doc(log((1 << 170, 0, 0)), [True]*3), TOPIC, TOKEN_STANDARDS)
        with self.assertRaisesRegex(ValueError, 'unique'):
            event.check_fixture(doc(log((0, 0, 0)), None), TOPIC, TOKEN_STANDARDS)

    def test_declaration_requires_a_single_matching_event(self):
        src = 'event Transfer(address indexed from, address indexed to, uint256 value);'
        self.assertEqual(event.declaration(src), TOKEN_STANDARDS['IERC20'])
        self.assertEqual(event.declaration(src.replace('uint256 value', 'uint256 indexed id')), TOKEN_STANDARDS['IERC721'])
        for bad in (src + '\n' + src, src.replace('uint256', 'bytes32'), src.replace('indexed', 'nonsense')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                event.declaration(bad)
