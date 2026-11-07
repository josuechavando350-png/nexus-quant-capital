"""Orchestration controls using explicitly fabricated QA/native doubles.

These do not execute EVMs or certify native acceptance. A separate real run of
prepare, finish and verify is required for that claim. No old fixture changes.
"""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_platform as joint
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class OwnedPlatformTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.prepared, self.out = self.root / 'prepared', self.root / 'final'
        self.solc, self.evm = self.root / 'solc', self.root / 'evm'
        self.snapshot = joint.quality.source_snapshot()
        self.digest = joint.sha(canonical(self.snapshot))
        self.runtime = {'system': 'Linux', 'architecture': 'x86_64', 'python_version': '3.12.3',
                        'sealed_memory': True, 'package_versions': dict(joint.doctor.PACKAGES),
                        'z3_sha256': joint.doctor.Z3_SHA256}
        self.result = {
            'status': 'LOCAL_DEFENSIVE_REVIEW_PASS', 'source_digest': self.digest,
            'platform_complete': False, 'vulnerability_confirmed': False,
            'stages': {'qa': {'status': 'LOCAL_QA_PASS', 'tests_run': 2},
                       'lab': {'cases_passed': 5}, 'fuzz': {'cases_verified': 256},
                       'economics': {'cases_checked': 3}, 'benchmark_control': {'cases': 8},
                       'sequence': {'cases_checked': 4}},
            'integration': {'items': [{'id': n} for n in range(1, 28)]},
            'capabilities': {'items': [{'id': n} for n in range(1, 51)]},
            'research_initiatives': {'items': [{'id': 'UNIT-' + str(n)} for n in range(25)]}}
        self.comparison = {'status': 'UNIT_DOUBLE_ONLY', 'source_digest': self.digest,
                           'known_cases': 6, 'vulnerability_confirmed': False}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(joint, 'LOCAL_FILES', {'qa/receipt.json', 'UNIT_TEST_ONLY.txt'}))
        self.stack.enter_context(patch.object(joint.native, 'FILES', {'comparison.json', 'UNIT_TEST_ONLY.txt'}))
        self.runtime_mock = self.stack.enter_context(patch.object(joint, '_qa_runtime', return_value=self.runtime))
        self.preflight = self.stack.enter_context(patch.object(joint, '_native_preflight'))
        self.qa_run = self.stack.enter_context(patch.object(joint.local, 'run_platform', side_effect=self.fake_qa))
        self.qa_verify = self.stack.enter_context(patch.object(joint.local, 'verify_platform', side_effect=self.fake_qa_verify))
        self.native_run = self.stack.enter_context(patch.object(joint.native, 'create', side_effect=self.fake_native))
        self.native_verify = self.stack.enter_context(patch.object(joint.native, 'verify', side_effect=self.fake_native_verify))

    def fake_qa(self, out):
        (out / 'qa').mkdir(parents=True, mode=0o700)
        (out / 'qa/receipt.json').write_bytes(canonical({'discovered': ['UNIT.ONE', 'UNIT.TWO']}))
        (out / 'UNIT_TEST_ONLY.txt').write_text('FABRICATED CONTROL; NO QA EXECUTION\n')
        return deepcopy(self.result)

    def fake_qa_verify(self, root):
        if (root / 'UNIT_TEST_ONLY.txt').read_text() != 'FABRICATED CONTROL; NO QA EXECUTION\n':
            raise ValueError('UNIT_QA_CHANGED')
        return deepcopy(self.result)

    def fake_native(self, root, *_):
        write_new_bundle(root, {'comparison.json': canonical(self.comparison),
                               'UNIT_TEST_ONLY.txt': b'FABRICATED CONTROL; NO NATIVE EXECUTION\n'})

    def fake_native_verify(self, root, *_):
        joint._manifest(root, joint.native.FILES)
        if (root / 'comparison.json').read_bytes() != canonical(self.comparison):
            raise ValueError('UNIT_NATIVE_CHANGED')
        return {'status': 'OWNED_QUOTA_CROSS_EVM_REPLAY_VERIFIED', 'cases': 6,
                'runtime_calls_per_engine': 228, 'vulnerability_confirmed': False}

    def prepare(self):
        return joint.prepare(self.prepared)

    def finish(self):
        return joint.finish(self.prepared, self.out, self.solc, self.evm, self.digest)

    def verify(self):
        return joint.verify(self.out, self.solc, self.evm, self.digest)

    def complete(self):
        self.prepare()
        return self.finish()

    def reseal(self, root, name, change):
        value = strict_json((root / name).read_bytes())
        change(value)
        raw = canonical(value)
        (root / name).write_bytes(raw)
        marker = strict_json((root / 'COMPLETE.json').read_bytes())
        marker['sha256'][name] = joint.sha(raw)
        (root / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_completion_and_verification_require_native_replay(self):
        self.complete()
        self.assertEqual(self.qa_run.call_count, 1)
        self.assertEqual(self.native_run.call_count, 1)
        self.assertEqual(self.native_verify.call_count, 1)
        self.verify()
        self.assertEqual(self.native_verify.call_count, 2)
        self.assertEqual(self.qa_run.call_count, 1)

    def test_preparation_never_runs_native(self):
        r = self.prepare()
        self.assertEqual(r['status'], 'OWNED_QA_PREPARED')
        self.assertFalse(r['native_executed'])
        self.native_run.assert_not_called()
        self.native_verify.assert_not_called()

    def test_final_is_self_contained_after_preparation_removed(self):
        self.complete()
        shutil.rmtree(self.prepared)
        self.assertEqual(self.verify()['status'], 'OWNED_PLATFORM_REVIEW_PASS')

    def test_environment_roles_and_limits_are_explicit(self):
        r = self.complete()
        self.assertEqual(r['qa_runtime']['package_versions']['cryptography'], '46.0.4')
        self.assertTrue(r['qa_and_eels_environments_separate'])
        self.assertEqual(r['worker_policy']['qa_count'], 8)
        self.assertEqual(r['worker_policy']['address_space_bytes'], 2 * 1024**3)
        self.assertEqual(r['worker_policy']['wall_seconds'], 180)
        self.assertEqual(r['worker_policy']['cpu_seconds'], 90)
        for field in ('platform_complete', 'vulnerability_confirmed', 'producer_authenticated',
                      'legacy_native_profile_recertified', 'aggregate_resource_budget_certified',
                      'external_targets_executed', 'network_used'):
            self.assertIs(r[field], False)
        self.assertEqual([len(r['plans'][k]) for k in ('integration_ids', 'capability_ids', 'initiative_ids')],
                         [27, 50, 25])
        self.assertFalse(r['qa']['tests_reexecuted_by_verifier'])

    def test_wrong_qa_packages_block_before_output(self):
        self.runtime_mock.side_effect = ValueError('WRONG_QA_PACKAGE')
        with self.assertRaises(ValueError): self.prepare()
        self.qa_run.assert_not_called()
        self.assertFalse(self.prepared.exists())

    def test_native_dependency_failure_prevents_native_and_output(self):
        self.prepare()
        self.preflight.side_effect = ValueError('WRONG_NATIVE_DEPENDENCY')
        with self.assertRaises(ValueError): self.finish()
        self.native_run.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_qa_failure_has_no_ready_marker(self):
        self.qa_run.side_effect = ValueError('QA_FAILED')
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse((self.prepared / 'readiness').exists())

    def test_qa_negative_status_has_no_ready_marker(self):
        self.result['status'] = 'BLOCKED'
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse((self.prepared / 'readiness').exists())

    def test_qa_runtime_changed_during_run_blocks_preparation(self):
        self.runtime_mock.side_effect = [self.runtime, {**self.runtime, 'sealed_memory': False}]
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse((self.prepared / 'readiness').exists())

    def test_source_changed_after_qa_blocks_preparation(self):
        def changed(out):
            result = self.fake_qa(out)
            self.stack.enter_context(patch.object(joint.quality, 'source_snapshot', return_value={'changed': 'f' * 64}))
            return result
        self.qa_run.side_effect = changed
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse((self.prepared / 'readiness').exists())

    def test_invalid_expected_source_blocks_before_execution(self):
        self.prepare()
        for bad in ('f' * 64, 'short', True, None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                joint.finish(self.prepared, self.out, self.solc, self.evm, bad)
        self.native_run.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_incomplete_preparation_rejected(self):
        self.prepare()
        (self.prepared / 'readiness/COMPLETE.json').unlink()
        with self.assertRaises(ValueError): self.finish()
        self.native_run.assert_not_called()

    def test_extra_preparation_file_rejected(self):
        self.prepare()
        (self.prepared / 'private-extra.txt').write_text('OWN UNIT INPUT')
        with self.assertRaises(ValueError): self.finish()

    def test_extra_preparation_directory_rejected(self):
        self.prepare()
        (self.prepared / 'extra').mkdir()
        with self.assertRaises(ValueError): self.finish()

    def test_symlink_preparation_root_rejected(self):
        self.prepare()
        link = self.root / 'link'
        link.symlink_to(self.prepared, target_is_directory=True)
        with self.assertRaises(ValueError): joint.verify_prepared(link, self.digest)

    def test_symlink_preparation_leaf_rejected(self):
        self.prepare()
        path = self.prepared / 'local/UNIT_TEST_ONLY.txt'
        copied = self.root / 'copy'
        copied.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(copied)
        with self.assertRaises(ValueError): self.finish()

    def test_resealed_wrong_runtime_pin_rejected(self):
        self.prepare()
        self.reseal(self.prepared / 'readiness', 'readiness.json',
                    lambda r: r['qa_runtime']['package_versions'].update(cryptography='45.0.7'))
        with self.assertRaises(ValueError): self.finish()

    def test_resealed_wrong_z3_rejected(self):
        self.prepare()
        self.reseal(self.prepared / 'readiness', 'readiness.json',
                    lambda r: r['qa_runtime'].update(z3_sha256='0' * 64))
        with self.assertRaises(ValueError): self.finish()

    def test_resealed_false_preparation_claim_rejected(self):
        self.prepare()
        self.reseal(self.prepared / 'readiness', 'readiness.json',
                    lambda r: r.update(producer_authenticated=True))
        with self.assertRaises(ValueError): self.finish()

    def test_resealed_relaxed_worker_budget_rejected(self):
        self.prepare()
        self.reseal(self.prepared / 'readiness', 'readiness.json',
                    lambda r: r['worker_policy'].update(address_space_bytes=4 * 1024**3))
        with self.assertRaises(ValueError): self.finish()

    def test_changed_preparation_during_copy_rejected(self):
        self.prepare()
        original = joint._copy_prepared
        def mutate(source, dest, hashes):
            (source / 'local/UNIT_TEST_ONLY.txt').write_text('CHANGED UNIT INPUT')
            original(source, dest, hashes)
        with patch.object(joint, '_copy_prepared', side_effect=mutate):
            with self.assertRaises(ValueError): self.finish()
        self.native_run.assert_not_called()
        self.assertFalse((self.out / 'review').exists())

    def test_existing_output_never_overwritten(self):
        self.prepare()
        self.out.mkdir()
        (self.out / 'keep').write_text('OWN INPUT')
        with self.assertRaises(ValueError): self.finish()
        self.assertEqual((self.out / 'keep').read_text(), 'OWN INPUT')

    def test_output_inside_preparation_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):
            joint.finish(self.prepared, self.prepared / 'new', self.solc, self.evm, self.digest)
        self.native_run.assert_not_called()

    def test_output_inside_source_rejected(self):
        with self.assertRaises(ValueError): joint.prepare(joint.ROOT / 'unit-not-created')
        self.qa_run.assert_not_called()

    def test_failed_native_creation_leaves_no_final_marker(self):
        self.prepare()
        self.native_run.side_effect = ValueError('NATIVE_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_failed_native_replay_leaves_no_final_marker(self):
        self.prepare()
        self.native_verify.side_effect = ValueError('REPLAY_FAILED')
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_wrong_native_replay_receipt_rejected(self):
        self.prepare()
        self.native_verify.side_effect = None
        self.native_verify.return_value = {'status': 'PASS'}
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_resealed_false_final_claim_rejected(self):
        self.complete()
        self.reseal(self.out / 'review', 'acceptance.json', lambda r: r.update(vulnerability_confirmed=True))
        with self.assertRaises(ValueError): self.verify()
        self.assertEqual(self.native_verify.call_count, 2)

    def test_resealed_false_native_comparison_rejected(self):
        self.complete()
        self.reseal(self.out / 'native', 'comparison.json', lambda r: r.update(vulnerability_confirmed=True))
        with self.assertRaises(ValueError): self.verify()

    def test_final_requires_complete_marker(self):
        self.complete()
        (self.out / 'review/COMPLETE.json').unlink()
        with self.assertRaises(ValueError): self.verify()
        self.assertEqual(self.native_verify.call_count, 1)

    def test_extra_final_stage_rejected(self):
        self.complete()
        (self.out / 'unexpected').mkdir()
        with self.assertRaises(ValueError): self.verify()
        self.assertEqual(self.native_verify.call_count, 1)

    def test_boolean_manifest_version_rejected(self):
        self.complete()
        path = self.out / 'review/COMPLETE.json'
        data = strict_json(path.read_bytes())
        data['schema_version'] = True
        path.write_bytes(canonical(data))
        with self.assertRaises(ValueError): self.verify()

    def test_changed_source_during_native_replay_rejected(self):
        self.prepare()
        original = self.fake_native_verify
        def changed(*args):
            result = original(*args)
            self.stack.enter_context(patch.object(joint.quality, 'source_snapshot', return_value={'changed': 'f' * 64}))
            return result
        self.native_verify.side_effect = changed
        with self.assertRaises(ValueError): self.finish()
        self.assertFalse((self.out / 'review').exists())

    def test_cli_error_omits_private_exception(self):
        self.qa_run.side_effect = ValueError('PRIVATE-OWN-CONTROL-PATH')
        output = io.StringIO()
        with redirect_stdout(output):
            rc = joint.main(['prepare-owned-platform', '--out', str(self.prepared)])
        self.assertEqual(rc, 2)
        self.assertNotIn('PRIVATE', output.getvalue())
        self.assertFalse(strict_json(output.getvalue())['vulnerability_confirmed'])


if __name__ == '__main__':
    unittest.main()
