"""Compare indexed routing with direct prefix matching, including overlap."""
import random
import unittest

from superhunter.quality import _assign_component_rows


def reference(rows, components):
    assigned = {name: [row for row in rows if any(row['id'].startswith(prefix)
                 for prefix in item['tests'])] for name, item in components.items()}
    prefixes = [prefix for item in components.values() for prefix in item['tests']]
    return assigned, any(not any(row['id'].startswith(prefix) for prefix in prefixes) for row in rows)


class QualityRowIndexTests(unittest.TestCase):
    def compare(self, identifiers, components):
        rows = [{'id': name, 'outcome': 'PASS' if index%3 else 'FAIL'} for index, name in enumerate(identifiers)]
        expected = reference(rows, components)
        actual = _assign_component_rows(rows, components)
        self.assertEqual(actual, expected)
        for name in components:
            self.assertEqual([id(row) for row in actual[0][name]], [id(row) for row in expected[0][name]])
        return actual

    def test_overlapping_prefixes_do_not_duplicate_shared_rows(self):
        result = self.compare(['test_a.Suite.first', 'test_b.Suite.second', 'test_a.Other.third'], {
            'shared': {'tests': ['test_a.', 'test_a.Suite.', 'test_a.']},
            'specific': {'tests': ['test_a.Suite.first']},
            'other': {'tests': ['test_b.']}})
        self.assertEqual([len(result[0][key]) for key in ('shared','specific','other')], [2,1,1])
        self.assertFalse(result[1])

    def test_broad_and_empty_prefixes_keep_original_meaning(self):
        result = self.compare(['test_a.C.one', 'test_ab.C.two', 'different'], {
            'broad': {'tests': ['test_a']}, 'universal': {'tests': ['']}, 'absent': {'tests': ['never.']}})
        self.assertEqual(len(result[0]['broad']), 2)
        self.assertEqual(len(result[0]['universal']), 3)
        self.assertFalse(result[1])

    def test_dotless_identifiers_leading_dot_and_unmapped_are_preserved(self):
        result = self.compare(['a', '.case', 'a.case', 'unknown.C.test'], {
            'plain': {'tests': ['a']}, 'dotted': {'tests': ['a.']}, 'leading': {'tests': ['.']}})
        self.assertEqual(len(result[0]['plain']), 2)
        self.assertEqual(len(result[0]['dotted']), 1)
        self.assertTrue(result[1])

    def test_duplicate_rows_and_original_order_are_not_normalized_away(self):
        result = self.compare(['test_b.C.z', 'test_a.C.y', 'test_b.C.z', 'test_a.C.x'], {
            'a': {'tests': ['test_a.']}, 'both': {'tests': ['test_a.', 'test_b.']}})
        self.assertEqual(len(result[0]['both']), 4)
        self.assertEqual([r['id'] for r in result[0]['a']], ['test_a.C.y', 'test_a.C.x'])

    def test_seeded_mixed_prefixes_match_direct_reference(self):
        rng = random.Random(20261108)
        identifiers = [f'test_{rng.randrange(30)}.C{rng.randrange(7)}.case_{i}' for i in range(1500)]
        components = {}
        for i in range(60):
            patterns = []
            for _ in range(rng.randrange(1,5)):
                module = rng.randrange(35)
                patterns.append(rng.choice([f'test_{module}', f'test_{module}.', f'test_{module}.C2.']))
            components[f'component_{i}'] = {'tests': patterns}
        self.compare(identifiers, components)


if __name__ == '__main__':
    unittest.main()
