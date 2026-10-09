#!/usr/bin/env python3
"""Reproduce recovered scripts in a fresh tree with exactly one path edit."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

from reconcile_temporal_core import read_core, canon
from verify_server_recovery import require, sha

INPUTS_SHA = 'e29c4a3cde343268df165c83e6f98cfcf55799734c4e58f1f4ab8d45c2ac4d3f'
STAGES = {
    'd15b': ('rmc015_temporal_authority.py',
        'caccf63bacbb46b854f908f5ea138d5e2e2749fa41fcbd3f7ece7566b4b67b28',
        ['rmc015-temporal-episodes.jsonl', 'rmc015-censored-candidates.jsonl', 'rmc015-temporal-authority.json']),
    'd16': ('rmc016_capacity_authority.py',
        'f8ce9083a9f6cb4a8d84a5b14ef2b44b42d1d79bc23b2cfc97f12624f9aacb3f',
        ['rmc016-observed-event-economics.jsonl', 'rmc016-observed-transaction-economics.jsonl',
         'rmc016-observed-daily-market-baseline.jsonl', 'rmc016-capacity-authority.json']),
}


def replay(core, stage, output, inputs=None):
    files = read_core(core)
    if stage == 'd15b':
        require(inputs is not None and inputs.is_file(), 'complete D15B inputs required')
        require(sha(inputs.read_bytes()) == INPUTS_SHA, 'D15B inputs transport pin')
        with zipfile.ZipFile(inputs) as z:
            expected = {'start-risk/start-account-risk.jsonl', 'interest-only-crossing-candidate-envelope.jsonl'}
            require(len(z.namelist()) == 2 and set(z.namelist()) == expected, 'D15B input inventory')
            files.update({n: z.read(n) for n in z.namelist()})
        for summary, key, name in [
            ('start-risk/start-risk-authority.json', 'risk_ledger_sha256', 'start-risk/start-account-risk.jsonl'),
            ('interest-only-crossing-candidate-envelope-summary.json', 'output_sha256', 'interest-only-crossing-candidate-envelope.jsonl')]:
            require(sha(files[name]) == json.loads(files[summary])[key], 'D15B raw input binding')
    name, expected_source, expected_outputs = STAGES[stage]
    original = files['source/' + name]
    require(sha(original) == expected_source, 'reviewed source hash')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    working = output / 'work'
    working.mkdir()
    for n, raw in files.items():
        require(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts, 'safe input')
        path = working / n
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    old = b'R=Path("/root/workspace/RMC015_REPLAY_30D")'
    new = ('R=Path(' + repr(str(working)) + ')').encode()
    require(original.count(old) == 1, 'one exact source path assignment')
    adapted = original.replace(old, new)
    script = output / 'producer-path-adapted.py'
    script.write_bytes(adapted)
    completed = subprocess.run([sys.executable, str(script)], capture_output=True, cwd=output, timeout=180)
    (output / 'stdout.log').write_bytes(completed.stdout)
    (output / 'stderr.log').write_bytes(completed.stderr)
    require(completed.returncode == 0, 'producer failed; inspect preserved logs')
    reports = []
    for n, raw in files.items():
        actual = (working / n).read_bytes()
        require(actual == raw, 'replayed output/input differs: ' + n)
        if n in expected_outputs:
            reports.append({'file': n, 'bytes': len(raw), 'sha256': sha(raw), 'byte_identical': True})
    report = {'schema': 'nqc-server-producer-replay-v1', 'stage': stage,
        'source_sha256': expected_source, 'adapted_source_sha256': sha(adapted),
        'source_git_identity_authenticated': False, 'adaptation': 'ONE_R_PATH_ASSIGNMENT_ONLY',
        'old_assignment': old.decode(), 'new_assignment': new.decode(), 'output_byte_parity': reports,
        'all_other_staged_inputs_unchanged': True, 'exit_code': completed.returncode,
        'upstream_reconstruction_replayed': False, 'new_producer_certified': False,
        'driver_sha256': sha(Path(__file__).read_bytes())}
    (output / 'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('core', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    p.add_argument('--stage', choices=sorted(STAGES), required=True)
    p.add_argument('--inputs', type=Path)
    a = p.parse_args()
    print(json.dumps(replay(a.core, a.stage, a.output, a.inputs), sort_keys=True))
