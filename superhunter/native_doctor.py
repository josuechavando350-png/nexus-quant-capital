"""Diagnose prerequisites without running compilers, contracts or solver queries.

Readiness only: a PASS here never replaces QA or a native comparison. Paths,
environment values and package exception messages are not included in reports.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import stat
import sys

from .privacy import PrivateArgumentParser
from .safe_io import canonical
from . import quality

Z3_SHA256 = '7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0'
PACKAGES = {'PyYAML':'6.0.3','cryptography':'46.0.4'}
CHECKS = ('host','sealed_memory','qa_packages','z3_fixture_library','solc','geth','second_evm_packages')


def result(ok: bool, code: str, **public) -> dict:
    return {'status':'PASS' if ok else 'BLOCKED','code':code,**public}


def _host() -> dict:
    system, machine = platform.system(), platform.machine()
    supported = system == 'Linux' and machine in ('x86_64','amd64') and sys.version_info[:2] == (3,12)
    return result(supported, 'SUPPORTED_LAB_HOST' if supported else 'LINUX_X86_64_PYTHON312_REQUIRED',
                  system=system, architecture=machine,
                  python_version='.'.join(map(str,sys.version_info[:3])))


def _sealed_memory() -> dict:
    fd = None
    try:
        import fcntl
        flags = (fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE)
        fd = os.memfd_create('owned-readiness-probe',os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        os.write(fd,b'owned readiness probe')
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,flags)
        ok = fcntl.fcntl(fd,fcntl.F_GET_SEALS) & flags == flags
        return result(ok,'SEALED_MEMORY_AVAILABLE' if ok else 'SEALED_MEMORY_UNAVAILABLE')
    except (ImportError,AttributeError,OSError,ValueError):
        return result(False,'SEALED_MEMORY_UNAVAILABLE')
    finally:
        if fd is not None:
            os.close(fd)


def _qa_packages() -> dict:
    packages = {}
    for name,wanted in PACKAGES.items():
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = None
        packages[name] = {'expected':wanted,'matches':actual == wanted}
    ok = all(p['matches'] for p in packages.values())
    return result(ok,'QA_PACKAGES_MATCH' if ok else 'QA_PACKAGE_MISSING_OR_DIFFERENT',packages=packages)


def _z3_fixture_library() -> dict:
    # Only inspect the library that the existing backend would choose. Loading
    # an arbitrary library merely to ask its version would execute its code.
    try:
        from .smt_backend import _library_path
        path = _library_path()
        fd = os.open(path,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 64*1024**2:
                return result(False,'Z3_LIBRARY_UNAVAILABLE')
            with os.fdopen(fd,'rb',closefd=False) as stream:
                raw = stream.read(64*1024**2+1)
            if len(raw) != info.st_size:
                return result(False,'Z3_LIBRARY_CHANGED_DURING_READ')
        finally:
            os.close(fd)
        ok = hashlib.sha256(raw).hexdigest() == Z3_SHA256
        return result(ok,'Z3_FIXTURE_BYTES_MATCH' if ok else 'Z3_FIXTURE_BYTES_DIFFERENT',
                      expected_sha256=Z3_SHA256)
    except (OSError,ValueError,ImportError,AttributeError):
        return result(False,'Z3_LIBRARY_UNAVAILABLE')


def _tool(kind: str, path: Path) -> dict:
    if kind not in ('solc','geth'):
        raise ValueError('UNKNOWN_LAB_TOOL')
    try:
        if kind == 'solc':
            from .native_compile import read_pinned_binary
            image = read_pinned_binary(path)
        else:
            from .evm_execution import read_evm
            image = read_evm(path)
        return result(True,'PINNED_TOOL_BYTES_MATCH',sha256=hashlib.sha256(image).hexdigest())
    except (OSError,ValueError,ImportError,AttributeError):
        return result(False,'PINNED_TOOL_MISSING_OR_DIFFERENT')


def _second_evm_packages() -> dict:
    try:
        from .owned_cross_evm_worker import dependency_identity
        identity = dependency_identity()
        return result(True,'SECOND_EVM_PACKAGE_BYTES_MATCH',distributions=len(identity))
    except (OSError,ValueError,ImportError,AttributeError,PackageNotFoundError):
        return result(False,'SECOND_EVM_PACKAGES_MISSING_OR_DIFFERENT')


def diagnose(solc: Path, evm: Path) -> dict:
    rows = {'host':_host(),'sealed_memory':_sealed_memory(),'qa_packages':_qa_packages(),
            'z3_fixture_library':_z3_fixture_library(),'solc':_tool('solc',solc),
            'geth':_tool('geth',evm),'second_evm_packages':_second_evm_packages()}
    passed = {name:row['status'] == 'PASS' for name,row in rows.items()}
    prerequisites = {
        'qa':all(passed[n] for n in ('host','sealed_memory','qa_packages','z3_fixture_library')),
        'owned_geth':all(passed[n] for n in ('host','sealed_memory','solc','geth')),
        'owned_cross_evm':all(passed[n] for n in ('host','sealed_memory','solc','geth','second_evm_packages')),
    }
    return {'schema_version':1,'status':'LAB_PREREQUISITES_READY' if all(prerequisites.values())
            else 'LAB_PREREQUISITES_BLOCKED','checks':rows,'prerequisites':prerequisites,
            'source_digest':quality.sha(canonical(quality.source_snapshot())),
            'qa_executed':False,'native_contracts_executed':False,'solver_query_executed':False,
            'dependencies_installed':False,'network_used':False,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Check fixed owned lab prerequisites without contract execution')
    parser.add_argument('--solc',type=Path,required=True)
    parser.add_argument('--evm',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        report = diagnose(args.solc,args.evm)
        print(json.dumps(report,sort_keys=True))
        return 0 if report['status'] == 'LAB_PREREQUISITES_READY' else 2
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        print(json.dumps({'status':'LAB_DIAGNOSTIC_BLOCKED','vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
