"""Evaluation arithmetic, anti-omission controls and real own-policy execution.

General scoring fixtures are synthetic labels/results, never scanner output.
The fixed-policy tests actually invoke the existing permissions implementation.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from superhunter import benchmark as b, benchmark_controls as controls, permissions
from superhunter.safe_io import canonical, strict_json


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        cases, records = [], []
        for index, (truth, decision) in enumerate((
            ('positive', 'positive'), ('positive', 'negative'), ('positive', 'abstain'), ('positive', 'error'),
            ('negative', 'positive'), ('negative', 'negative'), ('negative', 'abstain'), ('negative', 'error'))):
            identifier = 'case-' + str(index)
            cases.append({'case_id': identifier, 'group_id': 'group-' + str(index),
                          'content_sha256': hashlib.sha256(identifier.encode()).hexdigest(), 'split': 'test',
                          'family': 'authorization', 'truth': truth,
                          'severity': 'high' if truth == 'positive' else 'none'})
            records.append({'case_id': identifier, 'decision': decision, 'elapsed_ms': 3,
                            'cost_micro_usd': 100})
        self.corpus = {'schema_version': 1, 'corpus_id': 'format-test',
                       'unit': 'one-reviewed-property-per-case', 'provenance': 'synthetic', 'cases': cases}
        self.run = {'schema_version': 1, 'run_id': 'test-only',
                    'producer': {'name': 'synthetic', 'source_sha256': 'a'*64},
                    'corpus_sha256': b.digest(self.corpus), 'evaluation_split': 'test', 'records': records}

    def sync(self):
        self.run['corpus_sha256'] = b.digest(self.corpus)

    def go(self):
        return b.evaluate(self.corpus, self.run)

    def create(self):
        (self.root/'corpus.json').write_bytes(canonical(self.corpus))
        (self.root/'run.json').write_bytes(canonical(self.run))
        return b.create(self.root/'corpus.json', self.root/'run.json', self.root/'out')

    def verify(self):
        return b.verify(self.root/'out', expected_corpus_sha256=b.digest(self.corpus))

    def reseal(self, filename, mutate):
        root = self.root/'out'
        obj = strict_json((root/filename).read_bytes())
        mutate(obj)
        raw = canonical(obj)
        (root/filename).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_exact_eight_cell_reference(self):
        result = self.go()
        section = result['overall']
        self.assertEqual(section['counts'], {k: 1 for k in (
            'tp','fp','tn','fn','abstain_positive','abstain_negative','error_positive','error_negative')})
        self.assertEqual(section['precision'], b.ratio(1, 2))
        self.assertEqual(section['recall_all_positives'], b.ratio(1, 4))
        self.assertEqual(section['recall_decided_cases_only'], b.ratio(1, 2))
        self.assertEqual(section['decision_coverage'], b.ratio(4, 8))
        self.assertEqual(section['not_detected_positives'], 3)

    def test_missing_result_never_improves_recall(self):
        self.run['records'].pop(1)  # Hiding the explicit false negative.
        with self.assertRaisesRegex(b.BenchmarkError, 'INCOMPLETE_OR_UNEXPECTED'):
            self.go()

    def test_abstention_remains_in_operational_recall(self):
        before = self.go()['overall']
        self.run['records'][1]['decision'] = 'abstain'
        after = self.go()['overall']
        self.assertEqual(after['recall_all_positives'], before['recall_all_positives'])
        self.assertEqual(after['recall_decided_cases_only']['value'], 1.0)
        self.assertEqual(after['not_detected_positives'], 3)

    def test_error_is_not_a_negative_or_success(self):
        self.run['records'][0]['decision'] = 'error'
        counts = self.go()['overall']['counts']
        self.assertEqual(counts['tp'], 0)
        self.assertEqual(counts['fn'], 1)
        self.assertEqual(counts['error_positive'], 2)

    def test_all_abstentions_not_perfect_precision(self):
        for row in self.run['records']:
            row['decision'] = 'abstain'
        result = self.go()['overall']
        self.assertIsNone(result['precision']['value'])
        self.assertEqual(result['recall_all_positives']['value'], 0)
        self.assertEqual(result['decision_coverage']['value'], 0)

    def test_no_true_positives_cost_is_undefined(self):
        for row in self.run['records']:
            row['decision'] = 'negative'
        self.assertIsNone(self.go()['resources']['cost_micro_usd_per_true_positive'])

    def test_no_positive_labels_recall_is_undefined(self):
        for row in self.corpus['cases']:
            row.update(truth='negative', severity='none')
        self.sync()
        self.assertIsNone(self.go()['overall']['recall_all_positives']['value'])

    def test_no_negative_labels_fpr_is_undefined(self):
        for row in self.corpus['cases']:
            row.update(truth='positive', severity='low')
        self.sync()
        self.assertIsNone(self.go()['overall']['false_positive_rate_decided_negatives']['value'])

    def test_no_empty_groups_inflate_per_severity(self):
        result = self.go()['recall_by_label_severity']
        self.assertEqual(result['high']['recall_all_positives'], b.ratio(1, 4))
        self.assertIsNone(result['critical']['recall_all_positives']['value'])
        self.assertNotIn('precision', result['high'])

    def test_precise_integer_costs_and_unknowns(self):
        self.run['records'][0]['cost_micro_usd'] = 10**18
        result = self.go()['resources']
        self.assertEqual(result['total_cost_micro_usd'], 10**18 + 700)
        self.run['records'][1]['cost_micro_usd'] = None
        result = self.go()['resources']
        self.assertFalse(result['cost_complete'])
        self.assertIsNone(result['total_cost_micro_usd'])
        self.assertIsNone(result['cost_micro_usd_per_true_positive'])
        self.assertEqual(result['known_cost_micro_usd'], 10**18 + 600)

    def test_elapsed_sum_not_claimed_wall_time(self):
        result = self.go()['resources']
        self.assertEqual(result['sum_declared_case_elapsed_ms'], 24)
        self.assertFalse(result['wall_clock_time_measured_here'])

    def test_declared_split_does_not_claim_blindness(self):
        result = self.go()
        for field in ('labels_authenticated','producer_execution_authenticated','blind_evaluation_established',
                      'generalization_established','vulnerability_confirmed','external_targets_executed'):
            self.assertIs(result[field], False)

    def test_duplicate_case_id_rejected(self):
        self.corpus['cases'][1]['case_id'] = self.corpus['cases'][0]['case_id']
        self.sync()
        with self.assertRaisesRegex(b.BenchmarkError, 'DUPLICATE_CASE_ID'):
            self.go()

    def test_duplicate_content_cannot_inflate_support(self):
        self.corpus['cases'][1]['content_sha256'] = self.corpus['cases'][0]['content_sha256']
        self.sync()
        with self.assertRaisesRegex(b.BenchmarkError, 'DUPLICATE_CONTENT'):
            self.go()

    def test_group_overlap_train_test_rejected(self):
        row = deepcopy(self.corpus['cases'][0])
        row.update(case_id='training', content_sha256='b'*64, split='train')
        self.corpus['cases'].append(row)
        self.sync()
        with self.assertRaisesRegex(b.BenchmarkError, 'RELATED_GROUP'):
            self.go()

    def test_content_overlap_train_test_rejected(self):
        row = deepcopy(self.corpus['cases'][0])
        row.update(case_id='training', group_id='separate', split='train')
        self.corpus['cases'].append(row)
        self.sync()
        with self.assertRaisesRegex(b.BenchmarkError, 'DUPLICATE_CONTENT_OR_SPLIT_LEAKAGE'):
            self.go()

    def test_distinct_train_cases_not_scored(self):
        row = deepcopy(self.corpus['cases'][0])
        row.update(case_id='training', group_id='training', content_sha256='c'*64, split='train')
        self.corpus['cases'].append(row)
        self.sync()
        self.assertEqual(self.go()['overall']['cases'], 8)

    def test_same_group_within_test_is_allowed(self):
        self.corpus['cases'][1]['group_id'] = self.corpus['cases'][0]['group_id']
        self.sync()
        self.assertEqual(self.go()['overall']['cases'], 8)

    def test_unexpected_result_rejected(self):
        self.run['records'][0]['case_id'] = 'not-in-corpus'
        with self.assertRaisesRegex(b.BenchmarkError, 'INCOMPLETE_OR_UNEXPECTED'):
            self.go()

    def test_duplicate_result_rejected(self):
        self.run['records'].append(deepcopy(self.run['records'][0]))
        with self.assertRaisesRegex(b.BenchmarkError, 'DUPLICATE_RESULT'):
            self.go()

    def test_wrong_corpus_digest_rejected(self):
        self.run['corpus_sha256'] = '0'*64
        with self.assertRaisesRegex(b.BenchmarkError, 'RUN_CORPUS_BINDING'):
            self.go()

    def test_empty_selected_split_rejected(self):
        self.run['evaluation_split'] = 'development'
        with self.assertRaisesRegex(b.BenchmarkError, 'EMPTY_EVALUATION_SPLIT'):
            self.go()

    def test_training_cannot_be_reported_as_test(self):
        self.run['evaluation_split'] = 'train'
        with self.assertRaisesRegex(b.BenchmarkError, 'EVALUATION_SPLIT'):
            self.go()

    def test_boolean_values_not_numeric_records(self):
        for key in ('elapsed_ms','cost_micro_usd'):
            old = self.run['records'][0][key]
            self.run['records'][0][key] = True
            with self.subTest(key=key), self.assertRaises(b.BenchmarkError):
                self.go()
            self.run['records'][0][key] = old

    def test_floats_negative_or_infinite_costs_rejected(self):
        for value in (-1, 1.5, float('nan'), float('inf'), '0'):
            self.run['records'][0]['cost_micro_usd'] = value
            with self.subTest(value=str(value)), self.assertRaises(b.BenchmarkError):
                self.go()

    def test_no_implicit_truth_or_default_decision(self):
        for key in ('decision', 'case_id'):
            row = self.run['records'][0].copy()
            del self.run['records'][0][key]
            with self.subTest(key=key), self.assertRaises(b.BenchmarkError):
                self.go()
            self.run['records'][0] = row

    def test_severity_inconsistent_with_truth_rejected(self):
        self.corpus['cases'][4]['severity'] = 'critical'
        self.sync()
        with self.assertRaisesRegex(b.BenchmarkError, 'TRUTH_SEVERITY'):
            self.go()

    def test_case_budget_enforced(self):
        with patch.object(b, 'MAX_CASES', 4), self.assertRaises(b.BenchmarkError):
            self.go()

    def test_unexpected_fields_not_accepted(self):
        self.run['confirmed_critical'] = True
        with self.assertRaisesRegex(b.BenchmarkError, 'RUN_SCHEMA'):
            self.go()

    def test_input_records_are_not_mutated(self):
        before = deepcopy((self.corpus, self.run))
        self.go()
        self.assertEqual(before, (self.corpus, self.run))

    def test_reordering_records_preserves_all_metrics(self):
        before = self.go()
        self.run['records'].reverse()
        after = self.go()
        for key in ('overall', 'recall_by_label_severity', 'by_family', 'resources', 'decisions'):
            self.assertEqual(before[key], after[key])
        self.assertNotEqual(before['run_sha256'], after['run_sha256'])

    def test_independent_counter_does_not_call_primary(self):
        rows = list(zip(self.corpus['cases'], self.run['records']))
        with patch.object(b, '_counts', side_effect=AssertionError('primary must not run')):
            self.assertEqual(b._reference_counts(rows)['tp'], 1)

    def test_counter_disagreement_blocks_result(self):
        with patch.object(b, '_reference_counts', return_value={'tp': 999}), self.assertRaisesRegex(b.BenchmarkError, 'COUNTER_DISAGREEMENT'):
            self.go()

    def test_seeded_counts_preserve_inventory(self):
        rng = random.Random(203)
        for _ in range(64):
            for record in self.run['records']:
                record['decision'] = rng.choice(b.DECISIONS)
            result = self.go()['overall']
            self.assertEqual(sum(result['counts'].values()), 8)
            self.assertEqual(result['positive_cases'], 4)
            self.assertEqual(result['negative_cases'], 4)
            self.assertEqual(result['not_detected_positives'], 4 - result['counts']['tp'])

    def test_bundle_roundtrip_and_original_bytes(self):
        expected = self.create()
        self.assertEqual(self.verify(), expected)
        self.assertEqual((self.root/'corpus.json').read_bytes(), (self.root/'out/corpus.json').read_bytes())

    def test_external_corpus_pin_mandatory(self):
        self.create()
        with self.assertRaisesRegex(b.BenchmarkError, 'EXTERNAL_CORPUS_PIN_MISMATCH'):
            b.verify(self.root/'out', expected_corpus_sha256='0'*64)

    def test_changed_labels_cannot_pass_external_pin(self):
        self.create()
        self.reseal('corpus.json', lambda obj: obj['cases'][0].update(truth='negative', severity='none'))
        with self.assertRaisesRegex(b.BenchmarkError, 'EXTERNAL_CORPUS_PIN_MISMATCH'):
            self.verify()

    def test_resealed_metrics_rejected(self):
        self.create()
        self.reseal('evaluation.json', lambda obj: obj['overall']['precision'].update(value=1.0))
        with self.assertRaisesRegex(b.BenchmarkError, 'METRICS_REPLAY_DISAGREEMENT'):
            self.verify()

    def test_resealed_generalization_claim_rejected(self):
        self.create()
        self.reseal('evaluation.json', lambda obj: obj.update(generalization_established=True))
        with self.assertRaisesRegex(b.BenchmarkError, 'METRICS_REPLAY_DISAGREEMENT'):
            self.verify()

    def test_audit_event_semantics_required(self):
        self.create()
        self.reseal('audit.json', lambda obj: obj['entries'][1].update(event='benchmark.fake'))
        with self.assertRaisesRegex(b.BenchmarkError, 'AUDIT_SEMANTICS'):
            self.verify()

    def test_changed_engine_identity_rejected(self):
        self.create()
        with patch.object(b, 'code_identity', return_value={'invalid': 'new-code'}), self.assertRaisesRegex(b.BenchmarkError, 'ENGINE_IDENTITY_MISMATCH'):
            self.verify()

    def test_private_outputs_and_no_overwrite(self):
        self.create()
        self.assertEqual((self.root/'out').stat().st_mode & 0o777, 0o700)
        for path in (self.root/'out').iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(b.BenchmarkError, 'NEW_OUTPUT_REQUIRED'):
            self.create()

    def test_extra_file_rejected_not_leaked(self):
        self.create()
        (self.root/'out/secret.txt').write_text('LOCAL TEST CANARY')
        with self.assertRaisesRegex(b.BenchmarkError, 'BUNDLE_FILE_SET'):
            self.verify()

    def test_symlink_input_rejected(self):
        self.create()
        (self.root/'alias.json').symlink_to(self.root/'corpus.json')
        with self.assertRaises((OSError, ValueError)):
            b.create(self.root/'alias.json', self.root/'run.json', self.root/'other')

    def test_missing_completion_marker_rejected(self):
        self.create()
        (self.root/'out/COMPLETE.json').unlink()
        with self.assertRaises(OSError):
            self.verify()

    def test_scorer_does_not_execute_process_or_network(self):
        with patch('socket.socket', side_effect=AssertionError('network')), patch('subprocess.run', side_effect=AssertionError('process')):
            self.create()
            self.verify()

    def test_cli_roundtrip_in_separate_processes(self):
        self.create()
        for args in (['evaluate-benchmark','--corpus',str(self.root/'corpus.json'),
                      '--run',str(self.root/'run.json'),'--out',str(self.root/'cli')],
                     ['verify-benchmark','--bundle',str(self.root/'cli'),
                      '--expected-corpus-sha256',b.digest(self.corpus)]):
            proc = subprocess.run([sys.executable,'-B','-m','superhunter',*args], cwd=b.ROOT.parent,
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse(json.loads(proc.stdout)['generalization_established'])

    def test_cli_diagnostics_never_echo_argument_values(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream, self.assertRaises(SystemExit):
            b.main(['verify-benchmark','--bundle','PRIVATE','--expected-corpus-sha256','0'*64,'--extra','SECRET'])
        self.assertNotIn('SECRET', stream.getvalue())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(b.main(['verify-benchmark','--bundle','PRIVATE','--expected-corpus-sha256','0'*64]),2)
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_fixed_control_labels_do_not_depend_on_predictions(self):
        with patch.object(permissions, 'analyze_policy', side_effect=AssertionError('engine')):
            self.assertEqual(len(controls.corpus_record()['cases']), 8)

    def test_fixed_control_calls_actual_permissions_engine(self):
        with patch.object(permissions,'analyze_policy', wraps=permissions.analyze_policy) as engine:
            corpus, run, traces = controls.execute()
        self.assertEqual(engine.call_count, 8)
        result = b.evaluate(corpus, run)
        self.assertEqual(result['overall']['counts']['tp'], 4)
        self.assertEqual(result['overall']['counts']['tn'], 4)
        self.assertEqual(result['overall']['counts']['fp'], 0)
        self.assertFalse(result['generalization_established'])
        self.assertTrue(traces['fixed_fixture_only'])

    def test_fixed_control_replay_reexecutes_engine(self):
        controls.create(self.root/'control')
        with patch.object(permissions,'analyze_policy', wraps=permissions.analyze_policy) as engine:
            result = controls.verify(self.root/'control')
        self.assertEqual(engine.call_count, 8)
        self.assertEqual(result['cases'], 8)

    def test_fixed_control_policy_cannot_be_changed_to_pass(self):
        controls.create(self.root/'out')
        self.reseal('traces.json', lambda obj: obj['cases'][0]['policy']['users']['alice'].update(disabled=True))
        with self.assertRaisesRegex(b.BenchmarkError, 'CONTROL_POLICY_CHANGED'):
            controls.verify(self.root/'out')

    def test_fixed_control_decisions_cannot_be_changed_to_pass(self):
        controls.create(self.root/'out')
        self.reseal('run.json', lambda obj: obj['records'][0].update(decision='negative'))
        with self.assertRaisesRegex(b.BenchmarkError, 'CONTROL_DECISION_MISMATCH'):
            controls.verify(self.root/'out')

    def test_fixed_control_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network')), patch('subprocess.run',side_effect=AssertionError('process')):
            result = controls.create(self.root/'control')
        self.assertEqual(result['status'], 'FIXED_PERMISSION_EVALUATION_REPLAYED')

    def test_fixed_cli_roundtrip(self):
        for args in (['benchmark-permissions','--out',str(self.root/'control')],
                     ['verify-permission-benchmark','--bundle',str(self.root/'control')]):
            proc = subprocess.run([sys.executable,'-B','-m','superhunter',*args],cwd=b.ROOT.parent,
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_existing_custody_signs_evaluation_and_detects_change(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from superhunter import custody
        self.create()
        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        now = datetime.now(timezone.utc)
        cid = str(uuid.uuid4())
        trust = {'schema_version':1, 'profile':custody.PROFILE, 'keys':[{
            'key_id':hashlib.sha256(pub).hexdigest(), 'public_key_hex':pub.hex(), 'producer_id':'benchmark-test',
            'case_ids':[cid], 'valid_from':(now-timedelta(hours=1)).isoformat(),
            'valid_until':(now+timedelta(hours=1)).isoformat(), 'revoked':False}]}
        statement = custody.attest(self.root/'out',key,trust,case_id=cid,producer_id='benchmark-test',
                                    issued_at=now.isoformat(),expires_at=(now+timedelta(minutes=30)).isoformat())
        result = custody.verify_attestation(self.root/'out',statement,trust,expected_case_id=cid,
                                            expected_producer_id='benchmark-test',at=now.isoformat())
        self.assertTrue(result['signature_valid'])
        self.assertFalse(result['semantic_evidence_verified'])
        self.reseal('evaluation.json',lambda obj:obj.update(generalization_established=True))
        with self.assertRaises(custody.CustodyError):
            custody.verify_attestation(self.root/'out',statement,trust,expected_case_id=cid,
                                        expected_producer_id='benchmark-test',at=now.isoformat())

    def test_new_component_has_required_checks(self):
        from superhunter import quality
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        self.assertIn('benchmark', quality.COMPONENTS['quality']['depends'])
        self.assertIn('test_benchmark.BenchmarkTests.test_missing_result_never_improves_recall', quality.REQUIRED_TESTS)


if __name__ == '__main__':
    unittest.main()
