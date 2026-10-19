import copy
import unittest

import audit_prefix as audit


class PrefixTests(unittest.TestCase):
    def test_source_bytes(self):
        audit.check_sources()

    def test_reviewed_call_order(self):
        self.assertEqual(len(audit.source_contract()), 12)

    def test_reordered_fee_capture_rejected(self):
        text = audit.SOURCE_PATHS['block'].read_text()
        old = 'err = l2Pricing.CommitMultiGasFees()'
        fee = 'baseFee, err := l2Pricing.BaseFeeWei()'
        text = text.replace(old, '__SWAP__').replace(fee, old).replace('__SWAP__', fee)
        with self.assertRaises(ValueError):
            audit.source_contract({'block': text})

    def test_reversed_copy_rejected(self):
        text = audit.SOURCE_PATHS['fees'].read_text().replace('cur, err := bf.next[i].Get()',
                                                            'cur, err := bf.current[i].Get()')
        with self.assertRaises(ValueError):
            audit.source_contract({'fees': text})

    def test_removed_model_guard_rejected(self):
        text = audit.SOURCE_PATHS['model'].read_text().replace('gasModel != GasModelMultiGasConstraints',
                                                              'gasModel == GasModelMultiGasConstraints')
        with self.assertRaises(ValueError):
            audit.source_contract({'model': text})

    def test_missing_nonce_assignment_rejected(self):
        text = audit.SOURCE_PATHS['storage'].read_text().replace('statedb.SetNonce(account, 1,',
                                                                'statedb.SetNonce(account, 0,')
        with self.assertRaises(ValueError):
            audit.source_contract({'storage': text})

    def test_internal_short_circuit_guard(self):
        text = audit.SOURCE_PATHS['transition'].read_text().replace('if endTxNow {', 'if false {')
        with self.assertRaises(ValueError):
            audit.source_contract({'transition': text})

    def test_conditional_rotation_not_applied_to_single(self):
        self.assertEqual(audit.fee_rotation_layout(61, 2, 0), [])
        self.assertEqual(audit.fee_rotation_layout(49), [])
        layout = audit.fee_rotation_layout(61, None, 1)
        self.assertEqual(len(layout), 9)
        self.assertEqual([r['resource'] for r in layout], list(range(9)))
        self.assertEqual(len({r['write_current'] for r in layout}), 9)
        self.assertTrue(all(r['read_next'] != r['write_current'] for r in layout))

    def test_unknown_parent_model_does_not_use_target_diagnostic(self):
        with self.assertRaises(ValueError):
            audit.fee_rotation_layout(61)
        report = audit.review()
        self.assertTrue(report['parent_pricing_model'].startswith('UNKNOWN'))
        self.assertTrue(report['rotation_layout_is_hypothetical_not_observed'])

    def test_observed_context_fee_is_not_parent_header_fee(self):
        report = audit.review()
        context = report['observed_header_context']
        self.assertEqual(context['parent_header_base_fee_wei'], 67350000)
        self.assertEqual(context['target_header_base_fee_wei'], 67514000)
        self.assertEqual(context['timestamp_delta'], 1)
        self.assertEqual(context['target_gas_limit'], 1 << 50)
        self.assertEqual(context['parent_header_arbos_version'], 61)
        implied = report['source_implied_parent_base_fee_not_a_storage_proof']
        self.assertEqual(implied['expected_wei_if_candidate_semantics_apply'], 67514000)
        self.assertFalse(implied['proof_acquired'])
        self.assertIsNone(implied['diagnostic_value'])

    def test_mutated_observed_header_rejected(self):
        parent, target = [audit.verify.read_json(audit.PREVIOUS / f'inputs/{n}-header.json')['result']
                          for n in ('parent', 'target')]
        mutated = copy.deepcopy(target)
        mutated['baseFeePerGas'] = parent['baseFeePerGas']
        with self.assertRaises(audit.verify.ValidationError):
            audit.header_context(parent, mutated)

    def test_no_completeness_or_admission_from_source_audit(self):
        report = audit.review()
        self.assertFalse(report['complete_access_list'])
        self.assertFalse(report['commercial_admission'])
        self.assertEqual(report['rpc_requests_sent'], 0)
        self.assertEqual(report['historical_proofs_acquired'], 0)
        filtered = report['nonce_assignments_on_open'][1]
        self.assertFalse(filtered['present_in_diagnostic'])
        self.assertFalse(filtered['requested_in_eight_read_plan'])
        self.assertIn('l2_base_fee', report['prefix_candidates_missing_from_eight_read_plan'])


if __name__ == '__main__':
    unittest.main()
