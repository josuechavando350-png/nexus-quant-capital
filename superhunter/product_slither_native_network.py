"""Same owned socket-denial policy with a separately pinned libseccomp kit image.

The historical owned_slither_network library pin and acceptance remain unchanged.
This profile stages the current image instead of trusting a host library path.
"""
import ctypes
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import socket
import stat

from .owned_slither_network import SYSCALLS, need

LIBRARY_SHA = 'c851a2378b4ef3a42ada5f8ff1604ad38f6bbcafa2aeea3f6680160d628c2f27'
LIBRARY_BYTES = 182560


def expected_proof():
    return {'profile': 'product-owned-slither-socket-filter-v1',
            'library_sha256': LIBRARY_SHA, 'library_loaded_from_sealed_bytes': True,
            'denied_syscalls': list(SYSCALLS), 'socket_controls_denied': 4,
            'no_new_privs': True, 'seccomp_filter_mode': True, 'inherited_sockets': 0,
            'host_filesystem_isolated': False, 'producer_authenticated': False}


def sealed_library(raw):
    # Linux UAPI fcntl.h: some CPython builds omit these named constants.
    # The profile is explicitly Linux x86_64 and verifies the resulting kernel seals.
    add_seals, get_seals, seals = 1033, 1034, 1 | 2 | 4 | 8
    fd = os.memfd_create('product-owned-slither-network', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
        fcntl.fcntl(fd, add_seals, seals)
        need(fcntl.fcntl(fd, get_seals) & seals == seals, 'PRODUCT_NETWORK_LIBRARY_SEALS')
        return ctypes.CDLL('/proc/self/fd/'+str(fd), use_errno=True)
    finally:
        os.close(fd)


def install(path):
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'PRODUCT_NETWORK_PLATFORM')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_size == LIBRARY_BYTES, 'PRODUCT_NETWORK_LIBRARY_FILE')
        raw = stream.read(LIBRARY_BYTES+1)
    need(len(raw) == LIBRARY_BYTES and hashlib.sha256(raw).hexdigest() == LIBRARY_SHA,
         'PRODUCT_NETWORK_LIBRARY_BYTES')
    need(len(list(Path('/proc/self/task').iterdir())) == 1, 'PRODUCT_NETWORK_SINGLE_THREAD')
    for name in os.listdir('/proc/self/fd'):
        try:
            info = os.fstat(int(name))
        except OSError:
            continue
        need(not stat.S_ISSOCK(info.st_mode), 'PRODUCT_NETWORK_INHERITED_SOCKET')
    lib = sealed_library(raw)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.restype = None
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                         ctypes.c_uint, ctypes.c_void_p]
    lib.seccomp_rule_add_array.restype = ctypes.c_int
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_load.restype = ctypes.c_int
    context = lib.seccomp_init(0x7fff0000)
    need(bool(context), 'PRODUCT_NETWORK_FILTER_INIT')
    try:
        for name in SYSCALLS:
            number = lib.seccomp_syscall_resolve_name(name.encode())
            need(number >= 0, 'PRODUCT_NETWORK_SYSCALL')
            need(lib.seccomp_rule_add_array(context, 0x00050000 | errno.EPERM, number, 0, None) == 0,
                 'PRODUCT_NETWORK_RULE')
        need(lib.seccomp_load(context) == 0, 'PRODUCT_NETWORK_LOAD')
    finally:
        lib.seccomp_release(context)
    for family, kind in ((socket.AF_INET, socket.SOCK_STREAM), (socket.AF_INET, socket.SOCK_DGRAM),
                         (socket.AF_INET6, socket.SOCK_STREAM), (socket.AF_UNIX, socket.SOCK_STREAM)):
        try:
            handle = socket.socket(family, kind)
        except OSError as error:
            need(error.errno == errno.EPERM, 'PRODUCT_NETWORK_ERRNO')
        else:
            handle.close()
            raise ValueError('PRODUCT_NETWORK_SOCKET_NOT_BLOCKED')
    state = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('Seccomp:', 'NoNewPrivs:')):
            key, value = line.split(':', 1)
            state[key] = value.strip()
    need(state == {'NoNewPrivs': '1', 'Seccomp': '2'}, 'PRODUCT_NETWORK_KERNEL_STATE')
    return expected_proof()
