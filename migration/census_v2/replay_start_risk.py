#!/usr/bin/env python3
"""Offline replay of retained start-risk computation, differential and authority.

Original RPC acquisition and canonical chain validation are outside this replay.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from reconcile_temporal_core import read_core, canon
from replay_temporal_upstream import file_sha
from verify_server_recovery import require, sha

SOURCES = [
    ('rmc015_start_risk.py', '6187ff2ae344d58e1e44dcbabde7dd794cadcf83bc38d1407a13c13e75d8f1d5',
     ['start-risk/start-account-risk.jsonl', 'start-risk/start-account-risk-summary.json']),
    ('rmc015_start_risk_differential.py', '8bad4b47409589259fe511f9770153e254d03411483380fe0339e85c34c31d38',
     ['start-risk/direct-differential.jsonl', 'start-risk/direct-differential-summary.json']),
    ('rmc015_start_risk_finalize.py', '4a132bc6370fe4f566e1e33ac2e90f472f85e82008bf3f5e61387064f6e6ddf5',
     ['start-risk/start-risk-authority.json']),
]


def replay(source_root, core, output):
    files = read_core(core)
    source_root, output = source_root.resolve(), output.resolve()
    require(not output.is_relative_to(source_root), 'isolated output required')
    original = source_root / 'RMC015_REPLAY_30D'
    authority = json.loads(files['start-risk/start-risk-authority.json'])
    risk = json.loads(files['start-risk/start-account-risk-summary.json'])
    diff = json.loads(files['start-risk/direct-differential-summary.json'])
    source_bytes = {}
    for name, expected, _ in SOURCES:
        raw = (source_root / name).read_bytes()
        require(sha(raw) == expected, 'reviewed offline source pin: ' + name)
        source_bytes[name] = raw
    pins = {}
    docs = {}
    for role, entry in authority['authorities'].items():
        name = entry['path']
        raw = (original / name).read_bytes()
        require(sha(raw) == entry['sha256'], 'historical input authority: ' + role)
        pins[name] = entry['sha256']
        docs[role] = json.loads(raw)
    pins.update({
        'start-user-state/nodies-fast.jsonl': risk['user_state_sha256'],
        'derived-start-scaled-state.jsonl': risk['scaled_state_sha256'],
        'start-market-state/nodies.jsonl': docs['market']['semantic_sha256'],
        'start-emode/nodies.jsonl': docs['emode']['semantic_sha256'],
        'start-normalized/nodies.jsonl': docs['normalized']['semantic_sha256'],
        'start-borrower-account-data/nodies.jsonl': docs['borrowers']['semantic_sha256'],
        'start-borrower-account-data/tenderly.jsonl': docs['borrowers']['semantic_sha256'],
    })
    # These two producer metadata files are additionally retained as transport
    # inputs; their ledger bytes are separately bound by the historical authority.
    transport_metadata = ['start-user-state/nodies-fast-summary.json',
                          'start-borrower-account-data/nodies-summary.json']
    for name in transport_metadata:
        pins[name] = file_sha(original / name)
    expected_outputs = {
        'start-risk/start-account-risk.jsonl': authority['risk_ledger_sha256'],
        'start-risk/start-account-risk-summary.json': sha(files['start-risk/start-account-risk-summary.json']),
        'start-risk/direct-differential.jsonl': diff['differential_sha256'],
        'start-risk/direct-differential-summary.json': authority['direct_differential_sha256'],
        'start-risk/start-risk-authority.json': sha(files['start-risk/start-risk-authority.json']),
    }
    output.mkdir(parents=True, exist_ok=False)
    work = output / 'work'
    work.mkdir()
    inventory = []
    for name, expected in {**pins, **expected_outputs}.items():
        src = original / name
        require(file_sha(src) == expected, 'original file binding: ' + name)
        inventory.append({'file': name, 'bytes': src.stat().st_size, 'sha256': expected,
                          'binding': 'TRANSPORT_METADATA' if name in transport_metadata else 'HISTORICAL_HASH'})
        if name in pins:
            dst = work / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            require(file_sha(dst) == expected, 'copy hash: ' + name)
    (output / 'input-inventory.json').write_bytes(canon(inventory))
    report = {'schema': 'nqc-start-risk-replay-v1', 'status': 'RUNNING', 'stages': [],
        'driver_sha256': file_sha(Path(__file__)), 'input_inventory_sha256': file_sha(output / 'input-inventory.json'),
        'source_git_identity_authenticated': False, 'new_rpc_acquisition': False,
        'independent_provider_acquisition_authenticated': False,
        'full_upstream_reconstruction_complete': False, 'new_producer_certified': False}
    try:
        for name, expected, outputs in SOURCES:
            raw = source_bytes[name]
            old = b'ROOT=Path("/root/workspace/RMC015_REPLAY_30D")'
            require(raw.count(old) == 1, 'one path assignment')
            adapted = raw.replace(old, ('ROOT=Path(' + repr(str(work)) + ')').encode())
            (output / ('original-' + name)).write_bytes(raw)
            script = output / ('adapted-' + name)
            script.write_bytes(adapted)
            require(all(not (work / n).exists() for n in outputs), 'fresh outputs required')
            result = subprocess.run([sys.executable, str(script)], cwd=work, capture_output=True, timeout=180)
            (output / (name + '.stdout')).write_bytes(result.stdout)
            (output / (name + '.stderr')).write_bytes(result.stderr)
            stage = {'source': name, 'source_sha256': expected, 'adapted_source_sha256': sha(adapted),
                     'adaptation': 'ONE_ROOT_PATH_ASSIGNMENT_ONLY', 'exit_code': result.returncode, 'outputs': []}
            report['stages'].append(stage)
            require(result.returncode == 0, 'producer failed: ' + name)
            for n in outputs:
                actual = file_sha(work / n)
                stage['outputs'].append({'file': n, 'sha256': actual, 'byte_identical': actual == expected_outputs[n]})
                require(actual == expected_outputs[n], 'reproduced output hash: ' + n)
        for name, expected in {**pins, **expected_outputs}.items():
            require(file_sha(original / name) == expected, 'original changed: ' + name)
            require(file_sha(work / name) == expected, 'staged file changed: ' + name)
        report.update(status='PASS', output_file_count=5, position_accounts=authority['position_user_count'],
                      borrower_accounts=authority['borrower_count'], liquidatable_accounts=authority['liquidatable_count'],
                      exact_risk_rows=diff['exact_risk_rows'], risk_mismatches=diff['mismatch_count'],
                      borrower_provider_ledgers_byte_equal=True, all_original_inputs_unchanged=True,
                      all_staged_inputs_unchanged=True)
    except Exception as e:
        report.update(status='FAIL', failure=str(e))
        raise
    finally:
        (output / 'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ['source-root', 'core', 'output']:
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(replay(a.source_root, a.core, a.output), sort_keys=True))
