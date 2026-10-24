#!/usr/bin/env python3
"""Build the native client experiment with previously audited artificial inputs."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import textwrap

import audit_termux_collection_evidence as prior
from postgres_transport_runtime import CHECKS

ROOT = Path(__file__).resolve().parents[1]


def render():
    _, pinned = prior.pinned_inputs()
    inputs = {name: pinned[name] for name in ['postgres.sql', 'postgres_import.sql',
              'postgres_collection.sql', 'fixtures.sql', 'fixture-verification.json']}
    for name in ['collection_transport.py', 'postgres_transport_runtime.py']:
        inputs[name] = (ROOT / 'scripts' / name).read_bytes()
    inputs['transport-source.json'] = (json.dumps({'schema': 'nqc-miner-transport-sources-v1',
        'fixture_source_commit': prior.SOURCE, 'checks': CHECKS,
        'input_hashes': {n: hashlib.sha256(v).hexdigest() for n, v in inputs.items()},
        'postgres_client_runtime_executed': False, 'artificial_fixtures': True,
        'observer_bridge_enabled': False, 'spending_authorized': False}, indent=2, sort_keys=True) + '\n').encode()
    chunks, hashes = [], []
    for i, (name, raw) in enumerate(inputs.items()):
        marker = 'NQC_MINER_SYNC_INPUT_' + str(i)
        encoded = '\n'.join(textwrap.wrap(base64.b64encode(gzip.compress(raw, mtime=0)).decode(), 76))
        chunks.append(f"base64 -d <<'{marker}' | gzip -d > \"$MINER_TEST_EVIDENCE/{name}\"\n{encoded}\n{marker}\n")
        hashes.append(f'{hashlib.sha256(raw).hexdigest()}  {name}\n')
    chunks.append("cat > \"$MINER_TEST_EVIDENCE/input.sha256\" <<'NQC_SYNC_HASHES'\n" + ''.join(hashes) + 'NQC_SYNC_HASHES\n')
    template = (ROOT / 'scripts/termux_sync_check.template.sh').read_text()
    return template.replace('__EMBEDDED_INPUTS__', ''.join(chunks)).replace('__EXPECTED_CASES__', str(len(CHECKS))), inputs


if __name__ == '__main__':
    script, inputs = render()
    target = ROOT / 'scripts/nqc-miner-sync-check.sh'
    target.write_text(script)
    print(json.dumps({'file': str(target), 'sha256': hashlib.sha256(script.encode()).hexdigest(),
        'checks_prepared': len(CHECKS), 'input_hashes': {n: hashlib.sha256(v).hexdigest() for n, v in inputs.items()},
        'postgres_client_runtime_executed': False}, indent=2))
