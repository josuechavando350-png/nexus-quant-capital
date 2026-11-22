"""Check the pinned policy scope and the separate resource-pair comparison."""
import unittest

from superhunter import product_manifest_resources as domain

RULES = {'cpu': 'requests', 'memory': 'limits'}


def workload(*app, init=(), ephemeral=()):
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'spec': {'template': {'spec': {
        'containers': list(app), 'initContainers': list(init), 'ephemeralContainers': list(ephemeral)}}}}


class ManifestResourceTests(unittest.TestCase):
    def test_checks_do_not_infer_request_from_limit_or_reciprocal(self):
        app = {'resources': {'limits': {'cpu': '100m'}, 'requests': {'memory': '64Mi'}}}
        v = domain.summarize([workload(app)], RULES)
        self.assertEqual(v['policy_diagnostics'], {'cpu': 1, 'memory': 1})
        self.assertEqual(v['request_limit_pairs_compared'], 0)

    def test_exact_positive_resource_pairs_do_not_generate_diagnostics(self):
        app = {'resources': {'limits': {'cpu': '1', 'memory': '1Gi'},
                             'requests': {'cpu': '1000m', 'memory': '1024Mi'}}}
        v = domain.summarize([workload(app)], RULES)
        self.assertEqual(v['policy_diagnostics'], {'cpu': 0, 'memory': 0})
        self.assertEqual(v['request_limit_pairs_compared'], 2)
        self.assertEqual(v['container_resource_fields'], {'all_four': 1})

    def test_exact_zero_missing_and_ephemeral_cases_are_counted(self):
        app = {'resources': {'limits': {'memory': '0Mi'}, 'requests': {'cpu': '0m'}}}
        v = domain.summarize([workload(app, init=({},), ephemeral=({},))], RULES)
        self.assertEqual(v['policy_diagnostics'], {'cpu': 3, 'memory': 3})
        self.assertEqual(v['containers'], {'containers': 1, 'initContainers': 1, 'ephemeralContainers': 1})

    def test_positive_declared_pair_can_still_exceed_resource_cap(self):
        app = {'resources': {'limits': {'memory': '1023Mi'}, 'requests': {'memory': '1Gi'}}}
        with self.assertRaisesRegex(ValueError, 'exceeds limit'):
            domain.summarize([workload(app)], RULES)

    def test_bad_or_unsupported_quantities_fail_closed(self):
        for field, value in [('cpu', '-1m'), ('memory', '1m'), ('cpu', '1Mi'), ('cpu', True),
                             ('cpu', '0.001m'), ('memory', None), ('memory', '5MB')]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                domain.resource_value(field, value)
        self.assertEqual(domain.resource_value('cpu', '0.5'), 500)
        self.assertEqual(domain.resource_value('memory', '1.5Gi'), 1536 * 1024 ** 2)

    def test_empty_app_and_unsupported_kinds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no app containers'):
            domain.summarize([workload(init=({},))], RULES)
        with self.assertRaisesRegex(ValueError, 'workload kind'):
            domain.summarize([{**workload({}), 'kind': 'Service'}], RULES)
