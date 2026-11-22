"""Reconstruct a correction for a fixed NQC diagnostic and attest its exact changed lines."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .product_census_header import pinned
from .product_header_digest import SOURCE, SOURCE_SHA, variants
from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

MODULES = {
    'OpenHands/software-agent-sdk': ('151-software-agent-sdk', '3a893a1b26de7ec02cc0dd2427906eea6aea3fc7', [
        ('openhands-tools/openhands/tools/apply_patch/core.py', 'd6cbe551594b6f50c507338e9d4ea396188f0590', 'change_core.py')]),
    'SWE-agent/mini-swe-agent': ('152-mini-swe-agent', '04d809ceab9df28f9adaed044884180159172930', [
        ('src/minisweagent/utils/serialize.py', 'ccd5947bc9dbea7795555ca72670ccf6860d219f', 'trace_merge.py')]),
    'Aider-AI/aider': ('153-aider', '5dc9490bb35f9729ef2c95d00a19ccd30c26339c', [
        ('aider/diffs.py', '46266ac67802f960dfef1a1896dd1a7fdb65b532', 'aider/diffs.py'),
        ('aider/dump.py', '2c8bf31c2d80eafc6de73910cbf4e16e362dafd3', 'aider/dump.py')])}
LOCK = 'superhunter/product_supply/change-review-linux-py312.txt'


def assess(report, before, expected, diagnostic):
    old, new = before.decode().splitlines(), expected.decode().splitlines()
    if len(old) != len(new):
        raise EvidenceError('change review expects a replacement with stable line numbers')
    changed = [n for n, (a, b) in enumerate(zip(old, new), 1) if a != b]
    if changed != [4, 25] or diagnostic['line'] != changed[-1] or diagnostic['rule'] != 'G401':
        raise EvidenceError('diagnostic detached from source witness')
    diff = report['change']['unified'].splitlines()
    removed = [s[1:] for s in diff if s.startswith('-') and not s.startswith('--- ')]
    added = [s[1:] for s in diff if s.startswith('+') and not s.startswith('+++ ')]
    if (removed != [old[n-1] for n in changed] or added != [new[n-1] for n in changed]
            or re.search(r'(?m)^@@', report['change']['clean_comparison'])
            or report['change']['stale_patch_rejected'] is not True
            or report['file'] != 'header.go' or report['observation'] != diagnostic
            or report['source'] != {'before': sha(before), 'after': sha(expected)}):
        raise EvidenceError('reconstructed repair, diff and evidence record disagree')
    return {'lines': changed, 'diff_sha256': sha(report['change']['unified'].encode()),
            'before_sha256': sha(before), 'after_sha256': sha(expected),
            'evidence_record_sha256': sha(canonical(report)), 'diagnostic': diagnostic,
            'stale_patch_rejected': True}


def review(source_root, kit, go_report):
    if kit is None or go_report is None:
        raise EvidenceError('change review requires the scoring wheel directory and Go source diagnostic')
    raw = pinned(ROOT, SOURCE, SOURCE_SHA)
    changed = variants(raw)['changed']
    diagnostic, = go_report['diagnostics']
    if go_report['inputs_sha256']['changed'] != sha(changed):
        raise EvidenceError('Go receipt belongs to different source bytes')
    with tempfile.TemporaryDirectory(prefix='nqc-change-evidence-') as directory:
        work = Path(directory)
        for folder, revision, files in MODULES.values():
            repo = source_root/folder
            if git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
                raise EvidenceError('change review source revision differs')
            for path, oid, destination in files:
                blob = read_artifact(repo, path)
                if git(repo, 'rev-parse', revision + ':' + path).decode().strip() != oid or git_object('blob', blob) != oid:
                    raise EvidenceError('change review source blob differs')
                target = work/destination
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(blob)
        env = {'HOME': directory, 'TMPDIR': directory, 'PATH': '/usr/bin:/bin'}
        install_wheels(kit/'dspy-wheels', work, env, lock_path=LOCK, lock_digest='9f7cc2066f96f7a1aac2ebf7903acdaf22db4834226accede26a6b3dff033dc1', producer='NQC change review')
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S',
                               str(ROOT/'superhunter/product_change_worker.py')], check=True,
                              input=canonical({'before': changed.decode(), 'expected': raw.decode(), 'diagnostic': diagnostic}),
                              capture_output=True, cwd=work, env=env, timeout=30)
    decision = assess(strict_json(proc.stdout), changed, raw, diagnostic)
    return {name: {'revision': revision, 'source_blobs': {path: oid for path, oid, _ in files},
                   'result': decision, 'operation': operation}
            for (name, (_, revision, files)), operation in zip(MODULES.items(), (
                'reconstruct_repair_and_reject_stale_context', 'merge_source_diagnostic_and_change_history',
                'localize_source_edits_and_validate_clean_comparison'), strict=True)}
