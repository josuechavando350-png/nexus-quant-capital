import unittest

from superhunter import product_report_taxonomy as taxonomy
from superhunter.product_reasoning import EvidenceError


class ReportTaxonomyTests(unittest.TestCase):
    def example(self):
        tag = 'WSTG-INFO-02'
        old = 'WSTG-INPV-01'
        return {'classifications': {'used': {'wstg': [tag, old]}, 'unused': {'wstg': ['WSTG-INFO-01']}},
                'vulnerabilities': {'used': [{'wstg': [tag, old], 'path': 'private-canary'}], 'unused': []},
                'additionals': {}, 'anomalies': {}, 'suppressed_findings': {}}

    def test_distinguishes_declared_codes_from_citations_and_editions(self):
        result = taxonomy.summarize(self.example(), {'WSTG-INFO-02'}, {'WSTG-INFO-02', 'WSTG-INPV-01'})
        self.assertEqual(result['edition_membership'], {'both': ['WSTG-INFO-02'],
                         'release_4_2_only': ['WSTG-INPV-01'], 'current_only': [], 'neither': []})
        self.assertEqual(result['classified_ids'], 3)
        self.assertEqual(result['citations_in_records'], {'WSTG-INPV-01': 1, 'WSTG-INFO-02': 1})
        self.assertNotIn('canary', str(result))

    def test_unresolved_citation_is_retained(self):
        result = taxonomy.summarize(self.example(), set(), set())
        self.assertEqual(result['edition_membership']['neither'], ['WSTG-INFO-02', 'WSTG-INPV-01'])

    def test_unclassified_or_duplicate_citation_fails(self):
        for codes in (['WSTG-SESS-01'], ['WSTG-INFO-02'] * 2, ['WSTG-INFO-x2']):
            with self.subTest(codes=codes), self.assertRaises(EvidenceError):
                data = self.example()
                data['vulnerabilities']['used'][0]['wstg'] = codes
                taxonomy.summarize(data, set(), set())

    def test_suppressed_records_require_an_explicit_format(self):
        data = self.example()
        data['suppressed_findings'] = {'unexpected': [{}]}
        with self.assertRaises(EvidenceError):
            taxonomy.summarize(data, set(), set())

    def test_guide_rejects_citation_in_wrong_category(self):
        with self.assertRaises(EvidenceError):
            taxonomy.current_codes(b'{"categories":{"group":{"id":"WSTG-SESS","tests":[{"id":"WSTG-INFO-02"}]}}}')
