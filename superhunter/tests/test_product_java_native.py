"""Controls for native Java report attribution, completeness and concrete witnesses."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from superhunter import product_java_native as native
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json


class JavaNativeTests(unittest.TestCase):
    def setUp(self):
        self.pins, self.cases = native.inputs()
        raw = read_artifact(native.ROOT, native.PREFIX + 'samples.json')
        self.assertEqual(native.sha(raw), self.pins['samples_sha256'])
        self.samples = strict_json(raw)['reports']

    def xml(self, plugin=False):
        return E.fromstring(self.samples['with-plugin' if plugin else 'baseline'])

    def result(self, root=None, plugin=False):
        raw = E.tostring(self.xml(plugin) if root is None else root)
        return native.analysis_report(raw, plugin, self.cases, 'owned-source')

    def test_native_reports_preserve_baseline_and_attribute_plugin_result(self):
        baseline, enhanced = self.result(), self.result(plugin=True)
        self.assertEqual(len(baseline['diagnostics']), 3)
        self.assertEqual(len(enhanced['diagnostics']), 4)
        self.assertEqual(enhanced['clean_class_findings'], 0)
        self.assertEqual(native.plugin_difference(baseline, enhanced)['cwe'], 89)

    def test_missing_or_incomplete_analysis_cannot_report_success(self):
        for tag in ('Project', 'Errors', 'FindBugsSummary'):
            root = self.xml(); root.remove(root.find(tag))
            with self.subTest(section=tag), self.assertRaises(EvidenceError):
                self.result(root)
        for key, value in [('errors', '1'), ('missingClasses', '1')]:
            root = self.xml(); root.find('Errors').set(key, value)
            with self.subTest(field=key), self.assertRaises(EvidenceError):
                self.result(root)
        root = self.xml(); root.find('Errors').append(E.Element('MissingClass'))
        with self.assertRaises(EvidenceError):
            self.result(root)

    def test_wrong_project_or_plugin_attribution_is_rejected(self):
        for tag, value in [('Jar', 'classes/External.class'), ('SrcDir', '/outside'),
                           ('AuxClasspathEntry', '/outside')]:
            root = self.xml(); root.find('Project/' + tag).text = value
            with self.subTest(field=tag), self.assertRaises(EvidenceError):
                self.result(root)
        for plugin in (True, False):
            with self.subTest(plugin=plugin), self.assertRaises(EvidenceError):
                self.result(self.xml(not plugin), plugin)

    def test_unanalyzed_or_failing_clean_control_is_rejected(self):
        for replacement in ('OwnedOther', 'OwnedUnsafe'):
            root = self.xml(); root.find('.//ClassStats').set('class', replacement)
            with self.subTest(replacement=replacement), self.assertRaises(EvidenceError):
                self.result(root)
        root = self.xml(); root.find('.//ClassStats').set('bugs', '1')
        with self.assertRaises(EvidenceError):
            self.result(root)

    def test_diagnostic_severity_cwe_method_and_offsets_are_checked(self):
        for tag, field, value in [('', 'cweid', '89'), ('', 'priority', '3'), ('', 'rank', '20'),
                                  ('Method', 'name', 'unrelated'), ('Method', 'signature', '()V'),
                                  ('SourceLine', 'sourcefile', 'External.java'),
                                  ('SourceLine', 'start', '8'), ('SourceLine', 'startBytecode', '2')]:
            root = self.xml(); bug = root.find('BugInstance')
            target = bug if not tag else next(r for r in bug.findall(tag) if r.get('primary') == 'true')
            target.set(field, value)
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                self.result(root)

    def test_missing_duplicate_or_ambiguous_diagnostics_are_rejected(self):
        root = self.xml(); root.remove(root.find('BugInstance'))
        with self.assertRaises(EvidenceError):
            self.result(root)
        root = self.xml(); root.append(deepcopy(root.find('BugInstance')))
        with self.assertRaises(EvidenceError):
            self.result(root)
        root = self.xml(); bug = root.find('BugInstance')
        bug.append(deepcopy(next(r for r in bug.findall('SourceLine') if r.get('primary') == 'true')))
        with self.assertRaises(EvidenceError):
            self.result(root)

    def test_xml_declarations_size_and_wrong_runtime_are_rejected(self):
        for raw in (b'<!DOCTYPE x><BugCollection/>', b'<!ENTITY x "a">', b' ' * (native.MAX_BYTES + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(EvidenceError):
                native.analysis_report(raw, False, self.cases, 'owned-source')
        root = self.xml(); root.set('version', '4.0.0')
        with self.assertRaises(EvidenceError):
            self.result(root)
        root = self.xml(); root.find('FindBugsSummary').set('java_version', '17')
        with self.assertRaises(EvidenceError):
            self.result(root)

    def test_concrete_witness_checks_every_positive_and_corrected_condition(self):
        valid = {'unsafe_null_throws': True, 'safe_length': 4, 'unsafe_sql_inlines_input': True,
                 'safe_sql_uses_placeholder': True, 'safe_bound_parameter_matches': True,
                 'database_connections_opened': 0}
        self.assertEqual(native.witness_result(canonical(valid)), valid)
        for field in valid:
            changed = dict(valid); changed[field] = 1 if isinstance(valid[field], bool) else 99
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                native.witness_result(canonical(changed))

    def test_plugin_result_cannot_replace_or_relabel_baseline_diagnostics(self):
        baseline, enhanced = self.result(), self.result(plugin=True)
        enhanced['diagnostics'][0]['cwe'] = 0
        with self.assertRaises(EvidenceError):
            native.plugin_difference(baseline, enhanced)
        with self.assertRaises(EvidenceError):
            native.plugin_difference(baseline, baseline)

    def test_pin_substitution_is_rejected_before_tool_execution(self):
        with patch.object(native, 'read_artifact', return_value=b'{}'), \
                patch.object(native.subprocess, 'run') as execute:
            with self.assertRaisesRegex(EvidenceError, 'producer pins'):
                native.run(Path('/unused'))
        execute.assert_not_called()

    def test_modified_runtime_is_rejected_before_compilation_or_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp); (kit/'runtime/bin').mkdir(parents=True)
            (kit/'runtime/bin/java').write_bytes(b'not the pinned Java runtime')
            with patch.object(native.subprocess, 'run') as execute:
                with self.assertRaisesRegex(EvidenceError, 'release digest mismatch'):
                    native.run(kit)
            execute.assert_not_called()
