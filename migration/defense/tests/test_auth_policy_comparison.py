from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import nqc_defense.auth_policy_comparison as comparison
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256

PACKAGE=Path(__file__).resolve().parents[1]


class AuthPolicyComparisonTests(unittest.TestCase):
    def setUp(self):
        self.corpus=(PACKAGE/'docs/AUTH_EVALUATION_CORPUS.json').read_bytes()
        self.before=(PACKAGE/'docs/AUTH_EVALUATION_POLICY.json').read_bytes()
        value=json.loads(self.before); value['threshold']=4; self.after=canonical(value)

    def arguments(self):
        return self.corpus,sha256(self.corpus),self.before,sha256(self.before),self.after,sha256(self.after)

    def compare(self):
        return comparison.compare(*self.arguments())

    def test_reduced_false_positives_does_not_hide_new_false_negatives(self):
        report=self.compare()
        self.assertEqual(report['confusion_delta'],{'true_positive':-7,'false_positive':-2,'true_negative':2,'false_negative':7})
        self.assertEqual(report['prediction_changes']['alerts_removed'],9)
        self.assertEqual(report['classification_transitions']['true_positive->false_negative'],7)
        self.assertEqual(report['metric_delta']['recall'],{'numerator':-7,'denominator':9})
        self.assertEqual(report['metric_delta']['false_positive_rate'],{'numerator':-1,'denominator':3})
        self.assertIsNone(report['metric_delta']['precision'])
        self.assertIsNone(report['policy_recommendation'])
        self.assertFalse(report['production_policy_changed']); self.assertFalse(report['automatic_response'])

    def test_identical_policy_retains_every_exact_trigger_set(self):
        self.after=self.before; report=self.compare()
        self.assertEqual(report['baseline_report_digest'],report['candidate_report_digest'])
        self.assertTrue(all(value==0 for value in report['confusion_delta'].values()))
        self.assertTrue(all(value=={'numerator':0,'denominator':1} for value in report['metric_delta'].values()))
        for row in report['scenarios']:
            self.assertEqual(len(row['retained_trigger_sets']),row['baseline_case_count'])
            self.assertEqual(row['removed_trigger_sets'],[]); self.assertEqual(row['introduced_trigger_sets'],[])

    def test_swapping_roles_reverses_changes_without_inventing_undefined_ratios(self):
        forward=self.compare(); self.before,self.after=self.after,self.before; backward=self.compare()
        for key,value in forward['confusion_delta'].items(): self.assertEqual(backward['confusion_delta'][key],-value)
        self.assertEqual(backward['prediction_changes']['alerts_introduced'],9)
        for key,value in forward['metric_delta'].items():
            if value is None: self.assertIsNone(backward['metric_delta'][key])
            else: self.assertEqual(backward['metric_delta'][key],{'numerator':-value['numerator'],'denominator':value['denominator']})

    def test_trigger_set_digests_link_to_embedded_case_evidence(self):
        report=self.compare()
        a={s['id']:s for s in report['baseline_report']['scenarios']}
        b={s['id']:s for s in report['candidate_report']['scenarios']}
        for row in report['scenarios']:
            old={sha256(canonical(case)) for case in a[row['id']]['cases']}
            new={sha256(canonical(case)) for case in b[row['id']]['cases']}
            self.assertEqual(set(row['retained_trigger_sets']),old&new)
            self.assertEqual(set(row['removed_trigger_sets']),old-new)
            self.assertEqual(set(row['introduced_trigger_sets']),new-old)
        self.assertFalse(report['same_episode_matching_claimed'])

    def test_alert_retained_can_still_have_different_trigger_records(self):
        value=json.loads(self.after); value['threshold']=2; self.after=canonical(value)
        report=self.compare()
        changed=[r for r in report['scenarios'] if r['prediction_change']=='alerts_retained' and r['removed_trigger_sets'] and r['introduced_trigger_sets']]
        self.assertTrue(changed)

    def test_unlabeled_changes_never_enter_confusion_matrix(self):
        corpus=json.loads(self.corpus)
        for item in corpus['scenarios']: item['label']='unlabeled'
        self.corpus=canonical(corpus); report=self.compare()
        self.assertEqual(report['prediction_changes']['unlabeled_prediction_changes'],9)
        self.assertEqual(report['prediction_changes']['labeled_prediction_changes'],0)
        self.assertTrue(all(value==0 for value in report['confusion_delta'].values()))
        self.assertTrue(all(value is None for value in report['metric_delta'].values()))

    def test_invalid_candidate_pin_prevents_even_baseline_execution(self):
        args=list(self.arguments()); args[-1]='0'*64
        with patch.object(comparison,'evaluate') as evaluate:
            with self.assertRaisesRegex(Rejected,'evaluation_input_digest'): comparison.compare(*args)
            evaluate.assert_not_called()

    def test_invalid_candidate_policy_prevents_both_runs(self):
        value=json.loads(self.after); value['threshold']=True; self.after=canonical(value)
        with patch.object(comparison,'evaluate') as evaluate:
            with self.assertRaises(Rejected): self.compare()
            evaluate.assert_not_called()

    def test_different_implementation_fingerprint_is_rejected(self):
        original=comparison.evaluate; calls=0
        def evaluate(*args):
            nonlocal calls
            calls+=1; result=original(*args)
            if calls==2: result['implementation_sources']['auth_log.py']='0'*64
            return result
        with patch.object(comparison,'evaluate',side_effect=evaluate):
            with self.assertRaisesRegex(Rejected,'comparison_implementation_changed'): self.compare()

    def test_observation_difference_cannot_be_misrepresented_as_policy_effect(self):
        original=comparison.evaluate; calls=0
        def evaluate(*args):
            nonlocal calls
            calls+=1; result=original(*args)
            if calls==2: result['scenarios'][0]['rule_evaluated_records']-=1
            return result
        with patch.object(comparison,'evaluate',side_effect=evaluate):
            with self.assertRaisesRegex(Rejected,'comparison_observation_discrepancy'): self.compare()

    def test_report_recomputes_identically(self):
        self.assertEqual(self.compare(),self.compare())

    def test_changed_metrics_are_rejected_even_with_new_report_hash(self):
        report=self.compare(); modified=deepcopy(report); modified['confusion_delta']['false_negative']=0
        data=canonical(modified)
        with self.assertRaisesRegex(Rejected,'comparison_report_discrepancy'):
            comparison.verify_comparison(data,sha256(data),report)

    def test_oversized_and_wrong_hash_reports_are_rejected(self):
        report=self.compare()
        for data,digest in [(b'x'*(comparison.MAX_COMPARISON+1),'0'*64),(canonical(report),'0'*64)]:
            with self.assertRaises(Rejected): comparison.verify_comparison(data,digest,report)

    def test_publication_is_private_idempotent_and_never_replaces_different_result(self):
        report=self.compare()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'comparison.json'; first=comparison.publish_comparison(path,report)
            self.assertEqual(comparison.publish_comparison(path,report),first)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            altered=deepcopy(report); altered['policy_recommendation']='bad'
            with self.assertRaises(Rejected): comparison.publish_comparison(path,altered)
            self.assertEqual(path.read_bytes(),canonical(report))

    def test_cli_run_and_recompute_work_without_optional_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name,data in [('corpus',self.corpus),('baseline',self.before),('candidate',self.after)]:
                (root/(name+'.json')).write_bytes(data)
            common=['--corpus',str(root/'corpus.json'),'--corpus-digest',sha256(self.corpus),
                '--baseline-policy',str(root/'baseline.json'),'--baseline-digest',sha256(self.before),
                '--candidate-policy',str(root/'candidate.json'),'--candidate-digest',sha256(self.after)]
            cli=[sys.executable,'-B','-S',str(PACKAGE/'tools/auth_policy_comparison.py')]
            first=subprocess.run(cli+['run']+common+['--output',str(root/'report.json')],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr); digest=json.loads(first.stdout)['comparison_digest']
            verified=subprocess.run(cli+['verify']+common+['--report',str(root/'report.json'),'--report-digest',digest],capture_output=True,text=True)
            self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)

    def test_cli_recomputed_digest_cannot_accept_an_edited_transition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); report=self.compare(); report['classification_transitions']={}
            data=canonical(report); (root/'report.json').write_bytes(data)
            for name,value in [('corpus',self.corpus),('baseline',self.before),('candidate',self.after)]: (root/(name+'.json')).write_bytes(value)
            result=subprocess.run([sys.executable,'-B',str(PACKAGE/'tools/auth_policy_comparison.py'),'verify',
                '--corpus',str(root/'corpus.json'),'--corpus-digest',sha256(self.corpus),
                '--baseline-policy',str(root/'baseline.json'),'--baseline-digest',sha256(self.before),
                '--candidate-policy',str(root/'candidate.json'),'--candidate-digest',sha256(self.after),
                '--report',str(root/'report.json'),'--report-digest',sha256(data)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertEqual(json.loads(result.stdout)['reason'],'comparison_report_discrepancy')


if __name__=='__main__':
    unittest.main()
