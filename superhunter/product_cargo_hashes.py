"""Locate Cargo registry checksums in the verified Census SBOM with ast-grep."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

from .product_review import copy_release, sha
from .product_reasoning import EvidenceError
from .safe_io import strict_json

DIGEST = '9abc33cdb0e75c909bead3cefb94deccb1e4d71751392ff5f5bff7d1d09d6861'
RULE = {'id': 'cargo-checksums', 'language': 'Json', 'severity': 'info', 'message': 'Cargo checksum inventory',
        'rule': {'kind': 'object', 'has': {'kind': 'pair', 'has': {'field': 'key', 'regex': '^"hashes"$'}}}}


def assess(sbom, lock, matches):
    checksums = {}
    for pkg in tomllib.loads(lock.decode())['package']:
        if not pkg.get('source', '').startswith('registry+'):
            continue
        purl = f"pkg:cargo/{pkg['name']}@{pkg['version']}"
        if purl in checksums or not re.fullmatch('[a-f0-9]{64}', pkg['checksum']):
            raise EvidenceError('duplicate or invalid Cargo registry checksum')
        checksums[purl] = pkg['checksum']
    components = {c['purl']: c for c in strict_json(sbom)['components']}
    observed = {}
    for match in matches:
        start, end = (match['range']['byteOffset'][k] for k in ('start', 'end'))
        if (match['ruleId'] != RULE['id'] or match['file'] != 'census.cdx.json' or
                not 0 <= start < end <= len(sbom) or sbom[start:end] != match['text'].encode()):
            raise EvidenceError('ast-grep returned an unbound SBOM location')
        component = strict_json(sbom[start:end])
        purl = component['purl']
        if (purl not in checksums or purl in observed or components.get(purl) != component or
                component['bom-ref'] != purl or not any(h == {'alg': 'SHA-256', 'content': checksums[purl]}
                                                        for h in component['hashes']) or
                len([h for h in component['hashes'] if h['alg'] == 'SHA-256']) != 1):
            raise EvidenceError('ast-grep component differs from the registry entry in Cargo.lock')
        observed[purl] = {'checksum': checksums[purl], 'start_byte': start, 'end_byte': end}
    if not checksums or observed.keys() != checksums.keys():
        raise EvidenceError('incomplete ast-grep registry inventory')
    return dict(sorted(observed.items()))


def build(binary, sbom, lock):
    with tempfile.TemporaryDirectory(prefix='nqc-cargo-hashes-') as temp:
        work = Path(temp)
        copy_release('ast-grep', binary, work/'ast-grep', DIGEST)
        (work/'census.cdx.json').write_bytes(sbom)
        output = subprocess.check_output(['/usr/bin/unshare', '--user', '--map-current-user', '--net',
                                         str(work/'ast-grep'), 'scan', '--inline-rules', json.dumps(RULE),
                                         '--json=compact', 'census.cdx.json'], cwd=work,
                                        env={'HOME': temp, 'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'},
                                        stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
    records = assess(sbom, lock, json.loads(output))
    return {'version': '0.51.3', 'executable_sha256': DIGEST, 'lock_sha256': sha(lock), 'sbom_sha256': sha(sbom),
            'registry_components': len(records), 'locations': records}
