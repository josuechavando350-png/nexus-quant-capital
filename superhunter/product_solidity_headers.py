"""Compare Foundry profiles, Wake header metadata and solc parse-only metadata on the frozen NQC migration."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile

from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import canonical, read_artifact, strict_json

MANIFEST = 'migration/source-manifest.json'
MANIFEST_SHA = '07c126f5ccaba1d05d22e4adf964d57f59707d158ce76856ed92badec83a9b67'
FORGE_SHA = 'bf2f6a6f290389f9db6c850c82789472710394128250a99988e63f642c19a8b1'
SOLC_SHA = 'fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'
WHEEL = 'eth_wake-5.0.0-cp312-cp312-manylinux_2_28_x86_64.whl'
WAKE_SHA = '49db657cd8923c5b2015ef02904f0a63fe534391023259ca4b28e045a6a7c4f4'
LOCK = 'superhunter/product_supply/wake-metadata-linux-py312.txt'
LOCK_SHA = 'c674ff40372ce067db9eb66305966a0572b82f30893e271255f4ad70a05169a4'
MODULES = ('wake/core/solidity_version.py', 'wake/regex_parser/__init__.py',
           'wake/regex_parser/solidity_import.py', 'wake/regex_parser/solidity_parser.py')


def inputs():
    raw = read_artifact(ROOT, MANIFEST)
    if sha(raw) != MANIFEST_SHA:
        raise EvidenceError('unexpected NQC migration manifest')
    sources, configs = {}, {}
    for row in strict_json(raw)['files']:
        path = row['destination_path']
        if path.startswith('ci/') and path.endswith(('.sol', '/foundry.toml')):
            data = read_artifact(ROOT, path)
            if not (len(data) == row['bytes'] and sha(data) == row['source_sha256'] == row['payload_sha256']
                    and row['transformation'] == 'byte_identical'):
                raise EvidenceError('Solidity inventory differs from migration')
            group = configs if path.endswith('/foundry.toml') else sources
            group[path] = data.decode()
    return sources, configs


def run(args, work, env, payload=None):
    result = subprocess.run([*ISOLATE, *args], input=canonical(payload) if payload is not None else b'',
                            cwd=work, env=env, capture_output=True, timeout=75, check=True)
    return json.loads(result.stdout)


def compare(sources, profiles, wake, parsed):
    if set(wake) != set(sources) or set(parsed.get('sources', {})) != set(sources):
        raise EvidenceError('incomplete Solidity source observations')
    if any(e['severity'] == 'error' for e in parsed.get('errors', [])):
        raise EvidenceError('solc parse-only reported an error')
    files = {}
    for path, source in sorted(sources.items()):
        raw = source.encode()
        observed = wake[path]
        ast = parsed['sources'][path]['ast']
        nodes = ast['nodes']
        imports = sorted({n['file'] for n in nodes if n['nodeType'] == 'ImportDirective'})
        pragmas = [n['literals'] for n in nodes if n['nodeType'] == 'PragmaDirective']
        if (ast['nodeType'] != 'SourceUnit' or ast['absolutePath'] != path or ast.get('license') != 'MIT'
                or pragmas != [['solidity', '^', '0.8', '.24']] or imports != observed['imports']
                or observed['accepts'] != {'0.8.23': False, '0.8.24': True, '0.8.25': True, '0.9.0': False}
                or observed['blake2b_256'] != hashlib.blake2b(raw, digest_size=32).hexdigest()):
            raise EvidenceError('native Solidity header observations disagree')
        parent = next((str(d / 'foundry.toml') for d in PurePosixPath(path).parents
                       if str(d / 'foundry.toml') in profiles), None)
        if parent and not observed['accepts'].get(profiles[parent]['solc']):
            raise EvidenceError('source pragma excludes the associated compiler profile')
        edges = [{'literal': name, 'in_snapshot_at_relative_path': name.startswith(('./', '../')) and
                  posixpath.normpath(posixpath.join(posixpath.dirname(path), name)) in sources} for name in imports]
        files[path] = {'input_sha256': sha(raw), 'blake2b_256': observed['blake2b_256'], 'declared_spdx': ast['license'],
                       'imports': edges, 'version_probes': observed['accepts'], 'enclosing_profile': parent}
    edges = [edge for row in files.values() for edge in row['imports']]
    present = sum(edge['in_snapshot_at_relative_path'] for edge in edges)
    return {'source_manifest_sha256': MANIFEST_SHA, 'profiles': profiles, 'solidity_files': files,
            'sources_with_enclosing_profile': sum(r['enclosing_profile'] is not None for r in files.values()),
            'relative_import_edges': len(edges), 'present': present, 'unresolved': len(edges) - present}


def build(cache):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('the locked Solidity header reader requires CPython 3.12')
    sources, configs = inputs()
    with tempfile.TemporaryDirectory(prefix='nqc-solidity-headers-') as tmp:
        work = Path(tmp)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'FOUNDRY_OFFLINE': 'true', 'LC_ALL': 'C'}
        copy_release('Foundry', cache/'forge', work/'forge', FORGE_SHA)
        copy_release('solc', cache/'solc', work/'solc', SOLC_SHA)
        copy_release('Wake', cache/WHEEL, work/WHEEL, WAKE_SHA, executable=False)
        install_wheels(cache, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Wake metadata')
        with ZipFile(work/WHEEL) as wheel:
            for name in MODULES:
                dest = work/'lib'/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(wheel.read(name))
        profiles = {}
        for i, (path, text) in enumerate(sorted(configs.items())):
            root = work / str(i)
            root.mkdir()
            (root/'foundry.toml').write_text(text)
            expected = tomllib.loads(text)['profile']['default']
            config = run([work/'forge', 'config', '--root', root, '--json'], root, env)
            if config['offline'] is not True or any(config['solc' if k == 'solc_version' else k] != v
                                                     for k, v in expected.items()):
                raise EvidenceError('Foundry profile differs from source TOML')
            profiles[path] = {k: config[k] for k in ('solc', 'evm_version', 'optimizer_runs')}
        versions = sorted({'0.8.23', '0.8.25', '0.9.0'} | {p['solc'] for p in profiles.values()})
        worker = Path(__file__).with_name('product_solidity_headers_worker.py')
        wake = run([sys.executable, '-I', '-B', '-S', worker], work, env, {'sources': sources, 'versions': versions})
        parsed = run([work/'solc', '--no-import-callback', '--standard-json'], work, env, {
            'language': 'Solidity', 'sources': {p: {'content': s} for p, s in sources.items()},
            'settings': {'stopAfter': 'parsing', 'outputSelection': {'*': {'': ['ast']}}}})
    return compare(sources, profiles, wake, parsed)


def attach(index, kit):
    joint = build(kit)
    index.solidity_headers = joint
    evidence = {'report': 'solidity-headers', 'report_sha256': sha(canonical(joint)),
                'source_manifest_sha256': joint['source_manifest_sha256']}
    for name, version, digest, role in (
            ('foundry-rs/foundry', '1.10.0', FORGE_SHA, 'compiler_profiles'),
            ('ack3-ai/wake', '5.0.0', WAKE_SHA, 'source_headers'),
            ('argotorg/solidity', '0.8.24', SOLC_SHA, 'parse_only_source_metadata')):
        index.repos[name]['solidity_metadata_evidence'] = {
            **evidence, 'version': version, 'distribution_member_sha256': digest, 'role': role}
