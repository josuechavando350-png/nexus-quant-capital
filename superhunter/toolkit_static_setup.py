"""Prepare isolated native analyzers for the fixed NQC contract review."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from .product_slither_native import PINS, PINS_SHA
from .product_sources import git, toolkit_sources

SETUPTOOLS = '9aa3771f57f070bd13b9a3e83bd469413afc98c7'
SEMGREP_URL = 'https://registry.npmjs.org/@zibby/bin-semgrep-linux-x64/-/bin-semgrep-linux-x64-1.169.0.tgz'
SEMGREP_SHA = '11511eaa267d4edd235ea266a3a19158ba3ec077776fa1cd2f66c7dd769f5ffc'
ADERYN_SHA = 'ffd6ca658962e211a3ac821c646f69c8e14bf1b1001cbfe091bcd4535a691e46'


def run(*args):
    subprocess.run(args, check=True, timeout=600)


def checked_file(path, expected):
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('unexpected SHA-256 for ' + path.name)


def install_aderyn(archive, runtime):
    checked_file(archive, ADERYN_SHA)
    with tempfile.TemporaryDirectory(dir=runtime) as stage, tarfile.open(archive) as package:
        members = [m for m in package if m.isfile() and Path(m.name).name == 'aderyn']
        if len(members) != 1:
            raise ValueError('expected one Aderyn executable in the verified archive')
        tmp = Path(stage) / 'aderyn'
        with tmp.open('wb') as out, package.extractfile(members[0]) as source:
            shutil.copyfileobj(source, out)
        tmp.chmod(0o755)
        tmp.replace(runtime / 'aderyn')


def export_source(repo, commit, dest):
    with tempfile.TemporaryFile() as contents:
        subprocess.run(['git', '-C', repo, 'archive', commit], check=True, stdout=contents, timeout=180)
        contents.seek(0)
        with tarfile.open(fileobj=contents) as package:
            package.extractall(dest, filter='data')


def build_aderyn(root, runtime):
    source = root / 'upstream/aderyn'
    commit = next(r['commit'] for r in toolkit_sources() if r['path'] == 'upstream/aderyn')
    with tempfile.TemporaryDirectory(dir=runtime) as temp:
        build = Path(temp)
        export_source(source, commit, build)
        # rustup reads the pinned nightly from the upstream rust-toolchain.toml.
        subprocess.run(['cargo', 'build', '--locked', '--release', '-p', 'aderyn', '--bin', 'aderyn',
                        '--target-dir', build / 'target'], cwd=build, check=True, timeout=3600)
        binary = build / 'target/release/aderyn'
        version = subprocess.check_output([binary, '--version'], text=True, timeout=15)
        if version.strip().lower() != 'aderyn 0.6.8':
            raise ValueError('unexpected built Aderyn version')
        binary.replace(runtime / 'aderyn')


def install(root, runtime, wheelhouses, aderyn=None):
    destination = runtime / 'static'
    if destination.exists():
        raise ValueError('native analyzers are already installed in this runtime')
    # Build directly at the final path because Python entry points embed the venv path.
    destination.mkdir()
    try:
        with tempfile.TemporaryDirectory(dir=runtime) as tmp:
            stage = Path(tmp)
            pins = root / PINS
            checked_file(pins, PINS_SHA)
            packages = json.loads(pins.read_bytes())['packages']
            lock = stage / 'requirements.txt'
            lock.write_text(''.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in packages))
            run(sys.executable, '-m', 'venv', destination / 'venv')
            python = destination / 'venv/bin/python'
            indexes = []
            if wheelhouses:
                indexes.append('--no-index')
                for directory in wheelhouses:
                    indexes.extend(['--find-links', str(directory.resolve(strict=True))])
            run(python, '-m', 'pip', '--disable-pip-version-check', 'install', '--only-binary=:all:',
                '--require-hashes', *indexes, '-r', lock)
            build = stage / 'setuptools'
            run('git', 'init', '-q', build)
            run('git', '-C', build, 'fetch', '-q', '--depth=1', 'https://github.com/pypa/setuptools.git', SETUPTOOLS)
            run('git', '-C', build, 'checkout', '-q', '--detach', SETUPTOOLS)
            run(sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps', '--no-build-isolation',
                '--wheel-dir', stage, build)
            wheel, = stage.glob('setuptools-*.whl')
            run(python, '-m', 'pip', 'install', '--no-index', '--no-deps', wheel)
            plugin = stage / 'plugin'
            origin = root / 'upstream/slitherin'
            commit = next(r['commit'] for r in toolkit_sources() if r['path'] == 'upstream/slitherin')
            export_source(origin, commit, plugin)
            detector = plugin / 'slitherin/detectors/public_vs_external.py'
            before = '                    used_functions.add(call.name)'
            after = '                    if call.function is not None:\n                        used_functions.add(call.function.name)'
            original = git(origin, 'show', commit + ':slitherin/detectors/public_vs_external.py').decode()
            if original.count(before) != 1 or detector.read_text() != original:
                raise ValueError('Slitherin compatibility patch does not match its pinned source')
            detector.write_text(original.replace(before, after))
            run(python, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-build-isolation', plugin)

            download = stage / 'semgrep.tgz'
            run('curl', '-fsSL', '--retry', '2', '--max-time', '180', '-o', download, SEMGREP_URL)
            checked_file(download, SEMGREP_SHA)
            with tarfile.open(download) as package:
                package.extractall(destination, filter='data')
            (destination / 'package').rename(destination / 'semgrep')
            (destination / 'semgrep/osemgrep').symlink_to('semgrep-core')
            if aderyn:
                install_aderyn(aderyn, runtime)
    except BaseException:
        shutil.rmtree(destination)
        raise
