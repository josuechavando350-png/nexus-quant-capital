#!/usr/bin/env python3
"""Extract pinned, existing coverage evidence into a fresh offline working copy."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

import collect as c

HERE = Path(__file__).resolve().parent
RECOVERY_SHA = '63265e4a0910dbbea3f8ab0966b494ad4d08b44b42acd79d0c8727c15b4d5feb'
ORIGINAL_SHA = 'd73716fa61495906c9cbfdcc4442c25804cd47550a9de0f4a32ca287459e2e50'
SECOND_SHA = '913b4c530d53207e450ff72e21ad0a0b420af0b80574faee329c161f3daca18c'
THIRD_SHA = '6b5691d546ee3eb4aa291a7f32ef52689826021fb791136b67fa84c8e6fbd0c0'


def unpack(raw, digest, count, out):
    c.need(c.sha(raw) == digest, 'archive digest')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        c.need(len(names) == len(set(names)) == count, 'archive inventory')
        for name in names:
            path = PurePosixPath(name)
            c.need(not path.is_absolute() and '..' not in path.parts, 'unsafe member')
        out.mkdir(parents=True, exist_ok=False)
        for name in names:
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(archive.read(name))


def prepare(recovery, out):
    c.need(c.sha(recovery.read_bytes()) == RECOVERY_SHA, 'recovery version-four commitment')
    out.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(recovery) as archive:
        raw = archive.read('original-oracle-evidence.zip')
    c.need(c.sha(raw) == ORIGINAL_SHA, 'original oracle commitment')
    original = out / 'original-oracle-evidence.zip'
    original.write_bytes(raw)
    unpack(raw, ORIGINAL_SHA, 4397, out / 'original')
    parts = json.loads((HERE / 'sequential-checkpoint-002.parts.json').read_bytes())
    c.need(parts['sha256'] == SECOND_SHA and parts['bytes'] == 15143401, 'second archive identity')
    assembled = []
    for item in parts['parts']:
        c.need(Path(item['path']).name == item['path'], 'unsafe part')
        raw = (HERE / item['path']).read_bytes()
        c.need(c.sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'part commitment')
        assembled.append(raw)
    unpack(b''.join(assembled), SECOND_SHA, 50, out / 'second')
    unpack((HERE / 'sequential-checkpoint-003-delta.zip').read_bytes(), THIRD_SHA, 22, out / 'third')
    unpack((HERE / 'sequential-checkpoint-001.zip').read_bytes(),
           '4b594dbcc1e32ff8569adaa0a2cea3e374648e5c0d3d3331f0ad5f81b7e83633', 10, out / 'first')
    prefix = out / 'closed-prefix'
    prefix.mkdir()
    first, latest = out / 'second', out / 'third'
    progress = json.loads((latest / 'progress.json').read_bytes())
    base = json.loads((first / 'progress.json').read_bytes())
    c.need(progress['completed_files'][:43] == base['completed_files'], 'checkpoint prefix identity')
    for name in ['collect.py', 'resume.py', 'resume-plan.json', 'assets.json']:
        c.need((first / name).read_bytes() == (latest / name).read_bytes(), 'shared source substitution')
    for name, source in [('progress.json', latest), ('anchors.jsonl.gz', first)] + [
            (name, latest) for name in ['collect.py', 'resume.py', 'resume-plan.json', 'assets.json']]:
        (prefix / name).write_bytes((source / name).read_bytes())
    for item in progress['completed_files']:
        c.need(Path(item['file']).name == item['file'], 'unsafe capture')
        source = first if item['plan_offset'] < 43000 else latest
        raw = (source / item['file']).read_bytes()
        c.need(c.sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'closed capture commitment')
        (prefix / item['file']).write_bytes(raw)
    # These archives include all exact captures, failures and source manifests.
    for filename, digest, count, directory in [
        ('oracle-pilot-evidence.zip', 'eef4643d627d3d27b6fd0acaa54afb94dbfdf794bf5b91832acb2b930e53dc35', 37, 'pilot-bundle'),
        ('oracle-rate-limited-evidence.zip', 'efe884429fdc43af0231406ab951acb23a864ee21812849fa49b0ab323a03318', 220, 'partial-bundle'),
    ]:
        unpack((HERE / filename).read_bytes(), digest, count, out / directory)
    unpack((HERE.parent / 'full_window_recovery/complete-historical-evidence.zip').read_bytes(),
           'f5683de132f26671e62ee31a82c9e1c05fcaf2ff8e7a0a8ad2a0c447bc9efeeb', 699, out / 'full-window')
    return {'original': str(original), 'primary': str(out / 'original/drpc'),
            'checkpoint': str(prefix), 'pilot': str(out / 'pilot-bundle/pilot'),
            'partial': str(out / 'partial-bundle/remaining'), 'full_window': str(out / 'full-window')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recovery', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(prepare(args.recovery, args.out), sort_keys=True))
