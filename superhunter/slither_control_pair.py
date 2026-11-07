"""Paired positive/negative Slither laboratory acceptance using fixed owned sources.

Two scanner processes remain untrusted and are NOT network isolated here.
Only a source-bound contrast is accepted; findings remain UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from . import native_compile, owned_process, slither_owned_runner as positive, static_review
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json

CLEAN_SOURCE = positive.OWNED_SOURCE.replace(b'tx.origin', b'msg.sender')
CLEAN_SHA256 = 'f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1'
assert hashlib.sha256(CLEAN_SOURCE).hexdigest() == CLEAN_SHA256
FILES = {'summary.json', 'COMPLETE.json', 'positive', 'clean'}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def accept(result: dict, positive_case: bool) -> None:
    """Never treat bool counts, missing source binding or a tool error as evidence."""
    if (type(result) is not dict or any(type(result.get(key)) is not int
                for key in ('source_bound_alerts', 'unique_alert_count', 'raw_alert_count')) or
            result.get('normalization_complete') is not True or
            result.get('vulnerability_confirmed') is not False or
            result.get('source_bound_alerts') != (1 if positive_case else 0) or
            result.get('unique_alert_count') != (1 if positive_case else 0) or
            result.get('raw_alert_count') != (1 if positive_case else 0) or
            result.get('source_sha256') != {positive.SOURCE_NAME:
                sha(positive.OWNED_SOURCE if positive_case else CLEAN_SOURCE)} or
            result.get('input_kind') != 'external-report'):
        raise ValueError('SLITHER_CONTROL_MISMATCH')
    if positive_case:
        alerts = result.get('alerts')
        if (type(alerts) is not list or len(alerts) != 1 or
                alerts[0].get('check') != positive.DETECTOR or
                alerts[0].get('source_bound') is not True):
            raise ValueError('SLITHER_POSITIVE_NOT_VERIFIED')
    elif result.get('alerts') != []:
        raise ValueError('SLITHER_CLEAN_FALSE_POSITIVE')


def _run_clean(solc_bytes: bytes, commit: str, out: Path) -> None:
    """Run clean control only; no tool execution when the fixed sources drift."""
    with tempfile.TemporaryDirectory(prefix='superhunter-slither-clean-') as temp:
        work = Path(temp)
        positive._write_local(work / 'Owned.sol', CLEAN_SOURCE, 0o400)
        positive._write_local(work / 'solc', solc_bytes, 0o500)
        command = [sys.executable, '-I', '-B', str(positive.ROOT / 'slither_owned_worker.py'),
                   str(work), 'clean']
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            completed = owned_process.run(command, cwd=work,
                                          env={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                                               'HOME': str(work), 'PATH': '/usr/bin:/bin',
                                               'PYTHONDONTWRITEBYTECODE': '1'},
                                          timeout=90, stdout=stdout, stderr=stderr)
            if completed.returncode != 0:
                raise ValueError('SLITHER_CLEAN_PROCESS_FAILURE')
            if stdout.seek(0, os.SEEK_END) > 2_000_000 or stderr.seek(0, os.SEEK_END) > 2_000_000:
                raise ValueError('SLITHER_CLEAN_OUTPUT_OVERFLOW')
        if (read_artifact(work, 'Owned.sol') != CLEAN_SOURCE or
                native_compile.read_pinned_binary(work / 'solc') != solc_bytes):
            raise ValueError('CLEAN_FIXTURE_CHANGED')
        report = read_artifact(work, positive.REPORT_NAME)
        parsed = strict_json(report)
        if (set(parsed) != {'success', 'error', 'results'} or
                parsed['success'] is not True or parsed['error'] is not None or
                type(parsed['results']) is not dict or
                type(parsed['results'].get('detectors')) is not list):
            raise ValueError('SLITHER_CLEAN_BAD_REPORT')
        context = {
            'schema_version': 1, 'scope_id': 'owned-fixed-local-fixture-clean',
            'repository': {'repo': 'superhunter-owned/fixture', 'commit': commit},
            'tool': {'name': 'slither', 'version': positive.SCANNER_VERSION},
            'detectors': [positive.DETECTOR], 'report_sha256': sha(report),
            'sources': {positive.SOURCE_NAME: sha(CLEAN_SOURCE)},
            'input_kind': 'external-report',
        }
        observed = static_review.normalize(report, context, {positive.SOURCE_NAME: CLEAN_SOURCE})
        accept(observed, False)
        positive._write_local(work / 'context.json', canonical(context), 0o400)
        imported = static_review.import_report(work / positive.REPORT_NAME,
                                               work / 'context.json', work, out)
        accept(imported, False)
        if imported != observed:
            raise ValueError('CLEAN_IMPORT_MISMATCH')


def run_pair(solc: Path, out: Path, commit: str) -> dict:
    if type(commit) is not str or re.fullmatch('[0-9a-f]{40}', commit) is None:
        raise ValueError('COMMIT_REQUIRED')
    positive._allow_output(out)
    if positive.doctor(solc)['status'] != 'OWNED_SLITHER_READY':
        raise ValueError('SLITHER_UNAVAILABLE')
    compiler = native_compile.read_pinned_binary(solc)
    # No root success marker exists until both controls have passed.
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.mkdir(mode=0o700, exist_ok=False)
    _run_clean(compiler, commit, out / 'clean')
    pos = positive.run_owned(solc, out / 'positive', repo_commit=commit)
    if (pos.get('status') != 'OWNED_SLITHER_IMPORTED_UNVERIFIED' or
            pos.get('source_bound_alerts') != 1 or pos.get('unique_alert_count') != 1 or
            pos.get('vulnerability_confirmed') is not False):
        raise ValueError('SLITHER_POSITIVE_DIVERGED')
    accept(static_review.verify_report(out / 'positive'), True)
    accept(static_review.verify_report(out / 'clean'), False)
    summary = {'schema_version': 1, 'status': 'OWNED_SLITHER_PAIR_UNVERIFIED',
               'positive_sha256': sha(positive.OWNED_SOURCE),
               'clean_sha256': sha(CLEAN_SOURCE), 'scanner': 'slither',
               'scanner_version': positive.SCANNER_VERSION, 'detector': positive.DETECTOR,
               'positive_count': 1, 'clean_count': 0,
               'scanner_executed_in_local_worker': True,
               'network_isolation_proven': False,
               'independent_execution_replay': False, 'vulnerability_confirmed': False}
    positive._write_local(out / 'summary.json', canonical(summary), 0o600)
    marker = {'schema_version': 1, 'sha256': {
        'summary.json': sha(read_artifact(out, 'summary.json')),
        'positive/COMPLETE.json': sha(read_artifact(out, 'positive/COMPLETE.json')),
        'clean/COMPLETE.json': sha(read_artifact(out, 'clean/COMPLETE.json'))}}
    positive._write_local(out / 'COMPLETE.json', canonical(marker), 0o600)
    return verify_pair(out)


def verify_pair(out: Path) -> dict:
    if {p.name for p in out.iterdir()} != FILES or any((out / n).is_symlink() for n in FILES):
        raise ValueError('PAIR_FILE_SET')
    marker = strict_json(read_artifact(out, 'COMPLETE.json'))
    expected = {'summary.json', 'positive/COMPLETE.json', 'clean/COMPLETE.json'}
    if (type(marker) is not dict or set(marker) != {'schema_version', 'sha256'} or
            type(marker['schema_version']) is not int or marker['schema_version'] != 1 or
            type(marker['sha256']) is not dict or set(marker['sha256']) != expected or
            any(sha(read_artifact(out, name)) != marker['sha256'][name] for name in expected)):
        raise ValueError('PAIR_HASHES')
    summary = strict_json(read_artifact(out, 'summary.json'))
    required = {'schema_version', 'status', 'positive_sha256', 'clean_sha256',
                'scanner', 'scanner_version', 'detector', 'positive_count',
                'clean_count', 'scanner_executed_in_local_worker', 'network_isolation_proven',
                'independent_execution_replay', 'vulnerability_confirmed'}
    if (set(summary) != required or type(summary['schema_version']) is not int or
            summary['schema_version'] != 1 or summary['status'] != 'OWNED_SLITHER_PAIR_UNVERIFIED' or
            summary['positive_sha256'] != sha(positive.OWNED_SOURCE) or
            summary['clean_sha256'] != sha(CLEAN_SOURCE) or summary['scanner'] != 'slither' or
            summary['scanner_version'] != positive.SCANNER_VERSION or
            summary['detector'] != positive.DETECTOR or
            type(summary['positive_count']) is not int or summary['positive_count'] != 1 or
            type(summary['clean_count']) is not int or summary['clean_count'] != 0 or
            summary['scanner_executed_in_local_worker'] is not True or
            summary['network_isolation_proven'] is not False or
            summary['independent_execution_replay'] is not False or
            summary['vulnerability_confirmed'] is not False):
        raise ValueError('PAIR_SUMMARY')
    accept(static_review.verify_report(out / 'positive'), True)
    accept(static_review.verify_report(out / 'clean'), False)
    return summary


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Fixed positive/clean Slither laboratory')
    modes = parser.add_subparsers(dest='command', required=True)
    run = modes.add_parser('run-owned-slither-pair')
    for name in ('solc', 'out'):
        run.add_argument('--' + name, required=True, type=Path)
    run.add_argument('--repo-commit', required=True)
    check = modes.add_parser('verify-owned-slither-pair')
    check.add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        summary = (run_pair(args.solc, args.out, args.repo_commit) if
                   args.command == 'run-owned-slither-pair' else verify_pair(args.bundle))
        print(json.dumps({'status': summary['status'], 'positive_count': 1, 'clean_count': 0,
                          'vulnerability_confirmed': False}))
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'OWNED_SLITHER_PAIR_BLOCKED',
                          'error_type': type(exc).__name__, 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
