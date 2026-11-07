"""Kernel socket filter for a dedicated, single-threaded OWNED scanner worker.

This is a syscall boundary, not filesystem/host isolation or a general sandbox.
The pinned libseccomp image is loaded only after hashing and sealing its bytes.
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

LIBRARY_SHA256 = 'b4d9140a7797ccf3ac14f5d9d579b64f157111662940cb8330c632b11a8cea8e'
LIBRARY_BYTES = 125360
SYSCALLS = ('socket','socketpair','connect','bind','listen','accept','accept4',
            'sendto','sendmsg','sendmmsg','recvfrom','recvmsg','recvmmsg','shutdown',
            'io_uring_setup','io_uring_enter','io_uring_register')
PROFILE = 'owned-linux-x86_64-socket-filter-v1'


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def library_bytes() -> bytes:
    need(platform.system()=='Linux' and platform.machine()=='x86_64', 'OWNED_NETWORK_PLATFORM')
    path = Path('/lib/x86_64-linux-gnu/libseccomp.so.2').resolve(strict=True)
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size==LIBRARY_BYTES,'OWNED_NETWORK_LIBRARY_FILE')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw = stream.read(LIBRARY_BYTES+1)
        need(len(raw)==LIBRARY_BYTES and hashlib.sha256(raw).hexdigest()==LIBRARY_SHA256,
             'OWNED_NETWORK_LIBRARY_BYTES')
        return raw
    finally:
        os.close(fd)


def expected_proof() -> dict:
    return {'profile':PROFILE, 'library_sha256':LIBRARY_SHA256,
            'library_loaded_from_sealed_bytes':True, 'denied_syscalls':list(SYSCALLS),
            'socket_controls_denied':4, 'no_new_privs':True, 'seccomp_filter_mode':True,
            'inherited_sockets':0, 'host_filesystem_isolated':False,
            'producer_authenticated':False}


def _sealed_library(raw: bytes):
    fd = os.memfd_create('owned-slither-network',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(raw); stream.flush()
        seals = fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals)
        need(fcntl.fcntl(fd,fcntl.F_GET_SEALS)&seals==seals,'OWNED_NETWORK_LIBRARY_SEALS')
        return ctypes.CDLL('/proc/self/fd/'+str(fd),use_errno=True)
    finally:
        os.close(fd)


def install() -> dict:
    raw = library_bytes()
    need(len(list(Path('/proc/self/task').iterdir()))==1,'OWNED_NETWORK_SINGLE_THREAD_REQUIRED')
    for name in os.listdir('/proc/self/fd'):
        try: info = os.fstat(int(name))
        except OSError: continue
        need(not stat.S_ISSOCK(info.st_mode),'OWNED_NETWORK_INHERITED_SOCKET')
    lib = _sealed_library(raw)
    lib.seccomp_init.argtypes=[ctypes.c_uint32]; lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_release.argtypes=[ctypes.c_void_p]; lib.seccomp_release.restype=None
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.c_void_p]
    lib.seccomp_rule_add_array.restype=ctypes.c_int
    lib.seccomp_load.argtypes=[ctypes.c_void_p]; lib.seccomp_load.restype=ctypes.c_int
    context = lib.seccomp_init(0x7fff0000)
    need(bool(context),'OWNED_NETWORK_FILTER_INIT')
    try:
        for name in SYSCALLS:
            number = lib.seccomp_syscall_resolve_name(name.encode())
            need(number>=0,'OWNED_NETWORK_SYSCALL_UNAVAILABLE')
            need(lib.seccomp_rule_add_array(context,0x00050000|errno.EPERM,number,0,None)==0,
                 'OWNED_NETWORK_RULE_FAILED')
        need(lib.seccomp_load(context)==0,'OWNED_NETWORK_FILTER_LOAD')
    finally:
        lib.seccomp_release(context)
    for family,kind in ((socket.AF_INET,socket.SOCK_STREAM),(socket.AF_INET,socket.SOCK_DGRAM),
                        (socket.AF_INET6,socket.SOCK_STREAM),(socket.AF_UNIX,socket.SOCK_STREAM)):
        try: handle = socket.socket(family,kind)
        except OSError as error: need(error.errno==errno.EPERM,'OWNED_NETWORK_UNEXPECTED_ERRNO')
        else:
            handle.close(); raise ValueError('OWNED_NETWORK_SOCKET_NOT_BLOCKED')
    state = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('Seccomp:','NoNewPrivs:')):
            key,value = line.split(':',1); state[key]=value.strip()
    need(state=={'NoNewPrivs':'1','Seccomp':'2'},'OWNED_NETWORK_KERNEL_STATE')
    return expected_proof()
