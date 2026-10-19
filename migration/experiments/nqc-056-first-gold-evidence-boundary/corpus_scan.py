"""Bounded identifier search in frozen Git experiment history; no acquisition.

Does not execute/extract archived code, authenticate chains or prove global absence.
Only matching identifiers and metadata are emitted, never unrelated file contents.
"""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TX='0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4'
MARKET='0x0eed5a89c7d397d02fd0b9b8e42811ca67e50ed5aeaa4f22e506516c716cfbbf'
PUF='0xd9a442856c234a39a81a089c06451ebaa4306a72'
LIMIT=64*1024*1024
NEEDLES={'transaction_hex':TX[2:].encode(),'transaction_binary':bytes.fromhex(TX[2:]),
    'market_hex':MARKET[2:].encode(),'market_binary':bytes.fromhex(MARKET[2:]),
    'block_decimal':b'26104570','block_hex':hex(26104570)[2:].encode(),
    'block_binary':(26104570).to_bytes(4,'big'),
    'parent_decimal':b'26104569','parent_hex':hex(26104569)[2:].encode(),
    'parent_binary':(26104569).to_bytes(4,'big'),
    'pufETH_address':PUF[2:].encode(),'pufETH_binary':bytes.fromhex(PUF[2:]),'pufETH_symbol':b'pufeth'}


def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args])


def scan_bytes(raw, name, hits, skipped, stats, depth=0):
    stats['objects_or_members_scanned']+=1
    low=raw.lower()
    found=[label for label,needle in NEEDLES.items() if needle in (raw if label.endswith('_binary') else low)]
    if found:
        hits.append({'member':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'matches':found})
    if depth>=6:
        skipped.append({'member':name,'reason':'depth limit'});return
    try:
        if raw.startswith(b'PK\x03\x04') or name.endswith(('.zip','.pyz')):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in sorted(archive.infolist(),key=lambda x:x.filename):
                    if item.is_dir():continue
                    target=name+'!/'+item.filename
                    if item.file_size>LIMIT or item.flag_bits&1:
                        skipped.append({'member':target,'reason':'oversize or encrypted ZIP member'});continue
                    scan_bytes(archive.read(item),target,hits,skipped,stats,depth+1)
        elif raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:decoded=f.read(LIMIT+1)
            if len(decoded)>LIMIT:skipped.append({'member':name,'reason':'gzip expansion limit'})
            else:scan_bytes(decoded,name+'!/gunzip',hits,skipped,stats,depth+1)
        elif len(raw)>262 and raw[257:262]==b'ustar':
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
                for item in sorted(archive.getmembers(),key=lambda x:x.name):
                    if not item.isfile():continue
                    target=name+'!/'+item.name
                    if item.size>LIMIT:skipped.append({'member':target,'reason':'tar expansion limit'});continue
                    scan_bytes(archive.extractfile(item).read(),target,hits,skipped,stats,depth+1)
        elif name.endswith('.b64'):
            decoded=base64.b64decode(b''.join(raw.split()),validate=True)
            if len(decoded)>LIMIT:skipped.append({'member':name,'reason':'base64 expansion limit'})
            else:scan_bytes(decoded,name+'!/base64',hits,skipped,stats,depth+1)
    except (ValueError,OSError,zipfile.BadZipFile,tarfile.TarError) as exc:
        skipped.append({'member':name,'reason':'container decoding failed: '+type(exc).__name__})


def run():
    snapshot=json.loads((HERE/'REF_SNAPSHOT.json').read_text())
    tips=sorted({r['commit'] for r in snapshot['refs']})
    listed=git('rev-list','--objects',*tips,'--','migration/experiments').decode().splitlines()
    proc=subprocess.run(['git','-C',str(REPO),'cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],
        input=('\n'.join(r.split(' ',1)[0] for r in listed)+'\n').encode(),stdout=subprocess.PIPE,check=True)
    objects=[];hits=[];skipped=[];stats={'objects_or_members_scanned':0}
    for row,meta in zip(listed,proc.stdout.decode().splitlines()):
        blob,kind,size=meta.split()
        if kind!='blob':continue
        path=row.split(' ',1)[1]
        raw=git('cat-file','blob',blob)
        assert len(raw)==int(size)
        objects.append({'blob':blob,'bytes':len(raw),'path_hint':path,'sha256':hashlib.sha256(raw).hexdigest()})
        before=len(hits)
        scan_bytes(raw,path,hits,skipped,stats)
        for hit in hits[before:]:hit['containing_git_blob']=blob
    objects.sort(key=lambda r:r['blob']);hits.sort(key=lambda r:(r['containing_git_blob'],r['member']))
    return {'schema':'nqc056-corpus-search-v1','scope':'All Git blobs reachable from frozen remote tips under migration/experiments, including historical versions and supported containers',
        'refs':len(snapshot['refs']),'unique_tips':len(tips),'unique_blobs':len(objects),
        'raw_blob_bytes':sum(r['bytes'] for r in objects),'stats':stats,'objects':objects,
        'identifier_hits':hits,'container_limits_or_errors':skipped,
        'limitations':['Identifier search is not cryptographic chain verification or an exhaustive semantic proof of absence.',
            'Only literal text/binary identifiers and ZIP/gzip/tar/base64 envelopes are searched; unknown encodings/encrypted contents are not decoded.',
            'Scope is frozen repository experiment history, not external accounts or provider archives.'],
        'network_requests':0,'commercial_admission':False}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
