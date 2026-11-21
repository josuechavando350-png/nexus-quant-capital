"""Use Rust proptest to exercise the normal NQC cohort code on reordered real inventory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from superhunter.product_batches import cohorts
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT, sha
from superhunter.product_rustsec import prepare_build
from superhunter.safe_io import canonical, read_artifact

PIN = 'b8530004ccb15eae51c7e40009fbe317f341f804db54dc033eec1c50be28cfa0'
COHORTS_SHA = '72ecf2a0cfe6144827d17b69c30286fb8c4bd74995c14313cba9ba7dc94e6682'
DRIVER = 'superhunter/product_supply/batch-property-driver.txt'


def invariant(rows, order, split, change):
    arranged = [rows[i] for i in order]
    left, right = arranged[:split], arranged[split:]
    actual = cohorts(right + left)
    signature = [[[r['catalog_id'], r['repository']] for r in group] for group in actual]
    if sha(canonical(signature)) != COHORTS_SHA:
        return False
    other = change + 1
    variants = [arranged[:-1], arranged + [arranged[change]]]
    for field in ('catalog_id', 'repository'):
        duplicate = dict(arranged[change])
        duplicate[field] = arranged[other][field]
        if field == 'repository':
            duplicate[field] = duplicate[field].swapcase()
        variants.append([*arranged[:change], duplicate, *arranged[change + 1:]])
    for variant in variants:
        try:
            cohorts(variant)
        except EvidenceError:
            continue
        return False
    return True


def worker(work):
    rows = {row['catalog_id']: row for row in json.loads((work/'catalog.json').read_bytes())}
    trace = hashlib.sha256()
    cases = set()
    for line in sys.stdin:
        split, change, *order = map(int, line.split())
        passed = len(order) == 200 and set(order) == rows.keys() and invariant(rows, order, split, change)
        trace.update(line.encode())
        cases.add(line)
        print('pass' if passed else 'fail', flush=True)
    (work/'properties.json').write_bytes(canonical({'distinct_cases': len(cases), 'transcript_sha256': trace.hexdigest()}))


def build(cache, rust_bin, rows):
    with tempfile.TemporaryDirectory(prefix='nqc-batch-properties-') as temp:
        work = Path(temp)
        rust_bin = rust_bin.resolve(strict=True)
        src, lock, deps, config, run, rust, cargo = prepare_build(cache, rust_bin, work, 'proptest', '1.12.0', PIN)
        driver = read_artifact(ROOT, DRIVER)
        (src/'nqc_batch_check.rs').write_bytes(driver)
        with (src/'Cargo.toml').open('a') as f:
            f.write('\n[[bin]]\nname="nqc-batch-check"\npath="nqc_batch_check.rs"\n')
        run([str(rust_bin/'cargo'), '--config', str(config), 'build', '--frozen', '--no-default-features',
             '--features', 'std', '--bin', 'nqc-batch-check', '--jobs', '4'])
        (work/'catalog.json').write_bytes(canonical(rows))
        run([str(src/'target/debug/nqc-batch-check'), sys.executable, str(Path(__file__).resolve()), str(work)])
        record = json.loads(read_artifact(work, 'properties.json'))
    if record['distinct_cases'] != 128:
        raise EvidenceError('incomplete proptest batch coverage')
    return {**record, 'version': '1.12.0', 'release_sha256': PIN, 'driver_sha256': sha(driver),
            'build_lock_sha256': sha(lock), 'build_archives': len(deps), 'rustc': rust, 'cargo': cargo,
            'cohorts_sha256': COHORTS_SHA, 'valid_splits': 128, 'invalid_inputs_rejected': 512}


if __name__ == '__main__':
    worker(Path(sys.argv[1]))
