#!/usr/bin/env python3
"""Offline paired pressure experiment. Uses installed Rust; no downloads or RPC."""
import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stats(v):
    v = sorted(v)
    n = len(v)
    return {"n": n, **{k: v[math.ceil(n*q)-1] for k, q in
            [("p50", .5), ("p95", .95), ("p99", .99), ("p99_9", .999)]},
            "max": v[-1], "min": v[0]}


def values(raw):
    v = array.array('Q')
    v.frombytes(raw)
    if sys.byteorder != 'little':
        v.byteswap()
    return v


def run(cmd, output, env, cwd=ROOT):
    with output.open('w') as f:
        subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, stdout=f,
                       stderr=subprocess.STDOUT, check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--pilot', action='store_true')
    a = p.parse_args()
    a.out = a.out.resolve()
    assert not a.out.is_relative_to(REPO)
    a.out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(CARGO_TARGET_DIR=str(a.out/'target'), RUSTFLAGS='', PYTHONDONTWRITEBYTECODE='1')
    for label, cmd in [
        ('fmt', ['cargo', 'fmt', '--all', '--', '--check']),
        ('clippy', ['cargo', 'clippy', '--all-targets', '--locked', '--offline', '--', '-D', 'warnings']),
        ('tests', ['cargo', 'test', '--locked', '--offline']),
        ('build', ['cargo', 'build', '--release', '--locked', '--offline']),
    ]:
        run(cmd, a.out/(label+'.log'), env)
    run(['python3', 'migration/verify_isolation.py'], a.out/'isolation.log', env, REPO)
    run(['python3', '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py'],
        a.out/'isolation-tests.log', env, REPO)
    binary = a.out/'target/release/bench'
    cpu = min(os.sched_getaffinity(0))
    original_affinity = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    sources = [p for name in ['src', 'tests', 'scripts'] for p in sorted((ROOT/name).rglob('*'))
               if p.is_file() and '__pycache__' not in p.parts]
    sources += [ROOT/x for x in ['Cargo.toml', 'Cargo.lock', 'PRE_REGISTER.md']]
    dependencies = [p for base in [ROOT.parent, ROOT.parent/'r1-morpho']
                    for p in sorted((base/'src').rglob('*.rs'))]
    dependencies += [base/x for base in [ROOT.parent, ROOT.parent/'r1-morpho'] for x in ['Cargo.toml', 'Cargo.lock']]
    meta = {
        'scope': 'SYNTHETIC_FIXED_256_SLOTS_LOCAL_ONLY_NO_NETWORK',
        'pilot': a.pilot, 'threshold': 64,
        'cpu': subprocess.check_output(['lscpu'], text=True),
        'cpuinfo': Path('/proc/cpuinfo').read_text(),
        'platform': platform.platform(), 'available_affinity': original_affinity,
        'affinity': sorted(os.sched_getaffinity(0)),
        'rustc': subprocess.check_output(['rustc', '-vV'], text=True),
        'profile': 'O3, fat LTO, codegen-units=1, overflow-checks=true, RUSTFLAGS empty',
        'frequency': 'Uncontrolled KVM host; no physical core isolation, turbo/IRQ/governor changes',
        'clock': 'CLOCK_MONOTONIC_RAW; individual windows; no subtraction or trimming',
        'binary_sha256': sha(binary),
        'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sources},
        'dependency_sha256': {str(p.relative_to(ROOT.parent)): sha(p) for p in dependencies},
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'runs': []}
    configurations = ([('select', e, 5000) for e in [0, 16, 64, 255]] if a.pilot else
                      [('select', e, 20000) for e in [0, 1, 8, 16, 64, 65, 96, 128, 255]] +
                      [('cycle', e, 20000) for e in [0, 255]] + [('pipeline', 0, 200000)])
    tasks = [(rep, mode, expired, count, variant)
             for rep in range(1 if a.pilot else 3)
             for mode, expired, count in configurations for variant in ['original', 'batch', 'single', 'combined']]
    random.Random(666_204).shuffle(tasks)
    (a.out/'raw').mkdir()
    groups = {}
    observed = {}
    for rep, mode, expired, count, variant in tasks:
        label = f'{mode}-{expired}-{variant}-{rep}'
        prefix = a.out/'raw'/label
        start = time.monotonic()
        cmd = [str(binary), mode, variant, str(expired), str(count), str(666_250+rep), str(prefix)]
        info = json.loads(subprocess.check_output(cmd, text=True, env=env))
        raw = prefix.with_suffix('.bin').read_bytes()
        control = Path(str(prefix)+'_clock.bin').read_bytes()
        sample = values(raw)
        row = {'label': label, 'mode': mode, 'expired': expired, 'variant': variant, 'rep': rep,
               'metadata': info, 'stats_ns': stats(sample), 'clock_control_ns': stats(values(control)),
               'samples_sha256': hashlib.sha256(raw).hexdigest(),
               'control_sha256': hashlib.sha256(control).hexdigest(),
               'wall_seconds': time.monotonic()-start}
        meta['runs'].append(row)
        (a.out/'benchmark.json').write_text(json.dumps(meta, indent=2)+'\n')
        groups.setdefault(f'{mode}|{expired}|{variant}', []).extend(sample)
        observed[(rep, mode, expired, variant)] = info
        print(label, row['stats_ns'], flush=True)
    for rep in range(1 if a.pilot else 3):
        for mode, expired, _ in configurations:
            for variant in ['batch', 'single', 'combined']:
                assert observed[(rep, mode, expired, 'original')] == observed[(rep, mode, expired, variant)]
    (a.out/'summary.json').write_text(json.dumps({k: stats(v) for k, v in groups.items()}, indent=2)+'\n')
    with zipfile.ZipFile(a.out/'raw.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted((a.out/'raw').glob('*.bin')):
            z.write(path, path.name)
    with zipfile.ZipFile(a.out/'source.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sources:
            z.write(path, str(path.relative_to(ROOT)))
    run(['objdump', '-Cd', binary], a.out/'disassembly.txt', env)
    with zipfile.ZipFile(a.out/'disassembly.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(a.out/'disassembly.txt', 'disassembly.txt')
    print('COMPLETE', a.out, flush=True)


if __name__ == '__main__':
    main()
