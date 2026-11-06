"""Native SMT integration for our declared RBAC model; no target/exploit execution."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import permission_domain as domain, permission_smt as smt, smt_backend
from superhunter.safe_io import canonical,strict_json


class PermissionSMTTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.model=domain.example_model(corrected=True)
        self.source=self.root/'model.json';self.out=self.root/'out'

    def run_model(self,**kw):return smt.analyze_smt(self.model,**kw)[1]

    def create(self,**kw):
        self.source.write_bytes(canonical(self.model))
        return smt.create_smt(self.source,self.out,**kw)

    def reseal(self,name,edit):
        value=strict_json((self.out/name).read_bytes());edit(value)
        raw=canonical(value);(self.out/name).write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=smt.digest(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_corrected_model_proved_with_full_enumeration(self):
        r=self.run_model()
        self.assertEqual(r['status'],'POLICY_SMT_PROVED')
        self.assertTrue(r['solver_executed']);self.assertTrue(r['independently_exhaustive_confirmed'])
        self.assertEqual(r['enumeration']['examined_configurations'],4)
        self.assertFalse(r['vulnerability_confirmed']);self.assertFalse(r['solidity_analyzed'])

    def test_bad_model_violated_with_replayed_witness(self):
        self.model=domain.example_model(corrected=False);r=self.run_model()
        self.assertEqual(r['status'],'POLICY_SMT_VIOLATION')
        sat=[q for q in r['queries'] if q['violation']['status']=='SAT']
        self.assertTrue(sat)
        for q in sat:
            self.assertTrue(smt.replay_assignment(self.model,q['id'],q['violation']['assignment'])['violation'])

    def test_real_resource_exhaustion_never_proves(self):
        r=self.run_model(resource_limit=1)
        self.assertEqual(r['status'],'POLICY_SMT_INCONCLUSIVE')
        self.assertGreater(r['inconclusive_properties'],0)
        self.assertFalse(r['proved_for_declared_model'])
        self.assertTrue(any(q['violation']['status']=='UNKNOWN' for q in r['queries']))

    def test_timeout_budget_type_checked(self):
        with self.assertRaises(ValueError):self.run_model(timeout_ms=True)

    def test_wall_budget_exhausted_is_not_run(self):
        with patch('superhunter.permission_smt.time.monotonic',side_effect=[0]+[100]*30):
            r=self.run_model(wall_ms=1)
        self.assertEqual(r['status'],'POLICY_SMT_INCONCLUSIVE')
        self.assertFalse(r['solver_executed'])

    def test_empty_properties_are_not_a_proof(self):
        for name in ('assertions','separation_rules','revocations'):self.model['policy'][name]=[]
        r=self.run_model();self.assertEqual(r['status'],'POLICY_SMT_INCONCLUSIVE')
        self.assertFalse(r['solver_executed'])

    def test_reference_incomplete_declared_separately(self):
        self.model['max_states']=1;r=self.run_model()
        self.assertEqual(r['status'],'POLICY_SMT_PROVED')
        self.assertFalse(r['independently_exhaustive_confirmed'])
        self.assertFalse(r['enumeration']['coverage_complete'])
        self.assertEqual(r['enumeration']['unexamined_configurations'],3)

    def test_encoding_does_not_embed_policy_names(self):
        encoded=smt.compile_model(self.model)
        self.assertNotIn('alice',encoded['base']);self.assertNotIn('preparer',encoded['base'])
        self.assertIn('(set-logic QF_LIA)',encoded['base'])

    def test_symbolic_inheritance_independent_from_concrete_closure(self):
        with patch('superhunter.permissions._closures',side_effect=AssertionError):
            self.assertEqual(smt.compile_model(self.model)['variable_count'],2)

    def test_input_model_not_mutated(self):
        original=deepcopy(self.model);self.run_model();self.assertEqual(self.model,original)

    def test_disabled_user_has_no_granted_permission(self):
        self.model['policy']['users']['bob']['disabled']=True
        self.model['policy']['assertions']=[{'id':'disabled','user':'bob','permission':'read','expected':'DENY'}]
        r=self.run_model();self.assertEqual(r['status'],'POLICY_SMT_PROVED')

    def test_inherited_deny_overrides_other_direct_grant(self):
        p=self.model['policy'];p['roles']['blocked']={'inherits':['preparer'],'allow':[],'deny':[]}
        p['users']['alice']['roles']=['blocked','approver']
        p['revocations']=[];self.model['variables']=[]
        p['assertions']=[{'id':'inherited.deny','user':'alice','permission':'approve','expected':'DENY'}]
        self.assertEqual(self.run_model()['status'],'POLICY_SMT_PROVED')

    def test_revocation_does_not_remove_inherited_grant(self):
        p=self.model['policy'];p['roles']['indirect']={'inherits':['approver'],'allow':[],'deny':[]}
        p['users']['bob']['roles']=['approver','indirect'];p['assertions']=[];p['separation_rules']=[]
        p['revocations']=[{'id':'remove','user':'bob','remove_roles':['approver'],'must_deny':['approve']}]
        self.model['variables']=[]
        self.assertEqual(self.run_model()['status'],'POLICY_SMT_VIOLATION')

    def test_multiple_permissions_exact_cardinality(self):
        p=self.model['policy'];p['separation_rules']=[{'id':'count','permissions':['read','prepare','approve'],'max_allowed':1}]
        p['assertions']=[];p['revocations']=[]
        self.assertEqual(self.run_model()['status'],'POLICY_SMT_VIOLATION')

    def test_zero_variables_is_one_configuration(self):
        self.model['variables']=[];r=self.run_model()
        self.assertEqual(r['domain_configurations'],1);self.assertEqual(r['status'],'POLICY_SMT_PROVED')

    def test_concrete_counterexample_refutes_forged_unsat(self):
        self.model=domain.example_model(corrected=False)
        original=smt_backend.solve_generated
        def wrong(*args,**kwargs):
            r=original(*args,**kwargs)
            r.update(status='UNSAT',assignment=None,unknown_reason=None)
            return r
        with patch.object(smt_backend,'solve_generated',side_effect=wrong),self.assertRaisesRegex(ValueError,'DISAGREEMENT'):
            self.run_model()

    def test_incorrect_solver_witness_rejected(self):
        r=self.run_model();q=r['queries'][0];q['applicable']['assignment']=[1,False]
        enc=smt.compile_model(self.model)
        with self.assertRaisesRegex(ValueError,'WITNESS_SHAPE'):
            smt._check_record(self.model,enc,enc['properties'][0],'applicable',q['applicable'])

    def test_bundle_roundtrip_reexecutes_native_solver(self):
        first=self.create()
        with patch.object(smt_backend,'solve_generated',wraps=smt_backend.solve_generated) as call:
            again=smt.verify_smt(self.out)
        self.assertEqual(first,again);self.assertEqual(call.call_count,10)

    def test_original_private_policy_preserved(self):
        self.create();self.assertEqual((self.out/'model.json').read_bytes(),self.source.read_bytes())
        self.assertNotIn('alice',(self.out/'REVIEW.md').read_text())

    def test_resealed_false_approval_rejected(self):
        self.model=domain.example_model(corrected=False);self.create()
        self.reseal('analysis.json',lambda x:x.update(status='POLICY_SMT_PROVED',proved_for_declared_model=True))
        with self.assertRaisesRegex(ValueError,'ANALYSIS_MISMATCH'):smt.verify_smt(self.out)

    def test_resealed_changed_encoding_rejected(self):
        self.create();self.reseal('encoding.json',lambda x:x.update(base=x['base']+'(assert false)\n'))
        with self.assertRaisesRegex(ValueError,'ENCODING_MISMATCH'):smt.verify_smt(self.out)

    def test_resealed_engine_identity_rejected(self):
        self.create();self.reseal('analysis.json',lambda x:x['engine'].update(library_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'ENGINE_MISMATCH'):smt.verify_smt(self.out)

    def test_resealed_query_boolean_budget_rejected(self):
        self.create(timeout_ms=1)
        self.reseal('analysis.json',lambda x:x['queries'][0]['applicable'].update(timeout_ms=True))
        with self.assertRaisesRegex(ValueError,'BUDGET_TYPE'):smt.verify_smt(self.out)

    def test_resealed_audit_event_rejected(self):
        self.create();self.reseal('audit.json',lambda x:x['entries'][0].update(event='not.smt.start'))
        with self.assertRaisesRegex(ValueError,'AUDIT_SEMANTICS'):smt.verify_smt(self.out)

    def test_missing_manifest_rejected(self):
        self.create();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):smt.verify_smt(self.out)

    def test_extra_file_rejected(self):
        self.create();(self.out/'extra').write_text('extra')
        with self.assertRaisesRegex(ValueError,'FILE_SET'):smt.verify_smt(self.out)

    def test_symlink_model_rejected(self):
        self.create();p=self.out/'model.json';p.unlink();p.symlink_to(self.source)
        with self.assertRaises((OSError,ValueError)):smt.verify_smt(self.out)

    def test_output_existing_not_overwritten(self):
        self.create();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual(before,(self.out/'COMPLETE.json').read_bytes())

    def test_output_is_private(self):
        self.create();self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)

    def test_no_network_or_child_execution(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();smt.verify_smt(self.out)

    def test_cli_create_verify_separate_processes(self):
        self.source.write_bytes(canonical(self.model))
        base=[sys.executable,'-B','-m','superhunter']
        for args in (['check-permission-smt','--model',str(self.source),'--out',str(self.out)],
                     ['verify-permission-smt','--bundle',str(self.out)]):
            r=subprocess.run(base+args,cwd=smt.ROOT.parent,capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            self.assertEqual(json.loads(r.stdout)['status'],'POLICY_SMT_PROVED')

    def test_cli_error_hides_input_path(self):
        with redirect_stdout(io.StringIO()) as output:
            code=smt.main(['verify-permission-smt','--bundle',str(self.root/'SECRET_MARKER')])
        self.assertEqual(code,2);self.assertNotIn('SECRET_MARKER',output.getvalue())

    def test_cli_unknown_argument_hides_value(self):
        with patch('sys.stderr',new_callable=io.StringIO) as output,self.assertRaises(SystemExit):
            smt.main(['verify-permission-smt','--bundle',str(self.root),'--bad','SECRET_MARKER'])
        self.assertNotIn('SECRET_MARKER',output.getvalue())

    def test_missing_engine_never_synthetic_fallback(self):
        with patch.object(smt_backend,'PATHS',()),self.assertRaises(ValueError):self.run_model()


class GeneratedPolicySMTTests(unittest.TestCase):
    def test_native_solver_matches_sixteen_distinct_models(self):
        import random
        for seed in range(16):
            rng = random.Random(seed)
            roles = {}
            for i in range(3):
                roles['r'+str(i)] = {'inherits':['r'+str(j) for j in range(i) if rng.randrange(2)],
                    'allow':[p for p in ['read','write'] if rng.randrange(2)],
                    'deny':[p for p in ['read','write'] if rng.randrange(2)]}
            policy = {'schema_version':1,'model':'sh-rbac-v1','policy_id':'generated',
                'permissions':['read','write'],'roles':roles,
                'users':{'alice':{'roles':['r0'],'disabled':bool(seed%5==0)},
                         'bob':{'roles':['r1'],'disabled':False}},
                'assertions':[{'id':'a','user':'alice','permission':'write','expected':'DENY'},
                              {'id':'b','user':'bob','permission':'read','expected':'ALLOW'}],
                'separation_rules':[{'id':'s','permissions':['read','write'],'max_allowed':1}],
                'revocations':[{'id':'r','user':'alice','remove_roles':['r0'],'must_deny':['write']}]}
            model={'schema_version':1,'model':domain.MODEL,'policy':policy,
                'variables':[{'user':'alice','role':'r0'},{'user':'alice','role':'r2'},
                             {'user':'bob','role':'r1'}], 'max_states':8}
            with self.subTest(seed=seed):
                _,result=smt.analyze_smt(model)
                self.assertTrue(result['enumeration']['coverage_complete'])
                self.assertEqual(result['inconclusive_properties'],0)
                expected='POLICY_SMT_VIOLATION' if result['enumeration']['violating_configurations'] else 'POLICY_SMT_PROVED'
                self.assertEqual(result['status'],expected)
