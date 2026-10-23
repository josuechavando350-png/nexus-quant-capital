"""Declared transitive revocation for authenticated historical evidence batches.

This is local validity policy. It neither discovers undeclared relationships nor
authenticates canonical chain changes, and does not migrate legacy batch IDs.
"""
from pathlib import Path
import tempfile

from evidence_store import (admit, audit_store, create, export_store, read_batch,
                            revoke)
from historical_intake import ROOT, need, same
from historical_pipeline import query
from liquidator_intake import query_identities
from cashflow_intake import query_cashflow
from historical_state_intake import query_state_report
from temporal_intake import query_temporal_report, store_temporal_report
from integrity import canonical, digest
from rust_store_intake import (call, inventory, new_directory, parse_verifier,
                              read_transport, restore_transport, snapshot_objects,
                              write_transport)

SCHEMA='nqc.omega.dependency-transport.v1'
STAGES=('ledger','identities','cashflow','state','temporal')
VALIDATORS=(query,query_identities,query_cashflow,query_state_report,query_temporal_report)


def store_chain(path, root=ROOT):
    """Re-admit authenticated legacy objects under NEW, explicit dependency IDs.

    Each admission is atomic and checks its parents under the writer lock. The
    five-stage sequence is not a single transaction; an interrupted sequence
    retains only complete prior stages. No dependency is inferred from bytes.
    """
    with tempfile.TemporaryDirectory(prefix='omega-dependency-source-') as tmp:
        source=create(Path(tmp)/'original.sqlite')
        result=store_temporal_report(source,root=root)
        snapshot=export_store(source)
        need(len(snapshot['batches'])==len(snapshot['journal'])==5,'historical_stage_inventory')
        original=[e['batch'] for e in snapshot['journal']]
        need(all(e['kind']=='ADMIT' for e in snapshot['journal']),'historical_stage_events')
        batches={};source_batches={}
        for stage,old,validator in zip(STAGES,original,VALIDATORS):
            validator(source,old,root=root)
            parents=[] if not batches else [batches[STAGES[len(batches)-1]]]
            batches[stage]=admit(path,read_batch(source,old),parents=parents)
            source_batches[stage]=old
        same(query_temporal_report(path,batches['temporal'],root),result['report'],
             'dependency_temporal_source_mismatch')
    return {'batches':batches,'source_batches':source_batches,'report':result['report']}


def fixture(path,root=ROOT):
    create(path);chain=store_chain(path,root)
    unrelated=admit(path,{'control.bin':b'TEST_ONLY_UNRELATED_BRANCH_NOT_MARKET_EVIDENCE'},parents=[])
    before=export_store(path)
    original={b:read_batch(path,b) for b in chain['batches'].values()}
    root_batch=chain['batches']['ledger']
    revoke(path,root_batch,'CONTROLLED_DEPENDENCY_REVOCATION_TEST',
           canonical({'test_only':True,'root_batch':root_batch,'canonical_reorg':False}))
    status=audit_store(path)
    same(status['active_batches'],[unrelated],'unrelated_branch_invalidated')
    same(status['revoked_batches'],[root_batch],'wrong_explicit_revocation')
    same(status['invalidated_batches'],sorted(set(chain['batches'].values())-{root_batch}),
         'incomplete_descendant_invalidation')
    for batch in chain['batches'].values():
        try:read_batch(path,batch)
        except ValueError as e:need(str(e)=='batch_inactive_or_missing','unexpected_block_reason')
        else:raise ValueError('dependent_batch_still_active')
        need(read_batch(path,batch,include_revoked=True)==original[batch],'dependent_bytes_lost')
    try:query_temporal_report(path,chain['batches']['temporal'],root)
    except ValueError as e:need(str(e)=='batch_inactive_or_missing','unexpected_query_block')
    else:raise ValueError('dependent_temporal_query_still_active')
    return {'chain':chain,'unrelated':unrelated,'before':before,'status':status}


def expected_fields(path,prepared,root=ROOT):
    snapshot=export_store(path);status=prepared['status'];head=status['journal_head']
    objects=snapshot_objects(snapshot,head)
    return {'schema':SCHEMA,'status':'DEPENDENCY_TRANSPORT_PASS',
        'dependency_policy':'DECLARED_TRANSITIVE_V1','batches':prepared['chain']['batches'],
        'source_batches':prepared['chain']['source_batches'],'unrelated_batch':prepared['unrelated'],
        'temporal_report_commitment':prepared['chain']['report']['report_commitment_sha256'],
        'before_snapshot_id':digest(canonical(prepared['before'])),
        'snapshot_id':digest(canonical(snapshot)),'journal_head':head,
        'inventory':inventory(objects),'store_status':status,
        'dependency_edges':4,'blocked_batches':5,'default_reads_rejected':True,
        'forensic_bytes_preserved':True,'unrelated_branch_active':True,
        'restore_byte_identical':True,'stale_snapshot_rejected':True,
        'whole_chain_atomic':False,'undeclared_dependencies_inferred':False,
        'canonical_reorg_tested':False,'remote_replication_tested':False,
        'certified_components':0,'census_closed':False}


def verify_report(report,root=ROOT):
    need(type(report) is dict and report.get('report_commitment_sha256')==digest(canonical(
         {k:v for k,v in report.items() if k!='report_commitment_sha256'})),'dependency_report_digest')
    network=report.get('network',{})
    # Reuse the strict H19 namespace and standalone verifier format contracts.
    import re
    need(network.get('interfaces')==['lo'] and network.get('routable_network') is False
         and all(type(network.get(k)) is str and re.fullmatch(r'net:\[[0-9]+\]',network[k])
                 for k in ('network_namespace','parent_network_namespace'))
         and network['network_namespace']!=network['parent_network_namespace'],'dependency_network')
    with tempfile.TemporaryDirectory(prefix='omega-dependency-report-') as tmp:
        path=Path(tmp)/'evidence.sqlite';prepared=fixture(path,root)
        expected=expected_fields(path,prepared,root)
    verifier=report['rust_verifier']
    raw=('RMC_004_OFFLINE_VERIFY=PASS\n'+''.join(f'{k}={v}\n' for k,v in verifier.items())).encode()
    same(parse_verifier(raw,expected['inventory']),verifier,'dependency_rust_verifier')
    expected.update(network=network,rust_verifier=verifier)
    expected['report_commitment_sha256']=digest(canonical(expected))
    same(report,expected,'dependency_report_differs_from_sources')
    return report


def exercise(output,bridge,verifier,network,root=ROOT):
    output=new_directory(output,root)
    print('OMEGA_DEPENDENCY_BEGIN',flush=True)
    path=output/'source.sqlite';prepared=fixture(path,root)
    expected=expected_fields(path,prepared,root)
    snapshot=export_store(path);objects=snapshot_objects(snapshot,expected['journal_head'])
    write_transport(output/'input',objects)
    call([bridge,'import',output/'input',output/'rust-store'])
    checked=parse_verifier(call([verifier,'--store',output/'rust-store']),expected['inventory'])
    call([bridge,'export',output/'rust-store',output/'export'])
    need(read_transport(output/'export')==objects,'dependency_transport_bytes_changed')
    recovered=output/'restored.sqlite'
    restore_transport(output/'export',recovered,snapshot_id=expected['snapshot_id'],
                      expected_inventory=expected['inventory'],expected_head=expected['journal_head'])
    same(export_store(recovered),snapshot,'dependency_restore_changed')
    same(audit_store(recovered),prepared['status'],'dependency_status_changed')
    for batch in prepared['chain']['batches'].values():
        try:read_batch(recovered,batch)
        except ValueError as e:need(str(e)=='batch_inactive_or_missing','dependency_restore_error')
        else:raise ValueError('restored_dependent_still_active')
        need(read_batch(recovered,batch,include_revoked=True)==read_batch(path,batch,include_revoked=True),
             'restored_forensic_bytes_changed')
    need(read_batch(recovered,prepared['unrelated'])==read_batch(path,prepared['unrelated']),
         'restored_unrelated_bytes_changed')
    old=prepared['before'];old_head=old['journal'][-1];old_objects=snapshot_objects(old,digest(canonical(old_head)))
    write_transport(output/'old',old_objects)
    try:
        restore_transport(output/'old',output/'must-not-restore.sqlite',
                          snapshot_id=digest(canonical(old)),expected_inventory=inventory(old_objects),
                          expected_head=expected['journal_head'])
    except ValueError as e:need(str(e)=='external_checkpoint_mismatch','wrong_rollback_rejection')
    else:raise ValueError('stale_snapshot_accepted')
    need(not (output/'must-not-restore.sqlite').exists(),'rollback_published_destination')
    print('OMEGA_DEPENDENCY_ROLLBACK_REJECTED',flush=True)
    report={**expected,'network':network,'rust_verifier':checked}
    report['report_commitment_sha256']=digest(canonical(report))
    verify_report(report,root)
    (output/'report.json').write_bytes(canonical(report))
    print('OMEGA_DEPENDENCY_REPORT '+canonical(report).decode().strip(),flush=True)
    return report
