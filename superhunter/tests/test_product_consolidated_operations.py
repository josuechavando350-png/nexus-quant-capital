"""Exercise identity accounting with published controls. Replaying receipts is not a new producer run."""
import copy
import json
import unittest
from types import SimpleNamespace

from superhunter import product_batches, product_component_controls, product_matrix
from superhunter.product_native_capabilities import contracts, expected_receipt
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ProductIndex, ROOT, sha
from superhunter.safe_io import canonical
from superhunter.tools.verify_review_115 import unpack

SUPPLY = ROOT / 'superhunter/product_supply'
CAPSTONE = 'capstone-engine/capstone'


def published_index():
    archived = unpack((SUPPLY / 'review-117-session.json').read_bytes())
    docs = [json.loads(line) for line in archived.splitlines()]
    repos = {r['repository'].casefold(): r for r in docs if isinstance(r, dict) and 'catalog_id' in r}
    remote_roots = sum(r['source_inventory']['contents'] is None for r in repos.values())
    return SimpleNamespace(repos=repos, lookup=lambda name: repos[name.casefold()],
                           source_inventory={}, root_declarations={'remote_roots_verified': remote_roots},
                           owned_source_checks={}, census_header={}, geth_header={},
                           source_references={}, score_comparison={}, fork_headers={})


def capstone_proofs():
    observations = json.loads((SUPPLY / 'formats-batch.json').read_bytes())
    return {'component_control_receipt': product_component_controls.validate_group('object-format', observations)[CAPSTONE],
            'native_capability_receipt': expected_receipt('static', CAPSTONE, contracts()['static'])}


class ConsolidatedOperations(unittest.TestCase):
    def test_two_accepted_controls_preserve_both_receipts_and_credit_one_repo(self):
        index = published_index()
        before = product_matrix.build(index)
        self.assertEqual(index.lookup(CAPSTONE)['repository'], CAPSTONE)
        proofs = capstone_proofs()
        index.lookup(CAPSTONE).update(proofs)
        grouped = product_batches.coverage(index)
        after = product_matrix.build(index)
        row = next(row for row in after['rows'] if row['repository'] == CAPSTONE)
        expected = [{'role': 'executable', 'receipt': key, 'evidence_sha256': sha(canonical(proofs[key]))}
                    for key in sorted(proofs)]
        self.assertEqual(row['session_operations'], expected)
        self.assertEqual(grouped['identities'][row['id'] - 1]['session_operations'], expected)
        self.assertEqual((row['receipt'], row['session_evidence_sha256']),
                         (expected[0]['receipt'], expected[0]['evidence_sha256']))
        self.assertEqual(after['end_to_end'], before['end_to_end'] + 1)
        self.assertEqual(after['session_operation_count'], before['session_operation_count'] + 2)
        self.assertEqual(after['session_multi_operation_repositories'], before['session_multi_operation_repositories'] + 1)
        self.assertEqual(len({r['id'] for r in after['rows']}), 200)

    def test_bad_secondary_receipt_is_not_hidden_by_a_passing_primary(self):
        row = {'repository': CAPSTONE, **capstone_proofs()}
        for key in capstone_proofs():
            with self.subTest(key=key):
                bad = copy.deepcopy(row)
                bad[key]['invented_proof'] = True
                with self.assertRaises(EvidenceError):
                    product_batches.receipt(bad)

    def test_ticket_from_another_identity_is_rejected(self):
        row = {'repository': CAPSTONE, **capstone_proofs()}
        row['native_capability_receipt'] = expected_receipt('static', 'cppcheck-opensource/cppcheck', contracts()['static'])
        with self.assertRaises(EvidenceError):
            product_batches.session_operations(row)

    def test_control_bound_to_another_source_revision_is_rejected(self):
        row = {'repository': CAPSTONE, **capstone_proofs(), 'source_inventory': {'revision': '0' * 40}}
        with self.assertRaisesRegex(EvidenceError, 'revision differs'):
            product_batches.session_operations(row)

    def test_unavailable_group_loses_its_operation_only(self):
        row = {'repository': CAPSTONE, **capstone_proofs()}
        del row['component_control_receipt']
        self.assertEqual(product_batches.receipt(row), ('executable', 'native_capability_receipt'))
        del row['native_capability_receipt']
        self.assertEqual(product_batches.session_operations(row), [])

    def test_repeated_names_and_catalog_ids_are_rejected_before_indexing(self):
        first = {'repository': CAPSTONE, 'catalog_id': 132}
        for other in (dict(first, repository=CAPSTONE.upper(), catalog_id=133),
                      dict(first, repository='cppcheck-opensource/cppcheck')):
            with self.subTest(other=other), self.assertRaisesRegex(EvidenceError, 'duplicate'):
                ProductIndex({'repositories': [first, other]})
