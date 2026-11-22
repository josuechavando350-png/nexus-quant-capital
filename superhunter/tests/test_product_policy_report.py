from copy import deepcopy
import unittest

from superhunter import product_policy_report as report
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json


class PublicPrincipalReportTests(unittest.TestCase):
    def setUp(self):
        self.policies = report.iam_inputs()['policies']
        self.archive = strict_json(read_artifact(report.ROOT, report.SENTRY_REPORT))

    def test_five_reviewed_identity_policies_have_no_resource_principal(self):
        self.assertEqual(report.sha(canonical(self.policies)), report.OWNED_SHA)
        states = report.sentry_states(self.policies, self.archive)
        self.assertEqual(set(states), {'denied', 'permissions', 'readonly', 'unknown', 'wildcard'})
        self.assertNotEqual(states['permissions'], states['readonly'])
        for policy in self.policies.values():
            for stmt in report.statements(policy):
                self.assertEqual(stmt['Resource'], '*')
                self.assertNotIn('Principal', stmt)

    def test_misbound_or_missing_sentry_observation_rejected(self):
        self.archive['observations']['denied'], self.archive['observations']['readonly'] = (
            self.archive['observations']['readonly'], self.archive['observations']['denied'])
        with self.assertRaisesRegex(EvidenceError, 'another input'):
            report.sentry_states(self.policies, self.archive)
        self.archive['observations'].pop('unknown')
        with self.assertRaisesRegex(EvidenceError, 'cover these inputs'):
            report.sentry_states(self.policies, self.archive)

    def test_missing_effect_action_or_resource_fails_closed(self):
        for field in ('Action', 'Effect', 'Resource'):
            policy = deepcopy(self.policies['readonly'])
            policy['Statement'][0].pop(field)
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                report.statements(policy)

    def test_resource_policy_requires_explicit_principal(self):
        with self.assertRaisesRegex(EvidenceError, 'missing its principal'):
            report.statements(self.policies['readonly'], resource_policy=True)

    def test_unsupported_or_empty_principal_not_classified_as_private(self):
        for field, value in [('Principal', {}), ('Principal', {'unknown': '*'}), ('NotPrincipal', '*'),
                             ('Condition', {}), ('Condition', {'Equals': {'String': []}})]:
            policy = deepcopy(self.policies['wildcard'])
            policy['Statement'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(EvidenceError):
                report.statements(policy)

    def test_incomplete_or_extra_reference_case_rejected(self):
        table = '\n'.join('{filename: "sample-%d.json", want: false},' % n for n in range(8))
        source = '\n'.join('func Test%s(t *testing.T) {\n%s\nactual := policy.%s()\n}' % (fn, table, fn)
                           for fn in ('IsPublic', 'IsConditionallyPublic'))
        self.assertEqual(len(report.upstream_expectations(source)), 8)
        for modified in [source.replace('sample-7', 'sample-6', 1), source.replace('sample-7', 'extra-case', 1),
                         source.replace('actual := policy.IsPublic()', 'actual := false')]:
            with self.assertRaises(EvidenceError):
                report.upstream_expectations(modified)
