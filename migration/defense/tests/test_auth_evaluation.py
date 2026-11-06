import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import nqc_defense.auth_evaluation as evaluation
from nqc_defense.codec import Rejected, canonical, decode
from nqc_defense.files import sha256

PACKAGE = Path(__file__).resolve().parents[1]


class AuthEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.corpus = json.loads((PACKAGE/'docs/AUTH_EVALUATION_CORPUS.json').read_bytes())
        self.policy = json.loads((PACKAGE/'docs/AUTH_EVALUATION_POLICY.json').read_bytes())

    def arguments(self):
        corpus, policy = canonical(self.corpus),canonical(self.policy)
        return corpus,sha256(corpus),policy,sha256(policy)

    def run_evaluation(self, **kwargs):
        return evaluation.evaluate(*self.arguments(),**kwargs)

    def test_separate_authored_corpus_has_visible_errors_and_unknown_labels(self):
        report = self.run_evaluation()
        self.assertEqual(report['confusion_matrix'],{'true_positive':7,'false_positive':2,'true_negative':4,'false_negative':2})
        self.assertEqual(report['labeled_scenarios'],15)
        self.assertEqual(report['unlabeled_scenarios'],3)
        self.assertEqual(report['metrics']['precision'],{'numerator':7,'denominator':9,'parts_per_million':777777})
        self.assertEqual(report['evidence_bundles_verified_after_cleanup'],11)
        self.assertFalse(report['independent_evaluation']); self.assertFalse(report['production_accuracy_claimed'])

    def test_reports_reproduce_across_batch_sizes_reopens_and_temp_paths(self):
        self.assertEqual(self.run_evaluation(batch_size=1),self.run_evaluation(batch_size=200))

    def test_unlabeled_records_do_not_become_true_negatives(self):
        self.corpus['scenarios'] = [s for s in self.corpus['scenarios'] if s['label']=='unlabeled']
        report = self.run_evaluation()
        self.assertEqual(sum(report['confusion_matrix'].values()),0)
        for metric in report['metrics'].values():
            self.assertIsNone(metric['parts_per_million']); self.assertEqual(metric['denominator'],0)
        self.assertTrue(all(s['classification'] is None for s in report['scenarios']))

    def test_duplicate_late_invalid_and_unclassified_counts_remain_visible(self):
        results = {s['id']:s for s in self.run_evaluation()['scenarios']}
        self.assertEqual(results['review_out_of_order']['exclusion_reasons'],{'out_of_order':2})
        self.assertEqual(results['journal_reexport_routine']['excluded_by_kind'],{'sensor.duplicate':3})
        self.assertEqual(results['unlabeled_invalid_bytes']['excluded_by_kind'],{'sensor.input_rejected':2})
        self.assertEqual(results['native_nonfinal_unlabeled']['excluded_by_kind'],{'sensor.unclassified':3})

    def test_every_case_references_exact_input_bytes(self):
        report = self.run_evaluation()
        originals = {s['id']:[base64.b64decode(x) for x in s['records_base64']] for s in self.corpus['scenarios']}
        for result in report['scenarios']:
            lines = originals[result['id']]
            for case in result['cases']:
                self.assertTrue(case['trigger_conditions_verified'])
                self.assertEqual(len(case['trigger_records']),3)
                for ref in case['trigger_records']:
                    index = ref['record_index']; raw = lines[index]
                    self.assertEqual(ref['raw_sha256'],sha256(raw))
                    self.assertEqual(ref['start'],sum(map(len,lines[:index])))
                    self.assertEqual(ref['end']-ref['start'],len(raw))

    def test_offline_evidence_recheck_occurs_after_original_directory_is_removed(self):
        original = evaluation.verify_bundle; checked = []
        def verify(*args):
            value = decode(args[0],max_bytes=8*1024*1024,max_nodes=65536)
            self.assertFalse(Path(value['source_config']['root']).exists())
            checked.append(args[1]); return original(*args)
        with patch.object(evaluation,'verify_bundle',side_effect=verify):
            report = self.run_evaluation()
        self.assertEqual(len(checked),report['evidence_bundles_verified_after_cleanup'])

    def test_wrong_pin_prevents_any_store_creation(self):
        args = list(self.arguments()); args[1] = '0'*64
        with patch.object(evaluation.tempfile,'TemporaryDirectory') as temporary:
            with self.assertRaisesRegex(Rejected,'evaluation_input_digest'): evaluation.evaluate(*args)
            temporary.assert_not_called()

    def test_invalid_last_scenario_rejects_entire_corpus_before_execution(self):
        self.corpus['scenarios'][-1]['label'] = True
        with patch.object(evaluation,'OperationsStore') as store:
            with self.assertRaisesRegex(Rejected,'evaluation_label'): self.run_evaluation()
            store.create.assert_not_called()

    def test_noncanonical_input_is_rejected_even_with_matching_digest(self):
        corpus = json.dumps(self.corpus).encode(); policy = canonical(self.policy)
        with self.assertRaisesRegex(Rejected,'evaluation_input_not_canonical'):
            evaluation.evaluate(corpus,sha256(corpus),policy,sha256(policy))

    def test_duplicate_scenario_identity_rejected(self):
        self.corpus['scenarios'].append(deepcopy(self.corpus['scenarios'][0]))
        with self.assertRaisesRegex(Rejected,'evaluation_duplicate_scenario'): self.run_evaluation()

    def test_strict_policy_schema_and_bounds(self):
        for field,value in [('threshold',True),('threshold',1),('threshold',101),('window_seconds',0),('window_seconds',86401),('schema','other')]:
            with self.subTest(field=field,value=value):
                old = self.policy[field]; self.policy[field] = value
                with self.assertRaises(Rejected): self.run_evaluation()
                self.policy[field] = old
        self.policy['automatic_response'] = True
        with self.assertRaises(Rejected): self.run_evaluation()

    def test_native_host_scope_is_validated_before_running(self):
        self.corpus['scenarios'][0]['expected_host'] = 'node-eval'
        with self.assertRaisesRegex(Rejected,'auth_host_requires_native_format'): self.run_evaluation()

    def test_bad_record_encoding_and_incomplete_lines_are_rejected(self):
        scenario = self.corpus['scenarios'][0]
        for value in ['@@@',base64.b64encode(b'{}').decode(),base64.b64encode(b'{}\n{}\n').decode(),base64.b64encode(b'x'*16384+b'\n').decode(),'\ud800']:
            with self.subTest(value=value[:10]):
                scenario['records_base64'] = [value]
                with self.assertRaises(Rejected): self.run_evaluation()

    def test_corpus_byte_budget_is_enforced_before_decode(self):
        corpus = b'x'*(evaluation.MAX_CORPUS+1); policy = canonical(self.policy)
        with self.assertRaisesRegex(Rejected,'evaluation_input_budget'):
            evaluation.evaluate(corpus,sha256(corpus),policy,sha256(policy))

    def test_scenario_count_limit(self):
        scenario = self.corpus['scenarios'][0]
        self.corpus['scenarios'] = [{**scenario,'id':f'case-{i}'} for i in range(65)]
        with self.assertRaisesRegex(Rejected,'evaluation_scenario_count'): self.run_evaluation()

    def test_exact_maximum_total_records_execute_without_pagination_loss(self):
        scenario = self.corpus['scenarios'][0]
        # An actual valid success record, repeated in temporary logs; all 4096 are ingested.
        line = scenario['records_base64'][0]
        self.corpus['scenarios'] = [{**scenario,'id':f'case-{i}','records_base64':[line]*256} for i in range(16)]
        report = self.run_evaluation(batch_size=31)
        self.assertEqual(sum(s['records'] for s in report['scenarios']),4096)
        self.assertEqual(sum(s['rule_evaluated_records'] for s in report['scenarios']),4096)
        self.assertEqual(report['confusion_matrix']['true_negative'],16)

    def test_total_record_limit_rejects_before_io(self):
        scenario = self.corpus['scenarios'][0]; line = scenario['records_base64'][0]
        self.corpus['scenarios'] = [{**scenario,'id':f'case-{i}','records_base64':[line]*256} for i in range(16)]
        self.corpus['scenarios'].append({**scenario,'id':'extra','records_base64':[line]})
        with patch.object(evaluation.tempfile,'TemporaryDirectory') as temporary:
            with self.assertRaisesRegex(Rejected,'evaluation_total_records'): self.run_evaluation()
            temporary.assert_not_called()

    def test_maximum_distinct_cases_are_preserved_and_reverified(self):
        self.policy['threshold'] = 2
        scenario = self.corpus['scenarios'][0]
        lines = [canonical({'schema':'nqc-auth-log-v1','time_ns':i*1000000000,
            'outcome':'failure','principal':f'account{i//2}','remote_address':'192.0.2.70'})+b'\n' for i in range(256)]
        self.corpus['scenarios'] = [{**scenario,'label':'review','records_base64':[base64.b64encode(x).decode() for x in lines]}]
        report = self.run_evaluation()
        self.assertEqual(len(report['scenarios'][0]['cases']),128)
        self.assertEqual(report['evidence_bundles_verified_after_cleanup'],128)
        self.assertEqual(report['confusion_matrix']['true_positive'],1)

    def test_exact_maximum_scenario_count_executes(self):
        scenario = self.corpus['scenarios'][0]
        self.corpus['scenarios'] = [{**scenario,'id':f'case-{i}','records_base64':scenario['records_base64'][:1]} for i in range(64)]
        self.assertEqual(len(self.run_evaluation()['scenarios']),64)

    def test_label_changes_require_new_pin_and_do_not_change_detector_output(self):
        self.corpus['scenarios'] = [self.corpus['scenarios'][1]]
        before = self.run_evaluation(); self.corpus['scenarios'][0]['label'] = 'review'; after = self.run_evaluation()
        self.assertNotEqual(before['corpus_digest'],after['corpus_digest'])
        self.assertEqual(before['scenarios'][0]['cases'],after['scenarios'][0]['cases'])
        self.assertEqual(before['scenarios'][0]['classification'],'false_positive')
        self.assertEqual(after['scenarios'][0]['classification'],'true_positive')

    def test_evidence_verification_failure_never_produces_a_success_report(self):
        with patch.object(evaluation,'verify_bundle',side_effect=Rejected('test_evidence_failure')):
            with self.assertRaisesRegex(Rejected,'test_evidence_failure'): self.run_evaluation()

    def test_changed_source_fingerprint_rejects_report(self):
        original = Path.read_bytes; seen = 0
        def read(path):
            nonlocal seen
            data = original(path)
            if path.name == 'auth_evaluation.py':
                seen += 1
                if seen == 2: return data+b'\n'
            return data
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(Rejected,'evaluation_source_changed'): self.run_evaluation()

    def test_edited_report_rejected_despite_rehashed_content(self):
        report = self.run_evaluation(); altered = deepcopy(report); altered['confusion_matrix']['false_positive'] = 0
        data = canonical(altered)
        with self.assertRaisesRegex(Rejected,'evaluation_report_discrepancy'):
            evaluation.verify_report(data,sha256(data),report)

    def test_private_atomic_publication_recovers_identical_retry(self):
        report = self.run_evaluation()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'report.json'
            first = evaluation.publish_report(output,report)
            self.assertEqual(evaluation.publish_report(output,report),first)
            self.assertEqual(output.stat().st_mode&0o777,0o600)
            other = deepcopy(report); other['labeled_scenarios'] = 0
            with self.assertRaises(Rejected): evaluation.publish_report(output,other)
            self.assertEqual(output.read_bytes(),canonical(report))

    def test_public_output_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); root.chmod(0o755)
            with self.assertRaises(Rejected): evaluation.publish_report(root/'report.json',{})
            self.assertFalse((root/'report.json').exists())

    def test_cli_run_verify_and_wrong_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); corpus,corpus_pin,policy,policy_pin=self.arguments()
            (root/'corpus.json').write_bytes(corpus); (root/'policy.json').write_bytes(policy)
            common=['--corpus',str(root/'corpus.json'),'--corpus-digest',corpus_pin,'--policy',str(root/'policy.json'),'--policy-digest',policy_pin]
            cli=[sys.executable,'-B',str(PACKAGE/'tools/auth_evaluation.py')]
            run=subprocess.run(cli+['run']+common+['--output',str(root/'report.json')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr); receipt=json.loads(run.stdout)
            verified=subprocess.run(cli+['verify']+common+['--report',str(root/'report.json'),'--report-digest',receipt['report_digest']],capture_output=True,text=True)
            self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)
            common[3]='0'*64
            rejected=subprocess.run(cli+['run']+common+['--output',str(root/'bad.json')],capture_output=True,text=True)
            self.assertEqual(rejected.returncode,2); self.assertFalse((root/'bad.json').exists())

    def test_cli_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); corpus,pin,policy,policy_pin=self.arguments()
            (root/'real.json').write_bytes(corpus); (root/'link.json').symlink_to(root/'real.json'); (root/'policy.json').write_bytes(policy)
            run=subprocess.run([sys.executable,'-B',str(PACKAGE/'tools/auth_evaluation.py'),'run','--corpus',str(root/'link.json'),'--corpus-digest',pin,'--policy',str(root/'policy.json'),'--policy-digest',policy_pin,'--output',str(root/'report.json')],capture_output=True,text=True)
            self.assertEqual(run.returncode,2); self.assertFalse((root/'report.json').exists())


if __name__ == '__main__':
    unittest.main()
