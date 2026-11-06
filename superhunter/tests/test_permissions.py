"""Defensive configuration tests; no external applications or exploit execution."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import permissions as p, quality
from superhunter.safe_io import canonical, strict_json


class PermissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.policy = p.example_policy()

    def analyze(self):
        return p.analyze_policy(self.policy)

    def bundle(self):
        source = self.root/'policy.json'; source.write_bytes(canonical(self.policy))
        out = self.root/'out'; result = p.audit_policy(source,out)
        return out,result

    def reseal(self, root, name, change):
        path = root/name; data = strict_json(path.read_bytes()); change(data)
        raw = canonical(data); path.write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_known_good_policy_passes(self):
        result = self.analyze()
        self.assertEqual(result['status'],'POLICY_ASSERTIONS_PASS')
        self.assertEqual(result['counts']['checks'],5)
        self.assertEqual(result['counts']['reference_comparisons'],3)
        self.assertEqual(result['states']['alice']['allowed'],['prepare','read'])
        self.assertFalse(result['live_enforcement_verified'])
        self.assertFalse(result['vulnerability_confirmed'])

    def test_known_bad_policy_fails(self):
        self.policy['users']['alice']['roles'].append('approver')
        result = self.analyze()
        self.assertEqual(result['status'],'POLICY_ASSERTIONS_FAIL')
        self.assertEqual(result['counts']['failed'],2)
        self.assertEqual({c['kind'] for c in result['checks'] if not c['passed']},{'assertion','separation'})

    def test_default_deny_for_unassigned_user(self):
        self.policy['users']['alice']['roles']=[]
        self.assertEqual(self.analyze()['states']['alice']['allowed'],[])

    def test_disabled_user_has_no_effective_access(self):
        self.policy['users']['alice']['disabled']=True
        result=self.analyze()
        self.assertEqual(result['states']['alice']['allowed'],[])
        self.assertTrue(result['states']['alice']['disabled'])

    def test_explicit_deny_overrides_inherited_allow(self):
        self.policy['roles']['preparer']['deny']=['read']
        self.assertEqual(self.analyze()['states']['alice']['allowed'],['prepare'])

    def test_inherited_deny_overrides_direct_allow(self):
        self.policy['roles']['reader']['deny']=['prepare']
        self.assertEqual(self.analyze()['states']['alice']['allowed'],['read'])

    def test_allow_deny_same_role_is_unambiguous(self):
        self.policy['roles']['preparer']['deny']=['prepare']
        self.assertEqual(self.analyze()['states']['alice']['allowed'],['read'])

    def test_transitive_role_inheritance(self):
        self.policy['roles']['senior']={'inherits':['preparer'],'allow':[],'deny':[]}
        self.policy['users']['alice']['roles']=['senior']
        result=self.analyze()
        self.assertEqual(result['states']['alice']['roles'],['preparer','reader','senior'])

    def test_diamond_is_not_cycle(self):
        self.policy['roles']['combined']={'inherits':['preparer','approver'],'allow':[],'deny':[]}
        self.policy['users']['alice']['roles']=['combined']
        self.assertEqual(self.analyze()['counts']['failed'],2)

    def test_indirect_cycle_rejected(self):
        self.policy['roles']['reader']['inherits']=['preparer']
        with self.assertRaisesRegex(p.PolicyError,'CYCLE'):self.analyze()

    def test_self_cycle_rejected(self):
        self.policy['roles']['reader']['inherits']=['reader']
        with self.assertRaisesRegex(p.PolicyError,'CYCLE'):self.analyze()

    def test_unknown_role_rejected(self):
        self.policy['users']['alice']['roles']=['missing']
        with self.assertRaisesRegex(p.PolicyError,'UNKNOWN_ROLE'):self.analyze()

    def test_unknown_parent_rejected(self):
        self.policy['roles']['reader']['inherits']=['missing']
        with self.assertRaisesRegex(p.PolicyError,'UNKNOWN_ROLE'):self.analyze()

    def test_unknown_permission_rejected(self):
        self.policy['roles']['reader']['allow']=['missing']
        with self.assertRaisesRegex(p.PolicyError,'UNKNOWN_PERMISSION'):self.analyze()

    def test_unknown_assertion_user_rejected(self):
        self.policy['assertions'][0]['user']='missing'
        with self.assertRaisesRegex(p.PolicyError,'UNKNOWN_USER'):self.analyze()

    def test_duplicate_assignments_rejected(self):
        self.policy['users']['alice']['roles']=['preparer','preparer']
        with self.assertRaisesRegex(p.PolicyError,'DUPLICATE'):self.analyze()

    def test_unexpected_field_rejected_without_echo(self):
        self.policy['secret_marker_do_not_echo']=True
        with self.assertRaises(p.PolicyError) as cm:self.analyze()
        self.assertNotIn('secret_marker',str(cm.exception))

    def test_version_boolean_is_not_integer(self):
        self.policy['schema_version']=True
        with self.assertRaises(p.PolicyError):self.analyze()

    def test_disabled_number_is_not_boolean(self):
        self.policy['users']['alice']['disabled']=1
        with self.assertRaises(p.PolicyError):self.analyze()

    def test_maximum_boolean_is_not_integer(self):
        self.policy['separation_rules'][0]['max_allowed']=True
        with self.assertRaises(p.PolicyError):self.analyze()

    def test_no_assertions_is_not_policy_pass(self):
        for key in ('assertions','separation_rules','revocations'):self.policy[key]=[]
        self.assertEqual(self.analyze()['status'],'POLICY_REVIEW_ONLY')

    def test_revocation_does_not_remove_inherited_assignment(self):
        self.policy['roles']['backup']={'inherits':['approver'],'allow':[],'deny':[]}
        self.policy['users']['bob']['roles'].append('backup')
        result=self.analyze()
        self.assertEqual(result['revocations'][0]['unexpected_retained'],['approve'])
        self.assertEqual(result['counts']['failed'],1)

    def test_removing_denial_can_increase_access(self):
        self.policy['roles']['blocked']={'inherits':[],'allow':[],'deny':['approve']}
        self.policy['users']['bob']['roles'].append('blocked')
        self.policy['revocations'][0]['remove_roles']=['blocked']
        result=self.analyze()
        self.assertEqual(result['revocations'][0]['gained_permissions'],['approve'])
        self.assertEqual(result['status'],'POLICY_ASSERTIONS_FAIL')

    def test_revocation_requires_direct_assignment(self):
        self.policy['revocations'][0]['remove_roles']=['reader']
        with self.assertRaisesRegex(p.PolicyError,'REMOVE_UNASSIGNED'):self.analyze()

    def test_independent_reference_does_not_call_primary(self):
        with patch.object(p,'_primary',side_effect=AssertionError),patch.object(p,'_closures',side_effect=AssertionError):
            result=p._reference(self.policy,self.policy['users']['alice'])
        self.assertEqual(result['allowed'],['prepare','read'])

    def test_reference_disagreement_blocks_result(self):
        with patch.object(p,'_reference',return_value={}),self.assertRaisesRegex(p.PolicyError,'REFERENCE_DISAGREEMENT'):
            self.analyze()

    def test_input_is_unchanged(self):
        before=canonical(self.policy);self.analyze();self.assertEqual(canonical(self.policy),before)

    def test_generated_policies_agree_between_algorithms(self):
        rng=random.Random(23819)
        for case in range(128):
            roles={}
            for i in range(rng.randint(1,12)):
                roles[f'r{i}']={'inherits':[r for r in roles if rng.randrange(4)==0],
                              'allow':[q for q in self.policy['permissions'] if rng.randrange(2)],
                              'deny':[q for q in self.policy['permissions'] if rng.randrange(4)==0]}
            model={**self.policy,'roles':roles,'users':{'subject':{'roles':[r for r in roles if rng.randrange(2)],'disabled':bool(rng.randrange(4)==0)}},
                   'assertions':[],'separation_rules':[],'revocations':[]}
            with self.subTest(case=case):
                self.assertTrue(p.analyze_policy(model)['model_consistency_checked'])

    def test_maximum_role_chain_bounded(self):
        roles={f'r{i}':{'inherits':[f'r{i-1}'] if i else [],'allow':['read'],'deny':[]} for i in range(64)}
        self.policy.update(roles=roles, users={'subject':{'roles':['r63'],'disabled':False}},assertions=[],separation_rules=[],revocations=[])
        self.assertEqual(len(self.analyze()['states']['subject']['roles']),64)

    def test_excess_role_limit_rejected(self):
        self.policy['roles']={f'r{i}':{'inherits':[],'allow':[],'deny':[]} for i in range(65)}
        with self.assertRaisesRegex(p.PolicyError,'ROLE_LIMIT'):self.analyze()

    def test_duplicate_check_rejected(self):
        self.policy['assertions'].append(deepcopy(self.policy['assertions'][0]))
        with self.assertRaisesRegex(p.PolicyError,'DUPLICATE_CHECK'):self.analyze()

    def test_graph_node_and_edge_identity(self):
        out,_=self.bundle();graph=strict_json((out/'graph.json').read_bytes())
        self.assertEqual(graph['edges'],[['approver','reader'],['preparer','reader']])
        self.assertTrue(graph['acyclic'])

    def test_bundle_roundtrip(self):
        out,result=self.bundle();self.assertEqual(p.verify_permissions(out),result)
        self.assertEqual(set(x.name for x in out.iterdir()),p.FILES|{'COMPLETE.json'})

    def test_native_audit_is_actually_called(self):
        native=p.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as append:
            self.bundle()
        self.assertEqual(append.call_count,7)

    def test_altered_result_rejected_even_when_rehashed(self):
        out,_=self.bundle();self.reseal(out,'analysis.json',lambda d:d.update(live_enforcement_verified=True))
        with self.assertRaisesRegex(p.PolicyError,'RESULT_MISMATCH'):p.verify_permissions(out)

    def test_graph_tamper_rejected(self):
        out,_=self.bundle();self.reseal(out,'graph.json',lambda d:d.update(edges=[]))
        with self.assertRaisesRegex(p.PolicyError,'GRAPH_MISMATCH'):p.verify_permissions(out)

    def test_audit_semantics_rejected_even_when_rehashed(self):
        out,_=self.bundle()
        self.reseal(out,'audit.json',lambda d:d['entries'][1]['data'].update(passed=False))
        with self.assertRaisesRegex(p.PolicyError,'AUDIT_SEMANTICS'):p.verify_permissions(out)

    def test_boolean_schema_marker_rejected(self):
        out,_=self.bundle();marker=strict_json((out/'COMPLETE.json').read_bytes());marker['schema_version']=True
        (out/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaises(p.PolicyError):p.verify_permissions(out)

    def test_stale_code_rejected(self):
        out,_=self.bundle()
        with patch.object(p,'_code_digest',return_value='0'*64),self.assertRaisesRegex(p.PolicyError,'STALE_CODE'):
            p.verify_permissions(out)

    def test_missing_marker_rejected(self):
        out,_=self.bundle();(out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):p.verify_permissions(out)

    def test_no_overwrite(self):
        out,_=self.bundle();before=(out/'COMPLETE.json').read_bytes()
        with self.assertRaises(p.PolicyError):p.audit_policy(self.root/'policy.json',out)
        self.assertEqual((out/'COMPLETE.json').read_bytes(),before)

    def test_private_permissions(self):
        out,_=self.bundle();self.assertEqual(out.stat().st_mode & 0o777,0o700)
        for file in out.iterdir():self.assertEqual(file.stat().st_mode & 0o777,0o600)

    def test_no_network_or_child_execution(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.assertEqual(self.bundle()[1]['status'],'POLICY_ASSERTIONS_PASS')

    def test_cli_roundtrip_and_failure_exit(self):
        src=self.root/'policy.json';src.write_bytes(canonical(self.policy))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(['audit-permissions','--policy',str(src),'--out',str(self.root/'valid')]),0)
            self.assertEqual(p.main(['verify-permissions','--bundle',str(self.root/'valid')]),0)
        self.policy['users']['alice']['roles'].append('approver');src.write_bytes(canonical(self.policy))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(['audit-permissions','--policy',str(src),'--out',str(self.root/'invalid')]),1)

    def test_cli_does_not_echo_secret_filename(self):
        with redirect_stdout(io.StringIO()) as stream:
            code=p.main(['verify-permissions','--bundle',str(self.root/'password-secret-value')])
        self.assertEqual(code,2);self.assertNotIn('secret-value',stream.getvalue())

    def test_cli_dispatcher_reachable(self):
        proc=subprocess.run([sys.executable,'-B','-m','superhunter','audit-permissions','--help'],cwd=p.ROOT.parent,capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr)

    def test_component_and_checklist_linked(self):
        self.assertIn('permissions',quality.COMPONENTS)
        for num in (14,24):
            item=quality.catalog()['items'][num-1]
            self.assertEqual(item['status'],'PARTIAL')
            expected = ['permissions', 'permission_domain', 'permission_smt'] if item['id'] == 24 else ['permissions']
            self.assertEqual(item['components'], expected)
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])

    def test_report_never_claims_application_execution(self):
        report=p.render_analysis(self.analyze())
        self.assertIn('no los permisos efectivos',report)
        self.assertIn('no demuestra',report)


if __name__=='__main__':unittest.main()
