"""Own finite model controls, not real credentials or native EVM acceptance."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import itertools
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_authority_review as review
from superhunter import owned_authority_cases as corpus, owned_authority_model as model
from superhunter.safe_io import canonical, strict_json


class AuthorityReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.out = self.root / 'bundle'
        self.digest = review.sha(canonical(review.quality.source_snapshot()))

    def trace(self, name):
        case = next(c for c in corpus.cases() if c['case_id'] == name)
        return model.simulate(case['variant'], case['events'])

    def execution(self):
        return {'schema_version': 1, 'profile': model.PROFILE, 'source_digest': self.digest,
                'cases': [{'case_id': c['case_id'], 'trace': model.simulate(c['variant'], c['events'])}
                          for c in corpus.cases()]}

    def evaluate(self):
        return review.evaluate(self.execution(), self.digest)

    def reseal(self, name, mutation):
        path = self.out / name
        value = strict_json(path.read_bytes())
        mutation(value)
        raw = canonical(value)
        path.write_bytes(raw)
        marker = strict_json((self.out / 'COMPLETE.json').read_bytes())
        marker['sha256'][name] = review.sha(raw)
        (self.out / 'COMPLETE.json').write_bytes(canonical(marker))

    def test_latent_defect_remains_an_explicit_omission(self):
        result = self.evaluate()
        counts = result['metrics']['full']['counts']
        self.assertEqual({k: counts[k] for k in ('tp', 'tn', 'fp', 'fn')},
                         {'tp': 6, 'tn': 4, 'fp': 0, 'fn': 1})
        self.assertEqual(result['missed_case_ids'], ['latent_revocation'])
        self.assertFalse(result['all_seeded_cases_detected'])
        self.assertEqual((result['case_count'], result['observation_count']), (11, 42))
        self.assertEqual(result['metrics']['full']['recall_all_positives']['denominator'], 7)
        self.assertEqual(result['metrics']['full']['not_detected_positives'], 1)

    def test_clean_and_latent_cases_are_observationally_identical(self):
        clean, latent = self.trace('clean_repeat'), self.trace('latent_revocation')
        self.assertEqual(canonical(clean), canonical(latent))
        self.assertEqual(review.detect(clean), review.detect(latent))
        self.assertEqual(review.detect(latent)['coverage']['revoke_commands'], 0)
        groups = self.evaluate()['observationally_equal_case_groups']
        self.assertTrue(any(set(g['case_ids']) == {'clean_repeat', 'latent_revocation'} for g in groups))

    def test_issued_snapshot_ablation_creates_false_positives(self):
        counts = self.evaluate()['metrics']['issued_snapshot']['counts']
        self.assertEqual({k: counts[k] for k in ('tp', 'tn', 'fp', 'fn')},
                         {'tp': 4, 'tn': 2, 'fp': 2, 'fn': 3})
        self.assertEqual(review.detect(self.trace('clean_rotation'))['decision'], 'negative')
        self.assertEqual(review.detect(self.trace('clean_rotation'), 'issued_snapshot')['decision'], 'positive')

    def test_decision_only_omits_double_effect(self):
        counts = self.evaluate()['metrics']['decision_only']['counts']
        self.assertEqual((counts['tp'], counts['tn'], counts['fp'], counts['fn']), (5, 4, 0, 2))
        trace = self.trace('double_effect')
        self.assertEqual(review.detect(trace)['violations'][0]['reasons'], ['EFFECT_DELTA_MISMATCH'])
        self.assertEqual(review.detect(trace, 'decision_only')['decision'], 'negative')

    def test_subject_scope_and_generation_have_actual_witnesses(self):
        for name in ('subject_binding', 'scope_binding', 'stale_after_regrant', 'ignored_revocation'):
            with self.subTest(case=name):
                result = review.detect(self.trace(name))
                self.assertEqual(result['decision'], 'positive')
                self.assertTrue(any('UNAUTHORIZED_USE_ACCEPTED' in v['reasons'] for v in result['violations']))

    def test_repeated_valid_use_is_not_treated_as_replay_abuse(self):
        result = review.detect(self.trace('clean_repeat'))
        self.assertEqual(result['decision'], 'negative')
        self.assertEqual(result['coverage']['use_requests'], 3)
        self.assertFalse(result['absence_of_defect_proved'])

    def test_valid_use_denial_is_measured_without_bounty_severity(self):
        result = review.detect(self.trace('valid_denied'))
        self.assertEqual(result['violations'][0]['reasons'], ['VALID_USE_REJECTED'])
        self.assertNotIn('severity', result)

    def test_reference_disagreement_blocks_instead_of_inventing_a_verdict(self):
        trace = self.trace('clean_rotation')
        with patch.object(review.reference, 'expected_decisions', return_value=[True] * len(trace['events'])):
            with self.assertRaisesRegex(ValueError, 'REFERENCE_DISAGREEMENT'):
                review.detect(trace)

    def test_malformed_reference_result_is_blocked(self):
        for result in ([], None, [True] * 3, [1] * 4):
            with self.subTest(result=result), patch.object(review.reference, 'expected_decisions', return_value=result):
                with self.assertRaisesRegex(ValueError, 'REFERENCE_SCHEMA'):
                    review.detect(self.trace('clean_repeat'))

    def test_all_short_single_scope_sequences_agree_without_false_alarms(self):
        # 1296 own finite sequences, a QA differential control, not extra
        # independent benchmark samples or evidence of real-world coverage.
        alphabet = [corpus.event('grant'), corpus.event('revoke')]
        alphabet += [corpus.event('use', generation=n) for n in range(4)]
        count = 0
        for sequence in itertools.product(alphabet, repeat=4):
            result = review.detect(model.simulate('correct', list(sequence)))
            self.assertEqual(result['decision'], 'negative')
            count += 1
        self.assertEqual(count, 1296)

    def test_generated_multiscope_sequences_keep_reference_agreement(self):
        rng = random.Random(20261107)
        for _ in range(96):
            events = []
            for _ in range(12):
                op = rng.choice(('grant', 'revoke', 'use'))
                events.append(corpus.event(op, rng.choice(model.PRINCIPALS),
                    rng.choice(model.TENANTS), rng.choice(model.ACTIONS),
                    generation=rng.randrange(6)))
            self.assertEqual(review.detect(model.simulate('correct', events))['decision'], 'negative')

    def test_scope_renaming_preserves_classification(self):
        rename = {'alice': 'bob', 'bob': 'alice', 'north': 'south', 'south': 'north',
                  'read': 'write', 'write': 'read'}
        for case in corpus.cases():
            # Clone each logical event independently. A whole-list deepcopy
            # preserves repeated-event aliases and would rename them twice.
            events = [deepcopy(event) for event in case['events']]
            for event in events:
                for field in ('principal', 'tenant', 'action'):
                    event[field] = rename[event[field]]
                if event['credential'] is not None:
                    for field in ('principal', 'tenant', 'action'):
                        event['credential'][field] = rename[event['credential'][field]]
            original = review.detect(model.simulate(case['variant'], case['events']))
            renamed = review.detect(model.simulate(case['variant'], events))
            self.assertEqual(renamed['decision'], original['decision'])
            self.assertEqual([v['index'] for v in renamed['violations']], [v['index'] for v in original['violations']])

    def test_detector_rejects_variant_truth_and_case_labels(self):
        for field, value in (('variant', 'correct'), ('truth', 'negative'), ('case_id', 'clean_repeat')):
            trace = self.trace('clean_repeat')
            trace[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'TRACE_SCHEMA'):
                review.detect(trace)

    def test_detector_does_not_mutate_observations(self):
        trace = self.trace('clean_rotation')
        before = canonical(trace)
        for policy in review.POLICIES:
            review.detect(trace, policy)
        self.assertEqual(canonical(trace), before)

    def test_missing_duplicate_and_reordered_observations_rejected(self):
        trace = self.trace('clean_rotation')
        rows = trace['observations']
        for replacement in (rows[:-1], rows + [rows[0]], list(reversed(rows))):
            bad = deepcopy(trace)
            bad['observations'] = replacement
            with self.assertRaises(ValueError): review.detect(bad)

    def test_discontinuous_observations_are_invalid_evidence(self):
        trace = self.trace('clean_repeat')
        trace['observations'][2]['effects_before']['north.read'] += 1
        with self.assertRaisesRegex(ValueError, 'DISCONTINUOUS'):
            review.detect(trace)

    def test_booleans_cannot_replace_integer_evidence(self):
        mutations = [lambda t: t.update(schema_version=True),
                     lambda t: t['observations'][0].update(index=False),
                     lambda t: t['observations'][0]['effects_before'].update({'north.read': False}),
                     lambda t: t['events'][1]['credential'].update(generation=True)]
        for mutation in mutations:
            trace = self.trace('clean_repeat')
            mutation(trace)
            with self.assertRaises(ValueError): review.detect(trace)

    def test_numeric_acceptance_cannot_replace_boolean_status(self):
        trace = self.trace('clean_repeat')
        trace['observations'][1]['accepted'] = 1
        with self.assertRaises(ValueError): review.detect(trace)

    def test_event_budget_empty_overflow_and_unknown_scope_rejected(self):
        for events in ([], [corpus.event('grant')] * 65,
                       [corpus.event('grant', principal='outside-principal')],
                       [corpus.event('use', generation=65)]):
            with self.assertRaises(ValueError): model.simulate('correct', events)
        with self.assertRaises(ValueError): model.simulate('external-code', [corpus.event('grant')])

    def test_fixed_case_inventory_cannot_drop_or_duplicate_omissions(self):
        original = self.execution()
        for rows in (original['cases'][:-1], original['cases'] + [original['cases'][0]],
                     list(reversed(original['cases']))):
            altered = deepcopy(original)
            altered['cases'] = rows
            with self.assertRaises(ValueError): review.evaluate(altered, self.digest)

    def test_changed_declared_sequence_cannot_keep_original_label(self):
        execution = self.execution()
        execution['cases'][-1]['trace'] = self.trace('ignored_revocation')
        with self.assertRaisesRegex(ValueError, 'FIXED_SEQUENCE'):
            review.evaluate(execution, self.digest)

    def test_source_mismatch_blocks_before_models_run(self):
        review.create(self.out)
        with patch.object(model, 'simulate', wraps=model.simulate) as run:
            with self.assertRaisesRegex(ValueError, 'SOURCE_MISMATCH'):
                review.verify(self.out, '0' * 64)
        run.assert_not_called()

    def test_roundtrip_reexecutes_every_model(self):
        created = review.create(self.out)
        with patch.object(model, 'simulate', wraps=model.simulate) as run:
            verified = review.verify(self.out, self.digest)
        self.assertEqual(run.call_count, 11)
        self.assertEqual(canonical(created), canonical(verified))

    def test_rehashed_omission_removal_is_rejected_after_reexecution(self):
        review.create(self.out)
        def change(result):
            result['missed_case_ids'] = []
            result['all_seeded_cases_detected'] = True
            result['metrics']['full']['counts']['fn'] = 0
        self.reseal('evaluation.json', change)
        with patch.object(model, 'simulate', wraps=model.simulate) as run:
            with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
                review.verify(self.out, self.digest)
        self.assertEqual(run.call_count, 11)

    def test_rehashed_false_original_vulnerability_claim_is_rejected(self):
        review.create(self.out)
        self.reseal('evaluation.json', lambda r: r.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
            review.verify(self.out, self.digest)

    def test_marker_type_change_during_replay_is_rejected_byte_for_byte(self):
        review.create(self.out)
        original = review._execute
        def changed(expected):
            result = original(expected)
            marker = strict_json((self.out / 'COMPLETE.json').read_bytes())
            marker['schema_version'] = True
            (self.out / 'COMPLETE.json').write_bytes(canonical(marker))
            return result
        with patch.object(review, '_execute', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'EVIDENCE_CHANGED'):
                review.verify(self.out, self.digest)

    def test_missing_marker_or_extra_file_cannot_start_replay(self):
        review.create(self.out)
        (self.out / 'extra.json').write_text('{}')
        with patch.object(model, 'simulate', wraps=model.simulate) as run:
            with self.assertRaisesRegex(ValueError, 'INVENTORY'):
                review.verify(self.out, self.digest)
        run.assert_not_called()
        (self.out / 'extra.json').unlink()
        (self.out / 'COMPLETE.json').unlink()
        with self.assertRaises(ValueError): review.verify(self.out, self.digest)

    def test_symlink_artifact_rejected(self):
        review.create(self.out)
        saved = self.root / 'saved.json'
        saved.write_bytes((self.out / 'traces.json').read_bytes())
        (self.out / 'traces.json').unlink()
        (self.out / 'traces.json').symlink_to(saved)
        with self.assertRaises((ValueError, OSError)): review.verify(self.out, self.digest)

    def test_existing_and_source_tree_outputs_are_rejected(self):
        review.create(self.out)
        with self.assertRaises(ValueError): review.create(self.out)
        with self.assertRaises(ValueError): review.create(review.ROOT / 'OWN-NOT-CREATED')
        self.assertFalse((review.ROOT / 'OWN-NOT-CREATED').exists())

    def test_source_change_during_execution_blocks_result(self):
        snapshot = review.quality.source_snapshot()
        changed = {**snapshot, 'UNIT_ONLY_CHANGED_SOURCE': 'f' * 64}
        with patch.object(review.quality, 'source_snapshot', side_effect=[snapshot, snapshot, changed]):
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED_DURING_RUN'):
                review._execute(self.digest)

    def test_result_keeps_scope_and_noncertification_explicit(self):
        result = self.evaluate()
        for key in ('all_seeded_cases_detected', 'detector_receives_variant_or_truth',
                    'history_reference_uses_producer_state', 'producer_authenticated',
                    'native_evm_executed', 'cryptographic_credential_authentication_implemented',
                    'blind_benchmark', 'generalization_established', 'absence_of_defect_proved',
                    'platform_complete', 'vulnerability_confirmed'):
            self.assertIs(result[key], False)
        self.assertEqual(result['external_targets_executed'], 0)
        self.assertEqual(result['unique_seeded_mutations'], 6)
        self.assertEqual((result['activated_defect_cases'], result['latent_defect_cases']), (6, 1))

    def test_cli_completion_does_not_claim_all_cases_passed(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = review.main(['evaluate-owned-authority', '--out', str(self.out)])
        result = strict_json(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(result['counts']['fn'], 1)
        self.assertFalse(result['all_seeded_cases_detected'])
        self.assertNotIn('PASS', result['status'])

    def test_cli_has_no_target_input_and_redacts_private_paths(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit):
            review.main(['evaluate-owned-authority', '--out', str(self.out), '--target', 'PRIVATE-OWN-TEST'])
        self.assertNotIn('PRIVATE-OWN-TEST', output.getvalue())
        output = io.StringIO()
        with patch.object(review, '_execute', side_effect=ValueError('PRIVATE-OWN-TEST')), redirect_stdout(output):
            rc = review.main(['evaluate-owned-authority', '--out', str(self.out)])
        self.assertEqual(rc, 2)
        self.assertNotIn('PRIVATE-OWN-TEST', output.getvalue())


if __name__ == '__main__':
    unittest.main()
