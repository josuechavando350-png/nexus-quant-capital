"""Check the boundaries between direct release dependencies, development-only declarations, and unknowns."""
import copy
import unittest

from superhunter import product_development_manifest as review


class DevelopmentManifestTests(unittest.TestCase):
    @staticmethod
    def fixtures():
        rules = {'is_fuzz_manifest': ['package', 'metadata', 'cargo-fuzz'], 'collect_targets': ['bin', 'name']}
        public_doc = {'package': {'name': 'distribution', 'license': 'MIT'}, 'dependencies': {'shared': '1'},
                      'dev-dependencies': {'also_tested': '2'}}
        development_doc = {'package': {'name': 'checks', 'publish': False, 'metadata': {'cargo-fuzz': True}},
                           'dependencies': {'shared': '1', 'also_tested': '2', 'development-only': '1'},
                           'bin': [{'name': 'fixed-test-binary'}]}
        def result(doc, path, pid):
            pkg = doc['package']
            deps = [{'name': name, 'kind': kind, 'target': target, 'rename': alias}
                    for target, kind, name, alias in review.declared_dependencies(doc)]
            return {'resolve': None, 'workspace_root': path, 'workspace_members': [pid], 'workspace_default_members': [pid],
                    'packages': [{'name': pkg['name'], 'manifest_path': path + '/Cargo.toml', 'id': pid,
                                  'publish': [] if pkg.get('publish') is False else None, 'license': pkg.get('license'),
                                  'metadata': pkg.get('metadata'), 'dependencies': deps,
                                  'targets': [{'kind': ['bin'], 'name': b['name']} for b in doc.get('bin', [])]}]}
        return (rules, result(public_doc, '/src', 'p'), result(development_doc, '/src/aux', 'q'),
                public_doc, development_doc, '/src/Cargo.toml', '/src/aux/Cargo.toml')

    def test_marker_requires_boolean_true_at_exact_upstream_location(self):
        path = self.fixtures()[0]['is_fuzz_manifest']
        for value in (0, 1, False, 'true', None):
            self.assertFalse(review.marked({'package': {'metadata': {'cargo-fuzz': value}}}, path))
        self.assertFalse(review.marked({'metadata': {'cargo-fuzz': True}}, path))
        self.assertTrue(review.marked({'package': {'metadata': {'cargo-fuzz': True}}}, path))

    def test_dep_sets_distinguish_three_license_review_queues(self):
        data = review.review_pair(*self.fixtures())
        self.assertEqual(data['marked_direct_normal_also_in_release_normal'], ['shared'])
        self.assertEqual(data['marked_direct_normal_only_in_release_non_normal'], ['also_tested'])
        self.assertEqual(data['marked_direct_normal_absent_from_release_direct_declarations'], ['development-only'])
        self.assertIsNone(data['development_declared_license'])
        self.assertEqual(data['license_review'], 'pending')
        self.assertNotIn('fixed-test-binary', str(data))

    def test_marker_alone_does_not_override_workspace_membership_or_publishing(self):
        args = self.fixtures()
        args[1]['workspace_members'].append('q')
        with self.assertRaisesRegex(review.EvidenceError, 'not isolated'):
            review.review_pair(*args)
        args = self.fixtures()
        del args[4]['package']['publish']
        args[2]['packages'][0]['publish'] = None
        with self.assertRaisesRegex(review.EvidenceError, 'not isolated'):
            review.review_pair(*args)

    def test_missing_binary_witness_cannot_certify_development_scope(self):
        args = self.fixtures()
        args[2]['packages'][0]['targets'].clear()
        with self.assertRaisesRegex(review.EvidenceError, 'binary declarations'):
            review.review_pair(*args)

    def test_renamed_target_scoped_dependencies_and_reader_disagreement(self):
        doc = {'target': {'cfg(unix)': {'dependencies': {'renamed': {'package': 'real', 'version': '1'}}}}}
        self.assertEqual(review.declared_dependencies(doc), {('cfg(unix)', None, 'real', 'renamed'): 1})
        args = copy.deepcopy(self.fixtures())
        args[1]['packages'][0]['dependencies'][0]['kind'] = 'build'
        with self.assertRaisesRegex(review.EvidenceError, 'declarations differ'):
            review.review_pair(*args)
