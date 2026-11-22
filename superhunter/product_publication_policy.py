"""Evaluate upstream packaging inputs on disposable, offline release workspaces."""
from pathlib import Path
import re
import subprocess
import tempfile

from .product_reasoning import EvidenceError
from .product_report_quality_sources import pinned_blobs
from .product_review import ROOT, sha
from .safe_io import read_artifact, strict_json

PINS = 'superhunter/product_supply/publication-policy-inputs.json'
DIGEST = '33ca06a45f0a738588979731d3068acdcafb8d6467432de98ffb591478fdcf0f'
# These paths are fixed across projects; only the location of the upstream rule file varies.
OUTPUTS = (
    '.DS_Store', '.gradle/cache.bin', '.idea/workspace.xml', '.pytest_cache/v/cache/nodeids',
    '.vscode/launch.json', '_site/index.html', '__pycache__/review.cpython-312.pyc',
    'bin/tool', 'build/result.json', 'cache/probe.json', 'coverage/index.html', 'cover.out',
    'dist/artifact.zip', 'docs/book/index.html', 'node_modules/test/package.json', 'out/review.json',
    'review.exe', 'review.log', 'review.o', 'target/debug/review', 'vendor/example/notice.txt',
)
CONTROL = 'nqc-release-control.keep'


def git(work, *args, data=None, allowed=(0,)):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/dev/null', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_ALLOW_PROTOCOL': '', 'GIT_OPTIONAL_LOCKS': '0'}
    proc = subprocess.run(['/usr/bin/git', '-C', work, '-c', 'core.excludesFile=/dev/null',
                           '-c', 'core.hooksPath=/dev/null', *args],
                          input=data, capture_output=True, env=env, timeout=15)
    if proc.returncode not in allowed:
        raise EvidenceError('offline Git publication check failed')
    return proc.stdout


def paths(raw):
    return {p.decode() for p in raw.split(b'\0') if p}


def ignore_policy(location, raw):
    with tempfile.TemporaryDirectory(prefix='nqc-publication-') as tmp:
        work = Path(tmp)
        git(work, 'init', '--quiet', '--template=')
        parent = Path(location).parent
        samples = {(parent / item).as_posix() for item in (*OUTPUTS, CONTROL)}
        if parent != Path('.'):
            samples.add('_site/index.html')  # A docs-only policy cannot govern the repository root.
        for name in samples:
            path = work/name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(b'owned release fixture\n')
        baseline = paths(git(work, 'ls-files', '--others', '--exclude-standard', '-z'))
        if baseline != samples:
            raise EvidenceError('clean Git worktree already excluded release fixtures')
        (work/location).write_bytes(raw)
        visible = paths(git(work, 'ls-files', '--others', '--exclude-standard', '-z'))
        ignored = samples - visible
        probe = b''.join(p.encode() + b'\0' for p in sorted(samples))
        matched = paths(git(work, 'check-ignore', '-z', '--no-index', '--stdin', data=probe, allowed=(0, 1)))
        if ignored != matched or not ignored or (parent/CONTROL).as_posix() in ignored:
            raise EvidenceError('upstream ignore policy lacks a corroborated decision and held-out control')
        if parent != Path('.') and '_site/index.html' in ignored:
            raise EvidenceError('nested ignore rules escaped their directory')
        (work/location).unlink()
        if paths(git(work, 'ls-files', '--others', '--exclude-standard', '-z')) != baseline:
            raise EvidenceError('removing upstream policy did not restore the original staging candidates')
        return {'fixtures': len(samples), 'excluded_from_untracked_files': sorted(ignored),
                'available_for_staging': sorted(samples - ignored), 'restored_after_removal': True}


def dependency_policy(dockerfile, requirements):
    lines = [ln.strip() for ln in dockerfile.decode('utf-8-sig').splitlines() if ln.strip()]
    bases = [line[5:] for line in lines if line.startswith('FROM ')]
    if len(bases) != 1 or lines.count('RUN python3 -m pip install -r requirements.txt') != 1:
        raise EvidenceError('recipe does not consume the reviewed requirements')
    if 'COPY . /opt/jwt_tool' not in lines or lines.index('COPY . /opt/jwt_tool') > lines.index('RUN python3 -m pip install -r requirements.txt'):
        raise EvidenceError('requirements are not copied before installation')
    declared = {}
    for line in requirements.decode('utf-8-sig').splitlines():
        token = line.strip()
        if not token or token.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)(?:==([A-Za-z0-9_.+-]+))?', token)
        if not match or match[1].casefold() in declared:
            raise EvidenceError('unsupported or repeated dependency declaration')
        declared[match[1].casefold()] = match[2]
    if not declared:
        raise EvidenceError('empty build requirements')
    return {'base_image': bases[0], 'base_digest_pinned': bool(re.fullmatch(r'.+@sha256:[0-9a-f]{64}', bases[0])),
            'packages': declared, 'unpinned_packages': sorted(name for name, version in declared.items() if version is None)}


def review(root):
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != DIGEST:
        raise EvidenceError('publication policy inputs differ from the reviewed pins')
    observed = {}
    for source in strict_json(raw)['sources']:
        files = pinned_blobs(root/source['path'], source['revision'], source['files'])
        if 'Dockerfile' in files:
            comparison = dependency_policy(files['Dockerfile'], files['requirements.txt'])
            operation = 'check_version_reproducibility_of_declared_container_inputs'
        else:
            (location, rules), = files.items()
            comparison = ignore_policy(location, rules)
            operation = 'check_staging_of_release_artifacts_against_upstream_ignore_rules'
        observed[source['repository']] = {
            'revision': source['revision'], 'role': 'reference', 'operation': operation,
            'source_blobs': {p: entry[1] for p, entry in source['files'].items()}, 'result': comparison}
    return observed
