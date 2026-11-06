"""Driver tests. JSON output fixtures are not real compilation evidence.

No substitute executable is accepted as solc. The only non-solc execution below
exercises the private OS process boundary with the actual Python interpreter.
End-to-end solc compilation remains an unrun acceptance gate when binary absent.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import native_compile as nc, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class NativeCompileTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.src='// SPDX-License-Identifier: MIT\npragma solidity 0.8.30;\ncontract C { uint128 public value; }\n'
        self.raw=nc.standard_input({'C.sol':self.src})
        self.infile=self.root/'input.json';self.infile.write_bytes(self.raw)
        self.version=b'solc, the solidity compiler commandline interface\nVersion: 0.8.30+commit.73712a01.Linux.g++\n'
        # Pure shape fixture; never claimed to originate from compiler execution.
        self.output={'sources':{'C.sol':{'id':0,'ast':{'nodeType':'SourceUnit'}}},
                     'contracts':{'C.sol':{'C':{'storageLayout':{'storage':[],'types':{}}}}}}

    def bundle_fixture(self):
        output=canonical(self.output)
        receipt=nc._receipt(self.raw,output,self.version,b'',produced_at='2026-11-05T00:00:00+00:00')
        files={'input.json':self.raw,'output.json':output,'version.txt':self.version,'stderr.txt':b'',
               'receipt.json':canonical(receipt),'audit.json':canonical(nc._audit(receipt)),
               'REVIEW.md':nc._review(receipt)}
        out=self.root/'shape-fixture';write_new_bundle(out,files);return out

    def reseal(self,out,name,fn):
        value=strict_json((out/name).read_bytes());fn(value);raw=canonical(value);(out/name).write_bytes(raw)
        m=strict_json((out/'COMPLETE.json').read_bytes());m['sha256'][name]=nc.sha(raw)
        (out/'COMPLETE.json').write_bytes(canonical(m))

    def test_inline_input_uses_fixed_settings(self):
        data=nc.validate_input(self.raw)
        self.assertEqual(data['settings'],nc.SETTINGS)
        self.assertEqual(data['sources']['C.sol']['content'],self.src)
        self.assertEqual(data['settings']['modelChecker'],{'engine':'none'})

    def test_input_url_callback_not_allowed(self):
        data=strict_json(self.raw);data['sources']['C.sol']={'urls':['file:///private']}
        with self.assertRaisesRegex(nc.CompileError,'INLINE_ONLY'):
            nc.validate_input(canonical(data))

    def test_settings_cannot_enable_external_solver_or_codegen(self):
        for settings in ({'modelChecker':{'engine':'all'}}, {'optimizer':{'enabled':True}},
                         {'remappings':['x=/etc/']}, {'outputSelection':{'*':{'*':['*']}}}):
            with self.subTest(settings=settings):
                d=strict_json(self.raw);d['settings'].update(settings)
                with self.assertRaisesRegex(nc.CompileError,'FIXED_COMPILER_SETTINGS'):
                    nc.validate_input(canonical(d))

    def test_large_or_empty_source_rejected(self):
        for sources in ({},{'C.sol':''},{'C.sol':'x'*(nc.MAX_SOURCE+1)}):
            with self.subTest(count=len(sources)),self.assertRaises(ValueError):nc.standard_input(sources)

    def test_duplicate_json_and_unsafe_paths_rejected(self):
        with self.assertRaises(ValueError):nc.validate_input(b'{"language":"x","language":"Solidity"}')
        for name in ('../C.sol','/C.sol','C.sol\n','x\\C.sol'):
            with self.subTest(name=name),self.assertRaises(ValueError):nc.standard_input({name:self.src})

    def test_missing_binary_blocks_without_output(self):
        with patch.object(nc,'_execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(nc.CompilerUnavailable,'NOT_INSTALLED'):
                nc.compile_bundle(self.infile,self.root/'missing',self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_wrong_binary_never_executed(self):
        fake=self.root/'fake';fake.write_bytes(b'#!/bin/sh\necho not-a-compiler\n');fake.chmod(0o700)
        with patch.object(nc,'_execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(nc.CompileError,'HASH_MISMATCH'):
                nc.compile_bundle(self.infile,fake,self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_empty_binary_and_directory_rejected(self):
        path=self.root/'empty';path.touch()
        for p in (path,self.root):
            with self.subTest(p=p.name),self.assertRaises(nc.CompileError):nc.read_pinned_binary(p)

    def test_binary_symlink_not_followed(self):
        p=self.root/'linked';p.symlink_to(Path(sys.executable).resolve())
        with self.assertRaisesRegex(nc.CompileError,'UNREADABLE'):nc.read_pinned_binary(p)

    def test_wrong_platform_never_executes(self):
        with patch.object(nc.platform,'machine',return_value='aarch64'),self.assertRaises(nc.CompilerUnavailable):
            nc.read_pinned_binary(self.root/'missing')

    def test_existing_output_never_overwritten(self):
        p=self.root/'out';p.mkdir();(p/'old').write_bytes(b'old')
        with self.assertRaisesRegex(nc.CompileError,'NEW_OUTPUT'):
            nc.compile_bundle(self.infile,self.root/'missing',p)
        self.assertEqual((p/'old').read_bytes(),b'old')

    def test_output_inside_checkout_rejected_before_read(self):
        with self.assertRaisesRegex(nc.CompileError,'OUTPUT_INSIDE_CODE'):
            nc.compile_bundle(self.infile,self.root/'missing',nc.ROOT/'should-not-exist')
        self.assertFalse((nc.ROOT/'should-not-exist').exists())

    def test_version_is_full_build_not_substring(self):
        nc.verify_version(self.version)
        for v in (b'0.8.30',self.version.replace(b'73712a01',b'deadbeef'),b'prefix '+self.version):
            # prefix may affect first line but not exact Version line, so use that line directly.
            if v.startswith(b'prefix '):v=b'XVersion: 0.8.30+commit.73712a01.Linux.g++\n'
            with self.subTest(v=v),self.assertRaises(nc.CompileError):nc.verify_version(v)

    def test_exit_zero_with_errors_not_compilation_success(self):
        raw=canonical({'errors':[{'severity':'error','message':'synthetic compiler diagnostic'}]})
        r=nc.classify_output(nc.validate_input(self.raw),raw)
        self.assertEqual(r['status'],'SOLC_COMPILATION_FAILED')
        self.assertEqual(r['errors'],1)

    def test_output_shape_not_assertion_of_execution(self):
        r=nc.classify_output(nc.validate_input(self.raw),canonical(self.output))
        self.assertEqual(r['contracts'],1)
        self.assertNotIn('execution_verified',r)

    def test_absent_ast_or_layout_rejected(self):
        self.output['sources']['C.sol'].pop('ast')
        with self.assertRaisesRegex(nc.CompileError,'AST_MISSING'):
            nc.classify_output(nc.validate_input(self.raw),canonical(self.output))
        self.output['sources']['C.sol']['ast']={'nodeType':'SourceUnit'}
        self.output['contracts']['C.sol']['C'].pop('storageLayout')
        with self.assertRaisesRegex(nc.CompileError,'LAYOUT_MISSING'):
            nc.classify_output(nc.validate_input(self.raw),canonical(self.output))

    def test_unknown_source_and_malformed_diagnostics_rejected(self):
        self.output['sources']['Extra.sol']={'id':1,'ast':{'nodeType':'SourceUnit'}}
        with self.assertRaisesRegex(nc.CompileError,'SOURCE_SET'):
            nc.classify_output(nc.validate_input(self.raw),canonical(self.output))
        with self.assertRaises(nc.CompileError):nc.classify_output({},canonical({'errors':[{'severity':True}]}))

    def test_empty_contracts_not_misreported(self):
        self.output['contracts']={}
        with self.assertRaisesRegex(nc.CompileError,'NO_CONTRACT'):
            nc.classify_output(nc.validate_input(self.raw),canonical(self.output))

    def test_input_reference_is_mandatory(self):
        out=self.bundle_fixture()
        with self.assertRaisesRegex(nc.CompileError,'EXTERNAL_INPUT_MISMATCH'):
            nc._read_bundle(out,expected_input_sha256='0'*64)
        with self.assertRaisesRegex(nc.CompileError,'EXTERNAL_INPUT_HASH'):
            nc._read_bundle(out,expected_input_sha256='')

    def test_consistent_fixture_is_not_a_compiler_replay(self):
        out=self.bundle_fixture()
        raw=nc._read_bundle(out,expected_input_sha256=nc.sha(self.raw))
        self.assertFalse(strict_json(raw['receipt.json'])['remote_producer_authenticated'])
        with self.assertRaises(nc.CompilerUnavailable):
            nc.replay_bundle(out,self.root/'missing',expected_input_sha256=nc.sha(self.raw))

    def test_receipt_tampering_rejected_even_after_rehash(self):
        out=self.bundle_fixture()
        self.reseal(out,'receipt.json',lambda r:r.update(executed_contracts=True))
        with self.assertRaisesRegex(nc.CompileError,'DERIVED_ARTIFACT'):
            nc._read_bundle(out,expected_input_sha256=nc.sha(self.raw))

    def test_extra_file_rejected(self):
        out=self.bundle_fixture();(out/'extra').write_text('not declared')
        with self.assertRaisesRegex(nc.CompileError,'BUNDLE_FILES'):
            nc._read_bundle(out,expected_input_sha256=nc.sha(self.raw))

    def test_bundle_originals_and_permissions(self):
        out=self.bundle_fixture();nc._read_bundle(out,expected_input_sha256=nc.sha(self.raw))
        self.assertEqual((out/'input.json').read_bytes(),self.raw)
        self.assertEqual(out.stat().st_mode&0o777,0o700)
        self.assertTrue(all((x.stat().st_mode&0o777)==0o600 for x in out.iterdir()))

    def test_sealed_bytes_cannot_be_changed(self):
        with nc._sealed_executable(b'test data, not executable') as fd:
            with self.assertRaises(OSError):os.write(fd,b'mutated')
            os.lseek(fd,0,os.SEEK_SET)
            self.assertEqual(os.read(fd,128),b'test data, not executable')

    def test_real_os_process_boundary_not_a_compiler(self):
        image=Path(sys.executable).resolve().read_bytes()
        output,stderr=nc._execute(image,'version')
        self.assertIn(b'Python',output+stderr)
        with self.assertRaises(nc.CompileError):nc.verify_version(output)
        # The PUBLIC driver must reject this interpreter before execution.
        with self.assertRaisesRegex(nc.CompileError,'HASH_MISMATCH'):
            nc.read_pinned_binary(Path(sys.executable).resolve())

    def test_worker_never_accepts_user_flags(self):
        result=subprocess.run([sys.executable,'-I','-B',str(nc.ROOT/'solc_worker.py'),'arbitrary','3'],
                              capture_output=True,timeout=10)
        self.assertEqual(result.returncode,125)
        self.assertEqual(result.stderr,b'COMPILER_WORKER_ERROR\n')

    def test_private_process_mode_is_validated(self):
        with self.assertRaisesRegex(nc.CompileError,'EXECUTION_MODE'):
            nc._execute(b'\x7fELF'+b'x'*10,'--shell')

    def test_cli_blocker_exit_no_sensitive_path_echo(self):
        with redirect_stdout(io.StringIO()) as out:
            code=nc.main(['inspect-solc','--binary',str(self.root/'PRIVATE_VALUE')])
        r=json.loads(out.getvalue())
        self.assertEqual(code,3);self.assertEqual(r['status'],'COMPILATION_BLOCKED')
        self.assertFalse(r['compilation_performed']);self.assertNotIn('PRIVATE_VALUE',out.getvalue())

    def test_cli_unknown_values_not_echoed(self):
        with patch('sys.stderr',new_callable=io.StringIO) as out,self.assertRaises(SystemExit):
            nc.main(['inspect-solc','--binary','none','--unknown','PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE',out.getvalue())

    def test_package_entrypoint_routes_missing_compiler_to_blocker(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','inspect-solc','--binary',str(self.root/'none')]),redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),3)

    def test_component_registered_with_actual_dependencies(self):
        comp=quality.COMPONENTS['native_compile']
        self.assertEqual(set(comp['files']),{'native_compile.py','solc_worker.py'})
        self.assertIn('compiler_layout',comp['depends'])
        self.assertIn('native_compile',quality.COMPONENTS['quality']['depends'])
        self.assertIn('test_native_compile.NativeCompileTests.test_missing_binary_blocks_without_output',quality.REQUIRED_TESTS)


if __name__=='__main__':
    unittest.main()
