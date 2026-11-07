"""Read-only repository boundary review alongside the immutable legacy verifier.

Checks exact historical Git trees plus the explicitly admitted SuperHunter
source tree. Does not execute reviewed code, certify NQC, or prove runtime
containment. The historical migration checker and manifest stay unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from .privacy import PrivateArgumentParser
from .safe_io import canonical

HISTORICAL_TREES = {
    'ci':'8a8c94551f060b1d6ce3c501c8e9ddd2b26e7e72',
    'migration':'1c3262dc7ed09b8f3df76914ef45c3dd22ccafee',
    'nqc-census':'68dbd045014a49bd53b79440d9878f3e8035c739',
}
ROOT_FILES = {
    '.gitignore':'7518f5529fe0b23ea9195c5e3c4a1099a9e05d08',
    'AGENTS.md':'6c2fe3771bad272bb1839aabc2b45ef636a16531',
    'README.md':'2d620f813efdfa3c146fc7e17dd39f5ca11132c5',
}
DOCUMENTS = {'SUPERHUNTER_MASTER_PLAN.md','SUPERHUNTER_STATUS.md',
             'SUPERHUNTER_CRITICAL_RESEARCH.md'}
FORBIDDEN_PARTS = {'.github','.vercel','apps','packages','node_modules','.venv','venv'}
SOURCE_SUFFIXES = {'.py','.md','.json','.txt'}
MAX_FILES, MAX_TOTAL_BYTES, MAX_FILE_BYTES = 4096, 64*1024**2, 20*1024**2


class BoundaryError(ValueError):
    """Fixed diagnostics without private paths or source contents."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise BoundaryError(code)


def git_object(kind: str, payload: bytes) -> str:
    return hashlib.sha1(kind.encode()+b' '+str(len(payload)).encode()+b'\0'+payload).hexdigest()


def _capture(root: Path) -> tuple[dict, int]:
    need(root.is_dir() and not root.is_symlink(), 'ROOT_NOT_REGULAR_DIRECTORY')
    files, ignored, total, directory_count = {}, 0, 0, 0
    for base, dirs, names in os.walk(root, followlinks=False):
        relbase = Path(base).relative_to(root)
        for name in list(dirs):
            path = Path(base)/name
            need(not path.is_symlink(), 'SYMLINK_REJECTED')
            if relbase == Path('.') and name == '.git':
                dirs.remove(name)
                continue
            directory_count += 1
            need(directory_count <= MAX_FILES, 'DIRECTORY_COUNT_BUDGET')
            rel = path.relative_to(root)
            need(len(rel.parts) <= 20, 'PATH_DEPTH_BUDGET')
            need(rel.parts[0] in {*HISTORICAL_TREES,'superhunter'}, 'UNREVIEWED_ROOT_TREE')
            need(not any(p in FORBIDDEN_PARTS for p in rel.parts), 'CLIENT_OR_ACTIVE_TREE')
        for name in sorted(names):
            path = Path(base)/name
            rel = path.relative_to(root)
            info = path.lstat()
            need(stat.S_ISREG(info.st_mode), 'NONREGULAR_FILE')
            if relbase == Path('.') and name == '.git':
                continue  # Git worktree metadata is not source or an authority pin.
            key = rel.as_posix()
            need(not any(p in FORBIDDEN_PARTS for p in rel.parts), 'CLIENT_OR_ACTIVE_TREE')
            need('vercel' not in name.lower(), 'DEPLOYMENT_CONFIGURATION')
            if rel.parts[0] == 'superhunter' and '__pycache__' in rel.parts:
                need(path.suffix == '.pyc', 'UNREVIEWED_CACHE_PAYLOAD')
                ignored += 1
                need(ignored <= MAX_FILES, 'CACHE_COUNT_BUDGET')
                continue
            need(info.st_size <= MAX_FILE_BYTES, 'FILE_SIZE_BUDGET')
            total += info.st_size
            need(total <= MAX_TOTAL_BYTES and len(files) < MAX_FILES, 'INVENTORY_BUDGET')
            # O_NOFOLLOW makes a file replaced by a symlink fail closed. The
            # second full capture detects ordinary concurrent source changes.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                current = os.fstat(fd)
                need(stat.S_ISREG(current.st_mode) and current.st_size == info.st_size,
                     'FILE_CHANGED_DURING_READ')
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    raw = stream.read(MAX_FILE_BYTES+1)
                need(len(raw) == info.st_size, 'FILE_CHANGED_DURING_READ')
            finally:
                os.close(fd)
            mode = '100755' if info.st_mode & stat.S_IXUSR else '100644'
            files[key] = {'bytes':raw,'mode':mode}
    return files, ignored


def _tree(files: dict, prefix: str) -> str:
    children = {}
    for path, item in files.items():
        if not path.startswith(prefix+'/'):
            continue
        tail = path[len(prefix)+1:]
        name, slash, _ = tail.partition('/')
        if slash:
            children[name] = ('40000', None)
        else:
            children[name] = (item['mode'], git_object('blob', item['bytes']))
    need(bool(children), 'HISTORICAL_TREE_MISSING')
    payload = bytearray()
    for name, (mode, digest) in sorted(children.items(),
            key=lambda row:(row[0]+('/' if row[1][0]=='40000' else '')).encode()):
        if digest is None:
            digest = _tree(files, prefix+'/'+name)
        payload.extend(mode.encode()+b' '+name.encode()+b'\0'+bytes.fromhex(digest))
    return git_object('tree',bytes(payload))


def review(root: Path) -> dict:
    files, ignored = _capture(root)
    for name, wanted in ROOT_FILES.items():
        need(name in files and files[name]['mode'] == '100644' and
             git_object('blob',files[name]['bytes']) == wanted, 'ROOT_POLICY_CHANGED')
    historical = {name:_tree(files,name) for name in HISTORICAL_TREES}
    need(historical == HISTORICAL_TREES, 'HISTORICAL_TREE_CHANGED')
    historical_count = superhunter_count = 0
    documents = []
    for path, item in files.items():
        parts = Path(path).parts
        if parts[0] in HISTORICAL_TREES:
            historical_count += 1
        elif path in ROOT_FILES:
            continue
        elif path in DOCUMENTS:
            need(item['mode'] == '100644', 'EXECUTABLE_ROOT_DOCUMENT')
            documents.append(path)
        else:
            need(parts[0] == 'superhunter' and len(parts) > 1, 'UNREVIEWED_ROOT_FILE')
            need(Path(path).suffix in SOURCE_SUFFIXES or path == 'superhunter/.gitignore',
                 'UNREVIEWED_SUPERHUNTER_PAYLOAD')
            need(item['mode'] == '100644', 'EXECUTABLE_SOURCE_MODE')
            superhunter_count += 1
    need(historical_count == 642 and superhunter_count > 0, 'BOUNDARY_SCOPE')
    after, ignored_after = _capture(root)
    need(after == files and ignored_after == ignored, 'REPOSITORY_CHANGED_DURING_REVIEW')
    snapshot = {p:{'mode':v['mode'],'sha256':hashlib.sha256(v['bytes']).hexdigest()}
                for p,v in files.items()}
    return {'schema_version':1,'status':'REPOSITORY_BOUNDARY_PASS',
        'historical_tree_pins':historical,'historical_files_checked':historical_count,
        'superhunter_files_reviewed_for_boundary':superhunter_count,
        'root_documents':sorted(documents),'ignored_python_cache_files':ignored,
        'source_inventory_sha256':hashlib.sha256(canonical(snapshot)).hexdigest(),
        'active_workflows':0,'legacy_verifier_unchanged':True,
        'original_source_objects_checked':False,'canonical_recertification':False,
        'runtime_isolation_proved':False,'full_security_review':False}


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Review SuperHunter repository source boundaries')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args = p.parse_args(argv)
    try:
        print(json.dumps(review(args.root),sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
        reason = str(error) if type(error) is BoundaryError else 'BOUNDARY_INPUT_ERROR'
        print(json.dumps({'status':'REPOSITORY_BOUNDARY_BLOCKED','reason':reason,
                          'canonical_recertification':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
