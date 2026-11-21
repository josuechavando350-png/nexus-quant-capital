"""Run only Scorecard's License check on one immutable NQC revision and a public notice."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import strict_json

DIGEST = '9b2868dec1ca9f9c32fda97caeb7f3aba28bc74c1f982bd222f16749fe4b9211'
RELEASE = {'version': 'v5.7.0', 'commit': 'd7552fb3cdc05e9f6426177d3328887304fce554'}
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def snapshot(work, env):
    def git(*args):
        return subprocess.check_output(['/usr/bin/git', '--no-replace-objects', '-C', str(ROOT), *args],
                                       env=env, timeout=60)
    commit = git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    entries = {}
    for item in git('ls-tree', '-rz', commit).split(b'\0'):
        if item:
            meta, raw_name = item.split(b'\t', 1)
            mode, kind, digest = meta.decode().split()
            if mode not in ('100644', '100755') or kind != 'blob':
                raise EvidenceError('unsupported Git tree entry in license snapshot')
            entries[raw_name.decode()] = digest
    source = work/'source'
    source.mkdir()
    archive_path = work/'source.tar'
    git('archive', '--format=tar', '-o', str(archive_path), commit)
    with tarfile.open(archive_path) as archive:
        for entry in archive:
            if entry.isdir():
                continue
            if not entry.isfile() or entry.name not in entries or Path(entry.name).is_absolute() or '..' in Path(entry.name).parts:
                raise EvidenceError('unexpected path in license snapshot')
            raw = archive.extractfile(entry).read()
            blob = b'blob ' + str(len(raw)).encode() + b'\0' + raw
            if hashlib.sha1(blob).hexdigest() != entries.pop(entry.name):
                raise EvidenceError('license snapshot differs from tracked Git blob')
            path = source/entry.name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(raw)
    if entries:
        raise EvidenceError('missing tracked files in license snapshot')
    return commit, source


def check(binary, source, env):
    output = subprocess.check_output([*ISOLATE, str(binary), '--local', str(source), '--checks=License',
                                      '--show-details', '--format=json'], cwd=binary.parent, env=env,
                                     stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90)
    doc = strict_json(output)
    if doc['scorecard'] != RELEASE or doc['repo']['name'] != source.as_uri() or len(doc['checks']) != 1:
        raise EvidenceError('unbound Scorecard license report')
    row = doc['checks'][0]
    score = row['score']
    if (row['name'] != 'License' or type(score) is not int or score not in (0, 9, 10)
            or row['reason'] != ('license file detected' if score else 'license file not detected')):
        raise EvidenceError('invalid or incomplete Scorecard License check')
    return {'score': score, 'reason': row['reason']}


def build(executable, notices):
    if not notices:
        raise EvidenceError('Scorecard requires verified public notices for its positive control')
    name = next((n for n in sorted(notices) if notices[n].strip()), None)
    if name is None:
        raise EvidenceError('empty Scorecard license control')
    with tempfile.TemporaryDirectory(prefix='nqc-license-score-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'LC_ALL': 'C', 'PATH': '/usr/bin:/bin', 'TZ': 'UTC'}
        binary = work/'scorecard'
        copy_release('Scorecard', executable, binary, DIGEST)
        commit, source = snapshot(work, env)
        result = check(binary, source, env)
        control = work/'control'
        control.mkdir()
        (control/'LICENSE').write_bytes(notices[name])
        positive = check(binary, control, env)
        if positive['score'] == 0:
            raise EvidenceError('Scorecard failed the local license-file control')
        return {'producer': RELEASE, 'executable_sha256': DIGEST, 'nqc_commit': commit,
                'check': 'License', 'repository_result': result,
                'positive_control': {'notice': name, 'sha256': sha(notices[name]), **positive}}
