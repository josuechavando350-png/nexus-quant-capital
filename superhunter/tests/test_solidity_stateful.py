"""Fixed control checks. Captures are real solc/Z3 output from this delivery.

Mocked orchestration tests do NOT count as fresh compilations. The separate
native acceptance script uses the uploaded verified compiler without mocks.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import solidity_stateful as sf, quality
from superhunter.safe_io import canonical, strict_json, write_new_bundle

CAPTURE = Path(__file__).with_name('fixtures') / 'stateful_native_capture.json'
AT = '2026-11-05T18:17:02+00:00'


class StatefulTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.execution = strict_json(CAPTURE.read_bytes())

    def docs(self):
        return sf.documents(self.execution, AT)

    def make(self):
        out = self.root / 'case'
        write_new_bundle(out, self.docs())
        return out

    def reseal(self, root, name, fn):
        value = strict_json((root/name).read_bytes());fn(value)
        raw = canonical(value);(root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = sf.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_only_fixed_names_and_roles(self):
        for name, role in [('other','property'), ('conservation','other'), ([], 'property')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                sf.control_source(name, role)

    def test_control_diff_is_one_literal(self):
        a=sf.control_source('conservation','property');b=sf.control_source('delayed_credit','property')
        self.assertEqual(a.replace('steps == 2 ? 0 : 0','steps == 2 ? 1 : 0'), b)
        self.assertEqual(a.count('assert('),1)

    def test_fixed_input_has_no_urls_or_extra_sources(self):
        data=sf.fixed_input('conservation','property')
        self.assertEqual(set(data['sources']), {'State.sol'})
        self.assertEqual(set(data['sources']['State.sol']), {'content'})
        self.assertEqual(data['settings']['modelChecker']['engine'],'chc')

    def test_query_profile_rejects_commands(self):
        q=next(iter(self.execution['cases']['conservation']['runs']['property']['queries'].values()))
        sf.check_query(q)
        for bad in (q+'(exit)\n',q.replace('HORN','ALL'),q.replace('3000','0',1),q+'(check-sat)\n'):
            with self.assertRaises(ValueError):sf.check_query(bad)

    def test_query_budget(self):
        with patch.object(sf,'MAX_QUERY',1),self.assertRaises(ValueError):sf.check_query('anything')

    def test_real_z3_horn_polarity(self):
        # Pure logical unit controls, explicitly not attributed to solc.
        prefix='(set-option :timeout 3000)\n(set-logic HORN)\n'
        for formula,expected in [('true','SAFE'),('false','VIOLATED')]:
            with self.subTest(formula=formula):
                r=sf.solve(prefix+'(assert '+formula+')\n(check-sat)\n','normal')
                self.assertEqual(r['assertion_outcome'],expected)
                self.assertFalse(r['proof_certificate_independently_checked'])

    def test_compiler_captured_query_solved_by_real_z3(self):
        for name in ('conservation','delayed_credit'):
            run=self.execution['cases'][name]['runs']['property']
            q=next(iter(run['queries'].values()))
            self.assertEqual(sf.solve(q,'normal')['assertion_outcome'], run['assertion_outcome'])

    def test_actual_resource_exhaustion(self):
        q=next(iter(self.execution['cases']['conservation']['runs']['property']['queries'].values()))
        self.assertEqual(sf.solve(q,'exhausted')['assertion_outcome'],'UNKNOWN')

    def test_budget_cannot_be_user_code(self):
        q=next(iter(self.execution['cases']['conservation']['runs']['property']['queries'].values()))
        for budget in ('arbitrary',{},0):
            with self.assertRaises(ValueError):sf.solve(q,budget)

    def test_responses_are_only_fixed_status_lines(self):
        for response in ('sat\n(exit)', 'sat', 'true', 'SAFE'):
            with self.assertRaises(ValueError):
                sf.fixed_input('conservation','property',{'0x'+'0'*64:response})

    def test_reference_graph_and_sequence_states_match(self):
        for name in sf.NAMES:
            with self.subTest(name=name):
                self.assertEqual(sf.graph_reference(name)['states'],sf.sequence_reference(name)['states'])

    def test_exact_expected_reference_counts(self):
        for name in ('conservation','delayed_credit'):
            with self.subTest(name=name):
                g=sf.graph_reference(name);e=sf.sequence_reference(name)
                self.assertEqual(len(g['states']),49)
                self.assertEqual(g['transition_count'],288)
                self.assertEqual(e['sequences_examined'],4096)
                self.assertEqual(e['feasible_three_step_sequences'],816)
                self.assertEqual(g['third_step_states'],16)

    def test_delayed_error_requires_third_step(self):
        g=sf.graph_reference('delayed_credit');e=sf.sequence_reference('delayed_credit')
        self.assertTrue(all(d+c==15 for steps,d,c in g['states'] if steps<3))
        self.assertTrue(all(d+c==16 for steps,d,c in g['states'] if steps==3))
        self.assertEqual(e['shortest_violation_steps'],3)
        self.assertEqual(e['violating_three_step_sequences'],816)

    def test_enumerator_does_not_call_graph(self):
        with patch.object(sf,'graph_reference',side_effect=AssertionError):
            self.assertEqual(sf.sequence_reference('conservation')['feasible_three_step_sequences'],816)

    def test_reference_witness_is_not_claimed_solver_trace(self):
        w=sf.graph_reference('delayed_credit')['witness']
        sf.concrete_witness('delayed_credit',w)
        self.assertEqual(w['origin'],'finite-reference-not-solver-or-evm')

    def test_bad_witness_rejected(self):
        w=sf.graph_reference('delayed_credit')['witness']
        for key,value in [('quantities',[16,0,0]),('quantities',[True,0,0]),('final_state',[3,15,0]),
                          ('origin','EVM')]:
            with self.subTest(key=key),self.assertRaises(ValueError):sf.concrete_witness('delayed_credit',{**w,key:value})

    def test_impossible_precondition_has_no_certificate(self):
        r=sf.adjudicate('unreachable','SAFE','SAFE')
        self.assertEqual(r['status'],'VACUOUS_STATEFUL_NO_CERTIFICATION')
        self.assertEqual(r['enumeration']['feasible_three_step_sequences'],0)
        self.assertEqual(r['graph']['transition_count'],0)
        self.assertFalse(r['third_step_nonvacuity'])

    def test_unknown_cannot_become_safe(self):
        for name in sf.NAMES:
            for a,b in [('UNKNOWN','SAFE'),('SAFE','UNKNOWN'),('UNKNOWN','UNKNOWN')]:
                with self.subTest(name=name,a=a,b=b):
                    self.assertEqual(sf.adjudicate(name,a,b)['status'],'STATEFUL_FORMAL_INCONCLUSIVE')

    def test_false_safe_response_rejected_by_reference(self):
        with self.assertRaisesRegex(ValueError,'PROPERTY_REFERENCE_DISAGREEMENT'):
            sf.adjudicate('delayed_credit','SAFE','VIOLATED')

    def test_false_reachability_rejected(self):
        with self.assertRaisesRegex(ValueError,'REACHABILITY_DISAGREEMENT'):
            sf.adjudicate('conservation','SAFE','SAFE')

    def test_disagreeing_references_block(self):
        original=sf.sequence_reference('conservation');original['states']=[]
        with patch.object(sf,'sequence_reference',return_value=original),self.assertRaisesRegex(ValueError,'REFERENCE_STATE_DISAGREEMENT'):
            sf.adjudicate('conservation','SAFE','VIOLATED')

    def test_captured_compiler_locations_classify(self):
        for name in sf.NAMES:
            for role in sf.ROLES:
                r=self.execution['cases'][name]['runs'][role]
                self.assertEqual(sf.classification(name,role,json.loads(r['final_output_utf8'])),r['assertion_outcome'])

    def test_no_diagnostic_not_proof(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_SINGLE_TARGET_REQUIRED'):
            sf.classification('conservation','property',{})

    def test_other_location_not_accepted(self):
        d=json.loads(self.execution['cases']['conservation']['runs']['property']['final_output_utf8'])
        d['errors'][0]['sourceLocation']['start']+=1
        with self.assertRaisesRegex(ValueError,'ASSERTION_LOCATION'):sf.classification('conservation','property',d)

    def test_unknown_warning_blocks(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_DIAGNOSTIC'):
            sf.classification('conservation','property',{'errors':[{'severity':'warning','message':'unknown'}]})

    def test_compilation_error_cannot_be_clean(self):
        with self.assertRaisesRegex(ValueError,'COMPILATION_FAILED'):
            sf._output(canonical({'errors':[{'severity':'error'}]}))

    def test_missing_query_cannot_certify(self):
        # Actual compiler result substituted solely to test orchestration failures.
        r=self.execution['cases']['conservation']['runs']['property']
        d=json.loads(r['initial_output_utf8']);d.pop('auxiliaryInputRequested')
        with patch.object(sf.compiler,'_execute',return_value=(canonical(d),b'')),self.assertRaisesRegex(ValueError,'NO_SOLVER_QUERY'):
            sf.execute_role(b'', 'conservation','property','normal')

    def test_compiler_solver_disagreement_blocks(self):
        r=self.execution['cases']['conservation']['runs']['property']
        with patch.object(sf.compiler,'_execute',side_effect=[(r['initial_output_utf8'].encode(),b''),(r['final_output_utf8'].encode(),b'')]), \
             patch.object(sf,'solve',return_value={**r['solver'],'assertion_outcome':'VIOLATED'}),self.assertRaisesRegex(ValueError,'COMPILER_SOLVER_DISAGREEMENT'):
            sf.execute_role(b'', 'conservation','property','normal')

    def test_manifest_private_roundtrip(self):
        root=self.make()
        with patch.object(sf,'execute_lab',return_value=self.execution) as run:
            r=sf.replay(root, self.root/'unused')
        run.assert_called_once()
        self.assertTrue(r['same_engines_reexecuted']);self.assertFalse(r['evm_executed'])
        self.assertEqual(root.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in root.iterdir()))

    def test_native_audit_contains_every_control(self):
        a=strict_json(self.docs()['audit.json']);e=a['events']
        self.assertEqual(len(e),5)
        self.assertEqual([x['data']['name'] for x in e[1:4]],list(sf.NAMES))

    def test_no_success_claims_exceed_model(self):
        r=sf.result_from(self.execution,AT)
        self.assertFalse(r['evm_executed']);self.assertFalse(r['vulnerability_confirmed']);self.assertFalse(r['platform_complete'])
        self.assertEqual(r['status'],'STATEFUL_CONTROLS_COMPLETED')

    def test_resealed_result_rejected(self):
        root=self.make();self.reseal(root,'result.json',lambda v:v.update(evm_executed=True))
        with patch.object(sf,'execute_lab',return_value=self.execution),self.assertRaisesRegex(ValueError,'STATEFUL_REPLAY_MISMATCH'):
            sf.replay(root,self.root/'unused')

    def test_supplied_source_never_used_for_replay(self):
        root=self.make()
        self.reseal(root,'execution.json',lambda v:v['cases']['conservation']['runs']['property']['input']['sources']['State.sol'].update(content='PRIVATE_NOT_EXECUTABLE'))
        with patch.object(sf,'execute_lab',return_value=self.execution) as run,self.assertRaises(ValueError):
            sf.replay(root,self.root/'unused')
        self.assertEqual(run.call_args.args,(self.root/'unused','normal'))

    def test_external_budget_cannot_be_downgraded(self):
        root=self.make()
        with patch.object(sf,'execute_lab') as run,self.assertRaisesRegex(ValueError,'EXTERNAL_BUDGET_MISMATCH'):
            sf.replay(root,self.root/'unused',expected_budget='exhausted')
        run.assert_not_called()

    def test_missing_or_extra_artifact_rejected(self):
        root=self.make();(root/'extra').write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'BUNDLE_FILES'):sf.replay(root,self.root/'unused')

    def test_boolean_manifest_version_rejected(self):
        root=self.make();m=strict_json((root/'COMPLETE.json').read_bytes());m['schema_version']=True
        (root/'COMPLETE.json').write_bytes(canonical(m))
        with self.assertRaisesRegex(ValueError,'BUNDLE_SCHEMA'):sf.replay(root,self.root/'unused')

    def test_no_overwrite(self):
        root=self.make()
        with self.assertRaisesRegex(ValueError,'NEW_OUTPUT_REQUIRED'):sf.create(self.root/'missing',root)

    def test_missing_compiler_blocks_without_output(self):
        out=self.root/'absent'
        with self.assertRaises(ValueError):sf.create(self.root/'missing',out)
        self.assertFalse(out.exists())

    def test_invalid_produced_at(self):
        with self.assertRaises(ValueError):sf.documents(self.execution,'2026-11-05T00:00:00')

    def test_cli_errors_are_private(self):
        with redirect_stdout(io.StringIO()) as output:
            code=sf.main(['prove-stateful-controls','--solc',str(self.root/'PRIVATE'),'--out',str(self.root/'out')])
        self.assertEqual(code,2);self.assertNotIn('PRIVATE',output.getvalue())
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            sf.main(['prove-stateful-controls','--solc','PRIVATE','--out',str(self.root/'out'),'--target','SECRET'])
        self.assertNotIn('SECRET',stream.getvalue())

    def test_entrypoint_is_connected(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','prove-stateful-controls','--solc','missing','--out',str(self.root/'new')]), \
             patch.object(sf,'main',return_value=2) as run:
            self.assertEqual(__main__.main(),2)
        run.assert_called_once()

    def test_qa_component_and_required_controls(self):
        self.assertEqual(quality.COMPONENTS['solidity_stateful']['files'],['solidity_stateful.py'])
        self.assertIn('solidity_stateful',quality.COMPONENTS['quality']['depends'])
        self.assertIn('test_solidity_stateful.StatefulTests.test_delayed_error_requires_third_step',quality.REQUIRED_TESTS)

    def test_eight_groups_preserve_every_test_once(self):
        from superhunter.platform import _test_inventory
        from superhunter.quality_worker import partition_ids
        ids=_test_inventory();groups=partition_ids(ids,quality.PARTITION_COUNT)
        self.assertEqual(len(groups),8)
        self.assertTrue(all(groups))
        self.assertEqual(sorted(x for group in groups for x in group),ids)

    def test_partition_mode_matches_actual_group_count(self):
        from superhunter.tests.test_quality import QualityTests
        # Unit receipt only; not an assertion of running any of these tests.
        fixture=QualityTests();fixture.setUp()
        result=quality.aggregate_receipts(fixture.partition_receipts(),fixture.snapshot)
        self.assertEqual(result['execution_mode'],'8-exact-worker-partitions')
        self.assertEqual(len(result['partition_receipts']),8)

    def test_capture_in_source_snapshot(self):
        self.assertEqual(quality.source_snapshot()['tests/fixtures/stateful_native_capture.json'],sf.sha(CAPTURE.read_bytes()))


if __name__=='__main__':unittest.main()
