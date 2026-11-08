"""Pinned native Solidity compiler driver, with no fallback/emulated compiler.

Input is bounded inline Solidity Standard JSON. Compilation does not execute
contracts. This module never downloads tools, discovers targets or sends RPCs.
The optional compiler must exactly match the official Linux-amd64 0.8.30 pin.
A missing binary is a BLOCKER, not a passed compilation or skipped verification.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile

from . import compiler_layout
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PIN = {
    'version':'0.8.30+commit.73712a01',
    'platform':'linux-amd64',
    'sha256':'f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7',
    'filename':'solc-linux-amd64-v0.8.30+commit.73712a01',
    'index':'https://binaries.soliditylang.org/linux-amd64/list.json',
}
SETTINGS = {'optimizer':{'enabled':False}, 'evmVersion':'cancun',
            'modelChecker':{'engine':'none'},
            'outputSelection':{'*':{'':['ast'],'*':['storageLayout']}}}
FILES = {'input.json','output.json','version.txt','stderr.txt','receipt.json','audit.json','REVIEW.md'}
CODE_FILES = ('native_compile.py','solc_worker.py','safe_io.py','native_runtime.py','compiler_layout.py')
MAX_BINARY = 64_000_000
MAX_SOURCE = 64_000
HEX = re.compile('[0-9a-f]{64}\\Z')


class CompileError(ValueError):
    """Fixed codes only: never echo input source, paths, or tool diagnostics."""


class CompilerUnavailable(CompileError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise CompileError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def standard_input(sources: dict[str,str]) -> bytes:
    need(type(sources) is dict and 1 <= len(sources) <= 16,'SOURCE_COUNT')
    for name, source in sources.items():
        compiler_layout.source_name(name)
        need(type(source) is str and bool(source),'INLINE_SOURCE_REQUIRED')
    need(sum(len(s.encode('utf-8')) for s in sources.values()) <= MAX_SOURCE,'SOURCE_BUDGET')
    return canonical({'language':'Solidity','sources':{n:{'content':s} for n,s in sources.items()},'settings':SETTINGS})


def validate_input(raw: bytes) -> dict:
    need(type(raw) is bytes and len(raw) <= 128_000,'INPUT_BUDGET')
    data = strict_json(raw)
    need(set(data)=={'language','sources','settings'} and data['language']=='Solidity','INPUT_PROFILE')
    need(type(data['sources']) is dict,'SOURCES_SCHEMA')
    sources={}
    for name, row in data['sources'].items():
        need(type(row) is dict and set(row)=={'content'},'INLINE_ONLY_NO_URLS')
        sources[name]=row['content']
    expected = strict_json(standard_input(sources))
    need(canonical(data)==canonical(expected),'FIXED_COMPILER_SETTINGS_REQUIRED')
    return data


def read_pinned_binary(path: Path) -> bytes:
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','amd64'):
        raise CompilerUnavailable('PINNED_PLATFORM_UNAVAILABLE')
    try:
        flags=os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        fd=os.open(path, flags)
    except FileNotFoundError:
        raise CompilerUnavailable('PINNED_SOLC_NOT_INSTALLED') from None
    except OSError:
        raise CompileError('COMPILER_FILE_UNREADABLE') from None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_BINARY,'COMPILER_FILE_TYPE_OR_SIZE')
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw=stream.read(MAX_BINARY+1)
        need(len(raw)<=MAX_BINARY and sha(raw)==PIN['sha256'],'COMPILER_HASH_MISMATCH')
        need(raw.startswith(b'\x7fELF'),'COMPILER_ELF_REQUIRED')
        return raw
    finally:
        os.close(fd)


@contextmanager
def _sealed_executable(raw: bytes):
    """Seal the exact bytes verified by the caller; the input path is never exec'd."""
    need(hasattr(os,'memfd_create') and hasattr(fcntl,'F_ADD_SEALS'),'SEALED_EXECUTION_UNAVAILABLE')
    fd=os.memfd_create('superhunter-solc',os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(raw);stream.flush()
        seals=fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals)
        os.lseek(fd,0,os.SEEK_SET)
        yield fd
    finally:
        os.close(fd)


def _execute(raw: bytes, mode: str, payload: bytes=b'') -> tuple[bytes,bytes]:
    """Private process boundary, also tested with the real OS Python executable.

    Production callers reach it only after read_pinned_binary(). No arbitrary
    executable, flag, environment or timeout is exposed through the CLI.
    """
    need(mode in ('version','compile'),'EXECUTION_MODE')
    need(type(raw) is bytes and raw.startswith(b'\x7fELF') and len(raw)<=MAX_BINARY,'EXECUTABLE_IMAGE')
    need(type(payload) is bytes and len(payload)<=128_000,'INPUT_BUDGET')
    with _sealed_executable(raw) as fd, tempfile.TemporaryDirectory(prefix='sh-solc-') as tmp:
        with tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            inp.write(payload);inp.seek(0)
            args=[sys.executable,'-I','-B',str(ROOT/'solc_worker.py'),mode,str(fd)]
            proc=subprocess.Popen(args,stdin=inp,stdout=out,stderr=err,cwd=tmp,
                                  env={'LANG':'C','LC_ALL':'C'},pass_fds=(fd,),start_new_session=True)
            try:
                rc=proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
                raise CompileError('COMPILER_TIMEOUT') from None
            stdout_size=out.seek(0,os.SEEK_END);stderr_size=err.seek(0,os.SEEK_END)
            need(stdout_size<2_000_000 and stderr_size<2_000_000,'COMPILER_OUTPUT_LIMIT')
            out.seek(0);err.seek(0)
            stdout,stderr=out.read(),err.read()
            need(rc==0,'COMPILER_PROCESS_ERROR')
            return stdout,stderr


def verify_version(raw: bytes) -> None:
    need(type(raw) is bytes and len(raw)<4096,'VERSION_OUTPUT')
    expected=('Version: '+PIN['version']+'.Linux.g++').encode()
    need(expected in raw.splitlines(),'COMPILER_VERSION_MISMATCH')


def classify_output(input_data: dict, raw: bytes) -> dict:
    """Exit zero is not sufficient: solc reports compilation errors in JSON."""
    out=strict_json(raw)
    diagnostics=out.get('errors',[])
    need(type(diagnostics) is list and len(diagnostics)<=2048,'DIAGNOSTIC_SCHEMA')
    for row in diagnostics:
        need(type(row) is dict and row.get('severity') in ('error','warning','info'),'DIAGNOSTIC_SCHEMA')
    error_count=sum(row['severity']=='error' for row in diagnostics)
    warnings=sum(row['severity']=='warning' for row in diagnostics)
    if error_count:
        return {'status':'SOLC_COMPILATION_FAILED','errors':error_count,'warnings':warnings,'contracts':0}
    sources=out.get('sources');contracts=out.get('contracts')
    need(type(sources) is dict and set(sources)==set(input_data['sources']),'OUTPUT_SOURCE_SET')
    for name,row in sources.items():
        need(type(row) is dict and type(row.get('id')) is int and row['id']>=0 and
             type(row.get('ast')) is dict and row['ast'].get('nodeType')=='SourceUnit','OUTPUT_AST_MISSING')
    need(type(contracts) is dict and set(contracts).issubset(sources),'OUTPUT_CONTRACTS')
    count=0
    for group in contracts.values():
        need(type(group) is dict,'OUTPUT_CONTRACTS')
        for row in group.values():
            need(type(row) is dict and type(row.get('storageLayout')) is dict,'OUTPUT_LAYOUT_MISSING')
            need(set(row['storageLayout'])=={'storage','types'} and type(row['storageLayout']['storage']) is list,
                 'OUTPUT_LAYOUT_SCHEMA')
            count+=1
    need(count>0,'NO_CONTRACT_OUTPUT')
    return {'status':'SOLC_COMPILATION_COMPLETED','errors':0,'warnings':warnings,'contracts':count}


def _engine() -> dict:
    return {'sha256':{n:sha(read_artifact(ROOT,n)) for n in CODE_FILES},'native_sources':source_inventory()}


def _receipt(raw_input: bytes, raw_output: bytes, version: bytes, stderr: bytes, *, produced_at: str) -> dict:
    need(type(produced_at) is str and len(produced_at)<=40,'PRODUCED_AT')
    observed=datetime.fromisoformat(produced_at)
    need(observed.tzinfo is not None,'PRODUCED_AT_TIMEZONE')
    inp=validate_input(raw_input);verify_version(version)
    return {'schema_version':1,**classify_output(inp,raw_output),'compiler_pin':PIN,'produced_at':produced_at,
            'input_sha256':sha(raw_input),'output_sha256':sha(raw_output),
            'version_sha256':sha(version),'stderr_sha256':sha(stderr),
            'engine':_engine(),'command':['--standard-json','--no-import-callback'],
            'executed_contracts':False,'vulnerability_confirmed':False,
            'remote_producer_authenticated':False,
            'receipt_meaning':'local-producer-statement-replay-required-for-execution-check'}


def _audit(receipt: dict) -> dict:
    audit=load_components().audit.AuditLog(clock=lambda:receipt['produced_at'])
    # The local producer's clock is retained, not authenticated by this hash chain.
    audit.append('compile.artifacts',{'receipt_sha256':sha(canonical(receipt))})
    audit.assert_intact()
    return {'clock_authenticated':False,'entries':[asdict(x) for x in audit.entries]}


def _review(receipt: dict) -> bytes:
    return (f"# Compilación local declarada\n\n{receipt['status']}\n\n"
            f"Errores: {receipt['errors']}. Advertencias: {receipt['warnings']}.\n"
            'La integridad del paquete no prueba ejecución. replay-compilation ejecuta el binario fijado\n'
            'y compara el resultado con la referencia externa de entrada. No es un segundo compilador.\n'
            'No se ejecutaron contratos, EVM, RPC, despliegues o pruebas de vulnerabilidades.\n'
            'El paquete contiene fuentes y diagnósticos privados.\n').encode()


def compile_bundle(input_path: Path, binary: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(),'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent),'OUTPUT_INSIDE_CODE')
    raw_input=read_artifact(input_path.parent,input_path.name);validate_input(raw_input)
    image=read_pinned_binary(binary)
    version,version_err=_execute(image,'version');verify_version(version)
    need(not version_err,'UNEXPECTED_VERSION_STDERR')
    engine=_engine()
    raw_output,stderr=_execute(image,'compile',raw_input)
    receipt=_receipt(raw_input,raw_output,version,stderr,produced_at=datetime.now(timezone.utc).isoformat())
    need(engine==_engine(),'ENGINE_CHANGED')
    files={'input.json':raw_input,'output.json':raw_output,'version.txt':version,'stderr.txt':stderr,
           'receipt.json':canonical(receipt),'audit.json':canonical(_audit(receipt)),'REVIEW.md':_review(receipt)}
    write_new_bundle(out,files)
    _read_bundle(out,expected_input_sha256=sha(raw_input))
    return receipt


def _read_bundle(root: Path, *, expected_input_sha256: str) -> dict[str,bytes]:
    need(type(expected_input_sha256) is str and HEX.fullmatch(expected_input_sha256) is not None,'EXTERNAL_INPUT_HASH_REQUIRED')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    need(set(marker)=={'schema_version','sha256'} and type(marker['schema_version']) is int and
         marker['schema_version']==1 and type(marker['sha256']) is dict and set(marker['sha256'])==FILES,'BUNDLE_SCHEMA')
    need({p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILES')
    raw={name:read_artifact(root,name) for name in FILES}
    need(all(sha(data)==marker['sha256'][name] for name,data in raw.items()),'BUNDLE_HASH')
    need(sha(raw['input.json'])==expected_input_sha256,'EXTERNAL_INPUT_MISMATCH')
    claimed=strict_json(raw['receipt.json'])
    receipt=_receipt(raw['input.json'],raw['output.json'],raw['version.txt'],raw['stderr.txt'],produced_at=claimed.get('produced_at'))
    need(raw['receipt.json']==canonical(receipt) and raw['audit.json']==canonical(_audit(receipt)) and
         raw['REVIEW.md']==_review(receipt),'DERIVED_ARTIFACT_MISMATCH')
    return raw


def replay_bundle(root: Path, binary: Path, *, expected_input_sha256: str) -> dict:
    raw=_read_bundle(root,expected_input_sha256=expected_input_sha256)
    image=read_pinned_binary(binary)
    version,err=_execute(image,'version');verify_version(version)
    need(not err and version==raw['version.txt'],'VERSION_REPLAY_MISMATCH')
    output,stderr=_execute(image,'compile',raw['input.json'])
    need(output==raw['output.json'] and stderr==raw['stderr.txt'],'COMPILER_REPLAY_MISMATCH')
    classification=classify_output(validate_input(raw['input.json']),output)
    return {'status':'COMPILATION_REPLAY_MATCH','compilation_status':classification['status'],
            'same_compiler_reexecuted':True,'independent_compiler':False,
            'vulnerability_confirmed':False,'input_sha256':expected_input_sha256,
            'compiler_sha256':PIN['sha256']}


def main(argv: list[str] | None=None) -> int:
    parser=PrivateArgumentParser(description='Pinned solc compilation only; no EVM or target execution')
    sub=parser.add_subparsers(dest='command',required=True)
    inspect=sub.add_parser('inspect-solc');inspect.add_argument('--binary',type=Path,required=True)
    comp=sub.add_parser('compile-solidity')
    for name in ('binary','input','out'):comp.add_argument('--'+name,type=Path,required=True)
    replay=sub.add_parser('replay-compilation')
    for name in ('binary','bundle'):replay.add_argument('--'+name,type=Path,required=True)
    replay.add_argument('--expected-input-sha256',required=True)
    a=parser.parse_args(argv)
    try:
        if a.command=='inspect-solc':
            image=read_pinned_binary(a.binary);version,err=_execute(image,'version');verify_version(version)
            need(not err,'UNEXPECTED_VERSION_STDERR')
            result={'status':'PINNED_COMPILER_AVAILABLE','compiler_sha256':PIN['sha256'],'compilation_performed':False}
        elif a.command=='compile-solidity':
            receipt=compile_bundle(a.input,a.binary,a.out)
            result={k:receipt[k] for k in ('status','errors','warnings','contracts','vulnerability_confirmed')}
        else:
            result=replay_bundle(a.bundle,a.binary,expected_input_sha256=a.expected_input_sha256)
        print(json.dumps(result))
        return 1 if result.get('status')=='SOLC_COMPILATION_FAILED' or result.get('compilation_status')=='SOLC_COMPILATION_FAILED' else 0
    except CompilerUnavailable as exc:
        print(json.dumps({'status':'COMPILATION_BLOCKED','reason':str(exc),'compilation_performed':False}));return 3
    except (ValueError,OSError,KeyError,TypeError,UnicodeError,RecursionError):
        print(json.dumps({'status':'COMPILATION_REJECTED','compilation_completed':False,
                          'execution_status':'UNVERIFIED_OR_INCOMPLETE'}));return 2


if __name__=='__main__':
    raise SystemExit(main())
