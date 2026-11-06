"""Unit/parser tests using captured REAL EVM output; mocks are not native acceptance.

The separate native acceptance recompiles and reruns both tools without mocks.
Only owned fixed arithmetic controls are involved; no external targets.
"""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_execution as e, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

AT = '2026-11-05T23:00:00+00:00'
FIXTURE = Path(__file__).parent/'fixtures/evm_state_capture.json'


class EVMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = strict_json(FIXTURE.read_bytes())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = deepcopy(self.capture)

    def case(self, name='conservation'):
        row = self.data['cases'][name]
        contract = strict_json(self.data['builds']['cases'][name]['output_utf8'])['contracts']['State.sol']['StatefulConservation']
        return row, contract

    def bundle(self):
        out = self.root/'case'
        write_new_bundle(out, e.documents(self.data, AT))
        return out

    def reseal(self, root, name, change):
        value = strict_json((root/name).read_bytes()); change(value)
        raw = canonical(value); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes()); marker['sha256'][name] = e.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_captured_native_runs_reparse_with_expected_counts(self):
        result = e.result_from(self.data, AT)
        self.assertEqual(result['call_outcomes'], {'COMMITTED':5,'PRECONDITION_REVERT':8,'ASSERTION_REVERT':2,'RESOURCE_EXHAUSTED':3})
        self.assertEqual((result['constructor_calls'], result['runtime_calls']), (3,18))
        self.assertFalse(result['vulnerability_confirmed'])

    def test_constructor_state_decoded_not_preloaded(self):
        row, contract = self.case()
        self.assertEqual(e.decode_state(row['constructor']['observed']['alloc'], contract), {'debit':15,'credit':0,'steps':0})
        self.assertEqual(e.genesis()['alloc'], {})
        self.assertEqual(row['constructor']['prestate_sha256'], e.sha(canonical(e.genesis())))

    def test_assertion_revert_does_not_commit_tentative_credit(self):
        row, contract = self.case('delayed_credit')
        call = row['calls'][3]
        self.assertEqual(call['reference']['status'], 'ASSERTION_REVERT')
        self.assertEqual(call['reference']['uncommitted_model_state']['credit'], 10)
        self.assertEqual(call['state_after']['credit'], 5)
        self.assertEqual(call['state_before'], call['state_after'])
        self.assertEqual(e.validate_case('delayed_credit',row,contract)['ASSERTION_REVERT'],2)

    def test_rejected_precondition_does_not_break_later_valid_call(self):
        row, _ = self.case()
        self.assertEqual(row['calls'][1]['state_before'],row['calls'][1]['state_after'])
        self.assertEqual(row['calls'][2]['reference']['status'],'COMMITTED')
        self.assertEqual(row['final_state'], {'debit':6,'credit':9,'steps':3})

    def test_out_of_gas_distinct_from_assertion_failure(self):
        row, _ = self.case('delayed_credit')
        self.assertEqual(row['calls'][-1]['reference']['status'],'RESOURCE_EXHAUSTED')
        self.assertEqual(row['calls'][-1]['execution']['observed']['error'],'out of gas')
        self.assertEqual(row['calls'][-1]['execution']['observed']['return_data'],'0x')
        self.assertEqual(row['calls'][3]['execution']['observed']['return_data'],e.PANIC_ASSERT)

    def test_unreachable_case_not_reported_as_vulnerability(self):
        row, _ = self.case('unreachable')
        self.assertEqual(row['final_state'],row['constructor_state'])
        self.assertTrue(all(c['reference']['status'] != 'COMMITTED' for c in row['calls']))
        self.assertFalse(e.result_from(self.data,AT)['source_properties_transferred_as_bytecode_proof'])

    def test_gas_budget_bound_in_genesis_not_only_cli(self):
        self.assertEqual(e.genesis(gas=1)['gasLimit'],'0x1')
        row,_ = self.case()
        low = row['calls'][-1]
        alloc = row['calls'][-2]['execution']['observed']['alloc']
        self.assertEqual(low['execution']['prestate_sha256'],e.sha(canonical(e.genesis(alloc,gas=1))))
        self.assertNotEqual(e.genesis(gas=1),e.genesis())

    def test_genesis_does_not_mutate_observed_alloc(self):
        row,_=self.case();a=row['constructor']['observed']['alloc'];old=deepcopy(a)
        g=e.genesis(a);g['alloc'][e.SENDER]['balance']='999'
        self.assertEqual(a,old)

    def test_reference_preserves_input_and_rejects_boolean_quantities(self):
        state={'debit':10,'credit':5,'steps':2};old=deepcopy(state)
        self.assertEqual(e.reference('delayed_credit',state,4,e.GAS)['state'],state)
        self.assertEqual(state,old)
        for q in (True,-1,256,'4'):
            with self.subTest(q=q),self.assertRaises(e.EVMError):e.reference('conservation',state,q,e.GAS)
        with self.assertRaises(e.EVMError):e.reference('conservation',state,4,True)

    def test_duplicate_json_keys_rejected(self):
        raw=b'{"root":"'+b'0'*64+b'","root":"'+b'1'*64+b'","accounts":{}}'
        with self.assertRaisesRegex(e.EVMError,'DUPLICATE'):e.parse_run(raw)

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(e.EVMError,'NONFINITE'):e.parse_run(b'{"root":NaN}')

    def test_unknown_output_suffix_rejected(self):
        raw=self.case()[0]['constructor']['stdout_utf8'].encode()+b'\nunknown error\n'
        with self.assertRaisesRegex(e.EVMError,'RETURN_OR_ERROR'):e.parse_run(raw)

    def test_boolean_nonce_rejected(self):
        raw=self.case()[0]['constructor']['stdout_utf8'];d,i=json.JSONDecoder().raw_decode(raw)
        d['accounts'][e.SENDER]['nonce']=True
        with self.assertRaises(e.EVMError):e.parse_run(canonical(d)+raw[i:].encode())

    def test_unknown_account_rejected(self):
        raw=self.case()[0]['constructor']['stdout_utf8'];d,i=json.JSONDecoder().raw_decode(raw)
        d['accounts']['0x'+'ff'*20]=d['accounts'].pop(e.SENDER)
        with self.assertRaisesRegex(e.EVMError,'UNEXPECTED_EVM_ACCOUNT'):e.parse_run(canonical(d)+raw[i:].encode())

    def test_unknown_storage_slot_rejected(self):
        raw=self.case()[0]['constructor']['stdout_utf8'];d,i=json.JSONDecoder().raw_decode(raw)
        acct=next(x for x in d['accounts'].values() if x.get('code'));acct['storage']['0x'+'01'*32]='01'
        with self.assertRaisesRegex(e.EVMError,'STORAGE_PROFILE'):e.parse_run(canonical(d)+raw[i:].encode())

    def test_output_size_and_root_bounds(self):
        for raw in (b'',b' '*2_000_000,b'{"root":"0x0","accounts":{}}'):
            with self.assertRaises(e.EVMError):e.parse_run(raw)

    def test_runtime_not_replaced_by_handwritten_code(self):
        row,c=self.case();row['constructor']['observed']['alloc'][e.RECEIVER]['code']='0x00'
        with self.assertRaisesRegex(e.EVMError,'RUNTIME_NOT'):e.decode_state(row['constructor']['observed']['alloc'],c)

    def test_storage_layout_must_match_compiled_profile(self):
        row,c=self.case();c['storageLayout']['storage'][0]['offset']=1
        with self.assertRaisesRegex(e.EVMError,'FIXED_STORAGE'):e.decode_state(row['constructor']['observed']['alloc'],c)

    def test_extra_high_storage_bits_rejected(self):
        row,c=self.case();a=row['constructor']['observed']['alloc'];a[e.RECEIVER]['storage'][e.SLOT]=hex(1<<100)
        with self.assertRaisesRegex(e.EVMError,'UNEXPECTED_STORAGE_BITS'):e.decode_state(a,c)

    def test_missing_call_blocks_coverage(self):
        self.data['cases']['conservation']['calls'].pop()
        with self.assertRaisesRegex(e.EVMError,'CALL_COVERAGE'):e.result_from(self.data,AT)

    def test_swapped_calls_rejected(self):
        row,c=self.case();row['calls'][0],row['calls'][1]=row['calls'][1],row['calls'][0]
        with self.assertRaisesRegex(e.EVMError,'CALL_ORDER'):e.validate_case('conservation',row,c)

    def test_unknown_call_quantity_rejected(self):
        row,c=self.case();row['calls'][0]['quantity']=7
        with self.assertRaisesRegex(e.EVMError,'CALL_ORDER'):e.validate_case('conservation',row,c)

    def test_false_reference_does_not_override_execution(self):
        row,c=self.case('delayed_credit');row['calls'][3]['reference']['status']='COMMITTED'
        with self.assertRaisesRegex(e.EVMError,'FALSE_REFERENCE'):e.validate_case('delayed_credit',row,c)

    def test_observation_must_match_raw_stdout(self):
        row,c=self.case();row['calls'][0]['execution']['observed']['state_root']='0'*64
        with self.assertRaisesRegex(e.EVMError,'NOT_FROM_STDOUT'):e.validate_case('conservation',row,c)

    def test_prestate_binding_rejects_cross_run_substitution(self):
        row,c=self.case();row['calls'][1]['execution']['prestate_sha256']='0'*64
        with self.assertRaisesRegex(e.EVMError,'EXECUTION_BINDING'):e.validate_case('conservation',row,c)

    def test_call_selector_bound_to_compilation(self):
        row,c=self.case();row['calls'][0]['execution']['calldata']='0'*72
        with self.assertRaisesRegex(e.EVMError,'EXECUTION_BINDING'):e.validate_case('conservation',row,c)

    def test_formal_result_does_not_float_free(self):
        self.data['cases']['conservation']['source_property_status']='made-up-safe'
        with self.assertRaisesRegex(e.EVMError,'FORMAL_RESULT_BINDING'):e.result_from(self.data,AT)

    def test_source_substitution_rejected(self):
        self.data['builds']['cases']['conservation']['input']['sources']['State.sol']['content']+='// changed'
        with self.assertRaises(ValueError):e.result_from(self.data,AT)

    def test_external_execution_flags_remain_false(self):
        r=e.result_from(self.data,AT)
        for k in ('network_used','onchain_transactions','token_balances_or_profit_measured',
                  'source_properties_transferred_as_bytecode_proof','vulnerability_confirmed','platform_complete','independent_evm_used'):
            self.assertIs(r[k],False)

    def test_derived_documents_use_native_audit(self):
        native=e.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as calls:
            d=e.documents(self.data,AT)
        self.assertEqual(calls.call_count,23)
        self.assertEqual(len(strict_json(d['audit.json'])['events']),23)

    def test_data_derivation_has_no_network_or_processes(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.Popen',side_effect=AssertionError):
            self.assertFalse(strict_json(e.documents(self.data,AT)['result.json'])['platform_complete'])

    def test_original_capture_not_mutated(self):
        old=canonical(self.data);e.documents(self.data,AT);self.assertEqual(canonical(self.data),old)

    def test_private_bundle_permissions(self):
        root=self.bundle();self.assertEqual(root.stat().st_mode&0o777,0o700)
        for p in root.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_replay_never_executes_bundle_inputs(self):
        root=self.bundle()
        with patch.object(e,'execute',return_value=self.data) as run:
            result=e.replay(root,Path('expected-solc'),Path('expected-evm'))
        run.assert_called_once_with(Path('expected-solc'),Path('expected-evm'))
        self.assertTrue(result['same_engines_replayed'])

    def test_resealed_favorable_result_rejected(self):
        root=self.bundle();self.reseal(root,'result.json',lambda d:d.update(vulnerability_confirmed=True))
        with patch.object(e,'execute',return_value=self.data),self.assertRaisesRegex(e.EVMError,'REPLAY_MISMATCH'):
            e.replay(root,Path('s'),Path('e'))

    def test_resealed_root_rejected_by_native_replay_comparison(self):
        root=self.bundle()
        self.reseal(root,'execution.json',lambda d:d['cases']['conservation']['constructor']['observed'].update(state_root='0'*64))
        with patch.object(e,'execute',return_value=self.data),self.assertRaisesRegex(e.EVMError,'REPLAY_MISMATCH'):
            e.replay(root,Path('s'),Path('e'))

    def test_extra_bundle_file_rejected_before_replay(self):
        root=self.bundle();(root/'unexpected').write_text('no')
        with patch.object(e,'execute') as run,self.assertRaisesRegex(e.EVMError,'FILE_SET'):
            e.replay(root,Path('s'),Path('e'))
        run.assert_not_called()

    def test_existing_output_never_reexecuted_or_overwritten(self):
        root=self.bundle();before=(root/'COMPLETE.json').read_bytes()
        with patch.object(e,'execute') as run,self.assertRaises(e.EVMError):e.create(Path('s'),Path('e'),root)
        run.assert_not_called();self.assertEqual((root/'COMPLETE.json').read_bytes(),before)

    def test_missing_binary_blocks_before_compiler(self):
        with patch.object(e.builds,'execute') as build,self.assertRaisesRegex(e.EVMError,'BINARY_UNAVAILABLE'):
            e.execute(Path('s'),self.root/'absent')
        build.assert_not_called()

    def test_impostor_binary_never_executes(self):
        p=self.root/'impostor';p.write_bytes(b'#!/bin/sh\nexit 0\n')
        with patch('subprocess.Popen') as run,self.assertRaisesRegex(e.EVMError,'BINARY_SIZE'):e.read_evm(p)
        run.assert_not_called()

    def test_symlink_and_fifo_rejected(self):
        p=self.root/'link';p.symlink_to('/does-not-exist')
        with self.assertRaises(e.EVMError):e.read_evm(p)
        q=self.root/'fifo';os.mkfifo(q)
        with self.assertRaises(e.EVMError):e.read_evm(q)

    def test_binary_hash_mismatch_rejected(self):
        p=self.root/'small';p.write_bytes(b'\x7fELF0000')
        with patch.dict(e.PIN,{'bytes':8}),self.assertRaisesRegex(e.EVMError,'BINARY_HASH'):e.read_evm(p)

    def test_cli_no_arbitrary_target_or_rpc(self):
        for key in ('--rpc','--target','--source','--calldata'):
            with redirect_stderr(io.StringIO()) as out,self.assertRaises(SystemExit):
                e.main(['run-evm-state-controls','--solc','s','--evm','e','--out','o',key,'PRIVATE_VALUE'])
            self.assertNotIn('PRIVATE_VALUE',out.getvalue())

    def test_cli_missing_binary_sanitized(self):
        with redirect_stdout(io.StringIO()) as out:
            code=e.main(['run-evm-state-controls','--solc','SECRET_SOLC','--evm','PRIVATE_EVM','--out',str(self.root/'out')])
        self.assertEqual(code,2);self.assertNotIn('PRIVATE_EVM',out.getvalue());self.assertNotIn('SECRET_SOLC',out.getvalue())

    def test_entrypoint_registered(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','run-evm-state-controls','--solc','s','--evm','e','--out','o']),patch.object(e,'main',return_value=2) as run:
            self.assertEqual(__main__.main(),2)
        run.assert_called_once()

    def test_quality_includes_real_capture_and_required_tests(self):
        snap=quality.source_snapshot()
        self.assertIn('tests/fixtures/evm_state_capture.json',snap)
        self.assertIn('evm_execution',quality.COMPONENTS)
        self.assertEqual(quality.validate_components(snap),[])
        self.assertIn('test_evm_execution.EVMTests.test_gas_budget_bound_in_genesis_not_only_cli',quality.REQUIRED_TESTS)


if __name__ == '__main__':
    unittest.main()
