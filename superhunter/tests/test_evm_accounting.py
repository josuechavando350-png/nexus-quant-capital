"""Derivation of captured native execution; mocks isolate orchestration only.

These unit tests do NOT count a captured run or patched execute as a new EVM run.
Native acceptance runs/replays the pinned compiler, solver and EVM separately.
"""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_accounting as a, evm_execution as e, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

AT='2026-11-05T23:00:00+00:00'
FIXTURE=Path(__file__).parent/'fixtures/evm_accounting_capture_io_v2.json'


class CommittedEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture=strict_json(FIXTURE.read_bytes())

    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.data=deepcopy(self.capture)

    def go(self):return a.derive(self.data,AT)

    def bundle(self):
        root=self.root/'bundle';write_new_bundle(root,a.documents(self.data,AT));return root

    def reseal(self,root,name,fn):
        v=strict_json((root/name).read_bytes());fn(v);raw=canonical(v);(root/name).write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes());marker['sha256'][name]=e.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_expected_native_counts(self):
        r=self.go();self.assertEqual((r['calls_checked'],r['transfer_count'],r['per_call_cells_checked']),(18,5,36))
        self.assertEqual(r['failed_calls_without_transfer'],13)
        self.assertEqual(r['call_outcomes'],{'COMMITTED':5,'PRECONDITION_REVERT':8,'ASSERTION_REVERT':2,'RESOURCE_EXHAUSTED':3})

    def test_reverts_contribute_no_transfers(self):
        r=self.go()
        for case in r['cases'].values():
            for j in case['journal']:
                if j['outcome']!='COMMITTED':
                    self.assertEqual(j['applied_transfer_units'],'0');self.assertEqual(j['transfers'],[])
                    self.assertEqual(j['before_units'],j['after_units'])

    def test_tentative_credit_not_committed(self):
        j=self.go()['cases']['delayed_credit']['journal'][3]
        self.assertEqual(j['discarded_model_state']['credit'],10)
        self.assertEqual(j['after_units']['credit'],'5')
        self.assertFalse(j['discarded_state_is_observed_storage'])
        self.assertEqual(j['equations']['total_delta_units'],'0')

    def test_expected_final_states_and_per_case_amounts(self):
        cases=self.go()['cases']
        self.assertEqual(cases['conservation']['final_units'],{'debit':'6','credit':'9'})
        self.assertEqual(cases['conservation']['applied_transfer_units'],'9')
        self.assertEqual(cases['delayed_credit']['final_units'],{'debit':'10','credit':'5'})
        self.assertEqual(cases['delayed_credit']['applied_transfer_units'],'5')
        self.assertEqual(cases['unreachable']['applied_transfer_units'],'0')

    def test_no_financial_loss_inferred_from_counterexample(self):
        r=self.go()
        self.assertIsNone(r['monetary_valuation_usd']);self.assertFalse(r['token_balances_measured'])
        self.assertFalse(r['gas_cost_measured']);self.assertFalse(r['vulnerability_confirmed'])
        self.assertFalse(r['all_paths_proved']);self.assertFalse(r['derivation_reran_evm'])
        for c in r['cases'].values():
            self.assertIsNone(c['gas_cost_usd']);self.assertIsNone(c['financial_loss_usd'])
            self.assertFalse(c['source_counterexample_is_financial_loss'])

    def test_out_of_gas_not_success_or_property_proof(self):
        r=self.go()
        for c in r['cases'].values():
            self.assertEqual(c['journal'][-1]['outcome'],'RESOURCE_EXHAUSTED')
            self.assertEqual(c['journal'][-1]['applied_transfer_units'],'0')
        self.assertFalse(r['all_paths_proved'])

    def test_raw_output_reparsed_and_storage_decoded(self):
        with patch.object(e,'parse_run',wraps=e.parse_run) as parser,patch.object(e,'decode_state',wraps=e.decode_state) as decoder:
            self.go()
        self.assertGreaterEqual(parser.call_count,21);self.assertGreaterEqual(decoder.call_count,21)

    def test_existing_arithmetic_is_called_for_every_call_and_case(self):
        with patch.object(a.accounting,'reconcile_internal_units',wraps=a.accounting.reconcile_internal_units) as calc:
            self.go()
        self.assertEqual(calc.call_count,21)

    def test_bad_arithmetic_blocks_case(self):
        with patch.object(a.accounting,'reconcile_internal_units',return_value={'status':'UNIT_BALANCES_MISMATCH'}),self.assertRaisesRegex(a.EffectsError,'UNEXPLAINED'):
            self.go()

    def test_passing_aggregate_cannot_replace_per_call_evidence(self):
        self.data['cases']['conservation']['calls'].pop(1)
        with self.assertRaises(ValueError):self.go()

    def test_renamed_or_omitted_case_rejected(self):
        self.data['cases']['other']=self.data['cases'].pop('unreachable')
        with self.assertRaises(ValueError):self.go()

    def test_changed_quantity_rejected(self):
        self.data['cases']['conservation']['calls'][0]['quantity']=3
        with self.assertRaises(ValueError):self.go()

    def test_unchanged_final_total_cannot_hide_wrong_intermediate_state(self):
        c=self.data['cases']['conservation']['calls'][0]
        c['state_after']['debit']-=1;c['state_after']['credit']+=1
        with self.assertRaises(ValueError):self.go()

    def test_false_committed_reference_rejected(self):
        self.data['cases']['delayed_credit']['calls'][3]['reference']['status']='COMMITTED'
        with self.assertRaises(ValueError):self.go()

    def test_engine_identity_must_match_capture(self):
        self.data['engine']['sources_sha256']['evm_execution.py']='0'*64
        with self.assertRaisesRegex(a.EffectsError,'STALE_EVM_ENGINE'):self.go()

    def test_plain_derivation_never_launches_or_connects(self):
        with patch('subprocess.Popen',side_effect=AssertionError),patch('socket.socket',side_effect=AssertionError):
            self.assertFalse(self.go()['derivation_reran_evm'])

    def test_input_bytes_and_structure_not_modified(self):
        before=canonical(self.data);self.go();self.assertEqual(canonical(self.data),before)

    def test_decision_uses_observation_not_input_reference(self):
        self.assertEqual(a.classify({'error':'execution reverted','return_data':e.PANIC_ASSERT}),'ASSERTION_REVERT')
        with self.assertRaises(a.EffectsError):a.classify({'error':None,'return_data':e.PANIC_ASSERT})

    def test_order_bound_to_same_call_outputs(self):
        c=self.data['cases']['conservation']['calls'];c[0],c[2]=c[2],c[0]
        with self.assertRaises(ValueError):self.go()

    def test_replay_regenerates_instead_of_executing_bundle(self):
        root=self.bundle()
        with patch.object(e,'execute',return_value=self.data) as native:
            result=a.replay(root,Path('/supplied-solc'),Path('/supplied-evm'))
        native.assert_called_once_with(Path('/supplied-solc'),Path('/supplied-evm'))
        self.assertTrue(result['same_engines_replayed'])

    def test_resealed_false_economic_success_rejected(self):
        root=self.bundle();self.reseal(root,'effects.json',lambda r:r.update(monetary_valuation_usd=1000000))
        with patch.object(e,'execute',return_value=self.data),self.assertRaisesRegex(a.EffectsError,'REPLAY_MISMATCH'):
            a.replay(root,Path('solc'),Path('evm'))

    def test_resealed_tentative_transfer_rejected(self):
        root=self.bundle()
        self.reseal(root,'effects.json',lambda r:r['cases']['delayed_credit']['journal'][3].update(applied_transfer_units='4'))
        with patch.object(e,'execute',return_value=self.data),self.assertRaises(a.EffectsError):a.replay(root,Path('s'),Path('e'))

    def test_resealed_native_source_changed_never_executed(self):
        root=self.bundle()
        self.reseal(root,'evm--execution.json',lambda r:r['cases']['conservation'].update(final_state={'debit':0,'credit':100,'steps':3}))
        with patch.object(e,'execute',return_value=self.data) as runner,self.assertRaises(a.EffectsError):a.replay(root,Path('s'),Path('e'))
        runner.assert_called_once_with(Path('s'),Path('e'))

    def test_resealed_audit_event_rejected(self):
        root=self.bundle();self.reseal(root,'audit.json',lambda r:r['events'][1]['data'].update(entry_sha256='0'*64))
        with patch.object(e,'execute',return_value=self.data),self.assertRaises(a.EffectsError):a.replay(root,Path('s'),Path('e'))

    def test_missing_artifact_rejected_before_native_run(self):
        root=self.bundle();(root/'audit.json').unlink()
        with patch.object(e,'execute') as run,self.assertRaises((ValueError,OSError)):a.replay(root,Path('s'),Path('e'))
        run.assert_not_called()

    def test_extra_file_rejected_before_run(self):
        root=self.bundle();(root/'other.txt').write_text('extra')
        with patch.object(e,'execute') as run,self.assertRaises(a.EffectsError):a.replay(root,Path('s'),Path('e'))
        run.assert_not_called()

    def test_boolean_manifest_version_rejected(self):
        root=self.bundle();p=root/'COMPLETE.json';d=strict_json(p.read_bytes());d['schema_version']=True;p.write_bytes(canonical(d))
        with self.assertRaises(a.EffectsError):a.replay(root,Path('s'),Path('e'))

    def test_symlink_root_rejected(self):
        root=self.bundle();link=self.root/'link';link.symlink_to(root,target_is_directory=True)
        with self.assertRaises(a.EffectsError):a.replay(link,Path('s'),Path('e'))

    def test_create_no_overwrite_and_no_output_on_native_failure(self):
        root=self.bundle()
        with self.assertRaises(a.EffectsError):a.create(Path('s'),Path('e'),root)
        with patch.object(e,'execute',side_effect=ValueError('missing')),self.assertRaises(ValueError):
            a.create(Path('s'),Path('e'),self.root/'failed')
        self.assertFalse((self.root/'failed').exists())

    def test_create_permissions_and_original_outputs_preserved(self):
        out=self.root/'new'
        with patch.object(e,'execute',return_value=self.data):result=a.create(Path('s'),Path('e'),out)
        self.assertFalse(result['same_engines_replayed'])
        self.assertEqual(out.stat().st_mode & 0o777,0o700)
        for p in out.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)
        self.assertEqual(strict_json((out/'evm--execution.json').read_bytes()),self.data)

    def test_no_success_when_native_binary_missing(self):
        with redirect_stdout(io.StringIO()) as out:
            code=a.main(['run-evm-accounting','--solc','/missing','--evm','/missing','--out',str(self.root/'blocked')])
        self.assertEqual(code,2);self.assertEqual(json.loads(out.getvalue())['status'],'EVM_ACCOUNTING_BLOCKED')
        self.assertFalse((self.root/'blocked').exists())

    def test_no_rpc_target_or_payload_arguments(self):
        for arg in ('--rpc','--target','--source','--calldata'):
            with self.subTest(arg=arg),redirect_stderr(io.StringIO()) as err,self.assertRaises(SystemExit):
                a.main(['run-evm-accounting','--solc','x','--evm','x','--out','x',arg,'PRIVATE_VALUE'])
            self.assertNotIn('PRIVATE_VALUE',err.getvalue())

    def test_package_cli_is_connected(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','run-evm-accounting','--solc','/missing','--evm','/missing','--out',str(self.root/'c')]),redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),2)

    def test_quality_dependency_and_mandatory_tests_present(self):
        self.assertIn('accounting',quality.COMPONENTS['evm_accounting']['depends'])
        self.assertIn('evm_execution',quality.COMPONENTS['evm_accounting']['depends'])
        self.assertIn('test_evm_accounting.CommittedEffectsTests.test_reverts_contribute_no_transfers',quality.REQUIRED_TESTS)
        self.assertIn('tests/fixtures/evm_accounting_capture.json',quality.source_snapshot())


if __name__=='__main__':unittest.main()
