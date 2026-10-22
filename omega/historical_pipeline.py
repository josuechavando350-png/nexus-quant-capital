"""End-to-end historical intake, durable local publication, and verified restore.

Every read rebuilds the ledger from its retained original artifacts. SQLite and
snapshot hashes alone never grant authenticity to altered economic records.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from evidence_store import (admit, audit_store, create, export_store, read_batch,
                            restore_store, revoke, safe_path)
from historical_intake import (EVIDENCE, ROOT, build_ledger, need, same, verify_ledger)
from integrity import canonical, digest, read_regular, strict_json

SOURCE_NAMES = frozenset({'historical-intake-pin.json', 'rmc016-events.zip',
    'rmc016-receipts.zip', 'rmc016-events-metadata.json', 'rmc016-receipts-metadata.json',
    'rmc016-legs.zip', 'rmc016-legs-metadata.json'})
LEDGER_NAME = 'historical-ledger.json'


def ingest(store, directory=EVIDENCE, root=ROOT):
    objects = {name: read_regular(Path(directory)/name) for name in SOURCE_NAMES}
    # Freeze reads once before both validation and storage.
    with tempfile.TemporaryDirectory(prefix='omega-pipeline-input-') as tmp:
        for name, raw in objects.items(): (Path(tmp)/name).write_bytes(raw)
        ledger = build_ledger(Path(tmp), root)
    objects[LEDGER_NAME] = canonical(ledger)
    batch = admit(store, objects)
    return {'batch': batch, 'ledger': ledger,
            'journal_head': audit_store(store)['journal_head']}


def query(store, batch, *, root=ROOT, expected_head=None):
    audit_store(store, expected_head)
    objects = read_batch(store, batch)
    need(set(objects) == SOURCE_NAMES | {LEDGER_NAME}, 'pipeline_inventory_mismatch')
    with tempfile.TemporaryDirectory(prefix='omega-pipeline-read-') as tmp:
        for name in SOURCE_NAMES: (Path(tmp)/name).write_bytes(objects[name])
        ledger = verify_ledger(strict_json(objects[LEDGER_NAME]), Path(tmp), root)
    return ledger


def write_new(path, value):
    safe_path(path)
    with Path(path).open('xb') as f:
        f.write(canonical(value)); f.flush(); os.fsync(f.fileno())


def exercise(output, *, directory=EVIDENCE, root=ROOT):
    """Publish real data and independently replay a local replica before reporting."""
    output = Path(output).absolute()
    need(not any(p.is_symlink() for p in (output,*output.parents)), 'symlink_output')
    output.mkdir(exist_ok=False)
    store = create(output/'evidence.sqlite')
    imported = ingest(store,directory,root)
    batch, head = imported['batch'], imported['journal_head']
    original = query(store,batch,root=root,expected_head=head)
    snapshot = export_store(store)
    write_new(output/'snapshot.json',snapshot)
    replica = output/'replica.sqlite'
    restore_store(replica,strict_json(read_regular(output/'snapshot.json',32*1024*1024)))
    recovered = query(replica,batch,root=root,expected_head=head)
    same(recovered,original,'replica_ledger_mismatch')
    same(export_store(replica),snapshot,'replica_snapshot_mismatch')
    # Recovery/revocation scenario on an expendable copy, not a claim of a real reorg.
    revocation_probe = output/'revocation-probe.sqlite'
    restore_store(revocation_probe,snapshot)
    revoke(revocation_probe,batch,'CONTROLLED_LOCAL_REVOCATION_TEST',
           canonical({'scope':'TEST_ONLY_NOT_A_REAL_CHAIN_REORGANIZATION','batch':batch}))
    try:
        query(revocation_probe,batch,root=root)
    except ValueError as exc:
        need(str(exc)=='batch_inactive_or_missing','unexpected_revocation_error')
    else:
        raise ValueError('revoked_batch_still_queryable')
    need(read_batch(revocation_probe,batch,include_revoked=True)[LEDGER_NAME]==canonical(original),
         'revocation_deleted_evidence')
    report = {'schema':'nqc.omega.historical-pipeline.v1','status':'HISTORICAL_PIPELINE_LOCAL_PASS',
        'batch':batch,'journal_head':head,'snapshot_sha256':snapshot['snapshot_sha256'],
        'ledger_commitment_sha256':original['ledger_commitment_sha256'],
        'summary':original['summary'],'replica_ledger_byte_identical':True,
        'replica_inventory_byte_identical':True,'revoked_query_rejected':True,
        'revoked_evidence_preserved':True,'revocation_scenario':'CONTROLLED_LOCAL_TEST',
        'real_chain_reorg_tested':False,'remote_replication_tested':False,
        'rust_store_integrated':False,'new_acquisition_performed':False,
        'certified_components':0,'census_closed':False,'phase_advance_authorized':False,
        'authorities':original['authorities']}
    report['report_commitment_sha256']=digest(canonical(report))
    write_new(output/'report.json',report)
    return report


def verify_output(output,root=ROOT):
    output=Path(output)
    need(not any(p.is_symlink() for p in (output,*output.absolute().parents)), 'symlink_output')
    need({p.name for p in output.iterdir()} == {'evidence.sqlite','replica.sqlite',
         'revocation-probe.sqlite','snapshot.json','report.json'}, 'pipeline_output_inventory')
    report=strict_json(read_regular(output/'report.json'))
    need(report.get('report_commitment_sha256')==digest(canonical({
        k:v for k,v in report.items() if k!='report_commitment_sha256'})), 'pipeline_report_digest')
    for dbname in ('evidence.sqlite','replica.sqlite'):
        ledger=query(output/dbname,report['batch'],root=root,expected_head=report['journal_head'])
        same(ledger['summary'],report['summary'],'pipeline_summary_mismatch')
        same(ledger['ledger_commitment_sha256'],report['ledger_commitment_sha256'],'pipeline_ledger_mismatch')
        snapshot=export_store(output/dbname)
        need(snapshot['snapshot_sha256']==report['snapshot_sha256'],'pipeline_snapshot_mismatch')
    same(strict_json(read_regular(output/'snapshot.json',32*1024*1024)),snapshot,
         'exported_snapshot_mismatch')
    probe = audit_store(output/'revocation-probe.sqlite')
    need(probe['active_batches']==[] and probe['revoked_batches']==[report['batch']]
         and probe['event_count']==2, 'revocation_probe_mismatch')
    need(read_batch(output/'revocation-probe.sqlite',report['batch'],include_revoked=True)
         == read_batch(output/'evidence.sqlite',report['batch']), 'revoked_evidence_mismatch')
    with tempfile.TemporaryDirectory(prefix='omega-pipeline-verify-') as tmp:
        # Re-exercise from the archived inputs; compare all assertions, not merely booleans.
        objects=read_batch(output/'evidence.sqlite',report['batch'])
        source=Path(tmp)/'input';source.mkdir()
        for name in SOURCE_NAMES:(source/name).write_bytes(objects[name])
        expected=exercise(Path(tmp)/'output',directory=source,root=root)
    same(report,expected,'pipeline_report_differs_from_replay')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-directory',required=True,type=Path)
    p.add_argument('--verify',action='store_true')
    a=p.parse_args()
    try:
        result=verify_output(a.output_directory) if a.verify else exercise(a.output_directory)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,OSError,sqlite3.DatabaseError) as error:
        print(json.dumps({'status':'HISTORICAL_PIPELINE_BLOCKED','reason':str(error),'census_closed':False}))
        return 1


if __name__=='__main__':raise SystemExit(main())
