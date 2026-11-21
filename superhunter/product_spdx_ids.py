"""Classify the SPDX identifiers actually observed by NQC with OSV-Scanner's offline registry."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import canonical

SOURCE = 'osv-scanner-2.7.1.tar.gz'
SOURCE_SHA = '35472c072bca6571df8019843c3d2c2c7379160cc2c32fa1fe4c68f86cdd7704'
TOOLCHAIN = 'go1.27.3.linux-amd64.tar.gz'
TOOLCHAIN_SHA = '65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40'
SOURCES = ('go.mod', 'go.sum', 'internal/spdx/licenses.go', 'internal/spdx/verify.go', 'internal/spdx/verify_test.go')
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']
DRIVER = """package main

import (
    "encoding/json"
    "os"

    "github.com/google/osv-scanner/v2/internal/spdx"
)

func main() {
    var identifiers []string
    if err := json.NewDecoder(os.Stdin).Decode(&identifiers); err != nil { panic(err) }
    missing := spdx.Unrecognized(identifiers)
    if err := json.NewEncoder(os.Stdout).Encode(missing); err != nil { panic(err) }
}
"""


def source_index(evidence):
    by_id = defaultdict(list)
    for source, expression in sorted(evidence['sources'].items()):
        if expression:
            for ident in evidence['expressions'][expression]['identifiers']:
                by_id[ident].append(source)
    if not by_id or set(by_id) != set(evidence['groups_by_id']):
        raise EvidenceError('OSV license identifiers differ from the observed inventory')
    return dict(sorted(by_id.items()))


def classify(by_id, registry, observed):
    expected = [i for i in by_id if i.lower() not in registry and i.lower() != 'unknown']
    if observed != expected:
        raise EvidenceError('OSV-Scanner identifier output differs from the published license registry')
    return {i: {'status': ('recognized' if i.lower() in registry else
                           'unknown_marker' if i.lower() == 'unknown' else 'unlisted'), 'sources': sources}
            for i, sources in by_id.items()}


def build(cache, evidence):
    by_id = source_index(evidence)
    with tempfile.TemporaryDirectory(prefix='nqc-osv-license-') as tmp:
        root = Path(tmp)
        source, go = root/SOURCE, root/TOOLCHAIN
        copy_release('OSV-Scanner source', cache/SOURCE, source, SOURCE_SHA, executable=False)
        copy_release('Go toolchain', cache/TOOLCHAIN, go, TOOLCHAIN_SHA, executable=False)
        (root/'tmp').mkdir()
        env = {'HOME': tmp, 'TMPDIR': str(root/'tmp'), 'GOPATH': str(root/'gopath'), 'GOROOT': str(root/'go'),
               'LC_ALL': 'C', 'PATH': '/usr/bin:/bin', 'GOCACHE': str(root/'gocache'),
               'GOENV': 'off', 'GOWORK': 'off', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOTOOLCHAIN': 'local',
               'GOTELEMETRY': 'off', 'CGO_ENABLED': '0', 'GOMAXPROCS': '2'}
        def run(args, payload=b''):
            return subprocess.run([*ISOLATE, *map(str, args)], cwd=root, env=env, input=payload,
                                  capture_output=True, check=True, timeout=150).stdout
        run(['/usr/bin/tar', '--no-same-owner', '-xzf', go])
        hashes = {}
        with tarfile.open(source) as archive:
            for name in SOURCES:
                member = archive.getmember('osv-scanner-2.7.1/' + name)
                if not member.isfile() or member.size > 2 * 1024**2:
                    raise EvidenceError('unexpected OSV license source member')
                target = root/name
                target.parent.mkdir(exist_ok=True, parents=True)
                data = archive.extractfile(member).read()
                target.write_bytes(data)
                hashes[name] = sha(data)
        registry = set(re.findall(r'^\s*"([^"]+)":\s+true,\s*$', (root/'internal/spdx/licenses.go').read_text(), re.M))
        if not registry or 'mit' not in registry:
            raise EvidenceError('OSV SPDX license list is missing')
        (root/'main.go').write_text(DRIVER)
        binary = root/'go/bin/go'
        tests = [json.loads(l) for l in run([binary, 'test', '-mod=readonly', '-json',
                                             '-run', '^TestUnrecognized$', './internal/spdx']).splitlines()]
        if not any(r.get('Action') == 'pass' and r.get('Test') == 'TestUnrecognized' for r in tests):
            raise EvidenceError('OSV upstream license test did not pass')
        run([binary, 'build', '-mod=readonly', '-trimpath', '-o', 'registry-check', 'main.go'])
        actual = json.loads(run([root/'registry-check'], canonical(list(by_id))))
    records = classify(by_id, registry, [] if actual is None else actual)
    return {'version': '2.7.1', 'source_sha256': SOURCE_SHA, 'go_sha256': TOOLCHAIN_SHA, 'upstream_files': hashes,
            'registry_entries': len(registry), 'identifiers': records, 'unlisted': [i for i in records if records[i]['status'] == 'unlisted'],
            'observations_sha256': sha(canonical(records))}
