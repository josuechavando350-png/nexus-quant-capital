"""Install the tested Linux x86-64 toolkit into a private runtime directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from .product_sources import toolkit_sources
from .toolkit_build import DEPS, build_components

ROOT = Path(__file__).resolve().parents[1]
RELEASES = (
    ('solc', 'ethereum/solidity', 'v0.8.24', 'solc-static-linux', None,
     'fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'),
    ('forge', 'foundry-rs/foundry', 'v1.10.0', 'foundry_v1.10.0_linux_amd64.tar.gz', 'forge',
     '90729233bd9a683b872783ae2e3217fb56876fa2a3c37185f13e39dca8525041'),
    ('medusa', 'crytic/medusa', 'v1.5.1', 'medusa-linux-x64.tar.gz', 'medusa',
     'ddfe1517ae9028ef9fc331b00f5a6a9d5406f3fcd11a715d60c6b6fb3e4546d3'),
    ('echidna', 'crytic/echidna', 'v2.4.0', 'echidna-2.4.0-x86_64-linux.tar.gz', 'echidna',
     'a77a90501dd6269e12807156e9d409b160ce0c87fbb36fe323a896a4fb7a2d1d'),
    ('nuclei', 'projectdiscovery/nuclei', 'v3.11.1', 'nuclei_3.11.1_linux_amd64.zip', 'nuclei',
     'ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6'),
    ('gambit', 'Certora/gambit', 'v1.0.6', 'gambit-linux-v1.0.6', None,
     '76321d84564ff4d8222bfb359f1fe67eae69f21e689dbc9c23760257a94864fa'),
    ('libz3.so.4.12', 'Z3Prover/z3', 'z3-4.12.2', 'z3-4.12.2-x64-glibc-2.35.zip',
     'z3-4.12.2-x64-glibc-2.35/bin/libz3.so', '29604c87d74855690f5f43fa2ecb8e214af89bdddffac378ce403e29c6ea30ec'),
)
PYTHON_SOURCES = (
    ('crytic-compile', 'crytic/crytic-compile', 'b4f7d296d141ee8fb806cb573daaf3369e9bd125'),
    ('crypto', 'Legrandin/pycryptodome', 'cde63f8f9b64f1c8cd86249128cfd5986c2c43af'),
    ('cbor2', 'agronholm/cbor2', '6427d378872f6ea43d1f7053ad40bc1b760727f5'),
    ('select', 'crytic/solc-select', '0ec2946474fed4523bf91cb1f11f0b75a3a4bc76'),
)


def run(*args, cwd=None, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=600)


def install_release(folder, row):
    name, repo, tag, asset, member, digest = row
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        download = Path(tmp) / asset
        run('curl', '-fsSL', '--retry', '2', '--max-time', '180', '-o', download,
            f'https://github.com/{repo}/releases/download/{tag}/{asset}')
        with download.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise ValueError('release checksum mismatch: ' + name)
        output = Path(tmp) / 'checked'
        if member is None:
            download.rename(output)
        elif asset.endswith('.zip'):
            with zipfile.ZipFile(download) as archive, archive.open(member) as source, output.open('wb') as dest:
                shutil.copyfileobj(source, dest)
        else:
            with tarfile.open(download) as archive, archive.extractfile(member) as source, output.open('wb') as dest:
                shutil.copyfileobj(source, dest)
        output.chmod(0o755)
        output.replace(folder / name)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--wheelhouse', type=Path, action='append', default=[],
                        help='local directories of locked native Slither wheels (repeatable)')
    aderyn = parser.add_mutually_exclusive_group()
    aderyn.add_argument('--build-aderyn', action='store_true', help='build the CLI from its pinned source with Cargo')
    aderyn.add_argument('--aderyn-archive', type=Path, help='original Linux x86-64 Aderyn 0.6.8 release archive')
    args = parser.parse_args(argv)
    folder = args.runtime.resolve()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 12):
        parser.error('requires Linux x86-64 and Python 3.12')
    if folder.is_relative_to(ROOT):
        parser.error('put the runtime outside the source checkout')
    folder.mkdir(parents=True, exist_ok=True)
    try:
        from .toolkit_static_setup import build_aderyn, install_aderyn
        def prepare_aderyn():
            if args.build_aderyn:
                build_aderyn(ROOT, folder)
            else:
                install_aderyn(args.aderyn_archive, folder)

        if any(folder.iterdir()):
            if not ((folder / 'static/venv/bin/slither').is_file() and (folder / 'forge').is_file()
                    and (args.aderyn_archive or args.build_aderyn or not (folder / 'aderyn').exists())):
                parser.error('choose a new runtime, or supply Aderyn to a prepared native toolkit')
            prepare_aderyn()
            return 0
        run('git', 'submodule', 'update', '--init', '--jobs', '6', '--',
            *(row['path'] for row in toolkit_sources()), cwd=ROOT)
        for release in RELEASES:
            install_release(folder, release)
        for name, repo, commit in (*PYTHON_SOURCES, *DEPS):
            dest = folder / name
            run('git', 'init', '-q', dest)
            run('git', 'fetch', '-q', '--depth=1', f'https://github.com/{repo}.git', commit, cwd=dest)
            run('git', 'checkout', '-q', '--detach', commit, cwd=dest)
        build_components(ROOT, folder)
        wheels = folder / 'wheels'
        run('uv', 'build', '--offline', '--wheel', '--out-dir', wheels, folder / 'crytic-compile')
        run(sys.executable, '-m', 'venv', '--system-site-packages', folder / 'venv')
        python = folder / 'venv/bin/python'
        run(python, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-build-isolation', folder / 'crypto',
            wheels / 'crytic_compile-0.4.2-py3-none-any.whl',
            env={**os.environ, 'CC': 'gcc', 'LDSHARED': 'gcc -shared'})
        run('npm', 'install', '--prefix', folder / 'js', '--ignore-scripts', '--no-audit', '--no-fund',
            '--no-save', 'ts-node@10.9.1', 'typescript@4.8.4', 'solidity-ast@0.4.62', 'semver@7.3.8')
        from .toolkit_static_setup import install
        install(ROOT, folder, args.wheelhouse)
        prepare_aderyn()
        print(json.dumps({'runtime': str(folder), 'next': 'python3 -m superhunter toolkit check --runtime DIR --require-all-analyzers'}))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
