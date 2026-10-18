#!/usr/bin/env python3
"""Recompute every delivered percentile, compare outputs, verify source hashes."""
import hashlib
import json
from pathlib import Path
import zipfile
from reproduce import stats, values

ROOT = Path(__file__).resolve().parents[1]


def verify(directory):
    m = json.loads((directory/'benchmark.json').read_text())
    groups = {}
    outputs = {}
    with zipfile.ZipFile(directory/'raw.zip') as z:
        assert len(z.namelist()) == 2*len(m['runs'])
        for r in m['runs']:
            raw = z.read(r['label']+'.bin')
            clock = z.read(r['label']+'_clock.bin')
            assert hashlib.sha256(raw).hexdigest() == r['samples_sha256']
            assert hashlib.sha256(clock).hexdigest() == r['control_sha256']
            assert stats(values(raw)) == r['stats_ns']
            assert stats(values(clock)) == r['clock_control_ns']
            assert r['metadata']['distinct_warm_outputs'] > 1
            groups.setdefault(f'{r["mode"]}|{r["expired"]}|{r["variant"]}', []).extend(values(raw))
            outputs[(r['rep'], r['mode'], r['expired'], r['variant'])] = r['metadata']
    for (rep, mode, expired, variant), result in outputs.items():
        assert result == outputs[(rep, mode, expired, 'original')]
    assert {k: stats(v) for k, v in groups.items()} == json.loads((directory/'summary.json').read_text())
    with zipfile.ZipFile(directory/'source.zip') as z:
        for name, digest in m['source_sha256'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
            if directory.name == 'final':
                assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
    for name, digest in m['dependency_sha256'].items():
        assert hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest() == digest
    return {'runs': len(m['runs']), 'samples': sum(len(v) for v in groups.values()),
            'archived_source_and_dependencies_match': True,
            'current_source_required_and_matching': directory.name == 'final', 'all_percentiles_and_checksums_match': True}


if __name__ == '__main__':
    print(json.dumps({label: verify(ROOT/'evidence'/label) for label in ['pilot', 'final']}, indent=2))
