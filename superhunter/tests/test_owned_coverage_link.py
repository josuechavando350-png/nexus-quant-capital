import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_authority_coverage as historical
from superhunter import owned_authority_coverage_suite as additional
from superhunter import owned_coverage_link as link
from superhunter import quality
from superhunter.safe_io import canonical


class CoverageLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old, self.new, self.out = (self.root/name for name in ('historical', 'additional', 'linked'))
        self.source = historical.create(self.old)['source_digest']
        self.assertEqual(additional.create(self.new)['source_digest'], self.source)
        self.first = quality.sha((self.old/'COMPLETE.json').read_bytes())
        self.second = quality.sha((self.new/'COMPLETE.json').read_bytes())

    def collect(self):
        return link.collect(self.old, self.new, self.source, self.first, self.second)

    def create(self):
        return link.create(self.old, self.new, self.source, self.first, self.second, self.out)

    def verify(self):
        return link.verify(self.out, self.old, self.new, self.source, self.first, self.second)

    def reseal(self, root, files):
        (root/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256': {
            name: quality.sha((root/name).read_bytes()) for name in files}}))

    def test_both_reports_are_regenerated_with_external_anchors(self):
        old_verify, new_verify = historical.verify, additional.verify
        with patch.object(historical, 'verify', wraps=old_verify) as old, \
                patch.object(additional, 'verify', wraps=new_verify) as new:
            report = self.create()
        old.assert_called_once_with(self.old, self.source)
        new.assert_called_once_with(self.new, self.source)
        self.assertEqual(self.verify(), report)

    def test_gaps_and_denominators_remain_separate(self):
        report = self.collect()
        self.assertEqual((report['historical']['case_count'], report['historical']['unique_event_sequences']), (11, 9))
        self.assertEqual((report['additional']['case_count'], report['additional']['unique_event_sequences']), (16, 13))
        self.assertEqual(report['historical']['uncovered_conditions'], ['use_without_control'])
        self.assertEqual(report['additional']['uncovered_conditions'], [])
        self.assertEqual(report['additional_witnesses_for_historical_gaps'], {
            'use_without_control': [{'case_id': 'use_without_control--present', 'witness_indices': [0]}]})
        self.assertEqual(len(report['shared_event_sequences']), 4)
        for name in ('historical_gap_erased', 'case_units_pooled', 'vulnerability_confirmed',
                     'detector_evaluated', 'model_or_native_execution_performed', 'platform_complete'):
            self.assertIs(report[name], False)
        self.assertIsNone(report['global_progress'])

    def test_report_contains_no_local_paths(self):
        report = self.collect()
        self.assertNotIn(str(self.root), canonical(report).decode())
        self.assertEqual(set(report['evidence_sha256']), {'historical', 'additional'})
        self.assertEqual(report['anchors']['historical_complete_sha256'], self.first)

    def test_invalid_external_anchor_forms_are_rejected(self):
        for anchor in ('', '0'*63, 'G'*64, '0'*65, None, True):
            with self.subTest(anchor=anchor):
                with self.assertRaisesRegex(ValueError, 'EXTERNAL_ANCHORS_REQUIRED'):
                    link.collect(self.old, self.new, self.source, anchor, self.second)

    def test_equal_anchors_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DISTINCT_ANCHORS_REQUIRED'):
            link.collect(self.old, self.new, self.source, self.first, self.first)

    def test_wrong_external_anchor_is_rejected_before_replay(self):
        with patch.object(historical, 'verify', side_effect=AssertionError('must not replay')):
            with self.assertRaisesRegex(ValueError, 'ANCHOR_MISMATCH'):
                link.collect(self.old, self.new, self.source, '0'*64, self.second)

    def test_wrong_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'LINK_SOURCE'):
            link.collect(self.old, self.new, '0'*64, self.first, self.second)

    def test_same_input_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DISTINCT_INPUTS_REQUIRED'):
            link.collect(self.old, self.old, self.source, self.first, self.second)

    def test_nested_input_directories_are_rejected(self):
        nested = self.old/'nested'; nested.mkdir()
        with self.assertRaisesRegex(ValueError, 'DISTINCT_INPUTS_REQUIRED'):
            link.collect(self.old, nested, self.source, self.first, self.second)

    def test_swapped_profile_directories_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'INVENTORY'):
            link.collect(self.new, self.old, self.source, self.second, self.first)

    def test_input_from_another_source_cannot_be_resealed_into_this_version(self):
        record = json.loads((self.old/'coverage.json').read_text())
        record['source_digest'] = '1'*64
        (self.old/'coverage.json').write_bytes(canonical(record))
        self.reseal(self.old, historical.FILES)
        changed_anchor = quality.sha((self.old/'COMPLETE.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            link.collect(self.old, self.new, self.source, changed_anchor, self.second)

    def test_changed_input_anchor_does_not_get_trusted_from_itself(self):
        (self.new/'REVIEW.md').write_bytes(b'edited\n')
        self.reseal(self.new, additional.FILES)
        with self.assertRaisesRegex(ValueError, 'ANCHOR_MISMATCH'): self.collect()

    def test_historical_marker_changed_after_replay_is_rejected(self):
        verify = historical.verify
        def changed(*args):
            result = verify(*args)
            (self.old/'COMPLETE.json').write_text('{}')
            return result
        with patch.object(historical, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INPUT_CHANGED_DURING_REVIEW'): self.create()
        self.assertFalse(self.out.exists())

    def test_additional_file_changed_after_replay_is_rejected(self):
        verify = additional.verify
        def changed(*args):
            result = verify(*args)
            (self.new/'REVIEW.md').write_bytes(b'edited\n')
            return result
        with patch.object(additional, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INPUT_CHANGED_DURING_REVIEW'): self.create()
        self.assertFalse(self.out.exists())

    def test_extra_file_added_after_replay_is_rejected(self):
        verify = additional.verify
        def changed(*args):
            result = verify(*args)
            (self.old/'extra.json').write_text('{}')
            return result
        with patch.object(additional, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INVENTORY'): self.create()

    def test_changed_source_after_replay_is_rejected(self):
        verify = additional.verify
        snapshot = quality.source_snapshot()
        changed_snapshot = {**snapshot, 'owned_coverage_link.py': '0'*64}
        def changed(*args):
            result = verify(*args)
            self.patcher = patch.object(quality, 'source_snapshot', return_value=changed_snapshot)
            self.patcher.start(); self.addCleanup(self.patcher.stop)
            return result
        with patch.object(additional, 'verify', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): self.create()

    def test_unexpected_input_file_is_rejected(self):
        (self.old/'extra.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'INVENTORY'): self.collect()

    def test_symlink_input_root_is_rejected(self):
        alias = self.root/'alias'; alias.symlink_to(self.old, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'INPUT_DIRECTORIES'):
            link.collect(alias, self.new, self.source, self.first, self.second)

    def test_symlink_input_file_is_rejected(self):
        path = self.old/'coverage.json'; raw = path.read_bytes(); path.unlink()
        external = self.root/'outside.json'; external.write_bytes(raw); path.symlink_to(external)
        with self.assertRaises((ValueError, OSError)): self.collect()

    def test_existing_output_is_rejected(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'OUTPUT_LOCATION'): self.create()

    def test_nested_or_ancestor_output_is_rejected(self):
        for out in (self.old/'new', self.new/'new'):
            with self.subTest(out=out):
                with self.assertRaisesRegex(ValueError, 'OVERLAPPING_OUTPUT'):
                    link.create(self.old, self.new, self.source, self.first, self.second, out)
        with self.assertRaisesRegex(ValueError, 'OVERLAPPING_OUTPUT'):
            link._output_location(self.root, self.old, self.new, new=False)

    def test_repository_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'OUTPUT_LOCATION'):
            link.create(self.old, self.new, self.source, self.first, self.second, link.ROOT/'superhunter/unwanted-link')

    def test_symlink_output_is_rejected(self):
        self.create(); alias = self.root/'alias'; alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'OUTPUT_LOCATION'):
            link.verify(alias, self.old, self.new, self.source, self.first, self.second)

    def test_resealed_gap_erasure_is_rejected(self):
        record = self.create(); record['historical']['uncovered_conditions'] = []
        (self.out/'link.json').write_bytes(canonical(record)); self.reseal(self.out, link.FILES)
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.verify()

    def test_resealed_invented_detection_is_rejected(self):
        record = self.create(); record['detector_evaluated'] = True
        (self.out/'link.json').write_bytes(canonical(record)); self.reseal(self.out, link.FILES)
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.verify()

    def test_resealed_false_output_anchor_is_rejected(self):
        record = self.create(); record['anchors']['historical_complete_sha256'] = '0'*64
        (self.out/'link.json').write_bytes(canonical(record)); self.reseal(self.out, link.FILES)
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.verify()

    def test_output_hash_mismatch_is_rejected(self):
        self.create(); (self.out/'REVIEW.md').write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'LINK_HASH'): self.verify()

    def test_output_mutation_during_replay_is_rejected(self):
        self.create(); collect = link.collect
        def changed(*args):
            result = collect(*args)
            (self.out/'COMPLETE.json').write_text('{}')
            return result
        with patch.object(link, 'collect', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_CHANGED_DURING_REPLAY'): self.verify()

    def test_extra_output_file_is_rejected(self):
        self.create(); (self.out/'extra.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'INVENTORY'): self.verify()

    def test_cli_creates_and_verifies_in_separate_processes(self):
        common = ['--historical', str(self.old), '--additional', str(self.new),
                  '--expected-source', self.source, '--historical-anchor', self.first,
                  '--additional-anchor', self.second]
        command = [sys.executable, '-B', '-m', 'superhunter']
        made = subprocess.run(command + ['link-owned-coverage', '--out', str(self.out), *common],
            cwd=link.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual((made.returncode, made.stderr), (0, ''))
        checked = subprocess.run(command + ['verify-owned-coverage-link', '--bundle', str(self.out), *common],
            cwd=link.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual((checked.returncode, checked.stderr), (0, ''))
        self.assertEqual(json.loads(made.stdout), json.loads(checked.stdout))

    def test_cli_failure_does_not_print_local_paths(self):
        result = subprocess.run([sys.executable, '-B', '-m', 'superhunter', 'link-owned-coverage',
            '--out', str(self.out), '--historical', str(self.old), '--additional', str(self.new),
            '--expected-source', self.source, '--historical-anchor', '0'*64,
            '--additional-anchor', self.second], cwd=link.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {'status': 'OWNED_COVERAGE_LINK_BLOCKED'})
        self.assertEqual(result.stderr, '')

    def test_component_and_worker_registration(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(sum('test_owned_coverage_link' in group for group in QA_MODULE_GROUPS), 1)
        self.assertEqual(quality.COMPONENTS['owned_coverage_link']['files'], ['owned_coverage_link.py'])


if __name__ == '__main__':
    unittest.main()
