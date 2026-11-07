"""Clearly fabricated orchestration doubles; real acceptance runs separately."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from superhunter import owned_defensive_acceptance as joint
from superhunter.safe_io import canonical, strict_json, write_new_bundle
from superhunter.tests import test_owned_platform as quota_fixtures
from superhunter.tests import test_owned_authority_evm as authority_fixtures


class DefensiveAcceptanceTests(unittest.TestCase):
    def setUp(self):
        # Composition intentionally avoids inheriting/discovering the old tests again.
        self.fixture = quota_fixtures.OwnedPlatformTests('runTest'); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.prepared = self.fixture.root, self.fixture.prepared
        self.out, self.solc, self.evm = self.root / 'joint', self.fixture.solc, self.fixture.evm
        self.digest, self.snapshot = self.fixture.digest, self.fixture.snapshot
        counts = {'tp': 4, 'tn': 2, 'fp': 0, 'fn': 0, 'abstain_positive': 0,
                  'abstain_negative': 0, 'error_positive': 0, 'error_negative': 0}
        self.fixture.comparison = {'status': 'OWNED_QUOTA_CROSS_EVM_MATCH', 'source_digest': self.digest,
            'known_cases': 6, 'counts': counts, 'ablation_metrics': {'full': {'counts': counts}},
            'vulnerability_confirmed': False}
        first, second = authority_fixtures.synthetic_executions(self.digest)
        self.temporal, _ = joint.authority.compare(first, second, self.digest)
        stack = self.fixture.stack
        stack.enter_context(patch.object(joint.authority, 'FILES', {'comparison.json', 'UNIT_TEST_ONLY.txt'}))
        self.authority_run = stack.enter_context(patch.object(joint.authority, 'create', side_effect=self.fake_authority))
        self.authority_verify = stack.enter_context(patch.object(joint.authority, 'verify', side_effect=self.fake_authority_verify))

    def fake_authority(self, root, *_):
        write_new_bundle(root, {'comparison.json': canonical(self.temporal),
                               'UNIT_TEST_ONLY.txt': b'FABRICATED AUTHORITY CONTROL; NO NATIVE EXECUTION\n'})
        return deepcopy(self.temporal)

    def fake_authority_verify(self, root, *_):
        joint.quota._manifest(root, joint.authority.FILES)
        if (root / 'comparison.json').read_bytes() != canonical(self.temporal):
            raise ValueError('UNIT_AUTHORITY_CHANGED')
        return deepcopy(self.temporal)

    def finish(self):
        return joint.finish(self.prepared, self.out, self.solc, self.evm, self.digest)

    def complete(self):
        self.fixture.prepare(); return self.finish()

    def verify(self):
        return joint.verify(self.out, self.solc, self.evm, self.digest)

    def test_both_native_cohorts_must_be_reexecuted(self):
        self.complete()
        self.assertEqual(self.fixture.native_run.call_count, 1)
        self.assertEqual(self.fixture.native_verify.call_count, 1)
        self.assertEqual(self.authority_run.call_count, 1)
        self.assertEqual(self.authority_verify.call_count, 1)
        self.verify()
        self.assertEqual(self.fixture.native_verify.call_count, 2)
        self.assertEqual(self.authority_verify.call_count, 2)
        self.assertEqual(self.fixture.qa_run.call_count, 1)

    def test_complete_acceptance_retains_the_known_omission(self):
        result = self.complete()
        self.assertEqual(result['status'], 'OWNED_DEFENSIVE_ACCEPTANCE_COMPLETE')
        self.assertFalse(result['all_seeded_cases_detected'])
        self.assertTrue(result['all_known_controls_clean'])
        self.assertEqual(result['cohorts']['temporal_authority']['counts']['fn'], 1)
        self.assertEqual(result['cohorts']['temporal_authority']['missed_case_ids'], ['latent_revocation'])

    def test_incompatible_case_units_are_not_pooled(self):
        result = self.complete()
        self.assertFalse(result['case_units_pooled']); self.assertIsNone(result['pooled_performance_score'])
        self.assertNotEqual(result['cohorts']['quota']['case_unit'], result['cohorts']['temporal_authority']['case_unit'])
        self.assertEqual([result['cohorts'][name]['known_cases'] for name in ('quota', 'temporal_authority')], [6, 11])

    def test_vm_success_ablation_is_preserved_as_false_positives(self):
        result = self.complete()
        metrics = result['cohorts']['temporal_authority']['vm_success_as_authorization_metrics']
        self.assertEqual(metrics['counts']['fp'], 3)

    def test_resource_environment_and_claim_limits_are_retained(self):
        result = self.complete()
        self.assertEqual(result['worker_policy'], joint.quota.WORKERS)
        self.assertEqual(result['qa_runtime']['package_versions']['cryptography'], '46.0.4')
        for name in ('producer_authenticated', 'independent_producers_proved', 'caller_identity_authenticated',
                     'platform_complete', 'vulnerability_confirmed', 'legacy_native_profile_recertified',
                     'aggregate_resource_budget_certified', 'blind_benchmark', 'generalization_established'):
            self.assertIs(result[name], False)
        self.assertEqual(result['global_progress'], 'not determined')
        self.assertIsNone(result['monetary_valuation_usd'])
        self.assertFalse(result['qa']['tests_reexecuted_by_verifier'])

    def test_final_bundle_survives_removal_of_original_preparation(self):
        self.complete(); shutil.rmtree(self.prepared)
        self.assertEqual(self.verify()['status'], 'OWNED_DEFENSIVE_ACCEPTANCE_COMPLETE')

    def test_failed_qa_prevents_all_native_work(self):
        self.fixture.qa_run.side_effect = ValueError('UNIT_QA_FAILED')
        with self.assertRaises(ValueError): self.complete()
        self.fixture.native_run.assert_not_called(); self.authority_run.assert_not_called()
        self.assertFalse((self.out / 'review').exists())

    def test_wrong_digest_blocks_before_creating_output(self):
        self.fixture.prepare()
        for value in ('0' * 64, 'short', True, None):
            with self.assertRaises(ValueError): joint.finish(self.prepared, self.out, self.solc, self.evm, value)
        self.assertFalse(self.out.exists()); self.authority_run.assert_not_called()

    def test_native_prerequisite_failure_prevents_output(self):
        self.fixture.prepare(); self.fixture.preflight.side_effect = ValueError('UNIT_RUNTIME_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse(self.out.exists()); self.authority_run.assert_not_called()

    def test_failed_quota_replay_blocks_authority_and_final_marker(self):
        self.fixture.prepare(); self.fixture.native_verify.side_effect = ValueError('UNIT_QUOTA_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.authority_run.assert_not_called(); self.assertFalse((self.out / 'review').exists())

    def test_failed_authority_execution_has_no_joint_completion_marker(self):
        self.fixture.prepare(); self.authority_run.side_effect = ValueError('UNIT_AUTHORITY_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.assertTrue((self.out / 'quota/review/COMPLETE.json').exists())
        self.assertFalse((self.out / 'review').exists())

    def test_failed_authority_replay_has_no_joint_completion_marker(self):
        self.fixture.prepare(); self.authority_verify.side_effect = ValueError('UNIT_AUTHORITY_REPLAY_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_verification_does_not_substitute_a_stored_report_for_replay(self):
        self.complete(); self.authority_verify.side_effect = ValueError('UNIT_ENGINE_UNAVAILABLE')
        with self.assertRaises(ValueError): self.verify()

    def test_source_identity_cannot_differ_between_native_cohorts(self):
        self.temporal['source_digest'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'AUTHORITY_REQUIRED'): self.complete()
        self.assertFalse((self.out / 'review').exists())

    def test_quota_nested_native_source_is_checked(self):
        self.fixture.comparison['source_digest'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'COHORT_IDENTITY'): self.complete()

    def test_published_reports_must_match_returned_verified_results(self):
        self.fixture.prepare(); original = self.fake_authority_verify
        def changed(root, *args):
            result = original(root, *args); result['unbound_field'] = 'UNIT'
            return result
        self.authority_verify.side_effect = changed
        with self.assertRaisesRegex(ValueError, 'REPORT_BINDING'): self.finish()

    def test_quota_changed_while_authority_runs_is_rejected(self):
        self.fixture.prepare(); original = self.fake_authority
        def change(root, *args):
            (self.out / 'quota/prepared/local/UNIT_TEST_ONLY.txt').write_text('CONCURRENT UNIT CHANGE\n')
            return original(root, *args)
        self.authority_run.side_effect = change
        with self.assertRaisesRegex(ValueError, 'QUOTA_CHANGED_DURING_AUTHORITY'): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_source_changed_during_document_render_prevents_marker(self):
        self.fixture.prepare(); original = joint._documents
        def change(result):
            self.fixture.stack.enter_context(patch.object(joint.quality, 'source_snapshot', return_value={'changed': '0' * 64}))
            return original(result)
        with patch.object(joint, '_documents', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'CHANGED_BEFORE_COMPLETION'): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_existing_output_is_never_overwritten(self):
        self.complete(); marker = (self.out / 'review/COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT'): self.finish()
        self.assertEqual((self.out / 'review/COMPLETE.json').read_bytes(), marker)

    def test_overlapping_preparation_output_is_rejected(self):
        self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, 'OVERLAPPING_OUTPUT'):
            joint.finish(self.prepared, self.prepared / 'final', self.solc, self.evm, self.digest)
        self.assertFalse((self.prepared / 'final').exists())

    def test_missing_native_cohort_cannot_complete_verification(self):
        self.complete(); shutil.rmtree(self.out / 'authority')
        with self.assertRaisesRegex(ValueError, 'STAGE_INVENTORY'): self.verify()

    def test_missing_joint_marker_is_not_inferred_from_child_markers(self):
        self.complete(); (self.out / 'review/COMPLETE.json').unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_extra_top_level_file_or_directory_is_rejected(self):
        self.complete(); (self.out / 'extra').mkdir()
        with self.assertRaisesRegex(ValueError, 'STAGE_INVENTORY'): self.verify()
        (self.out / 'extra').rmdir(); (self.out / 'extra').write_bytes(b'OWN UNIT INPUT')
        with self.assertRaisesRegex(ValueError, 'STAGE_INVENTORY'): self.verify()

    def test_extra_native_evidence_is_not_silently_exported(self):
        self.complete(); (self.out / 'authority/extra.json').write_bytes(b'{}')
        with self.assertRaises(ValueError): self.verify()

    def test_symlink_joint_root_or_native_file_is_rejected(self):
        self.complete(); link = self.root / 'link'; link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError): joint.verify(link, self.solc, self.evm, self.digest)
        file = self.out / 'authority/UNIT_TEST_ONLY.txt'; copied = self.root / 'copied'; file.rename(copied); file.symlink_to(copied)
        with self.assertRaises((OSError, ValueError)): self.verify()

    def test_rehashed_omission_removal_is_rejected(self):
        self.complete()
        self.fixture.reseal(self.out / 'review', 'acceptance.json', lambda r: r.update(all_seeded_cases_detected=True))
        with self.assertRaisesRegex(ValueError, 'REPORT_DIFFERS_FROM_REPLAY'): self.verify()

    def test_rehashed_pooled_performance_claim_is_rejected(self):
        self.complete()
        self.fixture.reseal(self.out / 'review', 'acceptance.json', lambda r: r.update(pooled_performance_score=1.0))
        with self.assertRaisesRegex(ValueError, 'REPORT_DIFFERS_FROM_REPLAY'): self.verify()

    def test_rehashed_false_production_or_producer_claim_is_rejected(self):
        self.complete()
        self.fixture.reseal(self.out / 'review', 'acceptance.json', lambda r: r.update(platform_complete=True, producer_authenticated=True))
        with self.assertRaisesRegex(ValueError, 'REPORT_DIFFERS_FROM_REPLAY'): self.verify()

    def test_joint_marker_byte_change_during_replay_is_rejected(self):
        self.complete(); original = self.fake_authority_verify
        def change(root, *args):
            result = original(root, *args); marker = self.out / 'review/COMPLETE.json'
            marker.write_bytes(marker.read_bytes() + b' ')
            return result
        self.authority_verify.side_effect = change
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_EVIDENCE_CHANGED'): self.verify()

    def test_native_evidence_changed_after_replay_is_rejected(self):
        self.complete(); original = self.fake_authority_verify
        def change(root, *args):
            result = original(root, *args)
            (self.out / 'quota/native/UNIT_TEST_ONLY.txt').write_text('CHANGED AFTER QUOTA REPLAY\n')
            return result
        self.authority_verify.side_effect = change
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_EVIDENCE_CHANGED'): self.verify()

    def test_denominators_do_not_accept_hidden_errors_or_boolean_counts(self):
        counts = self.temporal['metrics']['full']['counts']
        for key, value in (('fn', 0), ('tp', True), ('error_positive', 1), ('tn', -1)):
            changed = {**counts, key: value}
            with self.assertRaises(ValueError): joint._counts(changed, 7, 4)

    def test_abstentions_and_errors_remain_visible_in_correct_denominator(self):
        counts = deepcopy(self.temporal['metrics']['full']['counts'])
        counts.update(fn=0, error_positive=1)
        self.assertEqual(joint._counts(counts, 7, 4)['error_positive'], 1)
        counts.update(error_positive=0, abstain_positive=1)
        self.assertEqual(joint._counts(counts, 7, 4)['abstain_positive'], 1)

    def test_cli_private_error_does_not_reveal_input_paths(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            rc = joint.main(['verify-owned-defensive', '--bundle', '/private/own', '--solc', '/private/solc',
                             '--evm', '/private/evm', '--expected-source', '0' * 64])
        self.assertEqual(rc, 2); self.assertNotIn('/private', output.getvalue() + errors.getvalue())
        self.assertIn('OWNED_DEFENSIVE_ACCEPTANCE_BLOCKED', output.getvalue())
