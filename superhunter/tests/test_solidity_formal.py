"""Bounded formal controls: unit/parser tests plus real installed-Z3 checks.

Compiler captures are labeled fixtures. Native compiler acceptance runs outside
this suite and never borrows these mocked executions as proof of compilation.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import formal_captures
from superhunter import solidity_formal as f, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

AT = '2026-11-05T17:00:00+00:00'


class SolidityFormalTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(); self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.capture = deepcopy(formal_captures.CAPTURE)
        self.property = self.capture['cases']['conservation']['runs']['property']
        self.false = self.capture['cases']['off_by_one']['runs']['property']
        self.query = next(iter(self.property['queries'].values()))

    def bundle(self):
        out = self.root/'case'
        write_new_bundle(out, f._documents(self.capture, produced_at=AT))
        return out

    def reseal(self, root, name, change):
        data = strict_json((root/name).read_bytes()); change(data)
        raw = canonical(data); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = f.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_controls_restricted_to_own_sources(self):
        for name in f.NAMES:
            src = f.control_source(name, 'property')
            self.assertIn('public pure', src)
            self.assertNotIn('import ', src)
            self.assertEqual(src.count('assert('), 1)
        with self.assertRaises(f.FormalError): f.control_source('arbitrary', 'property')
        with self.assertRaises(f.FormalError): f.control_source('conservation', 'other')

    def test_bad_control_diff_is_one_literal(self):
        a = f.control_source('conservation', 'property')
        b = f.control_source('off_by_one', 'property')
        self.assertEqual(a.replace('+ 0;', '+ 1;'), b)

    def test_feasibility_preserves_body_and_guards(self):
        for name in f.NAMES:
            a, b = (f.control_source(name, role) for role in f.ROLES)
            self.assertEqual(a.split('assert(')[0], b.split('assert(')[0])
            self.assertIn('assert(false)', b)

    def test_exhaustive_counts_are_exact(self):
        a, b, u = (f.reference(name) for name in f.NAMES)
        self.assertEqual((a['enumerated_input_tuples'], a['feasible_input_tuples'], a['violating_input_tuples']), (4096, 2176, 0))
        self.assertEqual((b['feasible_input_tuples'], b['violating_input_tuples']), (2176, 2176))
        self.assertEqual(u['feasible_input_tuples'], 0)

    def test_fixed_compiler_profile(self):
        inp = f.fixed_input('conservation','property')
        self.assertEqual(inp['settings']['modelChecker']['solvers'], ['smtlib2'])
        self.assertEqual(inp['settings']['modelChecker']['targets'], ['assert'])
        self.assertEqual(set(inp['sources']), {'Control.sol'})
        self.assertNotIn('auxiliaryInput',inp)

    def test_caller_responses_not_modified(self):
        r = {'0x'+'a'*64:'unsat\n'}
        inp = f.fixed_input('conservation','property',r)
        r.clear()
        self.assertEqual(len(inp['auxiliaryInput']['smtlib2responses']),1)

    def test_unsupported_response_key_rejected(self):
        with self.assertRaises(f.FormalError): f.fixed_input('conservation','property',{'bad':'sat'})

    def test_query_must_have_one_check(self):
        with self.assertRaises(f.FormalError): f.split_query(self.query+'(check-sat)\n')

    def test_query_commands_cannot_be_extended(self):
        with self.assertRaises(f.FormalError): f.split_query(self.query+'(exit)\n')
        with self.assertRaises(f.FormalError): f.split_query(self.query.replace('(set-logic ALL)', '(reset)\n(set-logic ALL)'))

    def test_query_size_bound(self):
        with patch.object(f,'MAX_QUERY',1),self.assertRaises(f.FormalError): f.split_query(self.query)

    def test_wrong_query_prefix_rejected(self):
        with self.assertRaises(f.FormalError): f.split_query('(set-logic ALL)\n(check-sat)\n')

    def test_real_z3_answers_unsat_from_compiler_capture(self):
        result=f.solve_compiler_query(self.query,budget='normal')
        self.assertEqual(result['status'],'UNSAT')
        self.assertEqual(result['response'],'unsat\n')
        self.assertEqual(result['query_sha256'],f.sha(self.query.encode()))

    def test_real_z3_counterexample_is_checked_concretely(self):
        query=next(iter(self.false['queries'].values()))
        result=f.solve_compiler_query(query,budget='normal')
        self.assertEqual(result['status'],'SAT')
        witness=f.model_values(query,result['response'])
        f.check_witness('off_by_one','property',witness)
        self.assertNotEqual(witness['finalDebit']+witness['finalCredit'],witness['debit']+witness['credit'])

    def test_real_z3_resource_exhaustion_is_unknown(self):
        result=f.solve_compiler_query(self.query,budget='exhausted')
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['response'].strip(),'unknown')

    def test_missing_solver_is_not_a_proof(self):
        with patch.object(f.smt_backend,'_open_library',side_effect=f.smt_backend.SolverError('absent')):
            with self.assertRaises(ValueError): f.solve_compiler_query(self.query,budget='normal')

    def test_unknown_budget_rejected(self):
        with self.assertRaises(f.FormalError): f.solve_compiler_query(self.query,budget='unlimited')

    def test_no_warning_is_not_proof(self):
        with self.assertRaisesRegex(f.FormalError,'EXPLICIT_TARGET'):
            f.classify_target('conservation','property',{'errors':[]})

    def test_solver_unavailable_warning_blocks_success(self):
        output=strict_json(self.property['initial_output_utf8'])
        with self.assertRaises(f.FormalError): f.classify_target('conservation','property',output)

    def test_explicit_safe_diagnostic_has_expected_location(self):
        output=strict_json(self.property['final_output_utf8'])
        self.assertEqual(f.classify_target('conservation','property',output),'UNSAT')
        output['errors'][0]['sourceLocation']['start']+=1
        with self.assertRaisesRegex(f.FormalError,'LOCATION'): f.classify_target('conservation','property',output)

    def test_duplicate_target_diagnostic_rejected(self):
        output=strict_json(self.property['final_output_utf8']);output['errors']*=2
        with self.assertRaises(f.FormalError): f.classify_target('conservation','property',output)

    def test_unknown_warning_not_silently_discarded(self):
        output=strict_json(self.property['final_output_utf8'])
        output['errors'].append({'errorCode':'99999','severity':'warning','message':'unsupported'})
        with self.assertRaises(f.FormalError): f.classify_target('conservation','property',output)

    def test_compilation_error_even_with_ast_is_failure(self):
        output=strict_json(self.property['initial_output_utf8'])
        output['errors'].append({'severity':'error'})
        with self.assertRaisesRegex(f.FormalError,'COMPILATION_FAILED'): f._read_output(canonical(output))

    def test_missing_ast_rejected(self):
        with self.assertRaisesRegex(f.FormalError,'AST'): f._read_output(b'{"sources":{}}')

    def test_more_queries_not_silently_ignored(self):
        with self.assertRaises(f.FormalError):
            f.compiler_queries({'auxiliaryInputRequested':{'smtlib2queries':{'0x'+'a'*64:self.query,'0x'+'b'*64:self.query}}})

    def test_wrong_witness_rejected(self):
        witness=deepcopy(self.false['witness']);witness['finalCredit']+=1
        with self.assertRaisesRegex(f.FormalError,'ARITHMETIC'): f.check_witness('off_by_one','property',witness)

    def test_false_alarm_witness_rejected(self):
        witness={'debit':0,'credit':0,'quantity':0,'finalDebit':0,'finalCredit':0}
        with self.assertRaisesRegex(f.FormalError,'DOES_NOT_VIOLATE'): f.check_witness('conservation','property',witness)

    def test_witness_outside_guards_rejected(self):
        witness=deepcopy(self.false['witness']);witness['debit']=255
        with self.assertRaisesRegex(f.FormalError,'ASSUMPTIONS'): f.check_witness('off_by_one','property',witness)

    def test_boolean_witness_is_not_integer(self):
        witness=deepcopy(self.false['witness']);witness['debit']=False
        with self.assertRaises(f.FormalError): f.check_witness('off_by_one','property',witness)

    def test_unsat_without_feasible_inputs_is_not_certification(self):
        verdict=f.adjudicate('unreachable','UNSAT','UNSAT')
        self.assertEqual(verdict['status'],'VACUOUS_NO_CERTIFICATION')
        self.assertFalse(verdict['solidity_property_confirmed_only_within_fixed_model'])

    def test_unknown_never_substituted_by_exhaustive_success(self):
        verdict=f.adjudicate('conservation','UNKNOWN','SAT')
        self.assertEqual(verdict['status'],'FORMAL_INCONCLUSIVE')
        self.assertEqual(verdict['reference']['violating_input_tuples'],0)

    def test_reference_disagreement_blocks(self):
        with self.assertRaisesRegex(f.FormalError,'REFERENCE_DISAGREEMENT'):
            f.adjudicate('off_by_one','UNSAT','SAT')

    def test_feasibility_disagreement_blocks(self):
        with self.assertRaisesRegex(f.FormalError,'FEASIBILITY'): f.adjudicate('conservation','UNSAT','UNSAT')

    def test_execute_control_really_calls_both_compile_passes(self):
        a=self.property
        with patch.object(f.compiler,'_execute',side_effect=[(a['initial_output_utf8'].encode(),b''),(a['final_output_utf8'].encode(),b'')]) as call:
            result=f.execute_control(b'fixture-only','conservation','property','normal')
        self.assertEqual(call.call_count,2)
        second=strict_json(call.call_args_list[1].args[2])
        self.assertIn('auxiliaryInput',second)
        self.assertEqual(result['status'],'UNSAT')

    def test_missing_compiler_blocks_without_output(self):
        with self.assertRaises(ValueError): f.create(self.root/'absent',self.root/'new')
        self.assertFalse((self.root/'new').exists())

    def test_wrong_binary_is_never_executed(self):
        p=self.root/'fake';p.write_bytes(b'not the official compiler')
        with patch.object(f.compiler,'_execute') as execute,self.assertRaises(ValueError): f.create(p,self.root/'new')
        execute.assert_not_called()

    def test_replay_regenerates_fixed_lab_not_supplied_queries(self):
        out=self.bundle()
        with patch.object(f,'execute_lab',return_value=self.capture) as call:
            result=f.replay(out,self.root/'fixture')
        call.assert_called_once_with(self.root/'fixture','normal')
        self.assertTrue(result['same_compiler_and_solver_reexecuted'])
        self.assertFalse(result['independent_engine'])

    def test_resealed_favorable_result_rejected(self):
        out=self.bundle()
        self.reseal(out,'result.json',lambda d:d['controls'].update(off_by_one='PROPERTY_PROVED_IN_FIXED_MODEL'))
        with patch.object(f,'execute_lab',return_value=self.capture),self.assertRaisesRegex(f.FormalError,'REPLAY_MISMATCH'):
            f.replay(out,self.root/'fixture')

    def test_resealed_query_is_not_executed(self):
        out=self.bundle()
        self.reseal(out,'execution.json',lambda d:d['cases']['conservation']['runs']['property'].update(queries={'0x'+'a'*64:'(exit)'}))
        with patch.object(f,'execute_lab',return_value=self.capture) as call,self.assertRaises(f.FormalError):
            f.replay(out,self.root/'fixture')
        call.assert_called_once()

    def test_external_budget_cannot_be_downgraded(self):
        out=self.bundle()
        with patch.object(f,'execute_lab') as run,self.assertRaisesRegex(f.FormalError,'BUDGET_MISMATCH'):
            f.replay(out,self.root/'fixture',expected_budget='exhausted')
        run.assert_not_called()

    def test_output_no_overwrite(self):
        out=self.bundle()
        with self.assertRaisesRegex(f.FormalError,'NEW_OUTPUT'): f.create(self.root/'absent',out)

    def test_output_in_checkout_rejected(self):
        with self.assertRaisesRegex(f.FormalError,'OUTPUT_INSIDE_CODE'):
            f.create(self.root/'absent',f.ROOT/'unused-formal-case')

    def test_extra_bundle_file_rejected(self):
        out=self.bundle();(out/'unknown').write_bytes(b'')
        with self.assertRaisesRegex(f.FormalError,'BUNDLE_FILES'): f.replay(out,self.root/'fixture')

    def test_symlink_bundle_rejected(self):
        out=self.bundle();alias=self.root/'alias';alias.symlink_to(out,target_is_directory=True)
        with self.assertRaisesRegex(f.FormalError,'SYMLINK'): f.replay(alias,self.root/'fixture')

    def test_private_permissions(self):
        out=self.bundle()
        self.assertEqual(out.stat().st_mode&0o777,0o700)
        for p in out.iterdir(): self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_native_audit_binds_summary(self):
        result=f.result_from(self.capture,produced_at=AT)
        audit=f._audit(result)
        self.assertEqual(len(audit['events']),5)
        self.assertEqual(audit['events'][-1]['data']['result_sha256'],f.sha(canonical(result)))
        self.assertFalse(audit['clock_authenticated'])

    def test_quality_component_and_mandatory_tests(self):
        self.assertIn('solidity_formal',quality.COMPONENTS)
        self.assertIn('native_compile',quality.COMPONENTS['solidity_formal']['depends'])
        self.assertIn('test_solidity_formal.SolidityFormalTests.test_real_z3_resource_exhaustion_is_unknown',quality.REQUIRED_TESTS)

    def test_cli_rejects_arbitrary_source_and_target(self):
        for flag in ('--source','--target','--query'):
            with self.subTest(flag=flag),patch('sys.stderr',new_callable=io.StringIO) as err,self.assertRaises(SystemExit):
                f.main(['prove-solidity-controls','--out',str(self.root/'x'),'--binary','fake',flag,'PRIVATE'])
            self.assertNotIn('PRIVATE',err.getvalue())

    def test_cli_missing_binary_no_sensitive_output(self):
        with redirect_stdout(io.StringIO()) as output:
            code=f.main(['prove-solidity-controls','--binary',str(self.root/'SECRET'),'--out',str(self.root/'x')])
        self.assertEqual(code,2);self.assertNotIn('SECRET',output.getvalue())

    def test_no_queries_cannot_claim_solver_execution(self):
        empty={'status':'NO_TARGET','solver':None}
        version=b'Version: 0.8.30+commit.73712a01.Linux.g++\n'
        with patch.object(f.compiler,'read_pinned_binary',return_value=b'fixture'), \
             patch.object(f.compiler,'_execute',return_value=(version,b'')), \
             patch.object(f,'engine_identity',return_value={}), \
             patch.object(f,'execute_control',return_value=empty), \
             self.assertRaisesRegex(f.FormalError,'NO_SOLVER_EXECUTION'):
            f.execute_lab(self.root/'fixture')

    def test_main_entrypoint_is_connected(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','prove-solidity-controls','--binary','absent','--out',str(self.root/'x')]),redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),2)


if __name__=='__main__': unittest.main()
