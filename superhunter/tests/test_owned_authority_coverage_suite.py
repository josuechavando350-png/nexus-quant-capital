from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_authority_cases as historical
from superhunter import owned_authority_coverage as analyzer
from superhunter import owned_authority_coverage_cases as corpus
from superhunter import owned_authority_coverage_reference as reference
from superhunter import owned_authority_coverage_suite as suite
from superhunter import quality
from superhunter.safe_io import canonical


class CorpusTests(unittest.TestCase):
    def test_exact_expectations_match_both_algorithms(self):
        rows = corpus.cases()
        self.assertEqual(len(rows), 16)
        for row in rows:
            with self.subTest(case=row['case_id']):
                expected = row['expected_witness_indices']
                self.assertEqual(analyzer.coverage(row['events']), expected)
                self.assertEqual(reference.coverage(row['events']), expected)
        self.assertEqual(len(suite._evaluate(rows)), 16)

    def test_fixed_corpus_and_historical_pins_match(self):
        self.assertEqual(quality.sha(canonical(corpus.cases())), suite.CORPUS_SHA256)
        self.assertEqual(quality.sha(canonical(historical.cases())), suite.HISTORICAL_CASES_SHA256)
        self.assertEqual(len(historical.cases()), 11)

    def test_each_condition_has_one_present_and_one_absent_control(self):
        rows = corpus.cases()
        for condition in analyzer.CONDITIONS:
            pair = {row['role']: row for row in rows if row['condition'] == condition}
            self.assertEqual(set(pair), {'present', 'absent'})
            self.assertTrue(pair['present']['expected_witness_indices'][condition])
            self.assertEqual(pair['absent']['expected_witness_indices'][condition], [])

    def test_missing_and_duplicate_pair_rejected(self):
        rows = corpus.cases()
        with self.assertRaisesRegex(ValueError, 'CASE_COUNT'): suite._evaluate(rows[:-1])
        rows[-1] = deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, 'CASE_IDENTITY'): suite._evaluate(rows)

    def test_expected_indices_do_not_feed_algorithms(self):
        original = analyzer.coverage
        seen = []
        def record(events):
            self.assertTrue(all(set(event) == {'op', 'principal', 'tenant', 'action', 'credential'}
                                for event in events))
            seen.append(deepcopy(events))
            return original(events)
        with patch.object(analyzer, 'coverage', side_effect=record):
            suite._evaluate(corpus.cases())
        self.assertEqual(seen, [row['events'] for row in corpus.cases()])

    def test_false_authored_expectation_is_not_self_fulfilling(self):
        rows = corpus.cases()
        rows[1]['expected_witness_indices']['current_grant_use'] = []
        with self.assertRaisesRegex(ValueError, 'EXPECTATION_DISAGREEMENT'):
            suite._evaluate(rows)

    def test_false_role_rejected_before_evaluation(self):
        rows = corpus.cases()
        rows[0]['expected_witness_indices']['use_without_control'] = []
        with self.assertRaisesRegex(ValueError, 'SUITE_ROLE'): suite._evaluate(rows)

    def test_indices_reject_boolean_out_of_range_and_control_events(self):
        for invalid in ([True], [-1], [2], [0], [1, 1]):
            rows = corpus.cases()
            rows[1]['expected_witness_indices']['current_grant_use'] = invalid
            with self.subTest(indices=invalid):
                with self.assertRaisesRegex(ValueError, 'WITNESS'): suite._evaluate(rows)

    def test_indices_must_be_ordered(self):
        rows = corpus.cases()
        rows[12]['expected_witness_indices']['current_grant_use'] = [2, 1]
        with self.assertRaisesRegex(ValueError, 'WITNESS'): suite._evaluate(rows)

    def test_unknown_condition_and_detection_label_are_rejected(self):
        rows = corpus.cases(); rows[0]['truth'] = 'positive'
        with self.assertRaisesRegex(ValueError, 'CASE_SCHEMA'): suite._evaluate(rows)
        rows = corpus.cases(); rows[0]['expected_witness_indices']['unknown'] = []
        with self.assertRaisesRegex(ValueError, 'EXPECTATION_SCHEMA'): suite._evaluate(rows)

    def test_event_copy_aliases_do_not_change_other_cases_or_generations(self):
        rows = corpus.cases(); original = canonical(rows)
        rows[0]['events'][0]['credential']['generation'] = 64
        self.assertEqual(canonical(corpus.cases()), original)
        self.assertEqual(rows[1]['events'][1]['credential']['generation'], 1)
        repeat = next(r for r in rows if r['case_id'] == 'repeated_current_grant_use--present')
        repeat['events'][1]['credential']['generation'] = 64
        self.assertEqual(repeat['events'][2]['credential']['generation'], 1)
        before = canonical(corpus.cases())
        suite._evaluate(corpus.cases())
        self.assertEqual(canonical(corpus.cases()), before)

    def test_new_controls_do_not_change_old_latent_case(self):
        before = canonical(historical.cases())
        suite._evaluate(corpus.cases())
        old = {row['case_id']: row for row in historical.cases()}
        self.assertEqual(before, canonical(historical.cases()))
        self.assertEqual(old['latent_revocation']['events'], old['clean_repeat']['events'])
        self.assertFalse(old['latent_revocation']['seeded_defect_exercised'])
        self.assertEqual(old['latent_revocation']['truth'], 'positive')

    def test_counter_control_covers_unissued_generation_without_inventing_revocation(self):
        row = next(r for r in corpus.cases() if r['case_id'] == 'revoked_grant_use--absent')
        self.assertEqual(analyzer.coverage(row['events']), {name: [] for name in analyzer.CONDITIONS})


class SuiteBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'suite'

    def reseal(self):
        (self.root/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256': {
            name: quality.sha((self.root/name).read_bytes()) for name in suite.FILES}}))

    def test_bundle_separates_denominators_and_discloses_overlap(self):
        report = suite.create(self.root)
        self.assertEqual(suite.verify(self.root, report['source_digest']), report)
        self.assertEqual((report['case_count'], report['pair_count'], report['unique_event_sequences']),
                         (16, 8, 13))
        self.assertEqual((report['historical']['case_count'], report['historical']['unique_event_sequences']),
                         (11, 9))
        self.assertEqual(report['historical']['uncovered_in_all_cases'], ['use_without_control'])
        self.assertEqual(len(report['duplicate_event_sequences']), 1)
        self.assertEqual(len(report['duplicate_event_sequences'][0]['case_ids']), 4)
        self.assertTrue(report['shared_event_sequences'])
        for name in ('case_units_pooled', 'detector_evaluated', 'vulnerability_confirmed',
                     'model_or_native_execution_performed', 'platform_complete', 'producer_authenticated'):
            self.assertIs(report[name], False)
        self.assertIsNone(report['global_progress'])

    def test_historical_identity_change_blocks_creation(self):
        old = historical.cases(); old[-1]['truth'] = 'negative'
        with patch.object(historical, 'cases', return_value=old):
            with self.assertRaisesRegex(ValueError, 'HISTORICAL_IDENTITY'): suite.create(self.root)
        self.assertFalse(self.root.exists())

    def test_changed_corpus_blocks_creation(self):
        rows = corpus.cases(); rows[0]['events'][0]['credential']['generation'] = 2
        with patch.object(corpus, 'cases', return_value=rows):
            with self.assertRaisesRegex(ValueError, 'CORPUS_IDENTITY'): suite.create(self.root)
        self.assertFalse(self.root.exists())

    def test_disagreement_with_reference_blocks_publication(self):
        with patch.object(reference, 'coverage', return_value={}):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_DISAGREEMENT'): suite.create(self.root)
        self.assertFalse((self.root/'COMPLETE.json').exists())

    def test_both_algorithms_wrong_cannot_override_authored_expectation(self):
        result = {name: [] for name in analyzer.CONDITIONS}
        with patch.object(analyzer, 'coverage', return_value=result), \
                patch.object(reference, 'coverage', return_value=result):
            with self.assertRaisesRegex(ValueError, 'EXPECTATION_DISAGREEMENT'): suite.create(self.root)
        self.assertFalse(self.root.exists())

    def test_resealed_false_report_rejected(self):
        report = suite.create(self.root)
        report['historical']['uncovered_in_all_cases'] = []
        (self.root/'evaluation.json').write_bytes(canonical(report)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            suite.verify(self.root, report['source_digest'])

    def test_resealed_altered_expected_indices_rejected(self):
        report = suite.create(self.root)
        inputs = json.loads((self.root/'inputs.json').read_text())
        inputs['cases'][0]['expected_witness_indices']['use_without_control'] = []
        (self.root/'inputs.json').write_bytes(canonical(inputs)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            suite.verify(self.root, report['source_digest'])

    def test_resealed_replacement_events_rejected(self):
        report = suite.create(self.root)
        inputs = json.loads((self.root/'inputs.json').read_text())
        inputs['cases'][0]['events'].insert(0, historical.event('grant'))
        (self.root/'inputs.json').write_bytes(canonical(inputs)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            suite.verify(self.root, report['source_digest'])

    def test_wrong_source_and_hash_mismatch_rejected(self):
        report = suite.create(self.root)
        with self.assertRaisesRegex(ValueError, 'SUITE_SOURCE'): suite.verify(self.root, '0'*64)
        (self.root/'REVIEW.md').write_bytes(b'changed\n')
        with self.assertRaisesRegex(ValueError, 'SUITE_HASH'):
            suite.verify(self.root, report['source_digest'])

    def test_inventory_rejects_extra_and_missing_files(self):
        report = suite.create(self.root)
        extra = self.root/'extra.json'; extra.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'INVENTORY'):
            suite.verify(self.root, report['source_digest'])
        extra.unlink(); (self.root/'COMPLETE.json').unlink()
        with self.assertRaisesRegex(ValueError, 'INVENTORY'):
            suite.verify(self.root, report['source_digest'])

    def test_symlinked_file_and_root_are_rejected(self):
        report = suite.create(self.root)
        alias = Path(self.temp.name)/'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'DIRECTORY'): suite.verify(alias, report['source_digest'])
        path = self.root/'evaluation.json'; raw = path.read_bytes(); path.unlink()
        external = Path(self.temp.name)/'external.json'; external.write_bytes(raw); path.symlink_to(external)
        with self.assertRaises((ValueError, OSError)): suite.verify(self.root, report['source_digest'])

    def test_marker_mutation_during_replay_is_rejected(self):
        report = suite.create(self.root); execute = suite._execute
        def changed(expected):
            result = execute(expected)
            (self.root/'COMPLETE.json').write_text('{}')
            return result
        with patch.object(suite, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_REPLAY'):
                suite.verify(self.root, report['source_digest'])

    def test_inventory_mutation_during_replay_is_rejected(self):
        report = suite.create(self.root); execute = suite._execute
        def changed(expected):
            result = execute(expected)
            (self.root/'extra.json').write_text('{}')
            return result
        with patch.object(suite, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INVENTORY'):
                suite.verify(self.root, report['source_digest'])

    def test_source_change_during_generation_blocks_completion(self):
        snapshot = quality.source_snapshot()
        changed = {**snapshot, 'owned_authority_coverage_suite.py': '0'*64}
        with patch.object(quality, 'source_snapshot', side_effect=[snapshot, snapshot, changed]):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): suite.create(self.root)
        self.assertFalse(self.root.exists())

    def test_existing_and_repository_destinations_are_rejected(self):
        suite.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): suite.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'):
            suite.create(suite.ROOT/'unwanted-suite')

    def test_cli_separate_processes(self):
        command = [sys.executable, '-B', '-m', 'superhunter']
        made = subprocess.run(command + ['review-owned-coverage-suite', '--out', str(self.root)],
            cwd=suite.ROOT.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual((made.returncode, made.stderr), (0, ''))
        receipt = json.loads(made.stdout)
        checked = subprocess.run(command + ['verify-owned-coverage-suite', '--bundle', str(self.root),
            '--expected-source', receipt['source_digest']], cwd=suite.ROOT.parent,
            capture_output=True, text=True, timeout=30)
        self.assertEqual((checked.returncode, checked.stderr), (0, ''))
        self.assertEqual(json.loads(checked.stdout), receipt)

    def test_component_and_worker_registration(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(sum('test_owned_authority_coverage_suite' in group for group in QA_MODULE_GROUPS), 1)
        self.assertEqual(set(quality.COMPONENTS['owned_authority_coverage_suite']['files']), {
            'owned_authority_coverage_cases.py', 'owned_authority_coverage_suite.py'})


if __name__ == '__main__':
    unittest.main()
