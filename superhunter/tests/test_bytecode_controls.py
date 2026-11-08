"""Captured REAL solc outputs plus explicit unit orchestration mocks.

No mock execution in this file counts as a native compiler run. The independent
acceptance commands use the uploaded pinned executable and installed Z3.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import bytecode_controls as bc, solidity_stateful as formal, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

FIXTURES = Path(__file__).with_name('fixtures')
AT = '2026-11-05T18:59:00+00:00'


class BytecodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.builds = strict_json((FIXTURES/'bytecode_native_capture.json').read_bytes())
        self.proof = strict_json((FIXTURES/'stateful_native_capture.json').read_bytes())

    def inspect(self, name='conservation'):
        return bc.inspect_output(name, self.builds['cases'][name]['output_utf8'].encode())

    def mutate_output(self, fn, name='conservation'):
        row = self.builds['cases'][name]
        output = strict_json(row['output_utf8'])
        fn(output['contracts']['State.sol']['StatefulConservation'])
        row['output_utf8'] = canonical(output).decode()

    def docs(self):
        return bc.documents(self.proof, self.builds, AT)

    def make(self):
        out = self.root/'bundle'; write_new_bundle(out, self.docs()); return out

    def reseal(self, root, name, fn):
        value = strict_json((root/name).read_bytes()); fn(value)
        raw = canonical(value); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes()); marker['sha256'][name] = bc.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_exact_source_reused_for_both_modes(self):
        for name in formal.NAMES:
            a = bc.build_input(name); b = formal.fixed_input(name, 'property')
            self.assertEqual(a['sources'], b['sources'])
            self.assertEqual(a['settings']['optimizer'], b['settings']['optimizer'])
            self.assertEqual(a['settings']['evmVersion'], b['settings']['evmVersion'])
            self.assertEqual(a['settings']['modelChecker'], {'engine':'none'})

    def test_only_fixed_controls_accepted(self):
        for name in ('external-target', {}, [], None):
            with self.subTest(name=name), self.assertRaises(ValueError): bc.build_input(name)

    def test_input_has_no_urls_callbacks_or_external_libraries(self):
        inp = bc.build_input('conservation')
        self.assertEqual(set(inp), {'language','sources','settings'})
        self.assertEqual(set(inp['sources']['State.sol']), {'content'})
        self.assertNotIn('libraries', inp['settings'])
        self.assertNotIn('auxiliaryInput', inp)

    def test_creation_and_runtime_are_not_conflated(self):
        for name in formal.NAMES:
            row = self.inspect(name)
            self.assertGreater(row['creation_bytes'], row['runtime_bytes'])
            self.assertNotEqual(row['creation_sha256'], row['runtime_sha256'])
            self.assertFalse(row['constructor_executed'])
            self.assertFalse(row['runtime_executed'])

    def test_real_capture_has_expected_abi_selector(self):
        self.assertEqual(self.inspect()['method_identifiers_as_compiled'], {'move(uint8)':'70e87aaf'})

    def test_corrected_and_altered_controls_have_distinct_code(self):
        a = self.inspect(); b = self.inspect('delayed_credit')
        self.assertNotEqual(a['source_sha256'], b['source_sha256'])
        self.assertNotEqual(a['runtime_sha256'], b['runtime_sha256'])
        self.assertEqual(a['abi_sha256'], b['abi_sha256'])

    def test_immutable_and_link_patches_not_silently_accepted(self):
        self.mutate_output(lambda c: c['evm']['deployedBytecode']['immutableReferences'].update({'1':[{}]}))
        with self.assertRaisesRegex(ValueError,'NO_LINK'): self.inspect()

    def test_linked_library_rejected(self):
        self.mutate_output(lambda c: c['evm']['bytecode']['linkReferences'].update({'Library.sol':{'L':[]}}))
        with self.assertRaisesRegex(ValueError,'NO_LINK'): self.inspect()

    def test_missing_or_odd_bytecode_rejected(self):
        for bad in ('', 'a', '__$placeholder$__', '0x60', 'GG'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): bc._object(bad,'BAD_OBJECT')

    def test_byte_budget_enforced(self):
        with patch.object(bc,'MAX_OBJECT_BYTES',1), self.assertRaises(ValueError): self.inspect()

    def test_abi_change_rejected(self):
        self.mutate_output(lambda c:c['abi'][0].update(name='different'))
        with self.assertRaisesRegex(ValueError,'FIXED_ABI'): self.inspect()

    def test_extra_entrypoint_rejected(self):
        self.mutate_output(lambda c:c['evm']['methodIdentifiers'].update({'other()':'00000000'}))
        with self.assertRaisesRegex(ValueError,'METHOD_IDENTIFIER'): self.inspect()

    def test_different_compiler_metadata_rejected(self):
        def edit(c):
            data=strict_json(c['metadata']); data['compiler']['version']='different'; c['metadata']=canonical(data).decode()
        self.mutate_output(edit)
        with self.assertRaisesRegex(ValueError,'METADATA_COMPILER'): self.inspect()

    def test_different_fork_metadata_rejected(self):
        def edit(c):
            data=strict_json(c['metadata']); data['settings']['evmVersion']='paris'; c['metadata']=canonical(data).decode()
        self.mutate_output(edit)
        with self.assertRaisesRegex(ValueError,'METADATA_TARGET'): self.inspect()

    def test_compilation_error_even_with_bytecode_rejected(self):
        raw=strict_json(self.builds['cases']['conservation']['output_utf8'])
        raw['errors']=[{'severity':'error','message':'Synthetic negative test'}]
        with self.assertRaisesRegex(ValueError,'COMPILATION_FAILED'): bc.inspect_output('conservation',canonical(raw))

    def test_formal_source_substitution_rejected(self):
        self.proof['cases']['conservation']['runs']['property']['input']['sources']['State.sol']['content']+='//changed'
        with self.assertRaisesRegex(ValueError,'FORMAL_BUILD_SOURCE_MISMATCH'):
            bc.bound_case('conservation',self.builds['cases']['conservation'],self.proof['cases']['conservation'])

    def test_formal_codegen_settings_must_match(self):
        self.proof['cases']['conservation']['runs']['property']['input']['settings']['optimizer']['enabled']=True
        with self.assertRaisesRegex(ValueError,'SETTINGS_MISMATCH'):
            bc.bound_case('conservation',self.builds['cases']['conservation'],self.proof['cases']['conservation'])

    def test_build_source_cannot_be_arbitrary(self):
        self.builds['cases']['conservation']['input']['sources']['State.sol']['content']='contract Other {}'
        with self.assertRaisesRegex(ValueError,'FIXED_BUILD_INPUT'):
            bc.bound_case('conservation',self.builds['cases']['conservation'],self.proof['cases']['conservation'])

    def test_missing_control_cannot_pass(self):
        del self.builds['cases']['unreachable']
        with self.assertRaisesRegex(ValueError,'COMPLETE_FIXED_CASE_SET'): self.docs()

    def test_source_property_not_promoted_to_bytecode_proof(self):
        result=bc.result_from(self.proof,self.builds,AT)
        self.assertEqual(result['status'],'NATIVE_BYTECODE_BUILT_EVM_PENDING')
        for key in ('evm_executed','bytecode_level_property_proved','constructor_executed','deployed',
                    'vulnerability_confirmed','platform_complete'):
            self.assertIs(result[key],False)
        self.assertEqual(result['controls']['unreachable']['source_property_status'],'VACUOUS_STATEFUL_NO_CERTIFICATION')

    def test_unknown_property_blocks_acceptance(self):
        self.proof['cases']['conservation']['verdict']['status']='STATEFUL_FORMAL_INCONCLUSIVE'
        with self.assertRaisesRegex(ValueError,'FORMAL_ACCEPTANCE_INCOMPLETE'): self.docs()

    def test_exhausted_budget_cannot_be_normal_acceptance(self):
        self.proof['budget']='exhausted'
        with self.assertRaisesRegex(ValueError,'FORMAL_PROFILE'): self.docs()

    def test_numeric_schema_not_boolean(self):
        self.builds['schema_version']=True
        with self.assertRaisesRegex(ValueError,'BUILD_ENVELOPE'): self.docs()

    def test_evm_claim_in_build_rejected(self):
        self.builds['constructor_initialization_checked']=True
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_EXECUTION_CLAIM'): self.docs()

    def test_creation_mocked_orchestration_preserves_raw_outputs(self):
        with patch.object(bc,'execute',return_value=(self.proof,self.builds)):
            bc.create(self.root/'unused',self.root/'created')
        self.assertEqual(strict_json((self.root/'created/builds.json').read_bytes()),self.builds)

    def test_replay_uses_regenerated_not_bundle_sources(self):
        root=self.make()
        self.reseal(root,'builds.json',lambda x:x['cases']['conservation']['input']['sources']['State.sol'].update(content='untrusted'))
        with patch.object(bc,'execute',return_value=(self.proof,self.builds)) as run, self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):
            bc.replay(root,self.root/'compiler')
        run.assert_called_once_with(self.root/'compiler')

    def test_resealed_evm_claim_rejected(self):
        root=self.make();self.reseal(root,'result.json',lambda x:x.update(evm_executed=True))
        with patch.object(bc,'execute',return_value=(self.proof,self.builds)),self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):
            bc.replay(root,self.root/'compiler')

    def test_resealed_runtime_change_rejected(self):
        root=self.make()
        def edit(value):
            row=value['cases']['conservation'];data=strict_json(row['output_utf8'])
            data['contracts']['State.sol']['StatefulConservation']['evm']['deployedBytecode']['object']='6000'
            row['output_utf8']=canonical(data).decode()
        self.reseal(root,'builds.json',edit)
        with patch.object(bc,'execute',return_value=(self.proof,self.builds)),self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):
            bc.replay(root,self.root/'compiler')

    def test_extra_artifact_rejected_before_execution(self):
        root=self.make();(root/'extra.txt').write_text('unlisted')
        with patch.object(bc,'execute',side_effect=AssertionError),self.assertRaisesRegex(ValueError,'BUNDLE_FILES'):
            bc.replay(root,self.root/'compiler')

    def test_no_overwrite(self):
        root=self.make()
        with patch.object(bc,'execute',side_effect=AssertionError),self.assertRaisesRegex(ValueError,'NEW_OUTPUT'):
            bc.create(self.root/'compiler',root)

    def test_private_bundle_permissions(self):
        root=self.make();self.assertEqual(root.stat().st_mode&0o777,0o700)
        for p in root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_symlink_bundle_rejected(self):
        root=self.make();link=self.root/'alias';link.symlink_to(root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'SYMLINK'):bc.replay(link,self.root/'compiler')

    def test_missing_compiler_is_blocked_not_fake_build(self):
        with redirect_stdout(io.StringIO()) as out:
            code=bc.main(['build-stateful-bytecode','--solc',str(self.root/'missing'), '--out',str(self.root/'blocked')])
        self.assertEqual(code,2);self.assertFalse((self.root/'blocked').exists())
        self.assertEqual(json.loads(out.getvalue())['status'],'NATIVE_BYTECODE_BUILD_BLOCKED')

    def test_native_audit_binds_every_control(self):
        data=strict_json(self.docs()['audit.json']);self.assertEqual(len(data['events']),5)
        self.assertEqual([e['data']['control'] for e in data['events'][1:4]],list(formal.NAMES))

    def test_cli_partial_not_success_code(self):
        with patch.object(bc,'create',return_value=bc.result_from(self.proof,self.builds,AT)),redirect_stdout(io.StringIO()) as out:
            code=bc.main(['build-stateful-bytecode','--solc','unused','--out','unused'])
        self.assertEqual(code,1);self.assertFalse(json.loads(out.getvalue())['evm_executed'])

    def test_cli_rejects_arbitrary_source_and_rpc(self):
        for opt in ('--source','--rpc','--target','--bytecode'):
            with self.subTest(opt=opt), patch('sys.stderr',new_callable=io.StringIO) as err,self.assertRaises(SystemExit):
                bc.main(['build-stateful-bytecode','--solc','unused','--out','unused',opt,'PRIVATE_VALUE'])
            self.assertNotIn('PRIVATE_VALUE',err.getvalue())

    def test_entrypoint_and_quality_are_connected(self):
        from superhunter import __main__
        self.assertIn('bytecode_controls',quality.COMPONENTS)
        self.assertIn('test_bytecode_controls.BytecodeTests.test_resealed_evm_claim_rejected',quality.REQUIRED_TESTS)
        self.assertIn('tests/fixtures/bytecode_native_capture.json',quality.source_snapshot())
        with patch('sys.argv',['superhunter','build-stateful-bytecode','--solc','x','--out','y']), \
             patch.object(bc,'main',return_value=1) as runner:
            self.assertEqual(__main__.main(),1)
        runner.assert_called_once()


if __name__=='__main__':unittest.main()
