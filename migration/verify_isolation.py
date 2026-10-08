#!/usr/bin/env python3
"""Verify isolated source identity. This never grants certification or executes CI."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess

SOURCE = 'josuechavando350-png/nexus-engine'
SOURCE_ID = 1333360261
COMMIT = 'e259739c9f75fedcd1061d2f78d6b8852e7a3060'
TREE = 'c9cc97b31daa96c3c427c6781333a706e988f342'
TARGET = 'josuechavando350-png/nexus-quant-capital'
TARGET_ID = 1411047452
SOURCE_ROOTS = ('ci/nqc-build-truth/', 'ci/nqc-census/', 'ci/nqc-protocol-fork/',
                'ci/nqc-t35/', 'ci/nqc-t36/', 'ci/nqc-t37/', 'nqc-census/')
LEGACY = 'ci/migration/legacy-workflows/'
TEST_NAMES = {'test_rmc006_recertification_runner.py', 'test_rmc006_recertification_workflow.py',
              'test_rmc011_historical_source_compatibility.py',
              'test_rmc011_independent_discovery_admission.py',
              'test_verify_rmc011_audit_workflow_contract.py',
              'test_verify_rmc011_bounded_family_promotion.py'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_bytes(source_git, path):
    return subprocess.check_output(['git', '-C', str(source_git), 'show', COMMIT+':'+path])


def transform(path, data):
    if Path(path).name not in TEST_NAMES or not path.startswith('ci/nqc-census/'):
        return data
    text = data.decode()
    text = text.replace('.github/workflows/', LEGACY)
    for name in ['nqc-census-aave-discovery.yml', 'nqc-census-capital-terminal-readiness.yml',
                 'nqc-census-capital-bounded-family-rejections.yml']:
        text = text.replace(LEGACY+name, LEGACY+name+'.disabled')
    text = text.replace('WORKFLOW_ROOT / ".github/workflows" / name',
                        'WORKFLOW_ROOT / "ci/migration/legacy-workflows" / (name + ".disabled")')
    text = text.replace('ROOT / ".github/workflows"', 'ROOT / "ci/migration/legacy-workflows"')
    text = text.replace('WORKFLOWS / filename', 'WORKFLOWS / (filename + ".disabled")')
    text = text.replace('WORKFLOWS / DISCOVERY', 'WORKFLOWS / (DISCOVERY + ".disabled")')
    return text.encode()


def verify(root, source_git=None):
    root = Path(root).resolve()
    m = json.loads((root/'migration/source-manifest.json').read_text())
    require(m['schema'] == 'nqc-isolated-import-v1', 'manifest schema')
    require((m['source_repository'], m['source_repository_id'], m['source_commit'], m['source_tree'])
            == (SOURCE, SOURCE_ID, COMMIT, TREE), 'source identity changed')
    require((m['proposed_destination'], m['destination_repository_id']) == (TARGET, TARGET_ID),
            'destination identity changed')
    require(m['authority'] == 'SOURCE_SNAPSHOT_ONLY_NO_NEW_CERTIFICATION', 'authority changed')
    entries = m['files']
    require(len(entries) == 637, 'source membership count')
    expected = set()
    paths = set()
    modified = set()
    source_count = workflow_count = 0
    for item in entries:
        origin, dest = item['source_path'], item['destination_path']
        require(origin not in paths and dest not in expected, 'duplicate mapping')
        paths.add(origin)
        expected.add(dest)
        require(not Path(dest).is_absolute() and '..' not in Path(dest).parts, 'unsafe path')
        if origin.startswith(SOURCE_ROOTS):
            require(dest == origin, 'source path moved')
            source_count += 1
        else:
            require(origin.startswith('.github/workflows/nqc-') and origin.endswith('.yml'), 'unrelated workflow')
            require(dest == LEGACY+Path(origin).name+'.disabled', 'workflow not disabled')
            workflow_count += 1
        path = root/dest
        mode = path.lstat().st_mode
        require(stat.S_ISREG(mode), 'nonregular payload')
        require(('100755' if mode & stat.S_IXUSR else '100644') == item['mode'], 'mode changed')
        data = path.read_bytes()
        require(len(data) == item['bytes'] and sha(data) == item['payload_sha256'], 'payload changed: '+dest)
        if item['source_sha256'] != item['payload_sha256']:
            require(origin.startswith('ci/nqc-census/') and Path(origin).name in TEST_NAMES,
                    'unreviewed source modification')
            require(item['transformation'] == 'test_workflow_path_only', 'unreviewed transformation')
            modified.add(Path(origin).name)
        else:
            require(item['transformation'] == 'byte_identical', 'incorrect unchanged label')
        if source_git:
            original = source_bytes(source_git, origin)
            require(sha(original) == item['source_sha256'], 'source hash mismatch')
            require(hashlib.sha1(b'blob '+str(len(original)).encode()+b'\0'+original).hexdigest()
                    == item['source_git_blob'], 'source Git blob mismatch')
            require(transform(origin, original) == data, 'unexpected transformation')
    require((source_count, workflow_count, modified) == (531, 106, TEST_NAMES), 'scope mismatch')
    imported_seen = set()
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if rel.parts[0] == '.git':
            continue
        require(not path.is_symlink(), 'symlink in repository')
        if path.is_dir():
            continue
        p = rel.as_posix()
        require(not p.startswith(('.github/', '.vercel/', 'apps/', 'packages/', 'runtime/')), 'forbidden active/client tree')
        require('vercel' not in path.name.lower(), 'deployment configuration')
        if p.startswith(SOURCE_ROOTS) or p.startswith(LEGACY):
            imported_seen.add(p)
        else:
            require(p.startswith('migration/') or p in {'README.md', 'AGENTS.md', '.gitignore'}, 'unreviewed root file')
    require(imported_seen == expected, 'extra or missing source file')
    if source_git:
        for ref in m['original_refs']:
            tree = subprocess.check_output(['git', '-C', str(source_git), 'show', '-s', '--format=%T', ref['commit']], text=True).strip()
            require(tree == ref['tree'], 'immutable original ref mismatch')
    return {'status': 'ISOLATED_SOURCE_IDENTITY_PASS', 'source_commit': COMMIT,
            'source_files': source_count, 'disabled_workflows': workflow_count,
            'active_workflows': 0, 'original_objects_checked': bool(source_git),
            'canonical_recertification': False, 'destination_repository_id': TARGET_ID}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source-git', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.source_git), indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit('ISOLATION_FAILED: '+str(error))
