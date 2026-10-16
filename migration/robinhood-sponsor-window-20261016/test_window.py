import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import admission_window as policy
import audit_window as audit


class WindowPolicyTests(unittest.TestCase):
    def test_short_window_never_satisfies_reference_buffer(self):
        for now in (1000, 1001):
            result = policy.compare(1000, 1001, now)
            self.assertTrue(result['entrypoint_v07_time_check'])
            self.assertFalse(result['rundler_reference_simulation_time_check'])
            self.assertFalse(result['rundler_reference_builder_time_check'])

    def test_exact_twenty_remaining_is_builder_only(self):
        result = policy.compare(1000, 1031, 1011)
        self.assertFalse(result['rundler_reference_simulation_time_check'])
        self.assertTrue(result['rundler_reference_builder_time_check'])
        self.assertTrue(policy.compare(1000, 1031, 1010)['rundler_reference_simulation_time_check'])
        self.assertFalse(policy.compare(1000, 1031, 1012)['rundler_reference_builder_time_check'])

    def test_future_authorization_is_not_admissible(self):
        result = policy.compare(1000, 1031, 999)
        self.assertTrue(all(not value for key, value in result.items() if key.endswith('_check')))

    def test_entrypoint_endpoint_is_inclusive(self):
        self.assertTrue(policy.compare(1000, 1031, 1031)['entrypoint_v07_time_check'])
        self.assertFalse(policy.compare(1000, 1031, 1032)['entrypoint_v07_time_check'])

    def test_unbounded_and_invalid_inputs_fail_closed(self):
        for args in [(1000, 0, 1000), (0, 31, 0), (1000, 1061, 1000),
                     (1001, 1000, 1000), (1000, 1031, True), (1000, 1031, 1.1),
                     (1000, 1031, -1), (1000, 1031, 1 << 48)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                policy.compare(*args)

    def test_reference_is_pinned_and_not_live_admission(self):
        ref = audit.read(audit.HERE / 'evidence/rundler-reference.json')
        self.assertEqual(ref['commit'], '9852824c649fbe56fea9712b26d4188bc25e38fc')
        self.assertEqual(ref['buffer_seconds'], policy.BUFFER_SECONDS)
        self.assertFalse(ref['live_robinhood_provider_version_authenticated'])
        self.assertFalse(policy.compare(1000, 1031, 1000)['full_bundler_admission_proven'])


class CapturedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = audit.HERE / 'evidence'
        cls.data = audit.read(cls.evidence / 'local/simulation-input.json')
        cls.original = audit.read(audit.PRIOR / 'evidence/fee-variant/simulation-input.json')
        cls.good = audit.result(cls.evidence / 'nitro/02-valid-after.json')
        cls.expired = audit.result(cls.evidence / 'nitro/04-expired.json')

    def test_full_captured_audit_and_no_revenue_claim(self):
        report = audit.audit(self.evidence)
        self.assertEqual(report['new_read_only_rpc_calls'], 12)
        self.assertEqual(report['net_surplus_before_costs_usdg'], '32.060665')
        self.assertFalse(report['realized_nqc_revenue'])
        self.assertFalse(report['production_bundler_admission_proven'])
        self.assertEqual(report['variants'][1]['nitro']['expired']['sponsor_charge_wei'], 0)
        self.assertGreater(report['variants'][1]['nitro']['expired']['network_fee_wei'], 0)

    def test_protocol_state_override_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['state_overrides'][audit.route.MORPHO] = {'balance': '0x0'}
        with self.assertRaisesRegex(ValueError, 'overridden account'):
            audit.validate_fixture(data, self.original)

    def test_other_nqc_fixture_change_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['state_overrides'][data['addresses']['executor']]['code'] = '0x'
        with self.assertRaisesRegex(ValueError, 'non-paymaster'):
            audit.validate_fixture(data, self.original)

    def test_signed_operation_change_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['transaction']['data'] += '00'
        with self.assertRaisesRegex(ValueError, 'operation or fixture'):
            audit.validate_fixture(data, self.original)

    def test_window_mismatch_in_return_data_is_rejected(self):
        trace = copy.deepcopy(self.good)
        frame = next(f for f in audit.flatten(trace) if f.get('input', '').startswith(audit.VALIDATE))
        raw = bytearray.fromhex(frame['output'][2:]); raw[63] = 1
        frame['output'] = '0x' + raw.hex()
        with self.assertRaisesRegex(ValueError, 'validation window'):
            audit.check_validation(trace, self.data)

    def test_nonempty_context_is_rejected(self):
        trace = copy.deepcopy(self.good)
        frame = next(f for f in audit.flatten(trace) if f.get('input', '').startswith(audit.VALIDATE))
        frame['output'] = frame['output'][:-2] + '01'
        with self.assertRaisesRegex(ValueError, 'empty paymaster context'):
            audit.check_validation(trace, self.data)

    def test_root_revert_alone_does_not_prove_route_was_not_called(self):
        trace = copy.deepcopy(self.expired)
        trace.setdefault('calls', []).append({'to': audit.route.MORPHO, 'error': 'execution reverted'})
        with self.assertRaisesRegex(ValueError, 'route executed'):
            audit.check_expired(trace, self.data)

    def test_sponsor_charge_must_reconcile_with_native_balances(self):
        fee, _ = audit.operation(self.good, True)
        diff = audit.result(self.evidence / 'nitro/05-valid-state-diff.json')
        fee['sponsor_charge_wei'] += 1
        with self.assertRaisesRegex(ValueError, 'EntryPoint balance'):
            audit.verify_diff(diff, self.data, fee, True)

    def test_expired_state_must_preserve_paymaster(self):
        fee = audit.check_expired(self.expired, self.data)
        diff = audit.result(self.evidence / 'nitro/06-expired-state-diff.json')
        diff['post'][self.data['addresses']['paymaster']] = {'balance': '0x0'}
        with self.assertRaisesRegex(ValueError, 'sponsorship or protocol'):
            audit.verify_diff(diff, self.data, fee, False)

    def test_response_tampering_is_detected_before_analysis(self):
        _, _, header, _, _, _ = audit.load_capture(audit.OLD / 'evidence/provider-capture')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'nitro'
            shutil.copytree(self.evidence / 'nitro', folder)
            with (folder / '01-not-due.json').open('a') as f:
                f.write(' ')
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                audit.authenticate_requests(folder, audit.read(self.evidence / 'local/nitro-plan.json'), self.data, header)


if __name__ == '__main__':
    unittest.main()
