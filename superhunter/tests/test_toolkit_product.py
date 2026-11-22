import unittest

from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ProductIndex, repositories
from superhunter.toolkit_index import ToolkitIndex
from superhunter.toolkit_product import join_results, prior_session
from superhunter.product_sources import toolkit_sources


class ToolkitProductTests(unittest.TestCase):
    def setUp(self):
        _, self.rows = prior_session()
        self.solidity = next(row for row in self.rows if row['repository'] == 'argotorg/solidity')
        self.tools = {'ethereum/solidity': {'path': 'upstream/solidity', 'commit': self.solidity['commit'],
                                            'tree': self.solidity['tree']}}
        self.ops = {'ethereum/solidity': ('engine', 'local test operation', {'tests': 1})}
        self.index = ToolkitIndex(ProductIndex({'repositories': repositories(), 'packages': [],
                                   'census_graph': {'nodes': []}, 'conflicting_python_pins': {}, 'tools': {},
                                   'minimum_python_pin_groups': 2,
                                   'profile_whose_isolation_resolves_all_observed_pin_conflicts': 'owned-spec-evm'}))

    def join(self):
        return join_results(self.rows, 'historical', self.tools, self.ops, 'subject', {})

    def test_alias_does_not_create_a_second_repository(self):
        session = self.join()
        self.assertEqual(session['unique_repositories'], len(self.rows))
        self.index.attach_toolkit(session)
        row = self.index.lookup('ethereum/solidity')
        self.assertEqual(row, self.index.lookup('ARGOTORG/SOLIDITY'))
        self.assertEqual(row['catalog_id'], self.solidity['id'])
        self.assertEqual(row['historical_operations'], self.solidity['session_operations'])
        self.assertEqual(row['toolkit']['repository'], 'ethereum/solidity')
        self.assertEqual(self.index.lookup('toolkit-matrix'), session)

    def test_mismatched_tree_or_missing_operation_fails(self):
        self.tools['ethereum/solidity']['tree'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'tree differs'):
            self.join()
        self.ops.clear()
        with self.assertRaisesRegex(ValueError, 'operations'):
            self.join()

    def test_bundle_identity_disagreement_blocks_attachment(self):
        session = self.join()
        session['repositories'][0]['catalog_id'] += 1
        with self.assertRaisesRegex(EvidenceError, 'identities differ'):
            self.index.attach_toolkit(session)
        with self.assertRaisesRegex(EvidenceError, 'requires'):
            self.index.lookup('toolkit-matrix')

    def test_full_profile_has_twenty_distinct_repositories_and_eight_shared(self):
        sources = toolkit_sources()
        self.tools = {r['repository']: {**r, 'tree': 'new'} for r in sources}
        for repo, tool in self.tools.items():
            shared = next((row for row in self.rows if row['commit'] == tool['commit']), None)
            if shared:
                tool['tree'] = shared['tree']
        self.ops = {name: ('library', 'test operation', {}) for name in self.tools}
        session = self.join()
        self.assertEqual((session['current_repositories'], session['overlapping_repositories'],
                          session['unique_repositories']), (20, 8, 212))
        self.index.attach_toolkit(session)
        for repo in self.tools:
            self.assertEqual(self.index.lookup(repo)['toolkit']['commit'], self.tools[repo]['commit'])
