"""Readiness diagnostics stay separate from execution and do not echo paths."""
from contextlib import ExitStack, redirect_stdout
import hashlib
from importlib.metadata import PackageNotFoundError
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import native_doctor as doctor


class NativeDoctorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def diagnose(self, failed=()):
        with ExitStack() as stack:
            for name in doctor.CHECKS:
                if name in ('solc','geth'): continue
                stack.enter_context(patch.object(doctor,'_'+name,
                    return_value=doctor.result(name not in failed,'CONTROL')))
            stack.enter_context(patch.object(doctor,'_tool',side_effect=lambda name,path:
                doctor.result(name not in failed,'CONTROL')))
            return doctor.diagnose(self.root/'solc',self.root/'evm')

    def test_ready_is_not_execution_or_certification(self):
        report = self.diagnose()
        self.assertEqual(report['status'],'LAB_PREREQUISITES_READY')
        self.assertTrue(all(report['prerequisites'].values()))
        for key in ('qa_executed','native_contracts_executed','solver_query_executed',
                    'dependencies_installed','network_used','vulnerability_confirmed'):
            self.assertIs(report[key],False)

    def test_missing_optional_engine_preserves_other_profiles(self):
        report = self.diagnose({'second_evm_packages'})
        self.assertEqual(report['prerequisites'],{'qa':True,'owned_geth':True,'owned_cross_evm':False})
        self.assertEqual(report['status'],'LAB_PREREQUISITES_BLOCKED')

    def test_missing_z3_blocks_qa_not_fixed_native_execution(self):
        report = self.diagnose({'z3_fixture_library'})
        self.assertEqual(report['prerequisites'],{'qa':False,'owned_geth':True,'owned_cross_evm':True})

    def test_each_native_prerequisite_blocks_both_engines(self):
        for failed in ('host','sealed_memory','solc','geth'):
            with self.subTest(failed=failed):
                report = self.diagnose({failed})
                self.assertFalse(report['prerequisites']['owned_geth'])
                self.assertFalse(report['prerequisites']['owned_cross_evm'])

    def test_unsupported_architecture_is_explicit(self):
        with patch.object(doctor.platform,'system',return_value='Linux'), \
             patch.object(doctor.platform,'machine',return_value='aarch64'):
            row = doctor._host()
        self.assertEqual(row['status'],'BLOCKED')
        self.assertEqual(row['code'],'LINUX_X86_64_PYTHON312_REQUIRED')

    def test_missing_sealed_memory_is_reported_without_exception_details(self):
        with patch.object(doctor.os,'memfd_create',side_effect=OSError('/private-probe')):
            row = doctor._sealed_memory()
        self.assertEqual(row,doctor.result(False,'SEALED_MEMORY_UNAVAILABLE'))
        self.assertNotIn('private',json.dumps(row))

    def test_qa_package_versions_are_checked(self):
        with patch.object(doctor,'version',side_effect=lambda name:doctor.PACKAGES[name]):
            self.assertEqual(doctor._qa_packages()['status'],'PASS')
        with patch.object(doctor,'version',return_value='0.0'):
            self.assertEqual(doctor._qa_packages()['status'],'BLOCKED')
        with patch.object(doctor,'version',side_effect=PackageNotFoundError('/private-metadata')):
            row = doctor._qa_packages()
        self.assertEqual(row['status'],'BLOCKED')
        self.assertNotIn('private-metadata',json.dumps(row))

    def test_z3_bytes_checked_without_loading_library(self):
        from superhunter import smt_backend
        path = self.root/'owned-library-fixture'; path.write_bytes(b'own fixture library bytes')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch.object(smt_backend,'_library_path',return_value=path), \
             patch.object(smt_backend.c,'CDLL',side_effect=AssertionError('Must not load library')), \
             patch.object(doctor,'Z3_SHA256',digest):
            self.assertEqual(doctor._z3_fixture_library()['status'],'PASS')
            path.write_bytes(b'changed own fixture library')
            self.assertEqual(doctor._z3_fixture_library()['code'],'Z3_FIXTURE_BYTES_DIFFERENT')

    def test_missing_z3_does_not_report_path(self):
        from superhunter import smt_backend
        with patch.object(smt_backend,'_library_path',side_effect=ValueError('/private-z3')):
            row = doctor._z3_fixture_library()
        self.assertEqual(row,doctor.result(False,'Z3_LIBRARY_UNAVAILABLE'))

    def test_wrong_native_tools_do_not_execute(self):
        from superhunter import native_compile,evm_execution
        path = self.root/'private-executable'; path.write_bytes(b'owned invalid executable')
        with patch.object(native_compile,'_execute',side_effect=AssertionError('Do not compile')), \
             patch.object(evm_execution,'_run',side_effect=AssertionError('Do not run EVM')):
            for kind in ('solc','geth'):
                row = doctor._tool(kind,path)
                self.assertEqual(row,doctor.result(False,'PINNED_TOOL_MISSING_OR_DIFFERENT'))
                self.assertNotIn(str(path),json.dumps(row))

    def test_unknown_tool_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_LAB_TOOL'):
            doctor._tool('arbitrary-tool',self.root)

    def test_second_engine_byte_mismatch_is_actionable_and_private(self):
        from superhunter import owned_cross_evm_worker
        with patch.object(owned_cross_evm_worker,'dependency_identity',
                          side_effect=ValueError('/private-dependency')):
            row = doctor._second_evm_packages()
        self.assertEqual(row,doctor.result(False,'SECOND_EVM_PACKAGES_MISSING_OR_DIFFERENT'))

    def test_cli_blocked_exit_and_profile_report(self):
        report = self.diagnose({'geth'})
        output = io.StringIO()
        with patch.object(doctor,'diagnose',return_value=report),redirect_stdout(output):
            code = doctor.main(['--solc','/private-solc','--evm','/private-evm'])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(output.getvalue()),report)
        self.assertNotIn('/private',output.getvalue())

    def test_cli_unexpected_input_error_does_not_leak(self):
        output = io.StringIO()
        with patch.object(doctor,'diagnose',side_effect=ValueError('/private-source')),redirect_stdout(output):
            code = doctor.main(['--solc','/private-solc','--evm','/private-evm'])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(output.getvalue())['status'],'LAB_DIAGNOSTIC_BLOCKED')
        self.assertNotIn('/private',output.getvalue())


if __name__ == '__main__':
    unittest.main()
