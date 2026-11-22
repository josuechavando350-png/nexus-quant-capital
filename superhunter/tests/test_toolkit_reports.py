import json
from pathlib import Path
import tempfile
import unittest

from superhunter.toolkit_reports import FORMATS, read_reports, summarize


class ToolkitReports(unittest.TestCase):
    def test_native_result_shapes(self):
        slither = {'success': True, 'results': {'detectors': [{'check': 'pess-x'}, {'check': 'other'}]}}
        examples = {
            'slither': (slither, {'detectors': {'pess-x': 1, 'other': 1}}),
            'slitherin': (slither, {'detectors': {'pess-x': 1}}),
            'aderyn': ({'low_issues': {'issues': [{'detector_name': 'd'}]}, 'high_issues': {'issues': []}},
                       {'low': {'d': 1}, 'high': {}}),
            'semgrep': ({'results': [{'check_id': 'x'}], 'errors': []}, {'checks': {'x': 1}, 'errors': 0}),
            'halmos': ({'test_results': {'C': [{'exitcode': 2}]}}, {'test_outcomes': {'timeout': 1}}),
            'echidna': ({'success': True, 'tests': [{'status': 'fuzzing'}]},
                        {'success': True, 'test_statuses': {'fuzzing': 1}}),
            'mythril': ({'success': True, 'issues': [{'severity': 'Low'}]}, {'issues_by_severity': {'Low': 1}}),
            'ityfuzz': ({'coverage': {'C': {'instruction_coverage': 2, 'total_instructions': 5,
                                             'branch_coverage': 0, 'total_branches': 0}}},
                        {'contracts': 1, 'instructions': {'covered': 2, 'total': 5},
                         'branches': {'covered': 0, 'total': 0}}),
            'kontrol': (b'<testsuites><testsuite><testcase name="t"><skipped/></testcase></testsuite></testsuites>',
                        {'test_outcomes': {'skipped': 1}}),
            'manticore': (b'Global runtime coverage:\na: 42.50%\n', {'contract_coverage_percent': [42.5]}),
            'nuclei': (b'{"template-id":"x","matcher-status":true,"info":{"severity":"info"}}\n',
                       {'events': 1, 'matched_by_severity': {'info': 1}}),
        }
        self.assertEqual(set(examples), set(FORMATS))
        for tool, (data, expected) in examples.items():
            with self.subTest(tool=tool):
                raw = data if isinstance(data, bytes) else json.dumps(data).encode()
                self.assertEqual(summarize(tool, raw), expected)

    def test_invalid_coverage_and_external_xml_are_rejected(self):
        with self.assertRaises(ValueError):
            summarize('ityfuzz', b'{"coverage":{"c":{"instruction_coverage":9,"total_instructions":2}}}')
        with self.assertRaises(ValueError):
            summarize('kontrol', b'<!DOCTYPE svg><testsuite/>')

    def test_import_failure_does_not_overwrite_an_earlier_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.json'
            path.write_text('{"errors":[],"results":[]}')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                read_reports([('semgrep', path), ('semgrep', path)])
            path.write_text('{"success":false}')
            with self.assertRaisesRegex(ValueError, 'failed analysis'):
                read_reports([('slither', path)])
