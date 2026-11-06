"""Controls for bounded native EVM corpus; synthetic fixtures/mocks are explicit.

Actual solc + Geth acceptance is run separately by the CLI, not inferred from
these unit tests. No third-party target is scanned or executed here.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_sequence_fuzz as fuzz
from superhunter import compiler_variants as variants, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

FIXTURE = Path(__file__).parent / 'fixtures/compiler_variant_capture.json'


class EVMSequenceFuzzTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.out=self.root/'case'
        self.solc=self.root/'missing-solc'
        self.evm=self.root/'missing-evm'
        self.seed=20261105
        self.size=12

    def test_first_corpus_reaches_third_step(self):
        sequences=fuzz.corpus(self.seed,12)
        self.assertEqual([q for q,gas in sequences[0]],[0,0,0,0])
        for case in sequences:
            s={'debit':15,'credit':0,'steps':0}
            statuses=[]
            for q,g in case:
                r=fuzz.independent_oracle('delayed_credit',s,q,g)
                statuses.append(r['status']);s=r['state']
            if case==sequences[0]:
                self.assertIn('ASSERTION_REVERT', statuses)

    def test_oracle_crosschecks_existing_reference(self):
        for name in fuzz.builds.formal.NAMES:
            for pre in range(4):
                for debit in (0,1,5,15):
                    s={'debit':debit,'credit':15-debit,'steps':pre}
                    for q in (0,1,15,16,255):
                        for gas in (fuzz.evm.GAS,1):
                            with self.subTest(name=name,pre=pre,q=q,gas=gas):
                                a=fuzz.verify_oracles(name,s,q,gas)
                                self.assertEqual(set(a),{'state','status','return_data','error'})

    def test_compiler_and_native_disagreement_rejected(self):
        capture=strict_json(FIXTURE.read_bytes())
        baseline=capture['baseline']
        sample=baseline['builds']['cases']['conservation']['output_utf8']
        contract=strict_json(sample)['contracts'][variants.builds.SOURCE_FILE][variants.builds.CONTRACT]
        row=baseline['cases']['conservation']
        # Genuine archived outputs, used as fixed unit fixtures, are NOT newly executed.
        with patch.object(fuzz.evm,'_run', side_effect=[row['constructor'],row['calls'][0]['execution']]):
            with self.assertRaisesRegex(fuzz.SequenceFuzzError,'NATIVE_EVM_ORACLE_DISAGREEMENT'):
                fuzz._run_profile('conservation','legacy_unoptimized',contract,b'dummy',
                                  fuzz.corpus(self.seed,9)[:1])

    def test_resealed_favorable_bundle_rejected(self):
        run=self._synthetic_run()
        files=fuzz.documents(run,'2026-11-05T00:00:00+00:00')
        write_new_bundle(self.out,files)
        with patch.object(fuzz,'execute',return_value=run):
            self.assertEqual(fuzz.replay(self.out,self.solc,self.evm,run['source_digest'])['status'],
                             'BOUNDED_NATIVE_SEQUENCE_FUZZ_PASS')
            result=strict_json((self.out/'result.json').read_bytes())
            result['vulnerability_confirmed']=True
            raw=canonical(result);(self.out/'result.json').write_bytes(raw)
            marker=strict_json((self.out/'COMPLETE.json').read_bytes())
            marker['sha256']['result.json']=hashlib.sha256(raw).hexdigest()
            (self.out/'COMPLETE.json').write_bytes(canonical(marker))
            with self.assertRaisesRegex(fuzz.SequenceFuzzError,'NATIVE_REPLAY_DISAGREEMENT'):
                fuzz.replay(self.out,self.solc,self.evm,run['source_digest'])

    def _synthetic_run(self):
        # Tiny unit fixture for audit/document serializer tests only; not native evidence.
        return {'schema_version':1,'profile':fuzz.PROFILE,'seed':self.seed,'cases_per_control':12,
                'source_digest':'a'*64,'executions':192,'constructor_executions':4,
                'controls':{},'outcomes':{},'sequences':[],
                'different_codegen_observations_agree':True,
                'unseen_state_space_proved_safe':False,'vulnerability_confirmed':False,
                'independent_evm_used':False,'network_used':False}

    def test_finite_generator_stable(self):
        self.assertEqual(fuzz.corpus(self.seed,24),fuzz.corpus(self.seed,24))

    def test_seed_changes_mutation_suffix(self):
        self.assertNotEqual(fuzz.corpus(1,24)[9:],fuzz.corpus(2,24)[9:])

    def test_seed_does_not_change_boundary_cases(self):
        self.assertEqual(fuzz.corpus(1,12)[:9],fuzz.corpus(2,12)[:9])

    def test_prefix_property(self):
        self.assertEqual(fuzz.corpus(self.seed,12),fuzz.corpus(self.seed,24)[:12])

    def test_bounded_minimum(self):
        self.assertEqual(len(fuzz.corpus(0,fuzz.MIN_CASES)),fuzz.MIN_CASES)

    def test_bounded_maximum(self):
        self.assertEqual(len(fuzz.corpus(2**64-1,fuzz.MAX_CASES)),fuzz.MAX_CASES)

    def test_sequences_unique(self):
        seq=fuzz.corpus(self.seed,24)
        self.assertEqual(len(seq),len({canonical(x) for x in seq}))

    def test_exact_four_steps(self):
        self.assertTrue(all(len(x)==4 for x in fuzz.corpus(self.seed,24)))

    def test_quantity_uint8(self):
        self.assertTrue(all(type(q) is int and 0 <= q <= 255
                            for c in fuzz.corpus(self.seed,24) for q,g in c))

    def test_only_two_gas_profiles(self):
        self.assertEqual({g for c in fuzz.corpus(self.seed,24) for q,g in c},{1,fuzz.evm.GAS})

    def test_boolean_seed_rejected(self):
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'SEED_UINT64_REQUIRED'):
            fuzz.corpus(True,12)

    def test_boolean_case_budget_rejected(self):
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'CASE_BUDGET'):
            fuzz.corpus(0,True)

    def test_negative_and_overflow_seed_rejected(self):
        for seed in (-1,2**64,'a'):
            with self.subTest(seed=seed),self.assertRaises(fuzz.SequenceFuzzError):
                fuzz.corpus(seed,12)

    def test_outside_case_budget_rejected(self):
        for cases in (0,1,8,25,1024,12.0):
            with self.subTest(cases=cases),self.assertRaises(fuzz.SequenceFuzzError):
                fuzz.corpus(self.seed,cases)

    def test_oracle_returns_new_state_without_modifying_input(self):
        state={'debit':15,'credit':0,'steps':0};before=deepcopy(state)
        out=fuzz.independent_oracle('conservation',state,5,fuzz.evm.GAS)
        self.assertEqual(out['state'],{'debit':10,'credit':5,'steps':1})
        self.assertEqual(state,before)

    def test_reverted_assertion_never_commits(self):
        state={'debit':11,'credit':4,'steps':2}
        out=fuzz.independent_oracle('delayed_credit',state,2,fuzz.evm.GAS)
        self.assertEqual(out['status'],'ASSERTION_REVERT')
        self.assertEqual(out['state'],state)
        self.assertEqual(out['return_data'],fuzz.evm.PANIC_ASSERT)

    def test_gas_exhaustion_never_commits(self):
        s={'debit':15,'credit':0,'steps':0}
        self.assertEqual(fuzz.independent_oracle('conservation',s,0,1)['state'],s)

    def test_fourth_call_reverted(self):
        state={'debit':13,'credit':2,'steps':3}
        out=fuzz.independent_oracle('conservation',state,1,fuzz.evm.GAS)
        self.assertEqual((out['status'],out['state']),('PRECONDITION_REVERT',state))

    def test_unreachable_guard_not_proven_safe(self):
        for q in (0,10,255):
            x=fuzz.independent_oracle('unreachable',{'debit':15,'credit':0,'steps':0},q,fuzz.evm.GAS)
            self.assertEqual(x['status'],'PRECONDITION_REVERT')

    def test_unknown_control_rejected(self):
        with self.assertRaises(fuzz.SequenceFuzzError):
            fuzz.independent_oracle('external',{'debit':15,'credit':0,'steps':0},1,fuzz.evm.GAS)

    def test_float_quantity_rejected(self):
        with self.assertRaises(fuzz.SequenceFuzzError):
            fuzz.independent_oracle('conservation',{'debit':15,'credit':0,'steps':0},1.0,fuzz.evm.GAS)

    def test_boolean_quantity_rejected(self):
        with self.assertRaises(fuzz.SequenceFuzzError):
            fuzz.independent_oracle('conservation',{'debit':15,'credit':0,'steps':0},True,fuzz.evm.GAS)

    def test_invalid_state_rejected(self):
        with self.assertRaises(fuzz.SequenceFuzzError):
            fuzz.independent_oracle('conservation',{'debit':15,'credit':0},1,fuzz.evm.GAS)

    def test_different_gas_not_silently_interchangeable(self):
        s={'debit':15,'credit':0,'steps':0}
        self.assertNotEqual(fuzz.independent_oracle('conservation',s,1,1)['status'],
                            fuzz.independent_oracle('conservation',s,1,fuzz.evm.GAS)['status'])

    def test_oracle_disagreement_is_a_blocker(self):
        with patch.object(fuzz.evm,'reference',return_value={'status':'COMMITTED','state':{'debit':15,'credit':0,'steps':0},
                        'return_data':'0x','error':None}):
            with self.assertRaisesRegex(fuzz.SequenceFuzzError,'INDEPENDENT_ORACLE_DISAGREEMENT'):
                fuzz.verify_oracles('delayed_credit',{'debit':10,'credit':5,'steps':2},0,fuzz.evm.GAS)

    def test_observable_profile_mismatch_detectable(self):
        row={'runs':[{'steps':[{'outcome':'COMMITTED','state_after':{'debit':14},'return_data':'0x','error':None}]}]}
        x=fuzz._behavior(row)
        row['runs'][0]['steps'][0]['state_after']={'debit':13}
        self.assertNotEqual(x,fuzz._behavior(row))

    def test_document_is_not_security_certification(self):
        data=fuzz.documents(self._synthetic_run(),'2026-11-05T00:00:00+00:00')
        result=strict_json(data['result.json'])
        self.assertFalse(result['vulnerability_confirmed'])
        self.assertFalse(result['unseen_state_space_proved_safe']) if 'unseen_state_space_proved_safe' in result else None
        self.assertFalse('SAFE_ALL_CONTRACTS' in data['REVIEW.md'].decode())

    def test_audit_binds_document_result(self):
        data=fuzz.documents(self._synthetic_run(),'2026-11-05T00:00:00+00:00')
        audit=strict_json(data['audit.json'])['entries']
        self.assertEqual(audit[-1]['event'],'fuzz.evm.complete')
        self.assertEqual(audit[-1]['data']['result_sha256'],fuzz.sha(data['result.json']))

    def test_missing_binary_blocked_before_any_execution(self):
        wrong='0'*64
        with patch.object(fuzz.compiler,'read_pinned_binary',side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(fuzz.SequenceFuzzError,'SOURCE_IDENTITY_MISMATCH'):
                fuzz.execute(self.solc,self.evm,self.seed,12,wrong)

    def test_external_reference_required(self):
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'EXTERNAL_SOURCE_DIGEST_REQUIRED'):
            fuzz.execute(self.solc,self.evm,self.seed,12,'not-hash')

    def test_no_symlink_output(self):
        self.out.symlink_to(self.root/'other')
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'NEW_PRIVATE_OUTPUT_REQUIRED'):
            fuzz.create(self.solc,self.evm,self.seed,12,'a'*64,self.out)

    def test_no_overwrite(self):
        self.out.mkdir()
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'NEW_PRIVATE_OUTPUT_REQUIRED'):
            fuzz.create(self.solc,self.evm,self.seed,12,'a'*64,self.out)

    def test_replay_requires_external_identity(self):
        run=self._synthetic_run();write_new_bundle(self.out,fuzz.documents(run,'2026-11-05T00:00:00+00:00'))
        with patch.object(fuzz,'execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(fuzz.SequenceFuzzError,'EXTERNAL_CODE_REFERENCE_MISMATCH'):
                fuzz.replay(self.out,self.solc,self.evm,'b'*64)

    def test_replay_ignores_unauthorized_extra_files(self):
        run=self._synthetic_run();write_new_bundle(self.out,fuzz.documents(run,'2026-11-05T00:00:00+00:00'))
        (self.out/'unknown').write_bytes(b'unsafe')
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'BUNDLE_INVENTORY'):
            fuzz.replay(self.out,self.solc,self.evm,'a'*64)

    def test_replay_rejects_original_file_tamper(self):
        run=self._synthetic_run();write_new_bundle(self.out,fuzz.documents(run,'2026-11-05T00:00:00+00:00'))
        (self.out/'REVIEW.md').write_bytes(b'altered')
        with self.assertRaisesRegex(fuzz.SequenceFuzzError,'BUNDLE_DIGEST'):
            fuzz.replay(self.out,self.solc,self.evm,'a'*64)

    def test_replay_does_not_execute_supplied_inputs(self):
        run=self._synthetic_run();write_new_bundle(self.out,fuzz.documents(run,'2026-11-05T00:00:00+00:00'))
        with patch.object(fuzz,'execute',return_value=run) as new_execute:
            fuzz.replay(self.out,self.solc,self.evm,'a'*64)
        new_execute.assert_called_once_with(self.solc,self.evm,self.seed,12,'a'*64)

    def test_cli_missing_sources_no_sensitive_echo(self):
        with redirect_stdout(io.StringIO()) as out:
            exit_code=fuzz.main(['replay-owned-evm','--bundle',str(self.root/'PRIVATE_SECRET'),
                    '--solc',str(self.solc),'--evm',str(self.evm),'--expected-source','a'*64])
        self.assertEqual(exit_code,2)
        self.assertNotIn('PRIVATE_SECRET',out.getvalue())

    def test_no_existing_source_modified_by_pure_oracles(self):
        a=fuzz.quality.source_snapshot()
        fuzz.corpus(self.seed,24)
        fuzz.independent_oracle('conservation',{'debit':15,'credit':0,'steps':0},3,fuzz.evm.GAS)
        self.assertEqual(a,fuzz.quality.source_snapshot())


if __name__=='__main__':unittest.main()
