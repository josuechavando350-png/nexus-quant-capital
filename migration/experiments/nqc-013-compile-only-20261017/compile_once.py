"""Compile-only probe. Not a trader, signer, RPC client, deployer or EVM test.

Run remotely only after the owner has approved the isolated workflow migration.
Uses the unchanged compiler/ABI verifier delivered in NQC 011.
"""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = 'josuechavando350-png/nexus-quant-capital'
REPO_ID = 1411047452
BRANCH = 'refs/heads/research/nqc-013-compile-only-20261017'
MESSAGE = 'NQC013_APPROVED_COMPILE_ONCE'
URL = 'https://binaries.soliditylang.org/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9'
EXPECTED = 'fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'
MAX_DOWNLOAD = 20_000_000


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inspect_payload() -> dict:
    from prepare_compile import LOCK
    for name, expected in LOCK.items():
        if sha((HERE/'source'/name).read_bytes()) != expected:
            raise ValueError('Source mismatch: ' + name)
    config = json.loads((HERE/'COMPILER_LOCK.json').read_text())
    if config['sha256'] != EXPECTED or config['version'] != '0.8.24+commit.e11b9ed9':
        raise ValueError('Compiler lock mismatch')
    return {'source_hashes': LOCK, 'compiler_sha256': EXPECTED,
            'compilation': 'NOT_RUN', 'EVM': 'NOT_RUN'}


def validate_run_environment() -> dict:
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('Execution requires the explicitly approved GitHub workflow')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    repo = event['repository']
    if (repo.get('id') != REPO_ID or repo.get('full_name') != REPO
            or repo.get('private') is not False):
        raise ValueError('Only the exact public NQC repository is eligible')
    if os.environ.get('GITHUB_REF') != BRANCH or os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise ValueError('Wrong branch or repeated attempt')
    if event.get('head_commit', {}).get('message') != MESSAGE:
        raise ValueError('Missing the one-shot activation commit marker')
    return {'producer_repository_id': REPO_ID, 'producer_sha': os.environ['GITHUB_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': 1,
            'branch': BRANCH, 'event': 'push'}


def fetch_compiler(directory: Path) -> Path:
    binary = directory/'solc-0.8.24'
    req = urllib.request.Request(URL, headers={'User-Agent': 'NQC-013-compile-only'})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Compiler download did not return HTTP 200')
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD or sha(data) != EXPECTED:
        raise ValueError('Compiler content exceeds bound or SHA-256 differs')
    binary.write_bytes(data)
    binary.chmod(0o700)
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true', help='No network or compiler execution')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    verified = inspect_payload()
    if args.inspect:
        print(json.dumps({'status': 'PAYLOAD_INTEGRITY_ONLY', **verified}, sort_keys=True))
        return 0
    producer = validate_run_environment()
    if args.output is None:
        raise ValueError('--output is required for the remote experiment')
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    status = {'status': 'NOT_RUN', 'compiled': False, 'evm_executed': False,
              'commercial_admission': False, **producer}
    try:
        binary = fetch_compiler(directory)
        from prepare_compile import prepare
        status.update(prepare(directory/'compilation', str(binary), EXPECTED))
    except Exception as error:
        status.update(status='BLOCKED_OR_FAILED', error_type=type(error).__name__, error=str(error))
    status.update(producer)
    # Logs/summary only: no upload-artifact, cache, package registry or git writes.
    print('NQC013_STATUS_BEGIN')
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    print('NQC013_STATUS_END')
    (directory/'status.json').write_text(json.dumps(status, indent=2)+'\n')
    artifacts = {}
    compiled = directory/'compilation'
    for filename in ('compiler_version.txt', 'compiler_stdout.json', 'compiler_stderr.txt',
                     'compiled_contracts.json', 'status.json'):
        candidate = compiled/filename
        if candidate.is_file():
            raw = candidate.read_bytes()
            artifacts[filename] = {'sha256': sha(raw), 'bytes': len(raw),
                                   'text': raw.decode('utf-8', errors='strict')}
    encoded = gzip.compress(json.dumps(artifacts, ensure_ascii=False).encode(), mtime=0)
    # Explicitly bound log output. A too-large result is not silently truncated.
    if len(encoded) <= 250_000:
        print('NQC013_COMPILER_EVIDENCE_GZIP_BASE64_BEGIN')
        print(base64.b64encode(encoded).decode('ascii'))
        print('NQC013_COMPILER_EVIDENCE_GZIP_BASE64_END')
    else:
        print(json.dumps({'evidence_export': 'EXCEEDS_LOG_BOUND', 'gzip_bytes': len(encoded)}))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('# NQC 013 - compilation only\n\n')
            stream.write('```json\n' + json.dumps(status, indent=2) + '\n```\n')
            stream.write('No EVM execution, sponsorship acceptance or realized profit is established.\n')
    return 0 if status.get('compiled') is True else 2


if __name__ == '__main__':
    sys.exit(main())
