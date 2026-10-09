#!/usr/bin/env python3
"""Explicit v1 prospective D06 mount boundary; never original-runner identity."""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

METHOD = 'fd-pinned-detached-readonly-mount-then-sudo-drop-v1'
ORIGINALS = {
    'run_premounted_d06_v1.py': 'ci/nqc-census/run_rmc006_recertification.py',
    'test_premounted_d06_replay_v1.py': 'ci/nqc-census/test_rmc006_recertification_replay.py',
}

# Only this fixed, standard-library-only text executes while privileged. No
# project import, shell, caller-selected command, file write or network request.
# Directory descriptors pin every lookup; mount syscalls use descriptors only.
MOUNT_SETUP = r'''
import ctypes, os, re, stat, sys

def require(value, message):
    if not value:
        raise ValueError(message)

def open_directory(path):
    require(path.startswith('/') and path != '/' and not path.endswith('/'), 'absolute nonroot directory required')
    parts = path.split('/')[1:]
    require(all(part not in ('', '.', '..') for part in parts), 'directory alias rejected')
    fd = os.open('/', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts:
            next_fd = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise

def read_text(path):
    with open(path) as stream:
        return stream.read()

def descriptor_mount_id(fd):
    return int(next(line.split()[1] for line in read_text('/proc/self/fdinfo/' + str(fd)).splitlines() if line.startswith('mnt_id:')))

class MountAttr(ctypes.Structure):
    _fields_ = [('attr_set', ctypes.c_uint64), ('attr_clr', ctypes.c_uint64),
               ('propagation', ctypes.c_uint64), ('userns_fd', ctypes.c_uint64)]

def mount_readonly(source, uid, device, inode):
    for line in read_text('/proc/self/mountinfo').splitlines():
        fields = line.split()
        target = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4])
        require(not target.startswith(source + '/'), 'descendant source mount rejected')
    fd = open_directory(source)
    tree = None
    try:
        info = os.fstat(fd)
        old_mount_id = descriptor_mount_id(fd)
        require((info.st_uid, info.st_dev, info.st_ino) == (uid, device, inode), 'source was replaced or is not runner-owned')
        libc = ctypes.CDLL(None, use_errno=True)
        libc.open_tree.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        libc.open_tree.restype = ctypes.c_int
        libc.mount_setattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint, ctypes.POINTER(MountAttr), ctypes.c_size_t]
        libc.mount_setattr.restype = ctypes.c_int
        libc.move_mount.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        libc.move_mount.restype = ctypes.c_int
        def checked(value):
            if value < 0:
                number = ctypes.get_errno()
                raise OSError(number, os.strerror(number))
            return value
        # OPEN_TREE_CLONE|OPEN_TREE_CLOEXEC|AT_EMPTY_PATH. No recursive clone:
        # the caller rejects descendant mounts rather than hiding their content.
        tree = checked(libc.open_tree(fd, b'', 1 | os.O_CLOEXEC | 0x1000))
        # MOUNT_ATTR_RDONLY only; zero attr_clr preserves every existing flag.
        attributes = MountAttr(1, 0, 0, 0)
        checked(libc.mount_setattr(tree, b'', 0x1000, ctypes.byref(attributes), ctypes.sizeof(attributes)))
        # MOVE_MOUNT_F_EMPTY_PATH|MOVE_MOUNT_T_EMPTY_PATH; attach to the pinned
        # source directory, even if a concurrent rename changes its pathname.
        checked(libc.move_mount(tree, b'', fd, b'', 0x4 | 0x40))
        check = open_directory(source)
        try:
            current = os.fstat(check)
            new_mount_id = descriptor_mount_id(check)
            require(new_mount_id != old_mount_id, 'source mount was not replaced')
            require((current.st_dev, current.st_ino) == (device, inode), 'source path changed after mount')
            require(os.statvfs(source).f_flag & os.ST_RDONLY, 'mounted source is not read-only')
            return old_mount_id, new_mount_id
        finally:
            os.close(check)
    finally:
        if tree is not None:
            os.close(tree)
        os.close(fd)
'''

ROOT_SETUP = MOUNT_SETUP + r'''
require(len(sys.argv) == 10 and os.getuid() == os.geteuid() == 0, 'fixed privileged setup arguments required')
# No inherited file/socket handles can carry write or host-network authority.
# GitHub log/stdin pipes and /dev/null are the only permitted standard handles.
for descriptor in (0, 1, 2):
    entry = os.fstat(descriptor)
    require(stat.S_ISFIFO(entry.st_mode) or (stat.S_ISCHR(entry.st_mode) and entry.st_rdev == os.stat('/dev/null').st_rdev), 'unexpected standard descriptor')
os.closerange(3, 2**31 - 1)
os.chdir('/')
root, uid, gid, device, inode, parent_net, parent_mount, head, tree = sys.argv[1:]
require(re.fullmatch(r'/[^\x00\n]+/nqc-standalone-d06-[1-9][0-9]*-[1-9][0-9]*', root), 'run-specific root required')
require(all(re.fullmatch(r'[1-9][0-9]*', value) for value in (uid, gid, inode)), 'nonzero runner identity required')
require(re.fullmatch(r'[0-9]+', device), 'invalid source device')
require(all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (head, tree)), 'exact producer identity required')
require(re.fullmatch(r'net:\[[0-9]+\]', parent_net) and re.fullmatch(r'mnt:\[[0-9]+\]', parent_mount), 'invalid parent namespace')
require(os.readlink('/proc/self/ns/net') != parent_net and os.readlink('/proc/self/ns/mnt') != parent_mount, 'fresh namespaces required')
old_mount_id, new_mount_id = mount_readonly(root + '/authenticated-original', int(uid), int(device), int(inode))
os.closerange(3, 2**31 - 1)
# All opened descriptors were CLOEXEC and explicitly closed. No privileged
# setup code remains: this process execs setpriv before any repository import.
# sudo may keep its normal monitor; no privileged repository worker is retained.
os.execv('/usr/bin/setpriv', ['/usr/bin/setpriv', '--reuid=' + uid, '--regid=' + gid,
    '--clear-groups', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all',
    '--no-new-privs', '--', '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin',
    'HOME=' + root + '/home', 'LC_ALL=C', 'PYTHONDONTWRITEBYTECODE=1',
    'GIT_CONFIG_NOSYSTEM=1', 'GIT_CONFIG_GLOBAL=/dev/null', 'GIT_TERMINAL_PROMPT=0',
    'GIT_ALLOW_PROTOCOL=', 'GIT_NO_REPLACE_OBJECTS=1', 'GIT_NO_LAZY_FETCH=1',
    'EXPECTED_COMMIT=' + head, 'EXPECTED_TREE=' + tree,
    'NQC_SOURCE_PREMOUNT_ID=' + str(old_mount_id), 'NQC_SOURCE_READONLY_MOUNT_ID=' + str(new_mount_id),
    '/bin/bash', '--noprofile', '--norc', root + '/build/migration/run_standalone_d06_offline.sh',
    root, root + '/build', parent_net, uid, gid, parent_mount, 'replay'])
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def mount_records(text):
    def decode(value):
        return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), value)
    records = []
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) >= 10 and '-' in fields[6:], 'malformed mountinfo')
        separator = fields.index('-', 6)
        records.append((Path(decode(fields[4])), set(fields[5].split(',')), fields[6:separator], int(fields[0])))
    return records


def require_no_descendant_mounts(source, text):
    for path, _flags, _optional, _mount_id in mount_records(text):
        require(path == source or not path.is_relative_to(source), 'descendant source mount rejected')


def readonly_proof(source):
    source = Path(source)
    require(source.is_absolute() and source.resolve() == source, 'source alias rejected')
    text = Path('/proc/self/mountinfo').read_text()
    require_no_descendant_mounts(source, text)
    rows = [(flags, optional, mount_id) for path, flags, optional, mount_id in mount_records(text) if path == source]
    require(len(rows) == 1 and 'ro' in rows[0][0], 'exact read-only source mount required')
    require(not any(item.startswith(('shared:', 'master:', 'propagate_from:')) for item in rows[0][1]),
            'private source mount required')
    old_id = int(os.environ.get('NQC_SOURCE_PREMOUNT_ID', '0'))
    new_id = int(os.environ.get('NQC_SOURCE_READONLY_MOUNT_ID', '0'))
    require(old_id > 0 and new_id == rows[0][2] and old_id != new_id, 'source mount identity differs')
    require(os.statvfs(source).f_flag & os.ST_RDONLY, 'source filesystem is not read-only')
    # Evidence files are deliberately 0444. Their DAC denial can precede EROFS,
    # so probe the owner-writable 0700 directory with an unnamed inode instead.
    # O_EXCL prevents linking it; there is no named path, existing-file write,
    # chmod or truncation. Unexpected success closes without writing and fails.
    require(stat.S_ISDIR(source.lstat().st_mode), 'readonly probe must be a source directory')
    flags = os.O_TMPFILE | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(source, flags, 0o600)
    except OSError as error:
        require(error.errno == errno.EROFS,
                'anonymous readonly probe expected EROFS; errno=' + str(error.errno) +
                ' (' + errno.errorcode.get(error.errno, 'UNKNOWN') + ')')
    else:
        os.close(fd)
        raise ValueError('readonly source unexpectedly permits anonymous write access')
    return {'schema': 'nqc-premounted-source-v2', 'method': METHOD, 'read_only': True,
            'write_open_errno': errno.EROFS, 'probe': 'source-directory-O_TMPFILE|O_EXCL',
            'probe_creates_named_file': False, 'probe_writes_or_truncates_existing': False,
            'probe_linkable': False, 'mount_flags': sorted(rows[0][0]),
            'descendant_mounts': False, 'private_mount': True,
            'premount_id': old_id, 'readonly_mount_id': new_id}



def runner_identity(repo, source, adapter_file):
    repo, adapter_file = Path(repo), Path(adapter_file).resolve()
    name = adapter_file.name
    require(name in ORIGINALS and adapter_file == repo / 'migration' / name, 'unknown prospective runner identity')
    original_path = ORIGINALS[name]
    return {'schema': 'nqc-prospective-d06-runner-v1', 'method': METHOD,
            'original_runner_byte_identical': False, 'certification_inherited': False,
            'original_path': original_path, 'original_sha256': hashlib.sha256((repo / original_path).read_bytes()).hexdigest(),
            'adapter_path': 'migration/' + name, 'adapter_sha256': hashlib.sha256(adapter_file.read_bytes()).hexdigest(),
            'boundary_path': 'migration/premounted_d06.py',
            'boundary_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'root_setup_sha256': hashlib.sha256(ROOT_SETUP.encode()).hexdigest(),
            'source_mount': readonly_proof(source)}


# Unprivileged negative-fixture preparation. No source mode or byte is changed.
STORE_MUTATION_CASES = {'missing-checkpoint', 'corrupted-checkpoint', 'missing-head', 'missing-stream',
                       'missing-manifest', 'missing-request', 'missing-response', 'missing-chunk', 'corrupted-chunk'}


def _fd_digest(fd):
    digest = hashlib.sha256(); offset = 0
    while True:
        data = os.pread(fd, 1024 * 1024, offset)
        if not data:
            return digest.hexdigest()
        digest.update(data); offset += len(data)


def source_state_snapshot(root):
    """Pin named membership, bytes, modes, ownership, links and inode identity."""
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root and root.is_dir(), 'source/fixture root alias')
    uid = os.getuid(); require(uid > 0, 'negative fixture requires nonroot owner')
    state = {}
    for path in (root, *sorted(root.rglob('*'))):
        info = path.lstat(); mode = stat.S_IMODE(info.st_mode)
        require(info.st_uid == uid, 'source/fixture owner differs')
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'source/fixture symlink or special file')
        regular = stat.S_ISREG(info.st_mode)
        require(mode == (0o444 if regular else 0o700), 'original extraction mode differs')
        digest = None
        if regular:
            require(info.st_nlink == 1, 'source/fixture hardlink rejected')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            try:
                current = os.fstat(fd)
                require((current.st_dev, current.st_ino, current.st_mode, current.st_nlink) ==
                        (info.st_dev, info.st_ino, info.st_mode, 1), 'source/fixture changed during snapshot')
                digest = _fd_digest(fd)
            finally:
                os.close(fd)
        state[str(path.relative_to(root))] = {'kind': 'file' if regular else 'directory', 'mode': mode,
            'uid': info.st_uid, 'gid': info.st_gid, 'links': info.st_nlink,
            'device': info.st_dev, 'inode': info.st_ino, 'sha256': digest}
    return state


def copy_mutation_fixture(source, target):
    """Create and prove a fresh independent clone before any of nine mutations."""
    import shutil
    source, target = Path(source), Path(target)
    require(source.is_absolute() and source.resolve() == source and
            target.is_absolute() and target.resolve() == target and target.parent.is_dir(), 'fixture path alias')
    require(target.name in {name + '-store' for name in STORE_MUTATION_CASES}, 'unexpected store fixture')
    require(not target.is_relative_to(source) and not source.is_relative_to(target), 'fixture overlaps immutable source')
    require(not target.exists() and not target.is_symlink(), 'fixture must be fresh')
    before = source_state_snapshot(source)
    shutil.copytree(source, target)
    copied = source_state_snapshot(target)
    require(set(copied) == set(before), 'fixture membership differs')
    source_identities = {(row['device'], row['inode']) for row in before.values()}
    for name, row in copied.items():
        require(all(row[field] == before[name][field] for field in ('kind', 'mode', 'uid', 'gid', 'sha256')),
                'fixture bytes or modes differ')
        require((row['device'], row['inode']) not in source_identities, 'fixture aliases source inode')
    require(source_state_snapshot(source) == before, 'copy changed immutable source')


def _fixture_directory_fd(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, 'fixture parent alias')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def overwrite_fixture_file(source, target, path, contents):
    """Temporarily add owner-write only to one proven copied corruption target."""
    source, target, path = Path(source), Path(target), Path(path)
    require(type(contents) is bytes, 'fixture contents must be bytes')
    require(all(value.is_absolute() and value.resolve() == value for value in (source, target, path)), 'fixture file alias')
    require(not target.is_relative_to(source) and not source.is_relative_to(target), 'fixture overlaps immutable source')
    require(path.is_relative_to(target) and path != target, 'mutation outside fixture')
    relative = path.relative_to(target)
    pattern = {'corrupted-checkpoint-store': r'streams/[0-9a-f]{64}/checkpoints/[0-9]{20}',
               'corrupted-chunk-store': r'objects/chunks/[0-9a-f]{2}/[0-9a-f]{64}'}.get(target.name)
    require(pattern is not None and re.fullmatch(pattern, relative.as_posix()), 'unexpected corruption target')
    parent = _fixture_directory_fd(path.parent)
    source_parent = copied = original = writer = None; changed_mode = False
    try:
        source_parent = _fixture_directory_fd((source / relative).parent)
        copied = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
        original = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=source_parent)
        copied_info, original_info = os.fstat(copied), os.fstat(original)
        for info in (copied_info, original_info):
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid() and
                    stat.S_IMODE(info.st_mode) == 0o444, 'corruption target must be an owned original-mode regular single-link file')
        require((copied_info.st_dev, copied_info.st_ino) != (original_info.st_dev, original_info.st_ino), 'corruption target aliases source')
        require(_fd_digest(copied) == _fd_digest(original), 'corruption fixture was not copied unchanged')
        os.fchmod(copied, 0o644); changed_mode = True
        writer = os.open(path.name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
        opened = os.fstat(writer)
        require((opened.st_dev, opened.st_ino, opened.st_nlink) ==
                (copied_info.st_dev, copied_info.st_ino, 1), 'corruption path changed before write')
        os.ftruncate(writer, 0)
        remaining = memoryview(contents)
        while remaining:
            count = os.write(writer, remaining)
            require(count > 0, 'short fixture write')
            remaining = remaining[count:]
    finally:
        try:
            if writer is not None:
                os.close(writer)
            if changed_mode:
                os.fchmod(copied, 0o444)
        finally:
            for fd in (copied, original, parent, source_parent):
                if fd is not None:
                    os.close(fd)
    after = path.lstat()
    require((after.st_dev, after.st_ino, after.st_nlink, stat.S_IMODE(after.st_mode)) ==
            (copied_info.st_dev, copied_info.st_ino, 1, 0o444), 'corruption target or restored mode changed')

def command(root, head, tree):
    import importlib.util
    spec = importlib.util.spec_from_file_location('checked_system_boundary', Path(__file__).with_name('materialize_historical_source.py'))
    boundary = importlib.util.module_from_spec(spec); spec.loader.exec_module(boundary)
    verify_system_executables = boundary.verify_system_executables
    uid, gid = os.getuid(), os.getgid()
    require(uid > 0 and gid > 0 and os.getresuid() == (uid,) * 3 and os.getresgid() == (gid,) * 3,
            'original nonroot runner required')
    root = Path(root)
    require(re.fullmatch(r'nqc-standalone-d06-[1-9][0-9]*-[1-9][0-9]*', root.name), 'run-specific root required')
    for path in (root, *(root / name for name in ('build', 'logs', 'home', 'authenticated-original'))):
        require(path.is_absolute() and path.resolve() == path and path.is_dir() and path.stat().st_uid == uid,
                'runner directory alias or ownership changed')
    require(all(re.fullmatch('[0-9a-f]{40}', value) for value in (head, tree)), 'exact producer identity required')
    source = root / 'authenticated-original'
    require_no_descendant_mounts(source, Path('/proc/self/mountinfo').read_text())
    info = source.stat()
    verify_system_executables()
    return ['/usr/bin/sudo', '-n', '--', '/usr/bin/env', '-i', 'PATH=/usr/bin:/bin',
            '/usr/bin/unshare', '--net', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-S', '-B', '-c', ROOT_SETUP, str(root), str(uid), str(gid),
            str(info.st_dev), str(info.st_ino), os.readlink('/proc/self/ns/net'),
            os.readlink('/proc/self/ns/mnt'), head, tree]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--expected-tree', required=True)
    args = parser.parse_args()
    subprocess.run(command(args.root, args.expected_commit, args.expected_tree), check=True)
