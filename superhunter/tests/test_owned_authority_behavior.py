from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_authority_behavior as behavior
from superhunter import owned_authority_coverage_cases as corpus
from superhunter import owned_authority_cases as historical
from superhunter import owned_authority_model as model
from superhunter import owned_authority_reference as reference
from superhunter import quality
from superhunter.safe_io import canonical


class BehaviorTests(unittest.TestCase):
    def test_all_authored_decisions_and_effects_match_correct_model_and_reference(self):
        traces, rows = behavior._evaluate(corpus.cases())
        self.assertEqual((len(traces), len(rows)), (16, 16))
        for row in corpus.cases():
            with self.subTest(case=row['case_id']):
                expected = behavior.expected_trace(row)
                self.assertEqual(model.simulate('correct', row['events']), expected)
                self.assertEqual(reference.expected_decisions(row['events']),
                                 [obs['accepted'] for obs in expected['observations']])

    def test_control_commands_and_denied_uses_do_not_produce_effects(self):
        traces, _ = behavior._evaluate(corpus.cases())
        for row in traces:
            for event, obs in zip(row['trace']['events'], row['trace']['observations']):
                if event['op'] != 'use' or not obs['accepted']:
                    self.assertEqual(obs['effects_before'], obs['effects_after'])

    def test_each_accepted_use_changes_exactly_one_counter_by_one(self):
        traces, _ = behavior._evaluate(corpus.cases())
        for row in traces:
            for event, obs in zip(row['trace']['events'], row['trace']['observations']):
                if event['op'] == 'use' and obs['accepted']:
                    delta = {key: obs['effects_after'][key] - obs['effects_before'][key]
                             for key in model.EFFECT_KEYS}
                    self.assertEqual(delta, {key: int(key == event['tenant'] + '.' + event['action'])
                                             for key in model.EFFECT_KEYS})

    def test_repeated_current_use_is_permitted_by_this_abstract_policy(self):
        traces, _ = behavior._evaluate(corpus.cases())
        trace = next(row['trace'] for row in traces if row['case_id'] == 'repeated_current_grant_use--present')
        self.assertEqual([row['accepted'] for row in trace['observations']], [True, True, True])
        self.assertEqual(trace['observations'][-1]['effects_after']['north.read'], 2)

    def test_unused_generation_after_revocation_is_still_denied(self):
        traces, _ = behavior._evaluate(corpus.cases())
        trace = next(row['trace'] for row in traces if row['case_id'] == 'revoked_grant_use--absent')
        self.assertIs(trace['observations'][-1]['accepted'], False)
        self.assertEqual(trace['observations'][-1]['effects_after'], dict.fromkeys(model.EFFECT_KEYS, 0))

    def test_model_receives_only_event_records_and_only_correct_variant(self):
        original = model.simulate
        seen = []
        def record(variant, events):
            self.assertEqual(variant, 'correct')
            self.assertTrue(all(set(event) == {'op', 'principal', 'tenant', 'action', 'credential'}
                                for event in events))
            seen.append(deepcopy(events))
            return original(variant, events)
        with patch.object(model, 'simulate', side_effect=record):
            behavior._evaluate(corpus.cases())
        self.assertEqual(seen, [row['events'] for row in corpus.cases()])

    def test_changed_and_missing_inputs_are_rejected_before_execution(self):
        rows = corpus.cases(); rows[0]['events'][0]['credential']['generation'] = 2
        for value in (rows, corpus.cases()[:-1]):
            with patch.object(model, 'simulate') as run:
                with self.assertRaisesRegex(ValueError, 'FIXED_CORPUS'): behavior._evaluate(value)
                run.assert_not_called()

    def test_missing_expectation_is_rejected(self):
        expectations = dict(behavior.EXPECTATIONS); expectations.pop(next(iter(expectations)))
        with patch.object(behavior, 'EXPECTATIONS', expectations):
            with self.assertRaisesRegex(ValueError, 'EXPECTATION_INVENTORY'):
                behavior._evaluate(corpus.cases())

    def test_expectation_types_are_strict(self):
        for malformed in (((0,), (0,)), ((False,), (False,)), ((False,), (-1,))):
            expectations = {**behavior.EXPECTATIONS, 'use_without_control--present': malformed}
            with patch.object(behavior, 'EXPECTATIONS', expectations):
                with self.assertRaisesRegex(ValueError, 'EXPECTATION_SCHEMA'):
                    behavior._evaluate(corpus.cases())

    def test_reference_cannot_disagree_with_authored_decision(self):
        with patch.object(reference, 'expected_decisions', return_value=[True]):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_DISAGREEMENT'):
                behavior._evaluate(corpus.cases())

    def test_model_boolean_replaced_by_integer_is_rejected(self):
        original = model.simulate
        def wrong(*args):
            trace = original(*args); trace['observations'][0]['accepted'] = 0
            return trace
        with patch.object(model, 'simulate', side_effect=wrong):
            with self.assertRaisesRegex(ValueError, 'MODEL_DISAGREEMENT'):
                behavior._evaluate(corpus.cases())

    def test_model_false_effect_is_rejected(self):
        original = model.simulate
        def wrong(*args):
            trace = original(*args); trace['observations'][0]['effects_after']['south.write'] = 1
            return trace
        with patch.object(model, 'simulate', side_effect=wrong):
            with self.assertRaisesRegex(ValueError, 'MODEL_DISAGREEMENT'):
                behavior._evaluate(corpus.cases())

    def test_agreeing_wrong_model_and_reference_cannot_override_authored_expectation(self):
        original = model.simulate
        def wrong(*args):
            trace = original(*args); trace['observations'][0]['accepted'] = True
            return trace
        with patch.object(model, 'simulate', side_effect=wrong), \
                patch.object(reference, 'expected_decisions', return_value=[True]):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_DISAGREEMENT'):
                behavior._evaluate(corpus.cases())

    def test_corpus_and_historical_cases_remain_unchanged(self):
        new, old = canonical(corpus.cases()), canonical(historical.cases())
        behavior._evaluate(corpus.cases())
        self.assertEqual(new, canonical(corpus.cases()))
        self.assertEqual(old, canonical(historical.cases()))
        cases = {row['case_id']: row for row in historical.cases()}
        self.assertEqual(cases['latent_revocation']['events'], cases['clean_repeat']['events'])
        self.assertFalse(cases['latent_revocation']['seeded_defect_exercised'])


class BehaviorBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'behavior'

    def reseal(self):
        (self.root/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256': {
            name: quality.sha((self.root/name).read_bytes()) for name in behavior.FILES}}))

    def test_roundtrip_discloses_model_only_scope_and_separate_denominators(self):
        report = behavior.create(self.root)
        self.assertEqual(behavior.verify(self.root, report['source_digest']), report)
        self.assertEqual((report['case_count'], report['unique_event_sequences']), (16, 13))
        self.assertEqual(report['model_variant'], 'correct')
        for field in ('native_execution_performed', 'detector_evaluated', 'injected_variants_executed',
                      'historical_detection_metrics_recomputed', 'historical_cases_and_labels_modified',
                      'case_units_pooled', 'producer_authenticated', 'vulnerability_confirmed',
                      'generalization_established', 'platform_complete'):
            self.assertIs(report[field], False)
        self.assertIsNone(report['global_progress'])
        self.assertEqual(report['accepted_uses'] + report['rejected_uses'], report['use_events'])

    def test_changed_historical_labels_block_creation(self):
        rows = historical.cases(); rows[-1]['truth'] = 'negative'
        with patch.object(historical, 'cases', return_value=rows):
            with self.assertRaisesRegex(ValueError, 'HISTORICAL_IDENTITY'): behavior.create(self.root)
        self.assertFalse(self.root.exists())

    def test_resealed_native_or_detection_claim_is_rejected(self):
        report = behavior.create(self.root)
        for field in ('native_execution_performed', 'detector_evaluated'):
            fake = {**report, field: True}
            (self.root/'evaluation.json').write_bytes(canonical(fake)); self.reseal()
            with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
                behavior.verify(self.root, report['source_digest'])

    def test_resealed_altered_trace_is_rejected(self):
        report = behavior.create(self.root)
        data = json.loads((self.root/'traces.json').read_text())
        data['cases'][0]['trace']['observations'][0]['accepted'] = True
        (self.root/'traces.json').write_bytes(canonical(data)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            behavior.verify(self.root, report['source_digest'])

    def test_resealed_authored_expectation_change_is_rejected(self):
        report = behavior.create(self.root)
        data = json.loads((self.root/'inputs.json').read_text())
        data['expectations']['use_without_control--present'] = [[True], [1]]
        (self.root/'inputs.json').write_bytes(canonical(data)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            behavior.verify(self.root, report['source_digest'])

    def test_wrong_source_is_rejected(self):
        behavior.create(self.root)
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_SOURCE'): behavior.verify(self.root, '0'*64)

    def test_hash_mismatch_is_rejected(self):
        report = behavior.create(self.root); (self.root/'REVIEW.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_HASH'):
            behavior.verify(self.root, report['source_digest'])

    def test_missing_and_extra_files_are_rejected(self):
        report = behavior.create(self.root)
        extra = self.root/'extra'; extra.write_text('x')
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_FILES'): behavior.verify(self.root, report['source_digest'])
        extra.unlink(); (self.root/'COMPLETE.json').unlink()
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_FILES'): behavior.verify(self.root, report['source_digest'])

    def test_symlinked_file_and_root_are_rejected(self):
        report = behavior.create(self.root)
        alias = Path(self.temp.name)/'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'BEHAVIOR_DIRECTORY'):
            behavior.verify(alias, report['source_digest'])
        path = self.root/'traces.json'; raw = path.read_bytes(); path.unlink()
        external = Path(self.temp.name)/'external'; external.write_bytes(raw); path.symlink_to(external)
        with self.assertRaises((OSError, ValueError)): behavior.verify(self.root, report['source_digest'])

    def test_marker_change_during_replay_is_rejected(self):
        report = behavior.create(self.root); execute = behavior._execute
        def changed(digest):
            result = execute(digest); (self.root/'COMPLETE.json').write_text('{}'); return result
        with patch.object(behavior, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'REPORT_CHANGED'):
                behavior.verify(self.root, report['source_digest'])

    def test_source_change_during_generation_blocks_completion(self):
        snapshot = quality.source_snapshot()
        with patch.object(quality, 'source_snapshot', side_effect=[snapshot, snapshot, {}]):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): behavior.create(self.root)
        self.assertFalse(self.root.exists())

    def test_existing_and_repository_destinations_are_rejected(self):
        behavior.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): behavior.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): behavior.create(behavior.ROOT/'unwanted')

    def test_cli_creation_and_verification_in_separate_processes(self):
        command = [sys.executable, '-B', '-m', 'superhunter']
        made = subprocess.run(command + ['review-owned-correct-behavior', '--out', str(self.root)],
            cwd=behavior.ROOT.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual((made.returncode, made.stderr), (0, ''))
        receipt = json.loads(made.stdout)
        checked = subprocess.run(command + ['verify-owned-correct-behavior', '--bundle', str(self.root),
            '--expected-source', receipt['source_digest']], cwd=behavior.ROOT.parent,
            capture_output=True, text=True, timeout=30)
        self.assertEqual((checked.returncode, checked.stderr), (0, ''))
        self.assertEqual(json.loads(checked.stdout), receipt)

    def test_cli_has_no_target_variant_or_external_input_option(self):
        for option in ('--variant', '--target', '--inputs'):
            result = subprocess.run([sys.executable, '-B', '-m', 'superhunter',
                'review-owned-correct-behavior', '--out', str(self.root), option, 'private-sentinel'],
                cwd=behavior.ROOT.parent, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('private-sentinel', result.stdout + result.stderr)
            self.assertFalse(self.root.exists())

    def test_component_and_worker_registration(self):
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        self.assertEqual(sum('test_owned_authority_behavior' in group for group in QA_MODULE_GROUPS), 1)
        self.assertEqual(quality.COMPONENTS['owned_authority_behavior']['files'], ['owned_authority_behavior.py'])


if __name__ == '__main__':
    unittest.main()
