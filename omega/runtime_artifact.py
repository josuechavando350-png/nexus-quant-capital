"""Bounded CI result artifact, bound to an independently retrieved API capture.

An expected capture digest is an EXTERNAL trust input, not self-authentication.
The CLI performs no API calls. Its result proves correspondence with that capture;
the reviewer must establish the capture's origin separately through GitHub.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import io
import json
from pathlib import Path
import re
import stat
import zipfile

from integrity import canonical, digest, read_regular, strict_json
from historical_intake import need, same, fields, utc
from pft_source_binding import DESTINATION, DESTINATION_ID, FALSE_AUTHORITY, git, verify_commit

LEGACY_SCHEMA = 'nqc.omega.runtime-artifact.v1'
TRANSPORT_SCHEMA = 'nqc.omega.runtime-artifact.v2'
DEPENDENCY_SCHEMA = 'nqc.omega.runtime-artifact.v3'
ECONOMIC_SCHEMA = 'nqc.omega.runtime-artifact.v4'
SCHEMA = 'nqc.omega.runtime-artifact.v5'
BRANCH = 'feat/omega-h2-executable-audit-20261022'
WORKFLOW = '.github/workflows/omega-h2-audit.yml'
ROOT = Path(__file__).resolve().parents[1]
MAX_PACKET = 1024 * 1024
MAX_ARCHIVE = MAX_PACKET + 65536
LEGACY_CODE_PATHS = ('omega/historical_intake.py','omega/evidence_store.py',
              'omega/historical_pipeline.py','omega/runtime_artifact.py',
              'omega/integrity.py','omega/h2_actions.py','omega/isolation.py',WORKFLOW)
TRANSPORT_CODE_PATHS = LEGACY_CODE_PATHS + ('omega/rust_store_intake.py','omega/rust_store_bridge.rs')
DEPENDENCY_CODE_PATHS = TRANSPORT_CODE_PATHS + ('omega/dependency_intake.py',)
ECONOMIC_CODE_PATHS = DEPENDENCY_CODE_PATHS + ('omega/execution_intake.py', 'omega/audit.py',
                                    'omega/architecture_v3.json')
CODE_PATHS = ECONOMIC_CODE_PATHS + ('omega/inclusion_fee_intake.py',)


def reject_authority(value):
    if type(value) is dict:
        for key,val in value.items():
            if key in set(FALSE_AUTHORITY) | {'can_sign','can_broadcast','can_spend',
                    'nqc_profitability_proven','nqc_execution_proven','current_market_coverage_proven'}:
                need(val is False,'runtime_authority_forbidden:'+key)
            reject_authority(val)
    elif type(value) is list:
        for val in value:reject_authority(val)


def inspect_packet(packet, *, expected_producer, expected_tree, stage, root=ROOT):
    need(type(packet) is dict and set(packet)=={'schema','producer','stage','records',
        'code_sha256','packet_commitment_sha256'},'packet_shape')
    need(packet['schema'] in (LEGACY_SCHEMA, TRANSPORT_SCHEMA, DEPENDENCY_SCHEMA, ECONOMIC_SCHEMA, SCHEMA) and packet['stage']==stage
         and stage in ('forks','replay'),'packet_scope')
    modern = packet['schema'] != LEGACY_SCHEMA
    dependent = packet['schema'] in (DEPENDENCY_SCHEMA, ECONOMIC_SCHEMA, SCHEMA)
    economic = packet['schema'] in (ECONOMIC_SCHEMA, SCHEMA)
    inclusion = packet['schema'] == SCHEMA
    need(packet['packet_commitment_sha256']==digest(canonical({
        k:v for k,v in packet.items() if k!='packet_commitment_sha256'})),'packet_commitment')
    reject_authority(packet)
    identity=packet['producer']
    fields(identity,{'repository':DESTINATION,'repository_id':DESTINATION_ID,
        'commit':expected_producer,'tree':expected_tree,'workflow_path':WORKFLOW,
        'workflow_sha':expected_producer,'artifact_id':None,'canonical_recertification':False,
        'identity_basis':'RUNNER_CONTEXT_PENDING_INDEPENDENT_API_READBACK'},'producer')
    for name in ('run_id','run_attempt'):
        need(type(identity[name]) is int and identity[name]>0,'invalid_run_identity')
    same(packet['code_sha256'],{p:digest(git(root,'show',expected_producer+':'+p))
                               for p in (CODE_PATHS if inclusion else ECONOMIC_CODE_PATHS if economic else DEPENDENCY_CODE_PATHS if dependent else TRANSPORT_CODE_PATHS if modern
                                         else LEGACY_CODE_PATHS)},'producer_code_digests')
    records=packet['records']
    need(type(records) is list and 1<len(records)<100,'record_inventory')
    for r in records:
        need(type(r) is dict and set(r)=={'name','value','sha256'} and type(r['name']) is str
             and type(r['value']) is dict and r['sha256']==digest(canonical(r['value'])),
             'record_integrity')
    counts=Counter(r['name'] for r in records)
    common={'producer','isolation-before','isolation-after','runner-unit-tests',
        'ci-capture-tests','historical-intake-tests','evidence-store-tests',
        'historical-pipeline-tests','runtime-artifact-tests','historical-pipeline','stage-complete'}
    stage_names=({'rpc-preflight','source-binding','blastapi-public','mevblocker-rpc','historical-forks'}
                 if stage=='forks' else {'network-isolation','disconnected-replay'})
    if modern and stage == 'replay': stage_names.add('rust-store-bridge')
    if dependent and stage == 'replay': stage_names.add('dependency-store-bridge')
    if economic and stage == 'replay': stage_names.add('execution-economics')
    if inclusion and stage == 'replay': stage_names.add('inclusion-fees')
    need(set(counts)==common|stage_names|{'command','download'}
         and all(counts[n]==1 for n in common|stage_names),'record_inventory')
    # Exact command inventory inherited from H2 plus retained-capture and four new test suites.
    need(counts['command']==(25 if stage=='forks' else (23 if modern else 22))
         and counts['download']==(2 if stage=='forks' else 4),'command_inventory')
    values={r['name']:r['value'] for r in records if counts[r['name']]==1}
    need(records[0]['name']=='producer' and records[-1]['name']=='stage-complete','record_order')
    same(values['producer'],identity,'record_producer')
    for record in records:
        if record['name']=='command':fields(record['value'],{'exit_code':0},'command')
    same(values['isolation-before'],values['isolation-after'],'isolation_changed')
    fields(values['isolation-after'],{'status':'OMEGA_OFFLINE_ISOLATION_PASS',
        'active_omega_workflows':1,'active_workflow_sha256':packet['code_sha256'][WORKFLOW]},'isolation')
    fields(values['isolation-after']['legacy_result'],{'source_files':531,'disabled_workflows':106,
        'active_workflows':0,'original_objects_checked':True,'status':'ISOLATED_SOURCE_IDENTITY_PASS'},'source_isolation')
    for name in (n for n in common if n.endswith('-tests')):
        tests=values[name]
        fields(tests,{'strict_pass':True,'status':'TESTS_PASS','issues':[],'skipped':[],
            'expected_failures':[],'unexpected_successes':[]},name)
        same(tests['discovered'],tests['successes'],name+'_coverage')
        need(type(tests['tests_run']) is int and tests['tests_run']==len(tests['successes'])>0
             and len(set(tests['successes']))==len(tests['successes']),name+'_count')
        need(tests['report_commitment_sha256']==digest(canonical({
            k:v for k,v in tests.items() if k!='report_commitment_sha256'})),name+'_digest')
    pipeline=values['historical-pipeline']
    fields(pipeline,{'status':'HISTORICAL_PIPELINE_LOCAL_PASS','replica_ledger_byte_identical':True,
        'replica_inventory_byte_identical':True,'revoked_query_rejected':True,
        'revoked_evidence_preserved':True,'real_chain_reorg_tested':False,
        'remote_replication_tested':False,'rust_store_integrated':False,'certified_components':0},'pipeline')
    need(pipeline['report_commitment_sha256']==digest(canonical({
        k:v for k,v in pipeline.items() if k!='report_commitment_sha256'})),'pipeline_commitment')
    if stage=='forks':
        from h2_actions import compare_forks
        a,b=values['blastapi-public'],values['mevblocker-rpc']
        result=compare_forks(a['positive'],b['positive'],a['negative'],b['negative'])
        same(result,values['historical-forks'],'fork_result')
        fields(values['source-binding'],{'producer_commit':expected_producer,
            'producer_tree':expected_tree,'original_ancestry_gate_preserved':True},'binding')
    else:
        result=values['disconnected-replay']
        fields(result,{'code_commit':expected_producer,'code_tree':expected_tree,
            'source_unchanged':True,'current_replay_byte_identical':True,
            'history_replay_byte_identical':True,'closeout_byte_identical':True,
            'source_store_root':'e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03',
            'result_store_root':'e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03'},'replay')
        network=values['network-isolation']
        fields(network,{'interfaces':['lo'],'routable_network':False},'network')
        need(all(type(network.get(k)) is str and re.fullmatch(r'net:\[[0-9]+\]',network[k])
                 for k in ('network_namespace','parent_network_namespace'))
             and network['network_namespace']!=network['parent_network_namespace'],'network_namespace')
        if modern:
            from rust_store_intake import verify_report
            transport = verify_report(values['rust-store-bridge'], root)
            same(transport['network'], network, 'bridge_network_disagrees')
        if dependent:
            from dependency_intake import verify_report as verify_dependency_report
            transport = verify_dependency_report(values['dependency-store-bridge'], root)
            same(transport['network'], network, 'dependency_network_disagrees')
        if economic:
            from execution_intake import verify_replay
            economics = verify_replay(values['execution-economics'], root)
            same(economics['network'], network, 'execution_network_disagrees')
        if inclusion:
            from inclusion_fee_intake import verify_replay as verify_inclusion_replay
            fees = verify_inclusion_replay(values['inclusion-fees'], root)
            same(fees['network'], network, 'inclusion_network_disagrees')
            same(fees['execution_report_commitment'],
                 economics['economic_report']['report_commitment_sha256'], 'inclusion_economics_disagrees')
            same(fees['gas_funding_policy'], economics['economic_report']['gas_funding_policy'],
                 'inclusion_gas_policy_disagrees')
    fields(values['stage-complete'],{'stage':stage,'status':'PHYSICAL_GATE_PASS',
        'producer':identity,'result_sha256':digest(canonical(result)),'certified_components':0},'complete')
    return {'records':len(records),'tests':{n:values[n]['tests_run'] for n in common if n.endswith('-tests')},
            'pipeline_commitment':pipeline['report_commitment_sha256'],
            'physical_result_sha256':digest(canonical(result))}


def write_packet(directory, identity, stage, records, root=ROOT):
    directory=Path(directory).absolute()
    need(not any(p.is_symlink() for p in (directory,*directory.parents)),'symlink_packet_directory')
    directory.mkdir(exist_ok=False)
    packet={'schema':SCHEMA,'producer':identity,'stage':stage,'records':records,
        'code_sha256':{p:digest(read_regular(root/p)) for p in CODE_PATHS}}
    packet['packet_commitment_sha256']=digest(canonical(packet))
    raw=canonical(packet)
    need(len(raw)<=MAX_PACKET,'packet_size_limit')
    inspect_packet(packet,expected_producer=identity['commit'],expected_tree=identity['tree'],stage=stage,root=root)
    with (directory/'runtime.json').open('xb') as f:f.write(raw)
    return packet['packet_commitment_sha256']


def unpack(raw):
    need(len(raw)<=MAX_ARCHIVE,'artifact_size_limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        need(z.namelist()==['runtime.json'] and not z.comment,'artifact_inventory')
        info=z.infolist()[0]
        need(stat.S_ISREG(info.external_attr>>16) and not info.is_dir() and not info.flag_bits&1
             and not info.extra and not info.comment and info.compress_type in (0,8)
             and 0<info.file_size<=MAX_PACKET,'artifact_member')
        with z.open(info) as f:b=f.read(MAX_PACKET+1)
        need(len(b)==info.file_size,'artifact_member_length')
    packet=strict_json(b)
    need(canonical(packet)==b,'packet_not_canonical')
    return packet


def verify_artifact(archive, capture, *, expected_capture_sha256, expected_producer, stage, root=ROOT):
    need(digest(canonical(capture))==expected_capture_sha256,'external_capture_digest')
    run,commit,artifact,jobs=(capture[k] for k in ('run','commit','artifact','jobs'))
    need(type(expected_producer) is str and re.fullmatch('[0-9a-f]{40}',expected_producer),'producer_sha')
    tree=commit['tree']['sha']
    verify_commit(root,expected_producer,tree)
    fields(commit,{'sha':expected_producer},'captured_commit')
    fields(run,{'head_sha':expected_producer,'head_branch':BRANCH,'status':'completed',
        'conclusion':'success','event':'push','path':WORKFLOW},'captured_run')
    for key in ('repository','head_repository'):
        fields(run[key],{'id':DESTINATION_ID,'full_name':DESTINATION,'private':False},'captured_repository')
    fields(run['head_commit'],{'id':expected_producer,'tree_id':tree},'captured_tree')
    fields(artifact['workflow_run'],{'id':run['id'],'head_sha':expected_producer,'head_branch':BRANCH,
        'repository_id':DESTINATION_ID,'head_repository_id':DESTINATION_ID},'artifact_run')
    fields(artifact,{'name':f"omega-runtime-{stage}-{expected_producer}-{run['run_attempt']}",
        'expired':False,'size_in_bytes':len(archive),'digest':'sha256:'+digest(archive)},'artifact_identity')
    need(type(artifact['id']) is int and artifact['id']>0,'artifact_id')
    need(utc(run['created_at'])<=utc(artifact['created_at'])<=utc(run['updated_at'])
         <=utc(capture['retrieved_at'])<utc(artifact['expires_at']),'artifact_capture_time')
    fields(jobs,{'total_count':2},'jobs')
    need(type(jobs['jobs']) is list and len(jobs['jobs'])==2,'job_count')
    by={j['name']:j for j in jobs['jobs']}
    need(set(by)=={'audit (forks)','audit (replay)'},'job_inventory')
    for j in by.values():
        fields(j,{'run_id':run['id'],'head_sha':expected_producer,'status':'completed',
            'conclusion':'success'},'job')
        need(all(s['conclusion']=='success' for s in j['steps']),'job_step_failure')
        need('Retain bounded runtime evidence' in {s['name'] for s in j['steps']},'upload_step_missing')
    packet=unpack(archive)
    fields(packet['producer'],{'run_id':run['id'],'run_attempt':run['run_attempt']},'packet_run')
    summary=inspect_packet(packet,expected_producer=expected_producer,expected_tree=tree,stage=stage,root=root)
    from historical_pipeline import exercise
    import tempfile
    with tempfile.TemporaryDirectory(prefix='omega-artifact-replay-') as tmp:
        replayed_pipeline=exercise(Path(tmp)/'pipeline',directory=root/'omega/evidence',root=root)
    retained_pipeline=next(r['value'] for r in packet['records'] if r['name']=='historical-pipeline')
    same(retained_pipeline,replayed_pipeline,'pipeline_does_not_reproduce')
    result={'schema':'nqc.omega.runtime-artifact-verification.v1',
        'status':'RUNTIME_ARTIFACT_MATCHES_EXTERNAL_CAPTURE','stage':stage,
        'producer_commit':expected_producer,'producer_tree':tree,'run_id':run['id'],
        'run_attempt':run['run_attempt'],'artifact_id':artifact['id'],'artifact_sha256':digest(archive),
        'external_capture_sha256':expected_capture_sha256,'packet_commitment_sha256':packet['packet_commitment_sha256'],
        'trust_basis':'CALLER_SUPPLIED_OUT_OF_BAND_CAPTURE_DIGEST','new_api_query_performed':False,
        'canonical_recertification':False,'census_closed':False,'certified_components':0,**summary}
    result['report_commitment_sha256']=digest(canonical(result))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--expected-capture-sha256',required=True)
    p.add_argument('--expected-producer',required=True)
    p.add_argument('--stage',choices=('forks','replay'),required=True)
    p.add_argument('--report',type=Path)
    a=p.parse_args()
    try:
        result=verify_artifact(read_regular(a.archive,MAX_ARCHIVE),strict_json(read_regular(a.capture)),
            expected_capture_sha256=a.expected_capture_sha256,expected_producer=a.expected_producer,stage=a.stage)
        if a.report:
            with a.report.open('xb') as f:f.write(canonical(result))
        print(json.dumps(result,sort_keys=True));return 0
    except (ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile) as error:
        print(json.dumps({'status':'RUNTIME_ARTIFACT_BLOCKED','reason':str(error),'census_closed':False}));return 1


if __name__=='__main__':raise SystemExit(main())
