from copy import deepcopy
import unittest

from superhunter import product_policy_catalog as catalog
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import read_artifact, strict_json


class PolicyCatalogTests(unittest.TestCase):
    def setUp(self):
        self.owned = catalog.inputs()['policies']
        self.sentry = strict_json(read_artifact(catalog.ROOT, catalog.SENTRY_REPORT))
        self.levels = {'iam:PassRole': 'Permissions management', 's3:GetObject': 'Read'}
        self.mapping = {'schema_version': '1.0.2', 'service_sdk_mappings': {'s3': ['S3'], 'iam': ['IAM']},
                        'sdk_method_iam_mappings': {
                            'S3.GetObject': [{'action': 's3:GetObject'}],
                            'S3.HeadObject': [{'action': 's3:GetObject', 'conditions': {'op': 'NotExists'}}],
                            'Example.Create': [{'action': 'iam:PassRole'}, {'action': 'iam:PassRole'}]}}

    def report(self):
        return catalog.join(self.owned, self.sentry, self.levels, self.mapping)

    def test_effective_unknown_and_denied_permissions_are_distinct(self):
        r = self.report()
        self.assertEqual(r['cases']['unknown']['included_in_allow_statement'], [])
        self.assertEqual(r['cases']['unknown']['unknown_actions'], ['iam:NQCActionDoesNotExist'])
        self.assertEqual(r['cases']['denied']['defined_actions'], ['iam:PassRole'])
        self.assertEqual(r['cases']['denied']['included_in_allow_statement'], [])
        self.assertEqual(r['cases']['wildcard']['defined_actions'], ['iam:PassRole', 's3:GetObject'])

    def test_cannot_infer_same_named_method_from_a_permission(self):
        r = self.report()['permissions']
        self.assertFalse(r['iam:PassRole']['has_same_named_mapped_method'])
        self.assertEqual(r['iam:PassRole']['sdk_methods_linked'], 1)
        self.assertTrue(r['s3:GetObject']['has_same_named_mapped_method'])
        self.assertEqual(r['s3:GetObject']['sdk_methods_with_mapping_conditions'], 1)
        self.assertIsNone(r['iam:NQCActionDoesNotExist']['defined_access_level'])

    def test_mapping_without_definition_is_rejected(self):
        self.mapping['sdk_method_iam_mappings']['Example.Unknown'] = [{'action': 'iam:NQCActionDoesNotExist'}]
        with self.assertRaisesRegex(EvidenceError, 'absent from the IAM definition'):
            self.report()

    def test_alternate_field_or_different_expansion_is_rejected(self):
        bad = deepcopy(self.mapping)
        bad['sdk_method_iam_mappings']['Example.Create'] = [{'permission': 'iam:PassRole'}]
        with self.assertRaisesRegex(EvidenceError, 'missing explicit'):
            catalog.join(self.owned, self.sentry, self.levels, bad)
        self.levels['iam:PassExtra'] = 'Permissions management'
        with self.assertRaisesRegex(EvidenceError, 'expansion disagree'):
            self.report()

    def test_independent_level_disagreement_is_rejected(self):
        self.levels['iam:PassRole'] = 'Read'
        with self.assertRaisesRegex(EvidenceError, 'access levels disagree'):
            self.report()

    def test_joined_consumers_reject_missing_mismatched_or_public_row(self):
        report = {'identity_policies_sha256': catalog.OWNED_SHA, 'sentry_report_sha256': catalog.SENTRY_SHA,
                  **self.report()}
        cloud = {'identity_policies_sha256': catalog.OWNED_SHA, 'sentry_report_sha256': catalog.SENTRY_SHA,
                 'owned_identity_policies': {k: {'public': False, 'conditional': False, 'statements': 1,
                                                 'action_review': v['sentry_action_review']}
                                             for k, v in report['cases'].items()}}
        verdict = catalog.corroborate(report, cloud)
        digest = verdict.pop('joint_sha256')
        self.assertEqual(digest, catalog.sha(catalog.canonical(verdict)))
        for field, value in [('public', True), ('action_review', 'differs')]:
            mutated = deepcopy(cloud)
            mutated['owned_identity_policies']['readonly'][field] = value
            with self.assertRaises(EvidenceError):
                catalog.corroborate(report, mutated)
        cloud['owned_identity_policies'].pop('readonly')
        with self.assertRaises(EvidenceError):
            catalog.corroborate(report, cloud)
