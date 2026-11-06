"""Finite declarative policy-domain checks, not a real-world exploit benchmark."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import permission_domain as d, permissions, quality
from superhunter.safe_io import canonical, strict_json


class DomainTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.model = d.example_model()
        self.source = self.root/'policy-domain.json'
        self.out = self.root/'evidence'

    def analyze(self):
        return d.analyze_domain(self.model)

    def create(self):
        self.source.write_bytes(canonical(self.model))
        return d.audit_domain(self.source, self.out)

    def reseal(self, name, mutate):
        value = strict_json((self.out/name).read_bytes())
        mutate(value)
        raw = canonical(value)
        (self.out/name).write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_enumerates_entire_four_configuration_domain(self):
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VIOLATION')
        self.assertEqual(result['domain_configurations'], 4)
        self.assertEqual(result['examined_configurations'], 4)
        self.assertEqual(result['violating_configurations'], 3)
        self.assertEqual([w['configuration_index'] for w in result['witnesses']], [1, 2, 3])
        self.assertEqual(result['property_evaluations'], 20)
        self.assertEqual(result['permission_reference_comparisons'], 12)
        self.assertEqual(len({c['assignment_sha256'] for c in result['configurations']}), 4)
        self.assertFalse(result['vulnerability_confirmed'])

    def test_corrected_policy_verified_only_in_declared_domain(self):
        self.model = d.example_model(corrected=True)
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VERIFIED')
        self.assertTrue(result['proven_for_declared_domain'])
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['violating_configurations'], 0)
        for key in ('live_enforcement_verified', 'production_reachability_verified', 'vulnerability_confirmed', 'producer_authenticated', 'smt_used', 'solidity_analyzed'):
            self.assertIs(result[key], False)

    def test_budget_never_counts_as_verified(self):
        self.model['max_states'] = 1
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_INCONCLUSIVE')
        self.assertEqual(result['unexamined_configurations'], 3)
        self.assertEqual(result['violating_configurations'], 0)
        self.assertFalse(result['proven_for_declared_domain'])
        self.assertIn('STATE_BUDGET', result['bound_reasons'])

    def test_partial_search_can_demonstrate_violation_but_not_completeness(self):
        self.model['max_states'] = 2
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VIOLATION')
        self.assertEqual(result['violating_configurations'], 1)
        self.assertFalse(result['coverage_complete'])

    def test_no_properties_is_not_proof(self):
        for name in ('assertions', 'revocations', 'separation_rules'):
            self.model['policy'][name] = []
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_INCONCLUSIVE')
        self.assertEqual(result['property_evaluations'], 0)
        self.assertFalse(result['proven_for_declared_domain'])
        self.assertIn('NO_PROPERTIES', result['bound_reasons'])

    def test_zero_variables_is_single_configuration_not_empty_domain(self):
        self.model['variables'] = []
        result = self.analyze()
        self.assertEqual(result['examined_configurations'], 1)
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VERIFIED')

    def test_work_budget_never_silently_completes(self):
        with patch.object(d, 'MAX_WORK', 1):
            result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_INCONCLUSIVE')
        self.assertIn('WORK_BUDGET', result['bound_reasons'])
        self.assertEqual(result['examined_configurations'], 1)

    def test_revoking_a_deny_role_can_change_effective_permission(self):
        p = self.model['policy']
        p['roles']['blocked'] = {'inherits': [], 'allow': [], 'deny': ['approve']}
        p['users']['alice']['roles'].append('blocked')
        self.model['variables'] = [{'user': 'alice', 'role': 'approver'}, {'user': 'alice', 'role': 'blocked'}]
        result = self.analyze()
        self.assertEqual([w['configuration_index'] for w in result['witnesses']], [3])
        self.assertEqual(result['violating_configurations'], 1)

    def test_declared_revocation_obligation_checked(self):
        p = self.model['policy']
        p['roles']['blocked'] = {'inherits': [], 'allow': [], 'deny': ['approve']}
        p['users']['alice']['roles'] = ['approver', 'blocked']
        p['revocations'].append({'id': 'remove.block', 'user': 'alice', 'remove_roles': ['blocked'], 'must_deny': ['approve']})
        self.model['variables'] = []
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VIOLATION')
        self.assertIn('revocation:remove.block', result['witnesses'][0]['violated_properties'])

    def test_conditional_revocation_coverage_not_faked(self):
        self.model['variables'] = [{'user': 'bob', 'role': 'approver'}]
        result = self.analyze()
        slot = result['property_coverage']['revocation:remove.approver']
        self.assertEqual(slot, {'evaluated': 1, 'failed': 0, 'not_applicable': 1})
        self.assertEqual(result['assignment_reference_comparisons'], 2)

    def test_disabled_users_do_not_gain_permissions(self):
        self.model['policy']['users']['alice']['disabled'] = True
        self.model['variables'] = [{'user': 'alice', 'role': 'approver'}]
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VERIFIED')

    def test_128_distinct_configurations_are_all_checked(self):
        self.model = d.example_model(corrected=True)
        for i in range(5):
            role = 'local' + str(i)
            self.model['policy']['roles'][role] = {'inherits': [], 'allow': [], 'deny': []}
            self.model['variables'].append({'user': 'alice', 'role': role})
        self.model['max_states'] = 128
        result = self.analyze()
        self.assertEqual(result['status'], 'POLICY_DOMAIN_VERIFIED')
        self.assertEqual(len({c['assignment_sha256'] for c in result['configurations']}), 128)
        self.assertEqual(result['property_evaluations'], 640)

    def test_witness_limit_does_not_hide_failure_count(self):
        for i in range(4):
            role = 'local' + str(i)
            self.model['policy']['roles'][role] = {'inherits': [], 'allow': [], 'deny': []}
            self.model['variables'].append({'user': 'alice', 'role': role})
        self.model['max_states'] = 64
        result = self.analyze()
        self.assertEqual(result['violating_configurations'], 48)
        self.assertEqual(len(result['witnesses']), 16)
        self.assertTrue(result['witnesses_truncated'])
        self.assertEqual(len(result['configurations']), 64)

    def test_deterministic_and_input_not_modified(self):
        before = deepcopy(self.model)
        one = self.analyze()
        self.assertEqual(before, self.model)
        self.assertEqual(canonical(one), canonical(self.analyze()))

    def test_permission_algorithm_disagreement_blocks_output(self):
        original = permissions._reference
        def wrong(policy, user):
            result = original(policy, user)
            result['allowed'] = ['imaginary']
            return result
        with patch.object(permissions, '_reference', side_effect=wrong), self.assertRaisesRegex(ValueError, 'PERMISSION_DISAGREEMENT'):
            self.create()
        self.assertFalse(self.out.exists())

    def test_enumerator_disagreement_blocks_output(self):
        with patch.object(d, '_reference_assignment', return_value={}), self.assertRaisesRegex(ValueError, 'ENUMERATION_DISAGREEMENT'):
            self.create()
        self.assertFalse(self.out.exists())

    def test_types_and_limits_fail_closed(self):
        for field, value in [('schema_version', True), ('max_states', True), ('max_states', 0), ('max_states', 4097), ('variables', {})]:
            with self.subTest(field=field, value=value):
                model = deepcopy(self.model); model[field] = value
                with self.assertRaises(ValueError): d.analyze_domain(model)

    def test_duplicate_or_unknown_variables_rejected(self):
        for variables in ([self.model['variables'][0]]*2, [{'user': 'nobody', 'role': 'approver'}], [{'user': 'alice', 'role': 'missing'}]):
            with self.subTest(variables=variables):
                model = deepcopy(self.model); model['variables'] = variables
                with self.assertRaises(ValueError): d.analyze_domain(model)

    def test_cycles_rejected_by_existing_policy_validator(self):
        self.model['policy']['roles']['reader']['inherits'] = ['approver']
        with self.assertRaisesRegex(ValueError, 'HIERARCHY_CYCLE'): self.analyze()

    def test_real_native_audit_is_used(self):
        native = d.load_components()
        original = native.audit.AuditLog.append
        events = []
        def append(instance, event, data):
            events.append(event)
            return original(instance, event, data)
        with patch.object(native.audit.AuditLog, 'append', append): self.create()
        self.assertEqual(events, ['domain.start', 'domain.coverage', 'domain.complete'])

    def test_reverification_after_input_removed(self):
        result = self.create()
        self.source.unlink()
        self.assertEqual(d.verify_domain(self.out), result)

    def test_raw_input_preserved_and_private(self):
        self.source.write_text(json.dumps(self.model, indent=4) + '\n')
        raw = self.source.read_bytes()
        d.audit_domain(self.source, self.out)
        self.assertEqual((self.out/'model.json').read_bytes(), raw)
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        for path in self.out.iterdir(): self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_resealed_false_approval_rejected(self):
        self.create()
        self.reseal('analysis.json', lambda x: x.update(status='POLICY_DOMAIN_VERIFIED', proven_for_declared_domain=True))
        with self.assertRaisesRegex(ValueError, 'RECALCULATION_MISMATCH'): d.verify_domain(self.out)

    def test_resealed_coverage_omission_rejected(self):
        self.create()
        self.reseal('analysis.json', lambda x: x['configurations'].pop())
        with self.assertRaisesRegex(ValueError, 'RECALCULATION_MISMATCH'): d.verify_domain(self.out)

    def test_resealed_different_model_rejected(self):
        self.create()
        self.reseal('model.json', lambda x: x.update(max_states=1))
        with self.assertRaisesRegex(ValueError, 'RECALCULATION_MISMATCH'): d.verify_domain(self.out)

    def test_semantic_audit_mutation_rejected_even_if_rehashed(self):
        self.create()
        raw = strict_json((self.out/'audit.json').read_bytes())
        raw['entries'][1]['data']['count'] = 999
        native = d.load_components()
        previous = '0'*64
        for row in raw['entries']:
            row['prev_hash'] = previous
            row['hash'] = native.audit.compute_hash(row['index'], row['timestamp'], row['event'], row['data'], previous)
            previous = row['hash']
        self.reseal('audit.json', lambda x: x.update(raw))
        self.reseal('receipt.json', lambda x: x.update(audit_head=previous))
        with self.assertRaisesRegex(ValueError, 'AUDIT_SEMANTICS'): d.verify_domain(self.out)

    def test_stale_code_rejected(self):
        self.create()
        with patch.object(d, '_code_digest', return_value='f'*64), self.assertRaisesRegex(ValueError, 'STALE_CODE'):
            d.verify_domain(self.out)

    def test_bad_file_hash_rejected(self):
        self.create()
        (self.out/'analysis.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH'): d.verify_domain(self.out)

    def test_extra_file_not_silently_exported(self):
        self.create()
        (self.out/'private-extra.txt').write_text('not part of bundle')
        with self.assertRaisesRegex(ValueError, 'FILE_SET'): d.verify_domain(self.out)

    def test_existing_bundle_never_overwritten(self):
        self.create(); before = (self.out/'COMPLETE.json').read_bytes()
        with self.assertRaises(ValueError): self.create()
        self.assertEqual(before, (self.out/'COMPLETE.json').read_bytes())

    def test_symlink_model_rejected(self):
        actual = self.root/'actual.json'; actual.write_bytes(canonical(self.model))
        self.source.symlink_to(actual)
        with self.assertRaises((OSError, ValueError)): d.audit_domain(self.source, self.out)

    def test_no_network_or_child_execution(self):
        with patch('socket.socket', side_effect=AssertionError('network')), patch('subprocess.run', side_effect=AssertionError('process')):
            self.create(); d.verify_domain(self.out)

    def test_summary_does_not_echo_user_identifiers(self):
        result = self.analyze()
        text = d.render_domain(result).decode()
        self.assertNotIn('alice', text)
        self.assertNotIn('bob', text)
        self.assertIn('dominio JSON declarado', text)

    def test_cli_executes_and_separate_process_reverifies(self):
        self.model = d.example_model(corrected=True)
        self.source.write_bytes(canonical(self.model))
        for args in (['check-permission-domain', '--model', str(self.source), '--out', str(self.out)],
                     ['verify-permission-domain', '--bundle', str(self.out)]):
            run = subprocess.run([sys.executable, '-B', '-m', 'superhunter', *args],
                                 cwd=d.ROOT.parent, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            self.assertTrue(json.loads(run.stdout)['proven_for_declared_domain'])
            self.assertFalse(json.loads(run.stdout)['vulnerability_confirmed'])

    def test_cli_inconclusive_not_success(self):
        self.model['max_states'] = 1
        self.source.write_bytes(canonical(self.model))
        with redirect_stdout(io.StringIO()) as output:
            code = d.main(['check-permission-domain', '--model', str(self.source), '--out', str(self.out)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'POLICY_DOMAIN_INCONCLUSIVE')

    def test_cli_failure_not_success(self):
        self.source.write_bytes(canonical(self.model))
        with redirect_stdout(io.StringIO()) as output:
            code = d.main(['check-permission-domain', '--model', str(self.source), '--out', str(self.out)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'POLICY_DOMAIN_VIOLATION')

    def test_cli_diagnostics_do_not_echo_input(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(d.main(['verify-permission-domain', '--bundle', str(self.root/'SECRET_MARKER')]), 2)
        self.assertNotIn('SECRET_MARKER', output.getvalue())
        with redirect_stderr(io.StringIO()) as error, self.assertRaises(SystemExit):
            d.main(['verify-permission-domain', '--bundle', str(self.out), '--unknown', 'SECRET_MARKER'])
        self.assertNotIn('SECRET_MARKER', error.getvalue())

    def test_qa_component_and_mandatory_tests_are_connected(self):
        component = quality.COMPONENTS['permission_domain']
        self.assertEqual(component['files'], ['permission_domain.py'])
        self.assertIn('permissions', component['depends'])
        self.assertTrue(any(x.startswith('test_permission_domain.') for x in quality.REQUIRED_TESTS))
        self.assertFalse(quality.validate_components(quality.source_snapshot()))


if __name__ == '__main__':
    unittest.main()
