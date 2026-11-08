"""Fixed syscall allowlist for one dedicated own snapshot-review process.

Input acquisition and module loading precede the filter. This is not a general
hostile-code sandbox, memory-integrity proof, or independent host attestation.
The filter is irreversible and must never be installed in a shared worker.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import stat

from . import owned_slither_network as pinned
from .safe_io import canonical

PROFILE = 'owned-linux-x86_64-preloaded-compute-v1'
MARKER_BYTES = b'SuperHunter own preloaded compute control\n'
ALLOW, DENY = 0x7fff0000, 0x00050000 | errno.EPERM
EQ, MASKED_EQ = 4, 7
# These calls do not acquire new filesystem objects or create another process.
PLAIN = ('brk', 'munmap', 'madvise', 'futex', 'rt_sigaction', 'rt_sigprocmask',
         'rt_sigreturn', 'sigaltstack', 'clock_gettime', 'gettimeofday', 'getpid',
         'gettid', 'getrusage', 'sched_yield', 'exit', 'exit_group', 'restart_syscall')
CONTROL_NAMES = ('new_read', 'new_write', 'new_directory', 'unix_socket', 'ipv4_socket')


class ComputeGuardError(ValueError):
    """Stable diagnostics without source paths or syscall payloads."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ComputeGuardError(reason)


class Comparison(ctypes.Structure):
    _fields_ = [('arg', ctypes.c_uint), ('op', ctypes.c_int),
                ('a', ctypes.c_uint64), ('b', ctypes.c_uint64)]


def rules() -> list[dict]:
    result = [{'syscall': name, 'comparisons': []} for name in PLAIN]
    def add(name, *comparisons):
        result.append({'syscall': name, 'comparisons': [list(c) for c in comparisons]})
    for descriptor in (0, 1, 2):
        add('close', (0, EQ, descriptor, 0))
        add('fstat', (0, EQ, descriptor, 0))
    add('read', (0, EQ, 0, 0))
    for descriptor in (1, 2):
        add('write', (0, EQ, descriptor, 0))
    # Anonymous mappings only, with fd=-1, and no executable protection.
    # Linux consumes mmap's fd as int; mask its lower 32 bits deliberately.
    add('mmap', (2, MASKED_EQ, 4, 0), (3, MASKED_EQ, 0x20, 0x20),
        (4, MASKED_EQ, 0xffffffff, 0xffffffff))
    add('mprotect', (2, MASKED_EQ, 4, 0))
    for flags in (0, 1):
        add('mremap', (3, EQ, flags, 0))
    for option in (21, 39):
        add('prctl', (0, EQ, option, 0))
    return result


def expected_proof(socket_baseline: dict) -> dict:
    need(type(socket_baseline) is dict and set(socket_baseline) == {'unix_socket', 'ipv4_socket'} and
         all(value in ('AVAILABLE', 'ALREADY_DENIED_EPERM') for value in socket_baseline.values()),
         'COMPUTE_SOCKET_BASELINE')
    return {'profile': PROFILE, 'library_sha256': pinned.LIBRARY_SHA256,
            'library_loaded_from_sealed_bytes': True, 'default_errno': errno.EPERM,
            'rules_sha256': hashlib.sha256(canonical(rules())).hexdigest(),
            'single_thread_checked_before_filter': True, 'inherited_descriptors': [0, 1, 2],
            'stdin_checked_as_devnull': True, 'stdout_stderr_checked_as_regular_or_pipe': True,
            'per_file_limit_after_library_load': 65536,
            'controls_available_before_filter': ['new_read', 'new_write', 'new_directory'],
            'socket_controls_before_filter': dict(socket_baseline),
            'preexisting_socket_denial_attributed_to_this_filter': False,
            'controls_denied_after_filter': list(CONTROL_NAMES), 'control_errno': errno.EPERM,
            'preloaded_control_sha256': hashlib.sha256(MARKER_BYTES).hexdigest(),
            'no_new_privs': True, 'seccomp_filter_mode': True,
            'input_acquisition_inside_filter': False, 'module_loading_inside_filter': False,
            'general_hostile_code_sandbox_proved': False, 'memory_integrity_proved': False,
            'host_authenticated': False, 'independent_execution_authenticated': False}


def _descriptors() -> None:
    observed = set()
    for name in os.listdir('/proc/self/fd'):
        descriptor = int(name)
        try:
            info = os.fstat(descriptor)
        except OSError as error:
            need(error.errno == errno.EBADF, 'COMPUTE_DESCRIPTOR_INSPECTION')
            continue  # listdir's own closed descriptor is not inherited.
        need(descriptor in (0, 1, 2), 'COMPUTE_EXTRA_DESCRIPTOR')
        observed.add(descriptor)
        if descriptor == 0:
            expected = os.stat('/dev/null')
            need(stat.S_ISCHR(info.st_mode) and info.st_rdev == expected.st_rdev and
                 fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE in (os.O_RDONLY, os.O_RDWR),
                 'COMPUTE_STDIN')
        else:
            need(stat.S_ISREG(info.st_mode) or stat.S_ISFIFO(info.st_mode), 'COMPUTE_OUTPUT_DESCRIPTOR')
    need(observed == {0, 1, 2}, 'COMPUTE_MISSING_DESCRIPTOR')


def _before(marker: Path) -> tuple[bytes, dict]:
    need(marker.name == 'owned-compute-control' and not marker.is_symlink(), 'COMPUTE_CONTROL_PATH')
    need(marker.is_file() and marker.read_bytes() == MARKER_BYTES, 'COMPUTE_CONTROL_BYTES')
    descriptor = os.open(marker, os.O_WRONLY | os.O_NOFOLLOW)
    os.close(descriptor)
    directory = marker.parent/'owned-compute-directory-control'
    os.mkdir(directory, 0o700)
    os.rmdir(directory)
    sockets = {}
    for name, family in (('unix_socket', socket.AF_UNIX), ('ipv4_socket', socket.AF_INET)):
        try:
            handle = socket.socket(family, socket.SOCK_STREAM)
        except OSError as error:
            need(error.errno == errno.EPERM, 'COMPUTE_SOCKET_BASELINE_ERRNO')
            sockets[name] = 'ALREADY_DENIED_EPERM'
        else:
            handle.close()  # No connection, bind, payload or remote address.
            sockets[name] = 'AVAILABLE'
    return MARKER_BYTES, sockets


def install(marker: Path) -> dict:
    """Install only in the fixed dedicated child, after its inputs are loaded."""
    need(len(list(Path('/proc/self/task').iterdir())) == 1, 'COMPUTE_SINGLE_THREAD_REQUIRED')
    loaded, socket_baseline = _before(marker)
    raw = pinned.library_bytes()
    lib = pinned._sealed_library(raw)
    # The sealed library is 125,360 bytes. The dedicated worker admits its
    # loading under 128 KiB, then lowers both limits before installing policy.
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.POINTER(Comparison)]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    # Prime output/hash encodings before the no-new-files boundary.
    proof = expected_proof(socket_baseline)
    json.dumps(proof)
    hashlib.sha256(loaded).hexdigest()
    _descriptors()
    context = lib.seccomp_init(DENY)
    need(bool(context), 'COMPUTE_FILTER_INIT')
    try:
        for rule in rules():
            number = lib.seccomp_syscall_resolve_name(rule['syscall'].encode())
            need(number >= 0, 'COMPUTE_SYSCALL_UNAVAILABLE')
            comparisons = (Comparison * len(rule['comparisons']))(
                *(Comparison(*values) for values in rule['comparisons']))
            need(lib.seccomp_rule_add_array(context, ALLOW, number, len(comparisons), comparisons) == 0,
                 'COMPUTE_RULE_FAILED')
        need(lib.seccomp_load(context) == 0, 'COMPUTE_FILTER_LOAD')
    finally:
        lib.seccomp_release(context)
    operations = (
        lambda: os.open(marker, os.O_RDONLY),
        lambda: os.open(marker, os.O_WRONLY),
        lambda: os.mkdir(marker.parent/'owned-compute-directory-control', 0o700),
        lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
        lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
    )
    for operation in operations:
        try:
            handle = operation()
        except OSError as error:
            need(error.errno == errno.EPERM, 'COMPUTE_CONTROL_ERRNO')
        else:
            if isinstance(handle, socket.socket):
                handle.close()
            elif type(handle) is int:
                os.close(handle)
            raise ComputeGuardError('COMPUTE_CONTROL_NOT_DENIED')
    need(hashlib.sha256(loaded).hexdigest() == proof['preloaded_control_sha256'], 'COMPUTE_PRELOADED_HASH')
    need(libc.prctl(39, 0, 0, 0, 0) == 1 and libc.prctl(21, 0, 0, 0, 0) == 2, 'COMPUTE_KERNEL_STATE')
    return proof
