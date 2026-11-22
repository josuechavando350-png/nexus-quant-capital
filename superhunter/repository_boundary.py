"""Read-only repository boundary review alongside the immutable legacy verifier.

Checks exact historical Git trees plus the explicitly admitted SuperHunter
source tree. Does not execute reviewed code, certify NQC, or prove runtime
containment. The historical migration checker and manifest stay unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from .privacy import PrivateArgumentParser
from .safe_io import canonical

HISTORICAL_TREES = {
    'ci':'8a8c94551f060b1d6ce3c501c8e9ddd2b26e7e72',
    'migration':'1c3262dc7ed09b8f3df76914ef45c3dd22ccafee',
    'nqc-census':'68dbd045014a49bd53b79440d9878f3e8035c739',
}
ROOT_FILES = {
    '.gitmodules':'d2d602ef33c5c2c77b7fb5a1a240ae9061f3f5b5',
    '.gitignore':'7518f5529fe0b23ea9195c5e3c4a1099a9e05d08',
    'AGENTS.md':'6c2fe3771bad272bb1839aabc2b45ef636a16531',
    'README.md':'2d620f813efdfa3c146fc7e17dd39f5ca11132c5',
}
# PRs 69--78 appended this reviewed guidance without changing one byte of the
# original isolation policy. Neither arbitrary appendices nor prefix edits are
# admitted. Keep the original Git blob pin above as a separately checked root.
AGENTS_ORIGINAL_BYTES = 1107
AGENTS_APPENDIX_BYTES = 3903
AGENTS_APPENDIX_SHA256 = '74d63e642a1b6eecdb5cefbbd3fe6640cd8ba30d05cc620283b66a459dbd59cf'
DOCUMENTS = {'SUPERHUNTER_MASTER_PLAN.md','SUPERHUNTER_STATUS.md',
             'SUPERHUNTER_CRITICAL_RESEARCH.md'}
FORBIDDEN_PARTS = {'.github','.vercel','apps','packages','node_modules','.venv','venv'}
SOURCE_SUFFIXES = {'.py','.md','.json','.txt'}
# The fixed browser driver reads three local review fixtures. Admit its reviewed
# bytes at this path only, independently of the product's runtime pin.
HTML_REVIEW_WORKER = 'superhunter/product_html_review_worker.cjs'
HTML_REVIEW_WORKER_SHA256 = '9549b514ef35283e67b246df0b3535a15c4b2460881bdbd88de7341ffa4f8ddd'
MAX_FILES, MAX_TOTAL_BYTES, MAX_FILE_BYTES = 4096, 64*1024**2, 20*1024**2


class BoundaryError(ValueError):
    """Fixed diagnostics without private paths or source contents."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise BoundaryError(code)


def git_object(kind: str, payload: bytes) -> str:
    return hashlib.sha1(kind.encode()+b' '+str(len(payload)).encode()+b'\0'+payload).hexdigest()


def _root_policy_matches(name: str, raw: bytes, wanted: str) -> bool:
    if git_object('blob', raw) == wanted:
        return True
    return (name == 'AGENTS.md' and
            len(raw) == AGENTS_ORIGINAL_BYTES + AGENTS_APPENDIX_BYTES and
            git_object('blob', raw[:AGENTS_ORIGINAL_BYTES]) == wanted and
            hashlib.sha256(raw[AGENTS_ORIGINAL_BYTES:]).hexdigest() == AGENTS_APPENDIX_SHA256)


def _file_stamp(info) -> tuple:
    # Reading may change atime. Compare object identity and mutation metadata,
    # not access time; these observations do not authenticate a hostile host.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _directory_read_failed(error: OSError) -> None:
    # os.walk otherwise ignores scandir errors and can return a partial tree.
    raise BoundaryError('DIRECTORY_READ_FAILED') from None


def _upstream_leaves(root: Path) -> set[str]:
    # The root policy pins the complete manifest, including its literal paths and URLs.
    from .safe_io import read_artifact

    try:
        raw = read_artifact(root, '.gitmodules')
    except (OSError, ValueError) as exc:
        raise BoundaryError('ROOT_POLICY_CHANGED') from exc
    need(git_object('blob', raw) == ROOT_FILES['.gitmodules'], 'ROOT_POLICY_CHANGED')
    return set(re.findall(r'^\tpath = upstream/([0-9]{3}-[a-z0-9_.-]+)$', raw.decode(), re.M))


def _capture(root: Path) -> tuple[dict, int]:
    need(root.is_dir() and not root.is_symlink(), 'ROOT_NOT_REGULAR_DIRECTORY')
    upstream_leaves = _upstream_leaves(root)
    files, ignored, total, directory_count = {}, 0, 0, 0
    for base, dirs, names in os.walk(root, followlinks=False, onerror=_directory_read_failed):
        relbase = Path(base).relative_to(root)
        for name in list(dirs):
            path = Path(base)/name
            need(not path.is_symlink(), 'SYMLINK_REJECTED')
            if relbase == Path('upstream'):
                need(name in upstream_leaves, 'UNREVIEWED_UPSTREAM_PATH')
                dirs.remove(name)  # External source has its own Git inventory.
                continue
            if relbase == Path('.') and name == '.git':
                dirs.remove(name)
                continue
            if relbase == Path('.') and name == 'upstream':
                continue
            directory_count += 1
            need(directory_count <= MAX_FILES, 'DIRECTORY_COUNT_BUDGET')
            rel = path.relative_to(root)
            need(len(rel.parts) <= 20, 'PATH_DEPTH_BUDGET')
            need(rel.parts[0] in {*HISTORICAL_TREES,'superhunter'}, 'UNREVIEWED_ROOT_TREE')
            need(not any(p in FORBIDDEN_PARTS for p in rel.parts), 'CLIENT_OR_ACTIVE_TREE')
        need(relbase != Path('upstream') or not names, 'UNREVIEWED_UPSTREAM_PATH')
        for name in sorted(names):
            path = Path(base)/name
            rel = path.relative_to(root)
            info = path.lstat()
            need(stat.S_ISREG(info.st_mode), 'NONREGULAR_FILE')
            need(rel.as_posix() != 'upstream', 'UPSTREAM_NOT_DIRECTORY')
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
            # Observe the same regular object before opening, on the acquired
            # descriptor, after reading, and at its path. The second complete
            # capture remains required; this is not an atomic tree snapshot.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                current = os.fstat(fd)
                need(stat.S_ISREG(current.st_mode) and _file_stamp(current) == _file_stamp(info),
                     'FILE_CHANGED_DURING_READ')
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    raw = stream.read(info.st_size+1)
                need(len(raw) == info.st_size and
                     _file_stamp(os.fstat(fd)) == _file_stamp(info) == _file_stamp(path.lstat()),
                     'FILE_CHANGED_DURING_READ')
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


def _review_captured(files: dict, ignored: int) -> dict:
    """Pure policy review of bytes already obtained by the bounded capturer.

    Internal entry point: filesystem acquisition and concurrent-change checks
    belong to the caller. This function performs no filesystem IO.
    """
    for name, wanted in ROOT_FILES.items():
        need(name in files and files[name]['mode'] == '100644' and
             _root_policy_matches(name,files[name]['bytes'],wanted), 'ROOT_POLICY_CHANGED')
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
            if path == HTML_REVIEW_WORKER:
                need(hashlib.sha256(item['bytes']).hexdigest() == HTML_REVIEW_WORKER_SHA256,
                     'REVIEWED_WORKER_CHANGED')
            else:
                need(Path(path).suffix in SOURCE_SUFFIXES or path == 'superhunter/.gitignore',
                     'UNREVIEWED_SUPERHUNTER_PAYLOAD')
            need(item['mode'] == '100644', 'EXECUTABLE_SOURCE_MODE')
            superhunter_count += 1
    need(historical_count == 642 and superhunter_count > 0, 'BOUNDARY_SCOPE')
    snapshot = {p:{'mode':v['mode'],'sha256':hashlib.sha256(v['bytes']).hexdigest()}
                for p,v in files.items()}
    return {'schema_version':1,'status':'REPOSITORY_BOUNDARY_PASS',
        'historical_tree_pins':historical,'historical_files_checked':historical_count,
        'external_source_contents_reviewed':False,
        'superhunter_files_reviewed_for_boundary':superhunter_count,
        'root_documents':sorted(documents),'ignored_python_cache_files':ignored,
        'source_inventory_sha256':hashlib.sha256(canonical(snapshot)).hexdigest(),
        'active_workflows':0,'legacy_verifier_unchanged':True,
        'original_root_policy_preserved':True,
        'reviewed_agents_appendix_sha256':(AGENTS_APPENDIX_SHA256
            if len(files['AGENTS.md']['bytes']) > AGENTS_ORIGINAL_BYTES else None),
        'original_source_objects_checked':False,'canonical_recertification':False,
        'runtime_isolation_proved':False,'full_security_review':False}


def _verify_import(files: dict) -> dict:
    """Replay the immutable migration checker and its tests on the admitted import bytes."""
    with tempfile.TemporaryDirectory(prefix='nqc-import-') as temp:
        root = Path(temp)
        for name, item in files.items():
            if name.split('/', 1)[0] not in HISTORICAL_TREES and name not in {
                    'README.md', 'AGENTS.md', '.gitignore'}:
                continue
            data = item['bytes']
            if name == 'AGENTS.md':
                data = data[:AGENTS_ORIGINAL_BYTES]
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(int(item['mode'][-3:], 8))

        def run(script):
            return subprocess.run([sys.executable, '-I', '-B', str(root/'migration'/script)],
                                  cwd=root, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)

        check = run('verify_isolation.py')
        need(check.returncode == 0, 'HISTORICAL_IMPORT_REJECTED')
        result = json.loads(check.stdout)
        need(result['status'] == 'ISOLATED_SOURCE_IDENTITY_PASS'
             and result['canonical_recertification'] is False, 'HISTORICAL_IMPORT_REJECTED')
        tests = run('test_isolation.py')
        count = re.search(rb'^Ran (\d+) tests in ', tests.stderr, re.MULTILINE)
        need(tests.returncode == 0 and count is not None and int(count[1]) == 9
             and tests.stderr.rstrip().endswith(b'\nOK'), 'HISTORICAL_IMPORT_TESTS_FAILED')
        return {'scope': 'imported source reconstructed from the reviewed product checkout',
                'checker': result, 'tests_passed': int(count[1])}


def review(root: Path, *, verify_import: bool = False) -> dict:
    files, ignored = _capture(root)
    result = _review_captured(files, ignored)
    if verify_import:
        result['historical_import'] = _verify_import(files)
    after, ignored_after = _capture(root)
    need(after == files and ignored_after == ignored, 'REPOSITORY_CHANGED_DURING_REVIEW')
    return result


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Review SuperHunter repository source boundaries')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--verify-import', action='store_true',
                   help='also run the original checker and nine tests on the admitted import files')
    args = p.parse_args(argv)
    try:
        print(json.dumps(review(args.root, verify_import=args.verify_import),sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,RecursionError,subprocess.TimeoutExpired) as error:
        reason = str(error) if type(error) is BoundaryError else 'BOUNDARY_INPUT_ERROR'
        print(json.dumps({'status':'REPOSITORY_BOUNDARY_BLOCKED','reason':reason,
                          'canonical_recertification':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
