"""Privacy regressions with synthetic private values and real optional SDK.

Stub QA outcomes test the adapter boundary, not a full QA execution. Complete
QA acceptance is separate. No network exporter is created by these tests.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import otel_qa as ot, otel_qa_schema as schema, quality
from superhunter.safe_io import canonical, write_new_bundle

PRIVATE = 'SYNTHETIC_PRIVATE_canary_8b6f'


def failure():
    return {'schema_version': 1, 'profile': ot.PROFILE, 'status': 'QA_FAILED',
            'qa_passed': False, 'qa_reverified_here': False, 'tests_run': 0,
            'source_digest': None, 'elapsed_ns': 5,
            'spans': [{'name': 'superhunter.qa.run', 'duration_ns': 4}],
            'sdk_version': ot.SDK_VERSION, 'exporter': 'in-memory-only',
            'network_export': False, 'target_scanned': False,
            'vulnerability_confirmed': False, 'error_type': 'ValueError',
            'dependency_identity': ot.dependencies.expected_identity(),
            'dependency_files_checked': True, 'process_memory_integrity_proved': False}


def success():
    p = failure()
    p.update(status='QA_VERIFIED', qa_passed=True, qa_reverified_here=True,
             tests_run=3, source_digest='a'*64, error_type=None)
    p['spans'].append({'name': 'superhunter.qa.verify', 'duration_ns': 1})
    return p


class TelemetrySchemaTests(unittest.TestCase):
    def test_valid_profiles_do_not_require_sdk(self):
        for p in (failure(), success()):
            schema.validate(p)
            p['profile'] = ot.LEGACY_PROFILE
            for key in ('dependency_identity', 'dependency_files_checked', 'process_memory_integrity_proved'):
                del p[key]
            schema.validate(p)

    def test_unknown_fields_rejected_at_each_level(self):
        for level in ('root', 'span', 'dependency'):
            with self.subTest(level=level):
                p = failure()
                node = {'root': p, 'span': p['spans'][0],
                        'dependency': p['dependency_identity']['opentelemetry-sdk']}[level]
                node['private_path'] = PRIVATE
                with self.assertRaises(ValueError):
                    schema.validate(p)

    def test_unbounded_error_values_rejected(self):
        for bad in (PRIVATE, '', {}, [], 0, False, 'ValueError\n'+PRIVATE):
            with self.subTest(kind=type(bad).__name__):
                p = failure(); p['error_type'] = bad
                with self.assertRaisesRegex(ValueError, 'TELEMETRY_ERROR_LABEL'):
                    schema.validate(p)

    def test_invalid_counters_rejected(self):
        for field in ('tests_run', 'elapsed_ns', 'duration_ns'):
            for value in (True, False, -1, 1.0, '1', None, 2**63):
                with self.subTest(field=field, value=value):
                    p = failure()
                    (p['spans'][0] if field == 'duration_ns' else p)[field] = value
                    with self.assertRaises(ValueError):
                        schema.validate(p)

    def test_digest_must_be_lowercase_hex(self):
        for digest in ('z'*64, 'A'*64, 'a'*63, 'a'*65, None, 0, PRIVATE.ljust(64, 'x')):
            with self.subTest(digest=digest):
                p = success(); p['source_digest'] = digest
                with self.assertRaisesRegex(ValueError, 'TELEMETRY_REQUIRES_QA'):
                    schema.validate(p)

    def test_span_cardinality_and_names(self):
        for spans in ([], [failure()['spans'][0]]*2, [failure()['spans'][0]]*3,
                      [{'name': PRIVATE, 'duration_ns': 0}], None):
            with self.subTest(spans=spans):
                p = failure(); p['spans'] = spans
                with self.assertRaises(ValueError):
                    schema.validate(p)

    def test_state_matrix_cannot_promote_failure(self):
        for patch_values in ({'qa_passed': True}, {'status': 'QA_VERIFIED'},
                             {'tests_run': 1}, {'source_digest': 'a'*64},
                             {'status': PRIVATE}, {'network_export': True}):
            with self.subTest(values=patch_values):
                p = failure(); p.update(patch_values)
                with self.assertRaises(ValueError):
                    schema.validate(p)

    def test_dependency_numeric_type_is_exact(self):
        p = failure()
        row = p['dependency_identity']['opentelemetry-sdk']
        row['runtime_files'] = float(row['runtime_files'])
        with self.assertRaisesRegex(ValueError, 'TELEMETRY_DEPENDENCY_IDENTITY'):
            schema.validate(p)

    def test_resealed_private_error_rejected(self):
        p = failure(); p['error_type'] = PRIVATE
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'resealed'
            write_new_bundle(root, {'telemetry.json': canonical(p),
                                    'PROFILE.md': ot._review(p).encode()})
            with self.assertRaisesRegex(ValueError, 'TELEMETRY_ERROR_LABEL'):
                ot.verify_profile(root)

    def test_exception_label_never_calls_string_conversion(self):
        class PrivateError(ValueError):
            def __str__(self):
                raise AssertionError('must not stringify')
        PrivateError.__name__ = PRIVATE
        self.assertEqual(schema.error_label(PrivateError()), 'ValueError')
        self.assertEqual(schema.error_label(Exception(PRIVATE)), 'Exception')
        self.assertEqual(schema.error_label(TimeoutError(PRIVATE)), 'TimeoutError')

    def test_cli_exception_class_name_is_redacted(self):
        private_error = type(PRIVATE, (ValueError,), {})
        with patch.object(ot, 'verify_profile', side_effect=private_error(PRIVATE)):
            with redirect_stdout(io.StringIO()) as output:
                code = ot.main(['verify-owned-qa-profile', '--bundle', PRIVATE])
        self.assertEqual(code, 2)
        self.assertNotIn(PRIVATE, output.getvalue())
        self.assertIn('ValueError', output.getvalue())

    def test_validation_does_not_mutate_payload(self):
        p = success(); before = deepcopy(p)
        schema.validate(p)
        self.assertEqual(p, before)


class TelemetrySDKPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def ready(self):
        if ot.readiness()['status'] != 'READY':
            with self.assertRaisesRegex(ValueError, 'DEPENDENCY'):
                ot.profile_owned_qa(self.root/'qa', self.root/'telemetry')
            return False
        return True

    def assert_private_absent(self, root):
        for path in root.iterdir():
            self.assertNotIn(PRIVATE.encode(), path.read_bytes())

    def test_private_exception_name_and_message_not_serialized(self):
        if not self.ready():
            return
        custom = type(PRIVATE, (ValueError,), {})
        with (patch.object(quality, 'run_check', side_effect=custom('/private/'+PRIVATE)),
              patch('socket.socket', side_effect=AssertionError('NETWORK_CALLED'))):
            p = ot.profile_owned_qa(self.root/PRIVATE, self.root/'telemetry')
        self.assertEqual(p['error_type'], 'ValueError')
        self.assertEqual(p['status'], 'QA_FAILED')
        self.assert_private_absent(self.root/'telemetry')

    def test_resource_environment_not_recorded(self):
        if not self.ready():
            return
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        exporter = InMemorySpanExporter()
        with (patch('opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter', return_value=exporter),
              patch.dict('os.environ', {'OTEL_RESOURCE_ATTRIBUTES': 'secret='+PRIVATE,
                                        'OTEL_SERVICE_NAME': PRIVATE}),
              patch.object(quality, 'run_check', side_effect=ValueError(PRIVATE)),
              patch('socket.socket', side_effect=AssertionError('NETWORK_CALLED'))):
            ot.profile_owned_qa(self.root/'qa', self.root/'telemetry')
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        for span in spans:
            self.assertEqual(dict(span.resource.attributes), {})
            self.assertEqual(dict(span.attributes), {})
            self.assertEqual(list(span.events), [])
            self.assertIsNone(span.status.description)
        self.assert_private_absent(self.root/'telemetry')

    def test_unhandled_exception_is_not_recorded_by_sdk(self):
        if not self.ready():
            return
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        exporter = InMemorySpanExporter()
        custom = type(PRIVATE, (Exception,), {})
        with (patch('opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter', return_value=exporter),
              patch.object(quality, 'run_check', side_effect=custom(PRIVATE))):
            with self.assertRaises(custom):
                ot.profile_owned_qa(self.root/'qa', self.root/'telemetry')
        self.assertFalse((self.root/'telemetry').exists())
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(list(spans[0].events), [])
        self.assertIsNone(spans[0].status.description)

    def test_invalid_success_payload_not_committed(self):
        if not self.ready():
            return
        forged = {'status': 'LOCAL_QA_PASS', 'tests_run': 3, 'source_digest': PRIVATE.ljust(64, 'x')}
        with (patch.object(quality, 'run_check', return_value=forged),
              patch.object(quality, 'verify_bundle', return_value=forged)):
            with self.assertRaisesRegex(ValueError, 'TELEMETRY_REQUIRES_QA'):
                ot.profile_owned_qa(self.root/'qa', self.root/'telemetry')
        self.assertFalse((self.root/'telemetry').exists())

    def test_valid_success_still_reverifies_qa(self):
        if not self.ready():
            return
        passed = {'status': 'LOCAL_QA_PASS', 'tests_run': 3, 'source_digest': 'a'*64}
        with (patch.object(quality, 'run_check', return_value=passed),
              patch.object(quality, 'verify_bundle', return_value=passed) as verify):
            p = ot.profile_owned_qa(self.root/'qa', self.root/'telemetry')
        self.assertTrue(p['qa_passed'])
        self.assertEqual(verify.call_count, 2)
        schema.validate(p)


if __name__ == '__main__':
    unittest.main()
