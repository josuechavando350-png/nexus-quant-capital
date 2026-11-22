"""Prepare or open the fixed catalog, license and Census evidence session."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from zipfile import ZipFile

from superhunter.product_census_header import EIP_COMMIT, EIP_SHA, LOCK as HEADER_LOCK, LOCK_SHA as HEADER_LOCK_SHA
from superhunter.product_census_header import SPEC_COMMIT, SPEC_SHA, pinned
from superhunter.product_notice_overlap import DIGEST as PMD_SHA
from superhunter.product_notice_ranking import ISOLATE, LOCK as HAYSTACK_LOCK, LOCK_SHA as HAYSTACK_SHA
from superhunter.product_review import ROOT, repositories
from superhunter.product_solidity_headers import LOCK as WAKE_LOCK, LOCK_SHA as WAKE_LOCK_SHA, SOLC_SHA, WAKE_SHA
from superhunter.product_supply_review import ASVS_COMMIT, GUIDES_COMMIT, UPSTREAM, WHEELS
from superhunter.product_upstream_notices import sources
from superhunter.safe_io import canonical, strict_json, write_new_bundle
from superhunter.tools.fetch_upstream_notices import fetch
from superhunter.tools.verified_downloads import acquire

GH = 'https://github.com/'
RAW = 'https://raw.githubusercontent.com/'
ASSETS = {
    'syft.tgz': (GH + 'anchore/syft/releases/download/v1.38.2/syft_1.38.2_linux_amd64.tar.gz',
                 '6aa9a7b9e53c0f06e2d79fb24641cc1c856bb41702c282a577691f54bad94996'),
    'cvc5.zip': (GH + 'cvc5/cvc5/releases/download/cvc5-1.3.1/cvc5-Linux-x86_64-static.zip',
                 '1a1cda20d2df4938fa4944a69f33ddc9172e319ece0eed0aa09c4d7abede3ed1'),
    'foundry.tgz': (GH + 'foundry-rs/foundry/releases/download/v1.10.0/foundry_v1.10.0_linux_amd64.tar.gz',
                    '90729233bd9a683b872783ae2e3217fb56876fa2a3c37185f13e39dca8525041'),
    'qdrant.tgz': (GH + 'qdrant/qdrant/releases/download/v1.20.2/qdrant-x86_64-unknown-linux-musl.tar.gz',
                   '7c3e956b97830a9faa6391540330380c2fa4aa2f92df99bd8d1880a703b922af'),
    'solc': (GH + 'argotorg/solidity/releases/download/v0.8.24/solc-static-linux', SOLC_SHA),
    'pmd.zip': (GH + 'pmd/pmd/releases/download/pmd_releases%2F7.29.0/pmd-dist-7.29.0-bin.zip', PMD_SHA),
    'asvs.csv': (RAW + f'OWASP/ASVS/{ASVS_COMMIT}/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv', UPSTREAM['asvs.csv']),
    'asvs-guides.md': (RAW + f'OWASP/CheatSheetSeries/{GUIDES_COMMIT}/IndexASVS.md', UPSTREAM['asvs-guides.md']),
    'blocks.py': (RAW + f'ethereum/execution-specs/{SPEC_COMMIT}/src/ethereum/forks/prague/blocks.py', SPEC_SHA),
    'eip-7685.md': (RAW + f'ethereum/EIPs/{EIP_COMMIT}/EIPS/eip-7685.md', EIP_SHA),
}


def run(args, cwd=ROOT):
    subprocess.run(args, check=True, cwd=cwd, stdout=sys.stderr)


def fetch_asset(work, item, cache=None):
    name, (url, digest) = item
    def download(target):
        run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2', '--max-time', '300',
             '--output', target, url])
    acquire(work/name, digest, download, cache)


def prepare(work, cache=None):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda x: fetch_asset(work, x, cache), ASSETS.items()))
    for archive, member in [('syft.tgz', 'syft'), ('foundry.tgz', 'forge'), ('qdrant.tgz', 'qdrant')]:
        with tarfile.open(work/archive) as tar, (work/member).open('xb') as dest:
            with tar.extractfile(member) as src:
                shutil.copyfileobj(src, dest)
    with ZipFile(work/'cvc5.zip') as z, z.open('cvc5-Linux-x86_64-static/bin/cvc5') as src, (work/'cvc5').open('xb') as dest:
        shutil.copyfileobj(src, dest)
    wake = pinned(ROOT, WAKE_LOCK, WAKE_LOCK_SHA)
    (work/'wake-wheels.txt').write_bytes(wake + f'eth-wake==5.0.0 --hash=sha256:{WAKE_SHA}\n'.encode())
    (work/'haystack-wheels.txt').write_bytes(pinned(ROOT, HAYSTACK_LOCK, HAYSTACK_SHA))
    for lock, folder in [(ROOT/WHEELS, 'supply-wheels'), (work/'haystack-wheels.txt', 'haystack'), (work/'wake-wheels.txt', '.')]:
        run([sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'download',
             '--only-binary=:all:', '--no-deps', '--require-hashes', '-r', lock, '-d', work/folder])
    lock = pinned(ROOT, HEADER_LOCK, HEADER_LOCK_SHA)
    (work/'package-lock.json').write_bytes(lock)
    (work/'package.json').write_bytes(canonical(strict_json(lock)['packages']['']))
    run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', work/'npm-cache'], cwd=work)
    with ThreadPoolExecutor(max_workers=6) as pool:
        docs = dict(pool.map(fetch, sources()))
    write_new_bundle(work/'upstream', docs)
    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp)/'supply-venv'
        run([sys.executable, '-m', 'venv', venv])
        python = venv/'bin/python'
        run([*ISOLATE, python, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check', 'install',
             '--no-index', '--no-deps', '--require-hashes', '--find-links', work/'supply-wheels', '-r', ROOT/WHEELS])
        run([*ISOLATE, sys.executable, '-B', '-m', 'superhunter', 'review-product', '--syft', work/'syft',
             '--cvc5', work/'cvc5', '--out', work/'product'])
        run([*ISOLATE, python, '-B', '-m', 'superhunter', 'review-product-supply', '--product', work/'product',
             '--out', work/'supply', '--asvs-csv', work/'asvs.csv', '--guide-index', work/'asvs-guides.md'])


NATIVE_INPUTS = frozenset((
    'ast-grep', 'cargo-deny', 'cargo-home', 'cdxgen-bundle', 'dependency-track', 'dotnet-runtime', 'guac-bundle',
    'json-grammar', 'license-proof-kits', 'lief-wheel', 'notice-review-wheels', 'osv-license-cache',
    'pgvector-packages', 'producer-bin-dir', 'profile-wheels', 'proptest-crates', 'qemu-aarch64',
    'rust-bin', 'rustsec-crates', 'sarif-sdk', 'scancode-release', 'scorecard', 'syft-arm64', 'tlc-jar', 'tree-sitter'))


def native_inputs(manifest):
    from superhunter.safe_io import read_artifact
    data = strict_json(read_artifact(manifest.parent, manifest.name))
    if not isinstance(data, dict) or set(data) != NATIVE_INPUTS:
        raise ValueError('native profile must name all and only the reviewed input slots')
    options = []
    for key, name in sorted(data.items()):
        if not isinstance(name, str) or not name or '\x00' in name:
            raise ValueError('invalid native input path')
        path = (manifest.parent/name).resolve(strict=True)
        options.extend(['--' + key, str(path)])
    return options


def review_queries():
    return [r['repository'] for r in repositories()] + [
        'batch:1', 'batch:2', 'upstream-notices', 'solidity-headers', 'notice:redistribution',
        'notice-overlaps:upstream-002-license.txt', 'census-header', 'integration-coverage', 'geth-census',
        'source-references', 'source-inventory', 'root-declarations', 'owned-source-checks', 'integration-matrix',
        'score-comparison', 'assurance-wheel-notices', 'recursive-source-trees', 'fork-headers']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-queries', action='store_true', help='run the 218 published PR 115 queries in order')
    parser.add_argument('--native-inputs', type=Path, help='use the complete reviewed native profile with local paths')
    parser.add_argument('--prepare', action='store_true', help='download fixed public inputs into a new external directory')
    from superhunter.product_native_capabilities import add_arguments, selected_kits
    add_arguments(parser)
    from superhunter.product_component_controls import DOMAINS
    parser.add_argument('--component-controls', choices=['all', *DOMAINS], help='consume fixed offline controls for the selected domain')
    parser.add_argument('--owned-source-kit', type=Path, help='fixed offline code and package reference comparisons')
    parser.add_argument('--fork-headers', action='store_true', help='validate two fixed headers using client schedules and the Hive corpus')
    parser.add_argument('--gosec-kit', type=Path, help='review the fixed NQC header digest with the verified Go toolchain')
    parser.add_argument('--score-kit', type=Path, help='offline wheel sets for the two fixed evaluation engines')
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--embedded-root-manifests', action='store_true', help='use the verified Git records stored in the product')
    sources.add_argument('--root-manifests', type=Path, help='verified dependency files from remote root trees')
    parser.add_argument('--download-cache', type=Path, help='reuse hash-verified assets outside the checkout (preparation only)')
    parser.add_argument('--compare-sources', type=Path, metavar='WORKSPACE', help='compare file IDs among the 200 pinned trees')
    parser.add_argument('--source-inventory', action='store_true', help='join the reviewed source audit')
    parser.add_argument('--source-references', type=Path, help='checkout containing pinned source type definitions')
    parser.add_argument('--geth-header', type=Path, help='pinned optional native Geth comparator')
    parser.add_argument('workspace', type=Path)
    parser.add_argument('queries', nargs='*', help='query-product keys; default: lines from stdin')
    args = parser.parse_args()
    if args.review_queries and args.queries:
        parser.error('choose the published queries or individual keys')
    queries = review_queries() if args.review_queries else args.queries
    if args.review_queries and args.gosec_kit and args.embedded_root_manifests:
        queries.extend(['portable-source-proof', 'go-header-digest'])
    if args.review_queries and args.component_controls:
        queries.append('component-controls')
    kits = selected_kits(args)
    if args.review_queries and kits:
        queries.append('native-capabilities')
    if args.compare_sources and not args.review_queries:
        parser.error('--compare-sources requires --review-queries to join the live integration matrix')
    work = args.workspace.resolve()
    cache = args.download_cache
    if cache is not None:
        if not args.prepare:
            parser.error('--download-cache requires --prepare')
        if cache.is_symlink():
            parser.error('download cache cannot be a symlink')
        cache = cache.resolve()
        if cache.is_relative_to(ROOT) or cache.is_relative_to(work) or work.is_relative_to(cache):
            parser.error('download cache and workspace must be separate directories outside the checkout')
    if args.prepare:
        if work.is_relative_to(ROOT) or work.exists():
            parser.error('preparation requires a new directory outside the checkout')
        work.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the destination; readers only open a completely prepared session.
        work.mkdir(mode=0o700)
        try:
            prepare(work, cache)
            (work/'READY').write_text('catalog-session-v1\n')
        except BaseException:
            shutil.rmtree(work)
            raise
    if not (work/'READY').is_file() or (work/'READY').read_text() != 'catalog-session-v1\n':
        parser.error('incomplete catalog session')
    cmd = [*ISOLATE, sys.executable, '-B', '-m', 'superhunter', 'query-product',
           '--bundle', work/'product', '--supply', work/'supply', '--notice-wheels', work/'supply-wheels',
           '--upstream-notices', work/'upstream', '--census-header-kit', work, '--solidity-metadata-kit', work,
           '--qdrant', work/'qdrant', '--haystack-wheels', work/'haystack', '--pmd-release', work/'pmd.zip',
           *(native_inputs(args.native_inputs.resolve()) if args.native_inputs else []),
           *(['--owned-source-kit', args.owned_source_kit.resolve()] if args.owned_source_kit else []),
           *[value for group, path in sorted(kits.items()) for value in ('--' + group + '-native-kit', path)],
           *(['--component-controls', args.component_controls] if args.component_controls else []),
           *(['--fork-headers'] if args.fork_headers else []),
           *(['--gosec-kit', args.gosec_kit.resolve()] if args.gosec_kit else []),
           *(['--score-kit', args.score_kit.resolve()] if args.score_kit else []),
           *(['--embedded-root-manifests'] if args.embedded_root_manifests else []),
           *(['--root-manifests', args.root_manifests.resolve()] if args.root_manifests else []),
           *(['--source-inventory'] if args.source_inventory else []),
           *(['--source-references', args.source_references.resolve()] if args.source_references else []),
           *(['--geth-header', args.geth_header.resolve()] if args.geth_header else []), *queries]
    if args.compare_sources:
        from superhunter.product_source_overlap import build, coverage
        run = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE)
        if run.returncode:
            sys.stdout.buffer.write(run.stdout)
            return run.returncode
        lines = run.stdout.splitlines()
        if len(lines) != len(queries):
            parser.exit(2, 'incomplete product transcript\n')
        try:
            matrix = strict_json(lines[queries.index('integration-matrix')])
            overlap = build(args.compare_sources)
            participation = coverage(overlap, matrix)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            parser.exit(2, f'source comparison incomplete: {error}\n')
        sys.stdout.buffer.write(run.stdout + canonical(overlap) + canonical(participation))
        return 0
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
