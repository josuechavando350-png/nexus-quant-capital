#!/usr/bin/env python3
"""Authenticate terminal checkpoint 007; assemble a fresh exact full prefix."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import collect as c

HERE = Path(__file__).resolve().parent
BASE_SHA = 'd1211693d2e2a1f3df589b2d163a88733aceb535e50f023cf62cef2979137527'
SHARED = ['collect.py','resume.py','resume-plan.json','assets.json','anchors.jsonl.gz']

def archive_bytes():
    lock=json.loads((HERE/'sequential-checkpoint-007-delta.parts.json').read_bytes())
    need_names=[f'sequential-checkpoint-007-delta.zip.part-{i:03d}' for i in range(1,len(lock['parts'])+1)]
    c.need([p['path'] for p in lock['parts']]==need_names,'archive part order')
    parts=[]
    for part in lock['parts']:
        raw=(HERE/part['path']).read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        c.need((len(raw),c.sha(raw),blob)==(part['bytes'],part['sha256'],part['git_blob']),'part bytes/digests')
        parts.append(raw)
    raw=b''.join(parts)
    c.need(len(raw)==lock['bytes'] and c.sha(raw)==lock['sha256'],'full archive commitment')
    return raw

def read_delta(raw):
    lock=json.loads((HERE/'sequential-checkpoint-007-delta.parts.json').read_bytes())
    c.need(c.sha(raw)==lock['sha256'] and len(raw)==lock['bytes'],'delta archive identity')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        c.need(len(names)==len(set(names))==55 and all(Path(n).name==n for n in names),'delta member inventory')
        files={n:z.read(n) for n in names}
    m=json.loads(files['manifest.json'])
    c.need(m['schema']=='nqc-closed-oracle-terminal-delta-007-v1'
           and m['base_evidence_commit']=='3c8e9117f09ea3c6a076ab57e30642f8a165a0fe'
           and m['base_readback_sha256']==c.sha(files['base-readback.json'])==BASE_SHA,'base identity')
    c.need(files['snapshot.py']==(HERE/'snapshot_terminal_seven.py').read_bytes()
           and m['snapshot_source_sha256']==c.sha(files['snapshot.py']),'snapshot source identity')
    entries=m['members']
    c.need(len(entries)==54 and {x['path'] for x in entries}==set(files)-{'manifest.json'},'member manifest')
    for item in entries:
        raw=files[item['path']]
        c.need((len(raw),c.sha(raw))==(item['bytes'],item['sha256']),'member identity')
    return files

def combined(base, files):
    prior_raw=(HERE/'checkpoint-006/continuation-readback.json').read_bytes()
    c.need(c.sha(prior_raw)==BASE_SHA and files['base-readback.json']==prior_raw,'published base identity')
    prior=json.loads(prior_raw)
    c.need(c.sha((base/'progress.json').read_bytes())==prior['checkpoint_sha256'],'base snapshot identity')
    raw=files['progress.json'];doc=json.loads(raw)
    c.need(files['acquisition.json']==raw,'terminal files identity')
    c.need(doc['status']=='COMPLETE_REQUESTED_MISSING_BLOCKS' and doc['failure'] is None
           and type(doc['observed_blocks']) is int
           and doc['observed_blocks']==doc['requested_blocks']==209866,'terminal completeness')
    items=doc['completed_files']
    c.need(items[:165]==prior['closed_file_commitments'] and len(items)==210,'closed prefix conservation')
    output={'progress.json':raw,'acquisition.json':raw}
    for name in SHARED:
        c.need((base/name).read_bytes()==files[name],'shared source or anchors changed')
        output[name]=files[name]
    for i,item in enumerate(items):
        count=min(1000,209866-i*1000)
        name=f'capture-{i*1000:06d}.jsonl.gz'
        c.need(item['file']==name and item['plan_offset']==i*1000 and item['complete'] is True
               and item['requested_blocks']==item['observed_blocks']==count,'closed file coordinate/count')
        raw=(base/name).read_bytes() if i<165 else files[name]
        c.need((len(raw),c.sha(raw))==(item['bytes'],item['sha256']),'closed capture identity')
        output[name]=raw
    return output

def prepare(base,out):
    files=combined(base,read_delta(archive_bytes()))
    out.mkdir(parents=True,exist_ok=False)
    for name,raw in files.items():
        with (out/name).open('xb') as f:f.write(raw)
    return {'schema':'nqc-oracle-checkpoint-007-assembly-v1','base_readback_sha256':BASE_SHA,
        'base_closed_files':165,'new_closed_files':45,'all_closed_files':210,
        'new_blocks_preserved':44866,'prices_verified_by_preparer':False,'census_closed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.base,a.out),sort_keys=True))
