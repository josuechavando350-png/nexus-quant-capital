from copy import deepcopy
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_authority_coverage as coverage
from superhunter import owned_authority_coverage_reference as reference
from superhunter.owned_authority_cases import cases, event
from superhunter.safe_io import canonical
from superhunter import quality


class CoverageTests(unittest.TestCase):
    def test_rotation_has_exact_temporal_witnesses(self):
        row = coverage.coverage(cases()[0]['events'])
        self.assertEqual(row['current_grant_use'], [1, 6])
        self.assertEqual(row['revoked_grant_use'], [3])
        self.assertEqual(row['stale_grant_after_regrant_use'], [5])
        self.assertEqual(row['current_grant_after_revocation_use'], [6])
        self.assertEqual(row['repeated_current_grant_use'], [])

    def test_latent_case_stays_identical_to_clean_repeat(self):
        source = {c['case_id']: c for c in cases()}
        a = coverage.coverage(source['latent_revocation']['events'])
        b = coverage.coverage(source['clean_repeat']['events'])
        self.assertEqual(a, b)
        self.assertEqual([k for k, v in a.items() if v],
                         ['current_grant_use', 'repeated_current_grant_use'])
        self.assertEqual(a['repeated_current_grant_use'], [2, 3])
        self.assertFalse(source['latent_revocation']['seeded_defect_exercised'])
        self.assertEqual(source['latent_revocation']['truth'], 'positive')

    def test_scope_and_principal_do_not_share_temporal_state(self):
        seq = [event('grant'), event('revoke'), event('use', principal='bob', generation=1),
               event('use', tenant='south', generation=1), event('use', action='write', generation=1)]
        row = coverage.coverage(seq)
        self.assertEqual(row['use_without_control'], [2, 3, 4])
        self.assertEqual(row['revoked_grant_use'], [])

    def test_mismatched_bindings_do_not_count_as_bound_temporal_coverage(self):
        token = event('use', generation=1)['credential']
        seq = [event('grant'), event('revoke'), event('use', principal='bob',
               tenant='south', credential=token)]
        row = coverage.coverage(seq)
        self.assertEqual(row['principal_mismatch_use'], [2])
        self.assertEqual(row['scope_mismatch_use'], [2])
        self.assertEqual(row['use_without_control'], [])
        self.assertEqual(row['revoked_grant_use'], [])

    def test_generation_never_issued_is_not_a_revoked_grant(self):
        seq = [event('grant'), event('revoke'), event('use', generation=0),
               event('use', generation=2), event('grant'), event('use', generation=2)]
        row = coverage.coverage(seq)
        self.assertEqual(row['revoked_grant_use'], [])
        self.assertEqual(row['stale_grant_after_regrant_use'], [])

    def test_early_future_generation_is_not_a_repeated_valid_use(self):
        seq = [event('use', generation=1), event('grant'), event('use', generation=1)]
        row = coverage.coverage(seq)
        self.assertEqual(row['use_without_control'], [0])
        self.assertEqual(row['current_grant_use'], [2])
        self.assertEqual(row['repeated_current_grant_use'], [])
        self.assertEqual(row, reference.coverage(seq))

    def test_new_generation_resets_repeat_condition(self):
        seq = [event('grant'), event('use', generation=1), event('grant'),
               event('use', generation=2), event('use', generation=2)]
        row = coverage.coverage(seq)
        self.assertEqual(row['repeated_current_grant_use'], [4])
        self.assertEqual(row['current_grant_after_revocation_use'], [])

    def test_revocation_without_old_grant_does_not_invent_one(self):
        seq = [event('revoke'), event('use', generation=0), event('grant'), event('use', generation=2)]
        row = coverage.coverage(seq)
        self.assertEqual(row['revoked_grant_use'], [])
        self.assertEqual(row['current_grant_after_revocation_use'], [3])
        self.assertEqual(row, reference.coverage(seq))

    def test_fixed_sequences_unchanged_and_labels_excluded(self):
        before = canonical({'cases': cases()})
        for case in cases():
            original = deepcopy(case['events'])
            self.assertEqual(coverage.coverage(case['events']), reference.coverage(case['events']))
            self.assertEqual(case['events'], original)
        self.assertEqual(before, canonical({'cases': cases()}))
        self.assertTrue(all(set(c) == {'case_id', 'events'} for c in coverage._inputs()['cases']))

    def test_invalid_records_are_rejected_by_both_algorithms(self):
        wrong = event('use', generation=1)
        wrong['credential']['generation'] = True
        extra = event('grant'); extra['truth'] = 'positive'
        for events in ([], [event('grant')] * 65, [wrong], [extra]):
            for implementation in (coverage.coverage, reference.coverage):
                with self.subTest(events=events[:1], implementation=implementation.__module__):
                    with self.assertRaises(ValueError): implementation(events)

    def test_history_reference_agrees_on_small_exhaustive_corpus(self):
        alphabet = [event('grant'), event('revoke'), event('use', generation=0),
                    event('use', generation=1), event('use', generation=3)]
        checked = 0
        for length in range(1, 5):
            for sequence in itertools.product(alphabet, repeat=length):
                events = list(sequence)
                self.assertEqual(coverage.coverage(events), reference.coverage(events))
                checked += 1
        self.assertEqual(checked, 780)

    def test_history_reference_agrees_on_seeded_multiscope_corpus(self):
        rng = random.Random(20261107)
        for _ in range(400):
            events = []
            for _ in range(rng.randint(1, 64)):
                op = rng.choice(('grant', 'revoke', 'use', 'use'))
                record = event(op, principal=rng.choice(('alice', 'bob')),
                    tenant=rng.choice(('north', 'south')), action=rng.choice(('read', 'write')),
                    generation=rng.randrange(9))
                if op == 'use' and rng.random() < 0.3:
                    record['credential']['principal'] = rng.choice(('alice', 'bob'))
                    record['credential']['tenant'] = rng.choice(('north', 'south'))
                events.append(record)
            self.assertEqual(coverage.coverage(events), reference.coverage(events))


class CoverageBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'report'

    def reseal(self):
        (self.root/'COMPLETE.json').write_bytes(canonical({'schema_version': 1, 'sha256': {
            name: quality.sha((self.root/name).read_bytes()) for name in coverage.FILES}}))

    def test_fixed_report_preserves_limits_and_duplicate_sequences(self):
        report = coverage.create(self.root)
        self.assertEqual(coverage.verify(self.root, report['source_digest']), report)
        self.assertEqual((report['case_count'], report['condition_count']), (11, 8))
        self.assertEqual(report['uncovered_in_all_cases'], ['use_without_control'])
        self.assertTrue(any(set(g['case_ids']) == {'clean_repeat', 'latent_revocation'}
                            for g in report['duplicate_event_sequences']))
        for name in ('vulnerability_confirmed', 'native_execution_performed',
                     'producer_authenticated', 'historical_detection_metrics_modified'):
            self.assertIs(report[name], False)
        self.assertIsNone(report['global_progress'])

    def test_resealed_false_coverage_is_rejected(self):
        report = coverage.create(self.root)
        report['cases'][-1]['witness_indices']['revoked_grant_use'] = [3]
        (self.root/'coverage.json').write_bytes(canonical(report)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            coverage.verify(self.root, report['source_digest'])

    def test_resealed_changed_input_cannot_replace_fixed_sequence(self):
        report = coverage.create(self.root)
        inputs = json.loads((self.root/'inputs.json').read_text())
        inputs['cases'][-1]['events'].append(event('revoke'))
        (self.root/'inputs.json').write_bytes(canonical(inputs)); self.reseal()
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            coverage.verify(self.root, report['source_digest'])

    def test_wrong_source_and_incomplete_inventory_rejected(self):
        report = coverage.create(self.root)
        with self.assertRaisesRegex(ValueError, 'COVERAGE_SOURCE'):
            coverage.verify(self.root, '0' * 64)
        (self.root/'COMPLETE.json').unlink()
        with self.assertRaisesRegex(ValueError, 'INVENTORY'):
            coverage.verify(self.root, report['source_digest'])

    def test_extra_file_and_symlink_are_rejected(self):
        report = coverage.create(self.root)
        extra = self.root/'extra.json'; extra.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'INVENTORY'):
            coverage.verify(self.root, report['source_digest'])
        extra.unlink()
        path = self.root/'coverage.json'; raw = path.read_bytes(); path.unlink()
        outside = Path(self.temp.name)/'outside.json'; outside.write_bytes(raw); path.symlink_to(outside)
        with self.assertRaises((ValueError, OSError)):
            coverage.verify(self.root, report['source_digest'])

    def test_reference_disagreement_prevents_complete_marker(self):
        with patch.object(reference, 'coverage', return_value={}):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_DISAGREEMENT'):
                coverage.create(self.root)
        self.assertFalse((self.root/'COMPLETE.json').exists())

    def test_modification_during_verification_is_rejected(self):
        report = coverage.create(self.root)
        execute = coverage._execute
        def changed(expected):
            result = execute(expected)
            (self.root/'REVIEW.md').write_bytes(b'changed\n')
            return result
        with patch.object(coverage, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_REPLAY'):
                coverage.verify(self.root, report['source_digest'])

    def test_existing_or_repository_output_is_rejected(self):
        coverage.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'): coverage.create(self.root)
        with self.assertRaisesRegex(ValueError, 'PRIVATE_OUTPUT'):
            coverage.create(coverage.ROOT/'unwanted-output')

    def test_cli_creates_and_verifies_in_separate_processes(self):
        command = [sys.executable, '-B', '-m', 'superhunter']
        made = subprocess.run(command + ['review-owned-authority-coverage', '--out', str(self.root)],
            cwd=coverage.ROOT.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual((made.returncode, made.stderr), (0, ''))
        receipt = json.loads(made.stdout)
        checked = subprocess.run(command + ['verify-owned-authority-coverage', '--bundle', str(self.root),
            '--expected-source', receipt['source_digest']], cwd=coverage.ROOT.parent,
            capture_output=True, text=True, timeout=30)
        self.assertEqual((checked.returncode, checked.stderr), (0, ''))
        self.assertEqual(json.loads(checked.stdout), receipt)

    def test_component_and_worker_registration_are_complete(self):
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        component = quality.COMPONENTS['owned_authority_coverage']
        self.assertEqual(set(component['files']), {
            'owned_authority_coverage.py', 'owned_authority_coverage_reference.py'})
        from superhunter.quality_worker import QA_MODULE_GROUPS
        self.assertEqual(sum('test_owned_authority_coverage' in group for group in QA_MODULE_GROUPS), 1)
