"""Reconcile the NQC dependency graph with the cargo-lock CLI from the RustSec workspace."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import tomllib

from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import canonical

RELEASE = 'cargo-lock-11.1.0'
DIGEST = '50524592e6bfbb1bf6f94e8184a786f637faeaf1cf37bbe65502b9a2c5c48939'
REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def unpack(cache, work, name, checksum, destination):
    archive = work/(name + '.crate')
    copy_release('RustSec build input', cache/archive.name, archive, checksum, executable=False)
    if (destination/name).exists():
        raise EvidenceError('duplicate crate in RustSec build')
    files = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            path = Path(member.name)
            if path.parts[:1] != (name,) or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise EvidenceError('invalid path in pinned RustSec build input')
            if member.isdir():
                continue
            relative = str(path.relative_to(name))
            if relative in files or relative == '.cargo-checksum.json':
                raise EvidenceError('duplicate file in pinned RustSec build input')
            raw = tar.extractfile(member).read()
            target = destination/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            files[relative] = sha(raw)
    (destination/name/'.cargo-checksum.json').write_bytes(canonical({'package': checksum, 'files': files}))


def assess(text, graph):
    nodes = {r['name'] + '@' + r['version']: sorted(r['requires']) for r in graph['nodes']}
    actual = {}
    current = None
    for line in text.splitlines():
        prefix = '  - ' if line.startswith('  - ') else '- '
        if not line.startswith(prefix) or len(fields := line[len(prefix):].split()) != 2:
            raise EvidenceError('invalid cargo-lock list output')
        key = '@'.join(fields)
        if prefix == '- ':
            if key in actual:
                raise EvidenceError('duplicate cargo-lock package')
            current = key
            actual[current] = []
        elif current is None:
            raise EvidenceError('cargo-lock dependency without a parent')
        else:
            actual[current].append(key)
    if not nodes or {k: sorted(v) for k, v in actual.items()} != nodes:
        raise EvidenceError('RustSec cargo-lock disagrees with the verified Census graph')
    return {'packages': len(nodes), 'edges': sum(map(len, nodes.values())),
            'graph_sha256': sha(canonical(nodes)), 'terminal_packages': sorted(k for k, v in nodes.items() if not v)}


def prepare_build(cache, rust_bin, work, name, version, digest):
    release = name + '-' + version
    temp = str(work)
    unpack(cache, work, release, digest, work)
    src = work/release
    deps_lock = (src/'Cargo.lock').read_bytes()
    dependencies = tomllib.loads(deps_lock.decode())['package']
    for dep in dependencies:
        if dep.get('source') == REGISTRY:
            unpack(cache, work, f"{dep['name']}-{dep['version']}", dep['checksum'], work/'vendor')
        elif (dep['name'], dep['version'], dep.get('source')) != (name, version, None):
            raise EvidenceError('unexpected source in Cargo build lock')
    config = work/'config.toml'
    config.write_text('[source.crates-io]\nreplace-with="local"\n[source.local]\ndirectory=' +
                      json.dumps(str(work/'vendor')) + '\n')
    env = {'HOME': temp, 'CARGO_HOME': str(work/'home'), 'PATH': str(rust_bin) + ':/usr/bin:/bin',
           'CARGO_NET_OFFLINE': 'true', 'CARGO_PROFILE_DEV_DEBUG': '0', 'CARGO_INCREMENTAL': '0',
           'LC_ALL': 'C', 'RUSTFLAGS': '--remap-path-prefix=' + temp + '=/nqc/rustsec'}
    def run(command):
        return subprocess.check_output([*ISOLATE, *command], cwd=src, env=env, stdin=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, text=True, timeout=300)
    rust = run([str(rust_bin/'rustc'), '--version']).strip()
    cargo = run([str(rust_bin/'cargo'), '--version']).strip()
    if not rust.startswith('rustc 1.98.1 (') or not cargo.startswith('cargo 1.98.1 ('):
        raise EvidenceError('offline build requires the reviewed Rust 1.98.1 toolchain')
    return src, deps_lock, dependencies, config, run, rust, cargo


def build(cache, rust_bin, lock, graph):
    rust_bin = rust_bin.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='nqc-rustsec-') as temp:
        work = Path(temp)
        src, deps_lock, dependencies, config, run, rust, cargo = prepare_build(
            cache, rust_bin, work, 'cargo-lock', '11.1.0', DIGEST)
        run([str(rust_bin/'cargo'), '--config', str(config), 'build', '--frozen', '--features', 'cli',
             '--bin', 'cargo-lock', '--jobs', '4'])
        source = work/'nqc.Cargo.lock'
        source.write_bytes(lock)
        output = run([str(src/'target/debug/cargo-lock'), 'list', '--dependencies', '--file', str(source)])
    return {**assess(output, graph), 'producer': 'RustSec/cargo-lock', 'version': '11.1.0',
            'release_sha256': DIGEST, 'build_lock_sha256': sha(deps_lock), 'nqc_lock_sha256': sha(lock),
            'build_archives': len(dependencies), 'rustc': rust, 'cargo': cargo}
