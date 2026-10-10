#!/usr/bin/env python3
"""Authenticate checkpoint 005 and extend a fresh, verified checkpoint-004 copy."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import collect as c

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = 'be2b776a3aa55c70f72c75a7ce2c36496aa698567b6ef23dd260b451e43b4758'
BASE_SHA = 'bada46df7f5f3fc4832b86cbba787d66a417d52f1a7be73bfe45feb906ff1f67'
SOURCE_SHA = '880eee9ce166b3a477b80a495ed804bbfc530c8a334c1f39dc5148134b00287a'
SHARED = ['collect.py', 'resume.py', 'resume-plan.json', 'assets.json', 'anchors.jsonl.gz']


def archive_bytes():
    manifest = json.loads((HERE / 'sequential-checkpoint-005-delta.parts.json').read_bytes())
    names = [f'sequential-checkpoint-005-delta.zip.part-{i:03d}' for i in range(1, 8)]
    c.need([p['path'] for p in manifest['parts']] == names, 'archive part inventory/order')
    result = []
    for part in manifest['parts']:
        raw = (HERE / part['path']).read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        c.need((len(raw), c.sha(raw), blob) == (part['bytes'], part['sha256'], part['git_blob']), 'part bytes/digests')
        result.append(raw)
    raw = b''.join(result)
    c.need(len(raw) == manifest['bytes'] == 20935131
           and c.sha(raw) == manifest['sha256'] == ARCHIVE_SHA, 'full delta archive commitment')
    return raw


def read_delta(raw):
    c.need(c.sha(raw) == ARCHIVE_SHA, 'delta archive digest')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        c.need(len(names) == len(set(names)) == 68
               and all(Path(n).name == n for n in names), 'delta member inventory')
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files['manifest.json'])
    c.need(manifest['schema'] == 'nqc-closed-oracle-delta-005-v1'
           and manifest['base_evidence_commit'] == 'a13e195b909cc55062ff2406a29a2a7f15f43867'
           and manifest['base_readback_sha256'] == c.sha(files['base-readback.json']) == BASE_SHA
           and manifest['snapshot_source_sha256'] == c.sha(files['snapshot.py']) == SOURCE_SHA,
           'delta base/snapshot source identity')
    entries = manifest['members']
    c.need(len(entries) == 67 and {x['path'] for x in entries} == set(files) - {'manifest.json'}, 'member manifest')
    for item in entries:
        c.need((len(files[item['path']]), c.sha(files[item['path']])) == (item['bytes'], item['sha256']),
               'member bytes/digest')
    return files


def combined(base, files):
    prior_raw = (HERE / 'checkpoint-004/continuation-readback.json').read_bytes()
    c.need(c.sha(prior_raw) == BASE_SHA and files['base-readback.json'] == prior_raw, 'published base identity')
    prior = json.loads(prior_raw)
    progress = json.loads(files['progress.json'])
    old_progress_raw = (base / 'progress.json').read_bytes()
    c.need(c.sha(old_progress_raw) == prior['checkpoint_sha256'], 'base snapshot identity')
    c.need(progress['completed_files'][:80] == prior['closed_file_commitments']
           and len(progress['completed_files']) == 139, 'closed prefix conservation')
    c.need(progress['status'] == 'RUNNING' and progress['failure'] is None
           and progress['observed_blocks'] == 139920, 'exact checkpoint state')
    output = {'progress.json': files['progress.json']}
    for name in SHARED:
        c.need((base / name).read_bytes() == files[name], 'shared source or anchors changed')
        output[name] = files[name]
    for i, item in enumerate(progress['completed_files']):
        name = f'capture-{i * 1000:06d}.jsonl.gz'
        c.need(item['file'] == name and item['plan_offset'] == i * 1000
               and item['requested_blocks'] == item['observed_blocks'] == 1000
               and item['complete'] is True, 'closed capture order/completeness')
        raw = (base / name).read_bytes() if i < 80 else files[name]
        c.need((len(raw), c.sha(raw)) == (item['bytes'], item['sha256']), 'closed capture identity')
        output[name] = raw
    return output


def prepare(base, out):
    files = combined(base, read_delta(archive_bytes()))
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items():
        with (out / name).open('xb') as stream:
            stream.write(raw)
    return {'schema': 'nqc-oracle-checkpoint-005-assembly-v1', 'archive_sha256': ARCHIVE_SHA,
            'base_readback_sha256': BASE_SHA, 'preparer_sha256': c.sha(Path(__file__).read_bytes()),
            'base_closed_files': 80, 'new_closed_files': 59, 'all_closed_files': 139,
            'prices_verified_by_this_preparer': False, 'census_closed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(prepare(args.base, args.out), sort_keys=True))
