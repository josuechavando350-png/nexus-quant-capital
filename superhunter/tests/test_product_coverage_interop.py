"""The consumer must preserve coverage semantics while discarding private details."""
from copy import deepcopy
import unittest
from xml.etree import ElementTree

from superhunter import product_coverage_interop as coverage
from superhunter.safe_io import canonical


def report(rows):
    return ('<OWASPZAPReport version="2.4.3"><site><alerts>' + ''.join(rows)
            + '</alerts></site></OWASPZAPReport>').encode()


def alert(risk, body):
    return f'<alertitem><pluginid>7</pluginid><riskcode>{risk}</riskcode><confidence>2</confidence>{body}</alertitem>'


def scenario(valid, status, *, sequence_failure=0):
    return {'valid': valid, 'status_code': status, 'invalid_due_to_sequence_failure': sequence_failure,
            'invalid_due_to_resource_failure': 0, 'invalid_due_to_parser_failure': 0, 'invalid_due_to_500': 0,
            'sample_request': {'private': 'UNPUBLISHED'}, 'endpoint': 'UNPUBLISHED'}


def llvm_doc():
    summary = {kind: {'count': 2, 'covered': 1, 'notcovered': 1, 'percent': 50}
               for kind in coverage.METRICS}
    return {'type': 'llvm.coverage.json.export', 'version': '2.0.1',
            'data': [{'files': [{'filename': 'UNPUBLISHED', 'summary': summary}], 'totals': deepcopy(summary)}]}


class CoverageReportTests(unittest.TestCase):
    def setUp(self):
        sample = '<uri>UNPUBLISHED</uri>'
        self.grouped = report([alert(2, '<count>2</count><instances><instance>' + sample
                                     + '</instance></instances>')])
        self.flat = report([alert(2, sample), alert(2, sample)])

    def test_examples_can_be_capped_without_losing_occurrences(self):
        totals = coverage.reconcile_alerts(self.grouped, self.flat)
        self.assertEqual(totals, {'rules': 1, 'occurrences': 2, 'displayed_examples': 1,
                                  'occurrences_by_risk': {'2': 2}})
        self.assertNotIn(b'UNPUBLISHED', canonical(totals))

    def test_disagreement_on_count_and_risk_fail_separately(self):
        for changed in (self.grouped.replace(b'<count>2', b'<count>3'),
                        self.grouped.replace(b'<riskcode>2', b'<riskcode>1')):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'disagree'):
                coverage.reconcile_alerts(changed, self.flat)

    def test_invalid_xml_and_inconsistent_record_shapes_are_rejected(self):
        cases = [b'<!DOCTYPE report []>' + self.flat, ('<!DOCTYPE r []>' + self.flat.decode()).encode('utf-16'),
                 b'<r>', self.flat.replace(b'<uri>', b'<count>2</count><uri>')]
        for raw in cases:
            with self.subTest(example=len(raw)), self.assertRaises(ValueError):
                coverage.zap_counts(raw, merged=False)
        xml = ElementTree.fromstring(self.grouped)
        group = xml.find('./site/alerts')
        group.append(deepcopy(group[0]))
        with self.assertRaisesRegex(ValueError, 'grouped'):
            coverage.zap_counts(ElementTree.tostring(xml), merged=True)

    def test_specification_cases_keep_no_response_apart_from_response_errors(self):
        rows = {'A': scenario(1, '204'), 'B': scenario(0, None, sequence_failure=1), 'C': scenario(0, '404')}
        result = coverage.specification_coverage(canonical(rows))
        self.assertEqual(result, {'cases': 3, 'outcomes': {'valid_response': 1, 'no_response': 1, 'invalid_response': 1}})
        self.assertNotIn(b'UNPUBLISHED', canonical(result))

    def test_specification_claim_cannot_be_both_valid_and_blocked(self):
        for row in (scenario(1, None), scenario(1, '200', sequence_failure=1), scenario(True, '200'), scenario(0, '')):
            with self.subTest(row=row), self.assertRaises(ValueError):
                coverage.specification_coverage(canonical({'case': row}))

    def test_llvm_totals_retain_denominators_and_drop_identifying_paths(self):
        doc = llvm_doc()
        result = coverage.llvm_coverage(canonical(doc))
        self.assertEqual(result['files'], 1)
        self.assertEqual(result['totals']['lines'], {'count': 2, 'covered': 1})
        self.assertNotIn(b'UNPUBLISHED', canonical(result))

    def test_llvm_rejects_resealed_inconsistent_global_and_duplicate_file(self):
        doc = llvm_doc()
        doc['data'][0]['totals']['lines'].update(count=4, covered=2, notcovered=2)
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            coverage.llvm_coverage(canonical(doc))
        doc = llvm_doc()
        files = doc['data'][0]['files']
        files.append(deepcopy(files[0]))
        with self.assertRaisesRegex(ValueError, 'repeated'):
            coverage.llvm_coverage(canonical(doc))

    def test_llvm_rejects_impossible_coverage_and_spoofed_percent(self):
        for mutation in ({'covered': 3}, {'count': True}, {'percent': 49}, {'notcovered': 0}):
            doc = llvm_doc()
            doc['data'][0]['files'][0]['summary']['lines'].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                coverage.llvm_coverage(canonical(doc))

    def test_trace_counts_ignore_continuations_and_marker_records(self):
        raw = (b'10 4: W0.T1 ifetch 3 bytes private operand\n'
               b'10 4: W0.T1     continuation\n11 4: W0.T1 <marker: private>\n'
               b'12 5: W0.T1 ifetch 4 bytes private operand\nView tool results:\n  2 : total instructions\n')
        first, records = coverage.trace_window(raw)
        self.assertEqual((first, len(records)), (4, 2))
        with self.assertRaisesRegex(ValueError, 'counts disagree'):
            coverage.trace_window(raw.replace(b'2 : total', b'3 : total'))
        with self.assertRaisesRegex(ValueError, 'discontinuous'):
            coverage.trace_window(raw.replace(b'12 5:', b'12 6:'))

    def test_trace_windows_require_consistent_contents_and_declared_input(self):
        src = 'set(zip_path\n        "${PROJECT_SOURCE_DIR}/clients/drcachesim/tests/drmemtrace.allasm_x86_64.trace.zip")\n'
        files = {}
        for label, skip, path in zip(('skip', 'skip2'), (0, 1), coverage.WINDOWS):
            src += (f'torunonly_api(tool.drcacheoff.{label} "${{drcachesim_path}}" "offline-{label}" "" '
                    f'"-infile;${{zip_path}};${{test_mode_flag}};-skip_instrs;{skip};" OFF OFF)\n')
            files[path] = (''.join(f'{n} {n}: W0.T2 ifetch 2 B\n' for n in (skip + 1, skip + 2)) +
                           'View tool results:\n 2 : total instructions\n').encode()
        files[coverage.WINDOW_SOURCE] = src.encode()
        self.assertEqual(coverage.reconcile_trace_windows(files), {
            'window_instructions': [2, 2], 'shared_instructions': 1, 'distinct_instructions': 3})
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            coverage.reconcile_trace_windows({**files, coverage.WINDOWS[1]: files[coverage.WINDOWS[1]].replace(b'2 B', b'3 B')})
        with self.assertRaisesRegex(ValueError, 'declared input'):
            coverage.reconcile_trace_windows({**files, coverage.WINDOW_SOURCE: src.replace('-skip_instrs;1;', '-skip_instrs;2;').encode()})

    def test_resource_columns_require_maxima_and_unambiguous_names(self):
        header = ','.join(coverage.RESOURCE_COLUMNS) + ','
        csv = f'"{header}",\n"1,2,3,4,",\n"2,3,4,5,",\n"",'
        snapshots = coverage._csv_snapshots(csv)
        self.assertEqual(snapshots[0]['EngineRusageRssMb_Max'], 3)
        for broken in [csv.replace('RssMb_Max', 'RssMb_Sum'),
                       csv.replace('RssMb_Max', 'VSizeMb_Max'), csv.replace('2,3,4,5,', '2,3,4,')]:
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                coverage._csv_snapshots(broken)

    def test_resource_cohorts_compare_export_to_original_shards(self):
        fields = coverage.RESOURCE_COLUMNS
        header = ','.join(fields) + ','
        groups = ' '.join(f'/*experiment_name=*/"Experiment{name}"' for name in 'ABAB')
        inits = ' '.join(f'/*{name}=*/ {n} * j,' for n, name in enumerate(fields.values(), 1))
        updates = ' '.join(f'new_stats.{name} += 1;' for name in fields.values())
        blocks = []
        for number, peak_shard in enumerate((3, 4), 1):
            rows = [','.join(str(unit * peak_shard + delta) for unit in range(1, 5)) + ',' for delta in (0, 1)]
            blocks.append(f'// CSV #{number}.\n{{\n"{header}",\n"{rows[0]}",\n"{rows[1]}",\n"",\n}},')
        fixture = ('TEST(Stats, DumpStatsToCsvFile) {\nconst uint64_t j = i + 1;\n'
                   'for (int i = 2; i < stats_vec.size(); ++i)\n' + groups + inits + updates +
                   '\nkExpectedCsvLines = {\n' + '\n'.join(blocks) + '\n  };\n'
                   'TEST(Stats, DumpStatsToExistingCsvFile)')
        peaks = coverage.resource_peaks(fixture.encode())
        self.assertEqual(peaks['fixture_peak_by_counter']['engine_rusage_rss_mb'], 13)
        for changed in (fixture.replace('4,8,12,16,', '4,8,18,16,'),
                        fixture.replace('engine_rusage_rss_mb += 1', 'engine_rusage_rss_mb += 2')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                coverage.resource_peaks(changed.encode())
