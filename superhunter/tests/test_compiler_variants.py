"""Differential checks with a captured REAL native run of fixed own controls.

Mocks explicitly isolate pipeline orchestration. Reading a capture or using a
mock is NOT a fresh compilation/EVM execution; separate native CLI acceptance
must run outside this unit suite. No target or arbitrary Solidity is executed.
"""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import compiler_variants as v, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

FIXTURE = Path(__file__).parent / 'fixtures/compiler_variant_capture.json'
AT = '2026-11-05T23:00:00+00:00'


class CompilerVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture = strict_json(FIXTURE.read_bytes())

    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.base = deepcopy(self.capture['baseline'])
        self.variants = deepcopy(self.capture['variants'])
        self.acceptance = self.root / 'native-acceptance'
        self.out = self.root / 'variants'
        self.solc, self.evm = self.root / 'solc', self.root / 'evm'

    def analyze(self):
        return v.analyze(self.base, self.variants)

    def item(self, name='conservation', profile='ir_optimized'):
        return self.variants[name][profile]

    def edit_output(self, fn, **selection):
        item = self.item(**selection)
        raw = strict_json(item['build']['output_utf8'])
        contract = raw['contracts'][v.builds.SOURCE_FILE][v.builds.CONTRACT]
        fn(contract)
        item['build']['output_utf8'] = canonical(raw).decode()

    def source(self):
        return v.sha(canonical(quality.source_snapshot()))

    def doubles(self):
        """Explicit fake acceptance and replay, not evidence of native execution."""
        stack = ExitStack(); self.addCleanup(stack.close)
        fake = {'status': 'FIXED_NATIVE_PLATFORM_REVIEW_PASS',
                'evidence_sha256': {'native': {'evm--execution.json': v.sha(canonical(self.base))}},
                'native_controls': {'execution_sha256': v.sha(canonical(self.base))}}
        self.baseline_call = stack.enter_context(patch.object(v, '_baseline', return_value=(self.base, fake)))
        self.variant_call = stack.enter_context(patch.object(v, 'compile_variants', return_value=self.variants))
        stack.enter_context(patch.object(v.joint, '_inputs', return_value=fake['evidence_sha256']))
        return fake

    def create(self):
        return v.create(self.acceptance, self.solc, self.evm, self.source(), self.out)

    def replay(self):
        return v.replay(self.out, self.acceptance, self.solc, self.evm, self.source())

    def reseal(self, name, fn):
        p = self.out/name
        value = strict_json(p.read_bytes());fn(value)
        raw = canonical(value);p.write_bytes(raw)
        marker = strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = v.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_committed_states_and_reverts_agree(self):
        r = self.analyze()
        self.assertEqual((r['controls'],r['profile_count'],r['constructors'],r['message_calls']),(3,3,9,54))
        self.assertEqual(r['cross_profile_observation_pairs'],42)
        self.assertEqual(r['outcomes'],{'COMMITTED':15,'PRECONDITION_REVERT':24,'ASSERTION_REVERT':6,'RESOURCE_EXHAUSTED':9})
        self.assertEqual({p['applied_units'] for p in r['cases']['delayed_credit']['profiles'].values()},{'5'})
        for c in r['cases'].values():
            self.assertEqual(c['distinct_runtimes'],3)
            self.assertTrue(c['same_observed_behavior'])

    def test_different_bytecode_is_not_behavior_disagreement(self):
        r = self.analyze()['cases']['conservation']['profiles']
        self.assertEqual([r[p]['runtime_bytes'] for p in v.PROFILES],[821,592,409])
        self.assertEqual(len({x['observable_sha256'] for x in r.values()}),1)
        self.assertEqual(len({x['runtime_sha256'] for x in r.values()}),3)

    def test_no_universal_independence_or_gas_equivalence_claim(self):
        r=self.analyze()
        for k in ('all_paths_proved','gas_cost_equivalence_proved','independent_compiler_used','independent_evm_used',
                  'formal_proof_transferred_to_optimized_bytecode'):
            self.assertIs(r[k],False)
        for c in r['cases'].values():
            for p in c['profiles'].values():self.assertIsNone(p['monetary_value_usd'])

    def test_profiles_change_only_explicit_compilation_options(self):
        for n in v.builds.formal.NAMES:
            base=v.build_input(n,v.PROFILES[0])
            for profile in v.PROFILES[1:]:
                other=v.build_input(n,profile)
                self.assertEqual(other['sources'],base['sources'])
                changed={k for k in set(base['settings'])|set(other['settings'])
                         if base['settings'].get(k)!=other['settings'].get(k)}
                self.assertEqual(changed,{'optimizer','viaIR'} if profile=='ir_optimized' else {'optimizer'})

    def test_build_input_returns_independent_copy(self):
        a=v.build_input('conservation','ir_optimized');a['settings']['optimizer']['runs']=1
        self.assertEqual(v.build_input('conservation','ir_optimized')['settings']['optimizer']['runs'],200)

    def test_arbitrary_profile_or_control_rejected(self):
        for name,p in [('other','ir_optimized'),('conservation','custom'),('conservation',True)]:
            with self.subTest(n=name,p=p), self.assertRaises(ValueError):v.build_input(name,p)

    def test_changed_source_cannot_pose_as_another_optimization(self):
        self.item()['build']['input']['sources']['State.sol']['content']+='// different source\n'
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):self.analyze()

    def test_optimizer_runs_must_match_fixed_profile(self):
        self.item()['build']['input']['settings']['optimizer']['runs']=1000
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):self.analyze()

    def test_missing_control_rejected(self):
        del self.variants['unreachable']
        with self.assertRaisesRegex(ValueError,'CONTROL_COVERAGE'):self.analyze()

    def test_missing_profile_rejected(self):
        del self.variants['conservation']['ir_optimized']
        with self.assertRaisesRegex(ValueError,'PROFILE_COVERAGE'):self.analyze()

    def test_extra_profile_rejected(self):
        self.variants['conservation']['custom']=deepcopy(self.item())
        with self.assertRaisesRegex(ValueError,'PROFILE_COVERAGE'):self.analyze()

    def test_metadata_cannot_claim_other_pipeline(self):
        def change(c):
            m=strict_json(c['metadata']);m['settings']['viaIR']=False;c['metadata']=canonical(m).decode()
        self.edit_output(change)
        with self.assertRaisesRegex(ValueError,'METADATA_PROFILE'):self.analyze()

    def test_numeric_via_ir_not_boolean(self):
        def change(c):
            m=strict_json(c['metadata']);m['settings']['viaIR']=1;c['metadata']=canonical(m).decode()
        self.edit_output(change)
        with self.assertRaisesRegex(ValueError,'METADATA_PROFILE'):self.analyze()

    def test_metadata_sources_not_substituted(self):
        def change(c):
            m=strict_json(c['metadata']);m['sources']['State.sol']['keccak256']='0x'+'0'*64;c['metadata']=canonical(m).decode()
        self.edit_output(change)
        with self.assertRaisesRegex(ValueError,'METADATA_SOURCE'):self.analyze()

    def test_compilation_failure_not_clean_result(self):
        x=self.item()['build'];raw=strict_json(x['output_utf8']);raw.setdefault('errors',[]).append({'severity':'error'})
        x['output_utf8']=canonical(raw).decode()
        with self.assertRaisesRegex(ValueError,'COMPILATION_FAILED'):self.analyze()

    def test_compiler_stderr_not_silently_dropped(self):
        self.item()['build']['stderr_utf8']='PRIVATE_CONTROL'
        with self.assertRaisesRegex(ValueError,'OUTPUT_REQUIRED'):self.analyze()

    def test_abi_substitution_rejected(self):
        self.edit_output(lambda c:c['abi'][0].update(name='other'))
        with self.assertRaisesRegex(ValueError,'ABI_OR_LAYOUT'):self.analyze()

    def test_unresolved_link_rejected(self):
        self.edit_output(lambda c:c['evm']['bytecode']['linkReferences'].update({'Other':[]}))
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_LINKS'):self.analyze()

    def test_layout_change_rejected(self):
        self.edit_output(lambda c:c['storageLayout']['storage'][0].update(slot='1'))
        with self.assertRaisesRegex(ValueError,'ABI_OR_LAYOUT'):self.analyze()

    def test_selector_change_rejected(self):
        self.edit_output(lambda c:c['evm']['methodIdentifiers'].update({'move(uint8)':'00000000'}))
        with self.assertRaisesRegex(ValueError,'SELECTOR_CHANGED'):self.analyze()

    def test_runtime_must_come_from_its_constructor(self):
        self.edit_output(lambda c:c['evm']['deployedBytecode'].update(object='00'))
        with self.assertRaisesRegex(ValueError,'CONSTRUCTOR_RESULT'):self.analyze()

    def test_changed_cached_observation_cannot_override_stdout(self):
        self.item()['execution']['calls'][0]['execution']['observed']['return_data']='0x00'
        with self.assertRaisesRegex(ValueError,'OBSERVATION_NOT_FROM_STDOUT'):self.analyze()

    def test_reference_cannot_claim_reverted_credit_persisted(self):
        self.item('delayed_credit')['execution']['calls'][3]['reference']['state']['credit']=10
        with self.assertRaisesRegex(ValueError,'FALSE_REFERENCE'):self.analyze()

    def test_missing_message_call_rejected(self):
        self.item()['execution']['calls'].pop()
        with self.assertRaisesRegex(ValueError,'CALL_COVERAGE'):self.analyze()

    def test_call_order_must_be_identical(self):
        a=self.item()['execution']['calls'];a[0],a[1]=a[1],a[0]
        with self.assertRaisesRegex(ValueError,'CALL_ORDER'):self.analyze()

    def test_gas_limit_must_match_not_just_label(self):
        self.item()['execution']['calls'][-1]['execution']['gas_limit']=v.evm.GAS
        with self.assertRaisesRegex(ValueError,'EXECUTION_BINDING'):self.analyze()

    def test_case_formal_status_cannot_be_promoted(self):
        self.item('delayed_credit')['execution']['source_property_status']='STATEFUL_PROPERTY_PROVED_IN_FIXED_MODEL'
        with self.assertRaisesRegex(ValueError,'FALSE_FORMAL_BINDING'):self.analyze()

    def test_cross_profile_disagreement_is_fail_closed(self):
        original=v.observable_trace
        calls=[0]
        def inconsistent(row):
            calls[0]+=1;r=original(row)
            if calls[0]==3:r['calls'][0]['return_data']='0x00'
            return r
        with patch.object(v,'observable_trace',side_effect=inconsistent),self.assertRaisesRegex(ValueError,'BEHAVIOR_DISAGREEMENT'):
            self.analyze()

    def test_accounting_disagreement_cannot_be_ignored(self):
        with patch.object(v.accounting,'reconcile_internal_units',return_value={'status':'INCONSISTENT'}),self.assertRaisesRegex(ValueError,'UNITS_MISMATCH'):
            self.analyze()

    def test_source_reference_checked_before_native_work(self):
        self.doubles()
        with self.assertRaisesRegex(ValueError,'EXTERNAL_SOURCE'):v.execute(self.acceptance,self.solc,self.evm,'0'*64)
        self.baseline_call.assert_not_called();self.variant_call.assert_not_called()

    def test_invalid_native_acceptance_prevents_alternate_execution(self):
        self.doubles();self.baseline_call.side_effect=ValueError('NATIVE_ACCEPTANCE_REJECTED')
        with self.assertRaises(ValueError):self.create()
        self.variant_call.assert_not_called();self.assertFalse(self.out.exists())

    def test_baseline_replay_is_actually_requested(self):
        raw=canonical(self.base);(self.acceptance/'native').mkdir(parents=True)
        (self.acceptance/'native/evm--execution.json').write_bytes(raw)
        accepted={'status':'FIXED_NATIVE_PLATFORM_REVIEW_PASS','evidence_sha256':{'native':{'evm--execution.json':v.sha(raw)}},
                  'native_controls':{'execution_sha256':v.sha(raw)}}
        with patch.object(v.joint,'verify',return_value=accepted) as verify:
            actual,_=v._baseline(self.acceptance,self.solc,self.evm,self.source())
        self.assertEqual(actual,self.base);verify.assert_called_once()

    def test_baseline_changed_after_replay_rejected(self):
        raw=canonical(self.base);(self.acceptance/'native').mkdir(parents=True)
        (self.acceptance/'native/evm--execution.json').write_bytes(raw)
        accepted={'status':'FIXED_NATIVE_PLATFORM_REVIEW_PASS','evidence_sha256':{'native':{'evm--execution.json':'0'*64}},
                  'native_controls':{'execution_sha256':v.sha(raw)}}
        with patch.object(v.joint,'verify',return_value=accepted),self.assertRaisesRegex(ValueError,'BASE_CHANGED'):
            v._baseline(self.acceptance,self.solc,self.evm,self.source())

    def test_receipt_roundtrip_runs_each_stage_again(self):
        self.doubles();first=self.create();second=self.replay()
        self.assertEqual(first,second)
        self.assertEqual(self.baseline_call.call_count,2);self.assertEqual(self.variant_call.call_count,2)
        self.assertFalse(first['qa_tests_reexecuted_here']);self.assertFalse(first['vulnerability_confirmed'])

    def test_replay_never_executes_supplied_variant_input(self):
        self.doubles();self.create()
        self.reseal('variants.json',lambda d:d['variants']['conservation']['ir_optimized']['build']['input']['sources']['State.sol'].update(content='MUST_NOT_EXECUTE'))
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.replay()
        call=self.variant_call.call_args.args
        self.assertEqual(call,(self.base,self.solc,self.evm))
        self.assertNotIn('MUST_NOT_EXECUTE',str(call))

    def test_resealed_favorable_summary_rejected(self):
        self.doubles();self.create()
        self.reseal('comparison.json',lambda d:d.update(independent_evm_used=True))
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.replay()

    def test_resealed_audit_rejected(self):
        self.doubles();self.create()
        self.reseal('audit.json',lambda d:d['events'][0]['data'].update(source_digest='0'*64))
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.replay()

    def test_extra_bundle_file_and_missing_marker_rejected(self):
        self.doubles();self.create();(self.out/'extra').write_text('untracked')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):self.replay()
        (self.out/'extra').unlink();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):self.replay()

    def test_bundle_permissions_and_no_overwrite(self):
        self.doubles();self.create()
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'NEW_SEPARATE_OUTPUT'):self.create()
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_source_or_base_drift_during_execution_rejected(self):
        self.doubles()
        with patch.object(v.joint,'_inputs',return_value={'changed':True}),self.assertRaisesRegex(ValueError,'CHANGED_DURING'):
            self.create()
        self.assertFalse(self.out.exists())

    def test_component_and_capture_are_bound_to_quality(self):
        snapshot=quality.source_snapshot()
        self.assertIn('tests/fixtures/compiler_variant_capture.json',snapshot)
        self.assertEqual(quality.validate_components(snapshot),[])
        self.assertIn('native_platform',quality.COMPONENTS['compiler_variants']['depends'])

    def test_cli_dispatch_and_error_privacy(self):
        from superhunter import __main__
        self.doubles()
        args=['review-compiler-variants','--out',str(self.out),'--acceptance',str(self.acceptance),
              '--solc',str(self.solc),'--evm',str(self.evm),'--expected-source',self.source()]
        with patch('sys.argv',['superhunter',*args]),redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(__main__.main(),0)
        self.assertEqual(json.loads(stream.getvalue())['message_calls'],54)
        with redirect_stderr(io.StringIO()) as stderr,self.assertRaises(SystemExit):
            v.main(args+['--target','PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE',stderr.getvalue())
        self.baseline_call.side_effect=ValueError('PRIVATE_VALUE')
        with redirect_stdout(io.StringIO()) as stream:
            args[2]=str(self.root/'new-out');self.assertEqual(v.main(args),2)
        self.assertNotIn('PRIVATE_VALUE',stream.getvalue())


if __name__=='__main__':
    unittest.main()
