"""Synthetic FORMAT fixtures, not fabricated Slither executions or vulnerability PoCs."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import static_review as sr
from superhunter.safe_io import canonical, strict_json

SOURCE = ('// SPDX-License-Identifier: MIT\npragma solidity 0.8.24;\n'
          '// Texto español: ñ\ncontract example_contract {\n'
          '    function ping() external pure returns (uint256) { return 1; }\n}\n').encode()


def fixture():
    name = 'contracts/Example.sol'
    start = SOURCE.index(b'contract example_contract')
    length = len(b'contract example_contract')
    line = SOURCE.count(b'\n', 0, start) + 1
    row = {'check': 'naming-convention', 'impact': 'Informational', 'confidence': 'High',
           'description': 'Synthetic FORMAT fixture: contract naming observation; no scanner executed.',
           'elements': [{'type': 'contract', 'name': 'example_contract', 'source_mapping': {
               'filename_relative': name, 'filename_absolute': '/unused/absolute/Example.sol',
               'filename_short': 'Example.sol', 'start': start, 'length': length,
               'lines': [line], 'starting_column': 1, 'ending_column': length + 1}}]}
    report = {'success': True, 'error': None, 'results': {'detectors': [row]}}
    context = {'schema_version': 1, 'scope_id': 'bounty-local-fixture',
               'repository': {'repo': 'own/local-fixtures', 'commit': 'a' * 40},
               'tool': {'name': 'slither', 'version': 'synthetic-format-fixture'},
               'detectors': ['naming-convention'], 'report_sha256': hashlib.sha256(canonical(report)).hexdigest(),
               'sources': {name: hashlib.sha256(SOURCE).hexdigest()}, 'input_kind': 'synthetic-format-fixture'}
    return report, context, {name: SOURCE}


class StaticReviewTests(unittest.TestCase):
    def setUp(self):
        self.report, self.context, self.sources = fixture()
        self.work = tempfile.TemporaryDirectory(); self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)

    def normalize(self):
        raw = canonical(self.report)
        self.context['report_sha256'] = hashlib.sha256(raw).hexdigest()
        return sr.normalize(raw, self.context, self.sources)

    def build(self):
        raw = canonical(self.report)
        self.context['report_sha256'] = hashlib.sha256(raw).hexdigest()
        (self.root/'input.json').write_bytes(raw)
        (self.root/'context.json').write_bytes(canonical(self.context))
        for name, value in self.sources.items():
            dest = self.root/'sources'/name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(value)
        out = self.root/'bundle'
        result = sr.import_report(self.root/'input.json', self.root/'context.json', self.root/'sources', out)
        return out, result

    def alter(self, root, name, fn):
        value = strict_json((root/name).read_bytes()); fn(value)
        raw = canonical(value); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_bundle_roundtrip(self):
        out, result = self.build()
        self.assertEqual(sr.verify_report(out), result)
        self.assertEqual(result['status'], 'STATIC_REVIEW_REQUIRED')
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertEqual(result['source_bound_alerts'], 1)

    def test_utf8_offsets_are_bytes_not_characters(self):
        result = self.normalize()
        loc = result['alerts'][0]['locations'][0]
        self.assertEqual(loc['start_byte'], SOURCE.index(b'contract'))
        self.assertEqual(loc['fragment_sha256'], hashlib.sha256(b'contract example_contract').hexdigest())
        self.assertNotEqual(loc['start_byte'], SOURCE.decode().index('contract'))

    def test_byte_range_mismatch_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['length'] = len(SOURCE) + 1
        with self.assertRaisesRegex(ValueError, 'BYTE_RANGE'): self.normalize()

    def test_unicode_split_rejected(self):
        mapping = self.report['results']['detectors'][0]['elements'][0]['source_mapping']
        mapping['start'] = SOURCE.index('ñ'.encode()) + 1; mapping['length'] = 1
        with self.assertRaises(ValueError): self.normalize()

    def test_wrong_source_hash_rejected(self):
        self.context['sources']['contracts/Example.sol'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_CONTENT'): self.normalize()

    def test_report_hash_mismatch_rejected(self):
        self.context['report_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'REPORT_CONTENT'):
            sr.normalize(canonical(self.report), self.context, self.sources)

    def test_duplicate_alert_count(self):
        self.report['results']['detectors'] *= 3
        result = self.normalize()
        self.assertEqual((result['raw_alert_count'], result['unique_alert_count'], result['duplicate_count']), (3, 1, 2))
        self.assertEqual(result['alerts'][0]['occurrences'], 3)
        self.assertEqual(result['alerts'][0]['detector_indices'], [0, 1, 2])

    def test_conflicting_duplicate_impact_not_silently_resolved(self):
        duplicate = deepcopy(self.report['results']['detectors'][0]); duplicate['impact'] = 'High'
        self.report['results']['detectors'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'CONTRADICTORY_DUPLICATE'): self.normalize()

    def test_all_duplicate_descriptions_retained(self):
        duplicate = deepcopy(self.report['results']['detectors'][0]); duplicate['description'] = 'Second description'
        self.report['results']['detectors'].append(duplicate)
        self.assertEqual(len(self.normalize()['alerts'][0]['description_sha256']), 2)

    def test_different_source_location_not_deduplicated(self):
        duplicate = deepcopy(self.report['results']['detectors'][0])
        duplicate['elements'][0]['source_mapping']['length'] += 1
        self.report['results']['detectors'].append(duplicate)
        self.assertEqual(self.normalize()['unique_alert_count'], 2)

    def test_zero_alerts_not_safety_certificate(self):
        self.report['results']['detectors'] = []
        result = self.normalize()
        self.assertEqual(result['status'], 'NO_ALERTS_IN_SUPPLIED_REPORT')
        self.assertFalse(result['code_certified_safe'])
        self.assertFalse(result['scanner_execution_verified'])

    def test_tool_failure_is_not_clean_scan(self):
        self.report['success'] = False; self.report['error'] = 'synthetic compiler failure'
        result = self.normalize()
        self.assertEqual(result['status'], 'TOOL_ERROR')
        self.assertFalse(result['normalization_complete'])

    def test_failed_tool_preserves_partial_record_count_without_promoting(self):
        self.report['success'] = False
        self.report['error'] = 'synthetic incomplete analysis'
        result = self.normalize()
        self.assertEqual(result['raw_alert_count'], 1)
        self.assertEqual(result['alerts'], [])
        self.assertFalse(result['normalization_complete'])

    def test_failed_tool_unknown_count_not_reported_as_zero(self):
        self.report = {'success': False, 'error': 'synthetic error', 'results': {}}
        result = self.normalize()
        self.assertIsNone(result['raw_alert_count'])
        self.assertFalse(result['normalization_complete'])

    def test_missing_detector_section_rejected(self):
        self.report['results'] = {'printers': []}
        with self.assertRaisesRegex(ValueError, 'DETECTOR_RESULTS_REQUIRED'): self.normalize()

    def test_missing_locations_explicitly_incomplete(self):
        self.report['results']['detectors'][0]['elements'] = []
        result = self.normalize()
        self.assertEqual(result['status'], 'INCOMPLETE_SOURCE_BINDING')
        self.assertEqual(result['unbound_alerts'], 1)
        self.assertFalse(result['normalization_complete'])

    def test_partial_locations_explicitly_incomplete(self):
        self.report['results']['detectors'][0]['elements'].append({'type': 'node', 'name': ''})
        result = self.normalize()
        self.assertEqual(result['status'], 'INCOMPLETE_SOURCE_BINDING')
        self.assertEqual(len(result['alerts'][0]['locations']), 1)

    def test_unknown_detector_rejected(self):
        self.report['results']['detectors'][0]['check'] = 'not-requested'
        with self.assertRaisesRegex(ValueError, 'UNDECLARED_DETECTOR'): self.normalize()

    def test_extra_sections_are_declared_ignored(self):
        self.report['results']['printers'] = []
        self.assertEqual(self.normalize()['ignored_result_sections'], ['printers'])

    def test_path_traversal_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['filename_relative'] = '../private.sol'
        with self.assertRaisesRegex(ValueError, 'UNSAFE_SOURCE_PATH'): self.normalize()

    def test_absolute_source_path_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['filename_relative'] = '/tmp/private.sol'
        with self.assertRaisesRegex(ValueError, 'UNSAFE_SOURCE_PATH'): self.normalize()

    def test_absolute_metadata_never_opened(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['filename_absolute'] = '/etc/shadow'
        result = self.normalize()
        self.assertNotIn('/etc/shadow', json.dumps(result))

    def test_out_of_inventory_source_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['filename_relative'] = 'Outside.sol'
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_SOURCE_INVENTORY'): self.normalize()

    def test_wrong_line_mapping_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['lines'] = [99]
        with self.assertRaisesRegex(ValueError, 'LINES_MISMATCH'): self.normalize()

    def test_boolean_offsets_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['start'] = True
        with self.assertRaisesRegex(ValueError, 'BYTE_RANGE'): self.normalize()

    def test_boolean_line_numbers_rejected(self):
        self.report['results']['detectors'][0]['elements'][0]['source_mapping']['lines'] = [True]
        with self.assertRaisesRegex(ValueError, 'LINES_MISMATCH'): self.normalize()

    def test_boolean_schema_rejected(self):
        self.context['schema_version'] = True
        with self.assertRaisesRegex(ValueError, 'CONTEXT_VERSION'): self.normalize()

    def test_numeric_success_rejected(self):
        self.report['success'] = 1
        with self.assertRaisesRegex(ValueError, 'ENVELOPE'): self.normalize()

    def test_success_with_error_rejected(self):
        self.report['error'] = 'contradiction'
        with self.assertRaisesRegex(ValueError, 'CONTRADICTORY_TOOL_ERROR'): self.normalize()

    def test_unsupported_severity_not_promoted(self):
        self.report['results']['detectors'][0]['impact'] = 'Critical'
        with self.assertRaisesRegex(ValueError, 'CLASSIFICATION'): self.normalize()

    def test_duplicate_json_keys_rejected(self):
        raw = b'{"success":true,"success":false,"error":null,"results":{}}'
        self.context['report_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            sr.normalize(raw, self.context, self.sources)

    def test_alert_limit_rejects_without_truncation(self):
        self.report['results']['detectors'] *= sr.MAX_ALERTS + 1
        with self.assertRaisesRegex(ValueError, 'DETECTOR_RESULTS_REQUIRED'): self.normalize()

    def test_mapping_byte_budget_rejects_without_truncation(self):
        with patch.object(sr, 'MAX_MAPPED_BYTES', 1), self.assertRaisesRegex(ValueError, 'MAPPED_BYTE_BUDGET'):
            self.normalize()

    def test_total_mapping_limit(self):
        with patch.object(sr, 'MAX_TOTAL_ELEMENTS', 0), self.assertRaisesRegex(ValueError, 'TOTAL_ELEMENT_LIMIT'):
            self.normalize()

    def test_element_limit_rejects_without_truncation(self):
        self.report['results']['detectors'][0]['elements'] *= sr.MAX_ELEMENTS + 1
        with self.assertRaisesRegex(ValueError, 'ELEMENT_LIMIT'): self.normalize()

    def test_fingerprint_changes_with_commit(self):
        original = self.normalize()['alerts'][0]['fingerprint']
        self.context['repository']['commit'] = 'b' * 40
        self.assertNotEqual(original, self.normalize()['alerts'][0]['fingerprint'])

    def test_tool_high_does_not_confirm_severity(self):
        self.report['results']['detectors'][0]['impact'] = 'High'
        result = self.normalize()
        self.assertEqual(result['alerts'][0]['tool_impact'], 'High')
        self.assertNotIn('final_severity', result['alerts'][0])
        self.assertFalse(result['vulnerability_confirmed'])

    def test_scope_and_commit_are_explicitly_unverified(self):
        result = self.normalize()
        for key in ('scope_authorization_verified', 'repository_commit_verified', 'producer_authenticated'):
            self.assertIs(result[key], False)

    def test_description_is_redacted_original_kept_private(self):
        secret = 'SYNTHETIC_PRIVATE_MARKER_92851'
        self.report['results']['detectors'][0]['description'] = 'api_key=' + secret
        out, result = self.build()
        self.assertNotIn(secret.encode(), (out/'REVIEW.md').read_bytes())
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn(secret.encode(), (out/'slither.json').read_bytes())

    def test_self_contained_verification(self):
        out, result = self.build()
        shutil.rmtree(self.root/'sources'); (self.root/'input.json').unlink()
        self.assertEqual(sr.verify_report(out), result)

    def test_resealed_normalized_claim_rejected(self):
        out, _ = self.build()
        self.alter(out, 'normalized.json', lambda x: x.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError, 'NORMALIZED_RESULT'): sr.verify_report(out)

    def test_resealed_counts_rejected(self):
        out, _ = self.build()
        self.alter(out, 'normalized.json', lambda x: x.update(unique_alert_count=0))
        with self.assertRaisesRegex(ValueError, 'NORMALIZED_RESULT'): sr.verify_report(out)

    def test_extra_bundle_file_rejected(self):
        out, _ = self.build(); (out/'secret.txt').write_text('synthetic')
        with self.assertRaisesRegex(ValueError, 'UNDECLARED_BUNDLE'): sr.verify_report(out)

    def test_manifest_true_is_not_version_one(self):
        out, _ = self.build()
        marker = strict_json((out/'COMPLETE.json').read_bytes()); marker['schema_version'] = True
        (out/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError, 'MANIFEST'): sr.verify_report(out)

    def test_audit_event_mismatch_rejected_even_when_rehashed(self):
        out, _ = self.build()
        self.alter(out, 'audit.json', lambda x: x['entries'][0]['data'].update(context_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'AUDIT_BINDING'): sr.verify_report(out)

    def test_existing_output_not_overwritten(self):
        out, _ = self.build()
        with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
            sr.import_report(self.root/'input.json', self.root/'context.json', self.root/'sources', out)

    def test_private_permissions(self):
        out, _ = self.build()
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        for item in out.iterdir(): self.assertEqual(item.stat().st_mode & 0o777, 0o600)

    def test_symlink_source_rejected(self):
        out, _ = self.build(); shutil.rmtree(out)
        path = self.root/'sources/contracts/Example.sol'; path.unlink(); path.symlink_to(self.root/'input.json')
        with self.assertRaises(OSError):
            sr.import_report(self.root/'input.json', self.root/'context.json', self.root/'sources', out)
        self.assertFalse(out.exists())

    def test_verification_has_no_network_or_target_execution(self):
        out, _ = self.build()
        with patch('socket.socket', side_effect=AssertionError('network')), patch('subprocess.run', side_effect=AssertionError('process')):
            self.assertFalse(sr.verify_report(out)['scanner_execution_verified'])

    def test_cli_actual_dispatch_and_verification(self):
        out, _ = self.build()
        cmd = [sys.executable, '-B', '-m', 'superhunter', 'verify-slither', '--bundle', str(out)]
        proc = subprocess.run(cmd, cwd=sr.ROOT.parent, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(json.loads(proc.stdout)['unique_alert_count'], 1)

    def test_cli_error_does_not_echo_path_or_secret(self):
        with redirect_stdout(io.StringIO()) as stream:
            code = sr.main(['verify-slither', '--bundle', str(self.root/'SYNTHETIC_SECRET_PATH')])
        self.assertEqual(code, 2)
        self.assertNotIn('SYNTHETIC_SECRET_PATH', stream.getvalue())

    def test_cli_incomplete_is_nonzero(self):
        self.report['results']['detectors'][0]['elements'] = []
        out, _ = self.build()
        with redirect_stdout(io.StringIO()) as stream:
            code = sr.main(['verify-slither', '--bundle', str(out)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'INCOMPLETE_SOURCE_BINDING')


if __name__ == '__main__':
    unittest.main()
