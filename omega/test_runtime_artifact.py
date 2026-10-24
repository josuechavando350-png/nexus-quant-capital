"""Adversarial packaging tests. Altered fixture packets are not CI evidence."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import ci_evidence
from historical_pipeline import exercise
from integrity import canonical, digest
from runtime_artifact import (CODE_PATHS, LEGACY_SCHEMA, LEGACY_CODE_PATHS, MAX_PACKET, ROOT, SCHEMA,
                              TRANSPORT_SCHEMA, TRANSPORT_CODE_PATHS, DEPENDENCY_SCHEMA,
                              DEPENDENCY_CODE_PATHS, ECONOMIC_SCHEMA, ECONOMIC_CODE_PATHS, inspect_packet,
                              unpack, verify_artifact, write_packet)


class RuntimeArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pin=ci_evidence.load_pin()
        cls.members=ci_evidence.unpack(ci_evidence.ARCHIVE_PATH.read_bytes(),pin['members'])
        cls.jobs=ci_evidence.verify_metadata(cls.members,pin)
        with tempfile.TemporaryDirectory() as tmp:
            cls.pipeline=exercise(Path(tmp)/'pipeline')

    def code_git(self,root,command,argument):
        self.assertEqual(command,'show')
        return (ROOT/argument.split(':',1)[1]).read_bytes()

    def packet(self,stage='forks'):
        records,_,_=ci_evidence.parse_log(self.members[stage+'.log'],self.jobs[stage])
        records=copy.deepcopy(records)
        def rec(name,value):return {'name':name,'value':value,'sha256':digest(canonical(value))}
        values={r['name']:r['value'] for r in records}
        tests=values['runner-unit-tests']
        extra=[rec(name,copy.deepcopy(tests)) for name in ('ci-capture-tests','historical-intake-tests',
            'evidence-store-tests','historical-pipeline-tests','runtime-artifact-tests')]
        extra += [rec('historical-pipeline',self.pipeline)]
        command=next(r for r in records if r['name']=='command')
        extra += [copy.deepcopy(command) for _ in range(8)]
        records[-1:-1]=extra
        for r in records:
            if r['name'] in ('isolation-before','isolation-after'):
                r['value']['active_workflow_sha256']=digest((ROOT/'.github/workflows/omega-h2-audit.yml').read_bytes())
                r['sha256']=digest(canonical(r['value']))
        p={'schema':LEGACY_SCHEMA if stage=='replay' else SCHEMA,
           'producer':values['producer'],'stage':stage,'records':records,
           'code_sha256':{f:digest((ROOT/f).read_bytes()) for f in
                         (LEGACY_CODE_PATHS if stage=='replay' else CODE_PATHS)}}
        return self.seal(p)

    def seal(self,p):
        p['packet_commitment_sha256']=digest(canonical({k:v for k,v in p.items() if k!='packet_commitment_sha256'}))
        return p

    def inspect(self,p):
        with patch('runtime_artifact.git',side_effect=self.code_git):
            return inspect_packet(p,expected_producer=ci_evidence.PRODUCER,
                                  expected_tree=ci_evidence.TREE,stage=p['stage'])

    def archive(self,p,name='runtime.json',mode=0o100644):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
            info=zipfile.ZipInfo(name);info.external_attr=mode<<16
            z.writestr(info,canonical(p))
        return out.getvalue()

    def capture(self,raw,stage='forks'):
        run=json.loads(self.members['run.json']);commit=json.loads(self.members['commit.json'])
        jobs=json.loads(self.members['jobs.json'])
        for job in jobs['jobs']:
            job['steps'].append({'name':'Retain bounded runtime evidence','conclusion':'success'})
        artifact={'id':123,'name':f'omega-runtime-{stage}-{ci_evidence.PRODUCER}-1',
            'expired':False,'size_in_bytes':len(raw),'digest':'sha256:'+digest(raw),
            'created_at':run['updated_at'],'expires_at':'2026-10-24T00:00:00Z',
            'workflow_run':{'id':run['id'],'head_sha':run['head_sha'],'head_branch':run['head_branch'],
                'repository_id':1411047452,'head_repository_id':1411047452}}
        return {'run':run,'commit':commit,'jobs':jobs,'artifact':artifact,'retrieved_at':'2026-10-23T00:00:00Z'}

    def verify(self,raw,capture,expected=None):
        with patch('runtime_artifact.git',side_effect=self.code_git):
            return verify_artifact(raw,capture,expected_capture_sha256=expected or digest(canonical(capture)),
                                   expected_producer=ci_evidence.PRODUCER,stage='forks')

    def test_both_stage_packet_shapes_and_no_certification(self):
        for stage in ('forks','replay'):
            result=self.inspect(self.packet(stage))
            self.assertGreater(result['records'],30)

    def test_v2_replay_requires_bridge_and_rejects_scope_inheritance(self):
        p=self.packet('replay');p['schema']=TRANSPORT_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in TRANSPORT_CODE_PATHS}
        self.seal(p)
        with self.assertRaisesRegex(ValueError,'record_inventory'):self.inspect(p)

    def test_v1_remains_accepted_without_new_transport_claim(self):
        p=self.packet();p['schema']=LEGACY_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in LEGACY_CODE_PATHS}
        self.seal(p)
        self.assertGreater(self.inspect(p)['records'],30)

    def test_v2_replay_accepts_bound_bridge_and_rejects_changed_claims(self):
        from test_rust_store_intake import synthetic_report
        p=self.packet('replay');p['schema']=TRANSPORT_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in TRANSPORT_CODE_PATHS}
        network=next(r['value'] for r in p['records'] if r['name']=='network-isolation')
        value=synthetic_report(network)
        record={'name':'rust-store-bridge','value':value,'sha256':digest(canonical(value))}
        command=copy.deepcopy(next(r for r in p['records'] if r['name']=='command'))
        p['records'][-1:-1]=[command,record];self.seal(p)
        self.assertEqual(self.inspect(p)['records'],41)
        value['corruption_rejected']=False
        value['report_commitment_sha256']=digest(canonical({k:v for k,v in value.items() if k!='report_commitment_sha256'}))
        record['sha256']=digest(canonical(value));self.seal(p)
        with self.assertRaises(ValueError):self.inspect(p)

    def dependent_packet(self):
        from test_rust_store_intake import synthetic_report
        from test_dependency_intake import synthetic_report as dependency_report
        p=self.packet('replay');p['schema']=DEPENDENCY_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in DEPENDENCY_CODE_PATHS}
        network=next(r['value'] for r in p['records'] if r['name']=='network-isolation')
        extras=[copy.deepcopy(next(r for r in p['records'] if r['name']=='command'))]
        for name,value in (('rust-store-bridge',synthetic_report(network)),
                           ('dependency-store-bridge',dependency_report(network))):
            extras.append({'name':name,'value':value,'sha256':digest(canonical(value))})
        p['records'][-1:-1]=extras;return self.seal(p)

    def test_v3_requires_dependency_record_and_retains_v2_scope(self):
        p=self.dependent_packet();self.assertEqual(self.inspect(p)['records'],42)
        p['records']=[r for r in p['records'] if r['name']!='dependency-store-bridge'];self.seal(p)
        with self.assertRaisesRegex(ValueError,'record_inventory'):self.inspect(p)
        p['schema']=TRANSPORT_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in TRANSPORT_CODE_PATHS}
        self.seal(p);self.assertEqual(self.inspect(p)['records'],41)

    def test_v3_resealed_dependency_claim_or_namespace_change_rejected(self):
        baseline=self.dependent_packet()
        for mutate in (lambda r:r.__setitem__('blocked_batches',4),
                       lambda r:r['network'].__setitem__('network_namespace','net:[999999]')):
            p=copy.deepcopy(baseline)
            record=next(r for r in p['records'] if r['name']=='dependency-store-bridge')
            mutate(record['value']);record['value']['report_commitment_sha256']=digest(canonical(
                {k:v for k,v in record['value'].items() if k!='report_commitment_sha256'}))
            record['sha256']=digest(canonical(record['value']));self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def economic_packet(self):
        from test_execution_intake import synthetic_replay
        p=self.dependent_packet();p['schema']=ECONOMIC_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in ECONOMIC_CODE_PATHS}
        network=next(r['value'] for r in p['records'] if r['name']=='network-isolation')
        value=synthetic_replay(network)
        p['records'][-1:-1]=[{'name':'execution-economics','value':value,'sha256':digest(canonical(value))}]
        return self.seal(p)

    def test_v4_requires_economics_record_and_keeps_v3_scope(self):
        p=self.economic_packet();self.assertEqual(self.inspect(p)['records'],43)
        p['records']=[r for r in p['records'] if r['name']!='execution-economics'];self.seal(p)
        with self.assertRaisesRegex(ValueError,'record_inventory'):self.inspect(p)
        p['schema']=DEPENDENCY_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in DEPENDENCY_CODE_PATHS}
        self.seal(p);self.assertEqual(self.inspect(p)['records'],42)

    def test_v4_rejects_resealed_paid_cost_or_titan_coverage(self):
        baseline=self.economic_packet()
        for key,value in [('titan_covered_executions',1),('complete_paid_cost_rows',1)]:
            p=copy.deepcopy(baseline)
            r=next(r for r in p['records'] if r['name']=='execution-economics')
            report=r['value']['economic_report'];report['summary'][key]=value
            report['report_commitment_sha256']=digest(canonical({k:v for k,v in report.items() if k!='report_commitment_sha256'}))
            r['value']['report_commitment_sha256']=digest(canonical({k:v for k,v in r['value'].items() if k!='report_commitment_sha256'}))
            r['sha256']=digest(canonical(r['value']));self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def inclusion_packet(self):
        from test_inclusion_fee_intake import synthetic_replay
        p=self.economic_packet();p['schema']=SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in CODE_PATHS}
        network=next(r['value'] for r in p['records'] if r['name']=='network-isolation')
        value=synthetic_replay(network)
        p['records'][-1:-1]=[{'name':'inclusion-fees','value':value,'sha256':digest(canonical(value))}]
        return self.seal(p)

    def test_v5_requires_inclusion_record_and_keeps_v4_scope(self):
        p=self.inclusion_packet();self.assertEqual(self.inspect(p)['records'],44)
        self.assertLessEqual(len(canonical(p)),MAX_PACKET)
        p['records']=[r for r in p['records'] if r['name']!='inclusion-fees'];self.seal(p)
        with self.assertRaisesRegex(ValueError,'record_inventory'):self.inspect(p)
        p['schema']=ECONOMIC_SCHEMA
        p['code_sha256']={f:digest((ROOT/f).read_bytes()) for f in ECONOMIC_CODE_PATHS}
        self.seal(p);self.assertEqual(self.inspect(p)['records'],43)

    def test_v5_rejects_inclusion_proof_from_another_namespace(self):
        p=self.inclusion_packet();r=next(r for r in p['records'] if r['name']=='inclusion-fees')
        r['value']['network']['network_namespace']='net:[999999]'
        r['value']['report_commitment_sha256']=digest(canonical(
            {k:v for k,v in r['value'].items() if k!='report_commitment_sha256'}))
        r['sha256']=digest(canonical(r['value']));self.seal(p)
        with self.assertRaisesRegex(ValueError,'inclusion_network_disagrees'):self.inspect(p)

    def test_v5_rejects_resealed_operator_fallback_and_invented_titan_coverage(self):
        baseline=self.inclusion_packet()
        for key in ('own_gas_fallback_allowed','execution_coverage_proven'):
            p=copy.deepcopy(baseline);r=next(r for r in p['records'] if r['name']=='inclusion-fees')
            value=r['value'];value['gas_funding_policy'][key]=True
            value['gas_policy_sha256']=digest(canonical(value['gas_funding_policy']))
            value['report_commitment_sha256']=digest(canonical(
                {k:v for k,v in value.items() if k!='report_commitment_sha256'}))
            r['sha256']=digest(canonical(value));self.seal(p)
            with self.assertRaisesRegex(ValueError,'differs_from_sources'):self.inspect(p)

    def test_artifact_matches_external_capture_without_self_authentication_claim(self):
        raw=self.archive(self.packet());report=self.verify(raw,self.capture(raw))
        self.assertEqual(report['status'],'RUNTIME_ARTIFACT_MATCHES_EXTERNAL_CAPTURE')
        self.assertEqual(report['trust_basis'],'CALLER_SUPPLIED_OUT_OF_BAND_CAPTURE_DIGEST')
        self.assertFalse(report['new_api_query_performed'])
        self.assertFalse(report['canonical_recertification'])

    def test_wrong_external_capture_digest_rejects(self):
        raw=self.archive(self.packet())
        with self.assertRaisesRegex(ValueError,'external_capture_digest'):
            self.verify(raw,self.capture(raw),'0'*64)

    def test_cross_repo_run_commit_and_artifact_rebinding_rejected(self):
        raw=self.archive(self.packet());base=self.capture(raw)
        for mutate in (lambda c:c['run']['repository'].__setitem__('id',1),
                       lambda c:c['run'].__setitem__('head_sha','0'*40),
                       lambda c:c['artifact']['workflow_run'].__setitem__('id',1),
                       lambda c:c['artifact'].__setitem__('name','other'),
                       lambda c:c['artifact'].__setitem__('digest','sha256:'+'0'*64)):
            c=copy.deepcopy(base);mutate(c)
            with self.assertRaises(ValueError):self.verify(raw,c)

    def test_incomplete_failed_or_expired_execution_rejects(self):
        raw=self.archive(self.packet());base=self.capture(raw)
        for mutate in (lambda c:c['run'].__setitem__('conclusion','failure'),
                       lambda c:c['jobs']['jobs'][0].__setitem__('conclusion','cancelled'),
                       lambda c:c['jobs']['jobs'][1]['steps'][-1].__setitem__('conclusion','skipped'),
                       lambda c:c['artifact'].__setitem__('expired',True),
                       lambda c:c.__setitem__('retrieved_at','2020-01-01T00:00:00Z')):
            c=copy.deepcopy(base);mutate(c)
            with self.assertRaises(ValueError):self.verify(raw,c)

    def test_missing_duplicate_and_unknown_evidence_records_reject(self):
        for mutate in (lambda p:p['records'].pop(),lambda p:p['records'].append(p['records'][0]),
                       lambda p:p['records'][1].__setitem__('name','unknown')):
            p=self.packet();mutate(p);self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def test_resealed_failed_command_and_test_skip_reject(self):
        for name,key,val in (('command','exit_code',1),('runner-unit-tests','strict_pass',False),
                             ('historical-intake-tests','skipped',[{'test':'skipped'}])):
            p=self.packet();r=next(r for r in p['records'] if r['name']==name)
            r['value'][key]=val;r['sha256']=digest(canonical(r['value']));self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def test_resealed_authority_and_code_digest_forgery_reject(self):
        for mutate in (lambda p:p['producer'].__setitem__('canonical_recertification',True),
                       lambda p:p['code_sha256'].__setitem__(CODE_PATHS[0],'0'*64)):
            p=self.packet();mutate(p);self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def test_replay_mutation_and_shared_namespace_reject(self):
        for name,key,val in (('disconnected-replay','source_unchanged',False),
                             ('disconnected-replay','code_commit','0'*40),
                             ('network-isolation','routable_network',True)):
            p=self.packet('replay');r=next(r for r in p['records'] if r['name']==name)
            r['value'][key]=val;r['sha256']=digest(canonical(r['value']));self.seal(p)
            with self.assertRaises(ValueError):self.inspect(p)

    def test_zip_inventory_modes_and_noncanonical_json_reject(self):
        for name,mode in (('../runtime.json',0o100644),('runtime.json',0o120777),
                          ('other',0o100644),('runtime.json',0o060600)):
            with self.assertRaises(ValueError):unpack(self.archive(self.packet(),name,mode))
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            i=zipfile.ZipInfo('runtime.json');i.external_attr=0o100644<<16
            z.writestr(i,b'{"x":1,"x":2}\n')
        with self.assertRaisesRegex(ValueError,'duplicate_json_key'):unpack(out.getvalue())

    def test_changed_outer_bytes_reject_even_when_zip_still_parseable(self):
        raw=self.archive(self.packet());c=self.capture(raw)
        with self.assertRaises(ValueError):self.verify(raw+b'junk',c)

    def test_bounded_packet_writer_no_overwrite_or_symlink(self):
        p=self.packet()
        with tempfile.TemporaryDirectory() as tmp,patch('runtime_artifact.git',side_effect=self.code_git):
            path=Path(tmp)/'packet'
            value=write_packet(path,p['producer'],p['stage'],p['records'])
            self.assertEqual(value,p['packet_commitment_sha256'])
            with self.assertRaises(FileExistsError):write_packet(path,p['producer'],p['stage'],p['records'])
            link=Path(tmp)/'link';link.symlink_to(path,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):write_packet(link,p['producer'],p['stage'],p['records'])


if __name__=='__main__':unittest.main()
