import json
from pathlib import Path
import tempfile
import unittest

from superhunter import product_review as product
from superhunter import product_supply_review as supply
from superhunter.safe_io import canonical, read_artifact, write_new_bundle


class SupplyTests(unittest.TestCase):
    def setUp(self):
        self.catalog = product.repositories()
        self.snapshot = read_artifact(product.ROOT, supply.IDENTITIES)
        self.catalog_bytes = read_artifact(product.ROOT, product.CATALOG)

    def test_200_ids_and_distinct_license_outcomes(self):
        rows = supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes)
        self.assertEqual(len(set(r['github_id'] for r in rows)), 200)
        self.assertEqual(sum(r['label_comparison'] == 'UNDETERMINED' for r in rows), 33)
        self.assertEqual(sum(r['label_comparison'] == 'DIFFERENT_TEXT' for r in rows), 18)
        self.assertEqual(sum(r['label_comparison'] == 'SAME_TEXT' for r in rows), 149)
        self.assertEqual(rows[135]['full_name'], 'anchore/syft')

    def test_one_modified_github_identity_or_mismatched_catalog_is_rejected(self):
        data = json.loads(self.snapshot)
        data['repositories'][0]['github_id'] = data['repositories'][1]['github_id']
        with self.assertRaisesRegex(ValueError, 'snapshot digest'):
            supply.identity_rows(canonical(data), self.catalog, self.catalog_bytes)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            supply.identity_rows(self.snapshot, list(reversed(self.catalog)), self.catalog_bytes)
        with self.assertRaisesRegex(ValueError, 'catalog digest'):
            supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes+b' ')

    def test_python_verification_binds_every_byte_and_claims_no_signature(self):
        materials = {'product/review.json': b'one', 'identities.json': b'two'}
        link = supply.python_link(materials, b'three')
        self.assertEqual(link['signatures'], [])
        self.assertEqual(set(link['signed']['materials']), set(materials))
        self.assertEqual(link['signed']['products']['supply.json']['sha256'], product.sha(b'three'))
        self.assertNotEqual(link, supply.python_link({**materials, 'identities.json': b'Two'}, b'three'))

    def test_wrong_owasp_revision_fails_before_interpretation(self):
        with self.assertRaisesRegex(ValueError, 'OWASP data differs'):
            supply.guidance({'asvs.csv': b'altered', 'asvs-guides.md': b''}, {})

    def test_missing_artifact_fails_even_with_a_valid_complete_marker(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)/'evidence'
            write_new_bundle(root, {'supply.json': b'{}', 'supply.link': b'{}'})
            with self.assertRaisesRegex(ValueError, 'incomplete or altered'):
                supply.verify(root, {}, {})

    def test_metadata_alone_cannot_promote_a_candidate_to_an_integration(self):
        rows = supply.identity_rows(self.snapshot, self.catalog, self.catalog_bytes)
        report = {'repositories': self.catalog, 'packages': [], 'census_graph': {'nodes': []},
                  'conflicting_python_pins': {}, 'tools': {}, 'minimum_python_pin_groups': 1,
                  'profile_whose_isolation_resolves_all_observed_pin_conflicts': None}
        index = product.ProductIndex(report, supply=({'source_roles': {}, 'controls': []}, rows))
        self.assertIsNone(index.lookup('crytic/slither')['supply_role'])
        self.assertNotIn('evidence', index.lookup('crytic/slither'))
        self.assertNotIn('github_identity', report['repositories'][0])
