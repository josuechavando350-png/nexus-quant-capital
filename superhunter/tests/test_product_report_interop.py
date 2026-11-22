"""Regression checks for disclosure, counters and producer semantics in report ingestion."""
import unittest

from superhunter import product_report_interop as interop


class ReportInteropTests(unittest.TestCase):
    def test_kubescape_uses_outcomes_and_verifies_two_levels_of_totals(self):
        raw = (b'<testsuites name="Kubescape Scanning" tests="2" errors="0" failures="1" skipped="0">'
               b'<testsuite name="NSA" tests="2" errors="0" failures="1" skipped="0">'
               b'<testcase classname="NSA/C-0001" name="sensitive"><failure>private</failure></testcase>'
               b'<testcase classname="NSA/C-0002"/></testsuite></testsuites>')
        result = interop.summary_with_controls('kubescape-junit', raw)
        self.assertEqual(result, {'itemized': 2, 'outcomes': {'fail': 1, 'pass': 1},
                                  'checks': {'C-0001': {'fail': 1}, 'C-0002': {'pass': 1}}})
        wrong_suite = raw.replace(b'NSA" tests="2"', b'NSA" tests="1"')
        with self.assertRaisesRegex(interop.EvidenceError, 'summary'):
            interop.junit_results(interop.parse_junit(wrong_suite))
        wrong_class = raw.replace(b'NSA/C-0002', b'ALT/C-0002')
        with self.assertRaisesRegex(interop.EvidenceError, 'suite'):
            interop.junit_results(interop.parse_junit(wrong_class))

    def test_xml_rejects_dtds_conflicting_outcomes_and_oversized_input(self):
        with self.assertRaisesRegex(interop.EvidenceError, 'markup'):
            interop.decode('kubescape-junit', b'<!DOCTYPE testsuites><testsuites/>')
        with self.assertRaisesRegex(interop.EvidenceError, 'byte limit'):
            interop.decode('kubescape-junit', b' ' * (interop.MAX_BYTES + 1))
        raw = (b'<testsuites name="Kubescape Scanning"><testsuite name="NSA">'
               b'<testcase classname="NSA/C-0001"><failure/><skipped/></testcase></testsuite></testsuites>')
        with self.assertRaisesRegex(interop.EvidenceError, 'conflicting'):
            interop.junit_results(interop.parse_junit(raw))

    def test_kube_bench_partial_report_only_counts_itemized_checks(self):
        totals = dict(total_pass=3, total_fail=1, total_info=0, total_warn=1)
        group = {**totals, 'tests': [{'results': [{'test_number': '1.1', 'status': 'FAIL', 'audit': 'private'}]}]}
        report = {'Controls': [group], 'Totals': totals}
        result = interop.summary_with_controls('kube-bench-json', interop.canonical(report))
        self.assertEqual(result, {'declared': 5, 'itemized': 1, 'unitemized': {'pass': 3, 'warn': 1},
                                  'outcomes': {'fail': 1}, 'checks': {'1.1': {'fail': 1}}})
        group['total_fail'] = 0
        with self.assertRaisesRegex(interop.EvidenceError, 'exceeds'):
            interop.bench_results(report)

    def test_phpstan_ignores_historical_tabs_and_counts_repeated_current_checks(self):
        error = {'line': 3, 'message': 'private', 'identifier': 'missingType.return'}
        report = {'result': {'tabs': [{'errors': [error]}], 'upToDateTabs': [{'errors': [error, error]}]}}
        result = interop.summary_with_controls('phpstan-playground', interop.canonical(report))
        self.assertEqual(result, {'itemized': 2, 'outcomes': {'error': 2},
                                  'checks': {'missingType.return': {'error': 2}}})
        error['line'] = True
        with self.assertRaisesRegex(interop.EvidenceError, 'location'):
            interop.phpstan_results(report)

    def test_psalm_joins_rules_uses_default_level_and_drops_private_locations(self):
        rules = [{'id': 'UnusedVariable', 'defaultConfiguration': {'level': 'note'}}]
        row = {'ruleId': 'UnusedVariable', 'ruleIndex': 0, 'message': {'text': 'private'}}
        run = {'tool': {'driver': {'name': 'Psalm', 'rules': rules}}, 'results': [row]}
        report = {'version': '2.1.0', 'runs': [run]}
        result = interop.summary_with_controls('psalm-sarif', interop.canonical(report))
        self.assertEqual(result, {'itemized': 1, 'outcomes': {'note': 1}, 'checks': {'UnusedVariable': {'note': 1}}})
        row['ruleIndex'] = 1
        with self.assertRaisesRegex(interop.EvidenceError, 'index'):
            interop.psalm_results(report)

    def test_sarif_rejects_foreign_producer_and_duplicate_definitions(self):
        run = {'tool': {'driver': {'name': 'Other', 'rules': []}}, 'results': []}
        doc = {'version': '2.1.0', 'runs': [run]}
        with self.assertRaisesRegex(interop.EvidenceError, 'producer'):
            interop.psalm_results(doc)
        run['tool']['driver'] = {'name': 'Psalm', 'rules': [{'id': 'One'}, {'id': 'One'}]}
        with self.assertRaisesRegex(interop.EvidenceError, 'duplicate'):
            interop.psalm_results(doc)

    def test_json_rejects_duplicate_semantic_fields(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            interop.decode('phpstan-playground', b'{"result":{},"result":{}}')


class MeasurementCoverageTests(unittest.TestCase):
    def setUp(self):
        from superhunter import product_report_quality_sources as quality
        self.quality = quality
        self.model = {'Config': {'comment'}, 'Hardware': {'cpu_threads'}, 'Results': {'config', 'hardware', 'targets'},
                      'Run': {'execs_per_sec', 'execs_total', 'fuzzers_used'}}

    @staticmethod
    def archive(targets):
        return {'config': {'comment': 'private'}, 'hardware': {'cpu_threads': 2}, 'targets': targets}

    @staticmethod
    def measurement(workers):
        return {'execs_per_sec': 12.3, 'execs_total': 122, 'fuzzers_used': workers}

    def test_modes_only_match_within_a_single_record_and_target(self):
        one, many = self.measurement(1), self.measurement(2)
        rows = [self.archive({'case-a': {'singlecore': one}, 'case-b': {'multicore': many}}),
                self.archive({'case-a': {'multicore': many}}),
                self.archive({'case-c': {'singlecore': one, 'multicore': many}}),
                self.archive({'case-d': {'singlecore': one, 'multicore': one}})]
        result = self.quality.study_coverage(rows, self.model)
        self.assertEqual(result['paired_within_one_target_record'], 1)
        self.assertEqual(result['target_records_without_eligible_pair'], 4)
        self.assertEqual(result['single_worker_multicore_labels'], 1)
        self.assertNotIn('case-a', str(result))
        self.assertNotIn('12.3', str(result))
        self.assertNotIn('private', str(result))

    def test_rejects_duplicate_historical_input(self):
        row = self.archive({'case-a': {'singlecore': self.measurement(1)}})
        with self.assertRaisesRegex(interop.EvidenceError, 'duplicate'):
            self.quality.study_coverage([row, row], self.model)

    def test_explicit_typed_counts_and_missing_settings(self):
        for bad in (self.measurement(True), self.measurement(2), dict(self.measurement(1), execs_total=1.5),
                    dict(self.measurement(1), execs_per_sec=0)):
            with self.subTest(bad=bad), self.assertRaisesRegex(interop.EvidenceError, 'inconsistent'):
                self.quality.study_coverage([self.archive({'a': {'singlecore': bad}})], self.model)
        row = self.archive({'a': {'singlecore': self.measurement(1)}})
        row['config'] = None
        with self.assertRaisesRegex(interop.EvidenceError, 'model'):
            self.quality.study_coverage([row], self.model)
