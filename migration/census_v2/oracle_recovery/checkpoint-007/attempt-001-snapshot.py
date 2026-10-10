#!/usr/bin/env python3
"""Preserve the terminal Ethereum continuation delta after checkpoint 006.

Copy-only, no RPC, no worker/process changes. Refuses incomplete acquisitions.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import zipfile

BASE_SHA = 'd1211693d2e2a1f3df589b2d163a88733aceb535e50f023cf62cef2979137527'
BASE_COMMIT = '3c8e9117f09ea3c6a076ab57e30642f8a165a0fe'

def need(value, message):
    if not value: raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def snapshot(live, base_path, out):
    base_raw=base_path.read_bytes()
    need(sha(base_raw)==BASE_SHA,'published checkpoint 006 identity')
    base=json.loads(base_raw)
    raw=(live/'progress.json').read_bytes()
    doc=json.loads(raw)
    need(doc['status']=='COMPLETE_REQUESTED_MISSING_BLOCKS' and doc['failure'] is None,'terminal success required')
    need((live/'acquisition.json').read_bytes()==raw,'matching terminal acquisition/progress')
    need(doc['producer_repository']=='josuechavando350-png/nexus-quant-capital'
         and doc['producer_commit']=='c163b876d3310855f1db45bfc3ab4189b24d865b','original producer')
    need(doc['workers']==1 and doc['maximum_batch_size']==10
         and doc['minimum_request_interval_seconds']>=1.1,'original controls')
    items=doc['completed_files']
    need(items[:165]==base['closed_file_commitments'] and len(items)==210,'exact published prefix')
    need(doc['observed_blocks']==doc['requested_blocks']==209866,'terminal observed count')
    for i,item in enumerate(items):
        count=min(1000,209866-i*1000)
        need(item['file']==f'capture-{i*1000:06d}.jsonl.gz'
             and item['plan_offset']==i*1000 and item['complete'] is True
             and item['requested_blocks']==item['observed_blocks']==count,'closed file coordinate/count')
    out.mkdir(parents=True,exist_ok=False)
    files={'progress.json':raw,'acquisition.json':raw,'base-readback.json':base_raw,
           'snapshot.py':Path(__file__).read_bytes()}
    for name in ['collect.py','resume.py','resume-plan.json','assets.json','anchors.jsonl.gz']:
        files[name]=(live/name).read_bytes()
    for item in items[165:]:
        data=(live/item['file']).read_bytes()
        need(len(data)==item['bytes'] and sha(data)==item['sha256'],'new closed file bytes')
        files[item['file']]=data
    manifest={'schema':'nqc-closed-oracle-terminal-delta-007-v1','base_evidence_commit':BASE_COMMIT,
        'base_readback_sha256':BASE_SHA,'base_closed_files':165,'new_closed_files':45,
        'new_blocks_preserved':44866,'preserved_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'snapshot_source_sha256':sha(files['snapshot.py']),'new_rpc_requests':0,'worker_modified':False,
        'prices_verified_by_snapshot':False,
        'members':[{'path':n,'bytes':len(b),'sha256':sha(b)} for n,b in sorted(files.items())]}
    files['manifest.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    for n,b in files.items():(out/n).write_bytes(b)
    target=out.with_suffix('.zip')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,b)
    report={'archive':str(target),'bytes':target.stat().st_size(),'sha256':sha(target.read_bytes()),
            'members':len(files),'manifest':manifest}
    print(json.dumps({k:v for k,v in report.items() if k!='manifest'},sort_keys=True))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['live','base','out']:p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();snapshot(args.live,args.base,args.out)
