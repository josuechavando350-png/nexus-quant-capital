#!/usr/bin/env python3
"""Replay two reviewed, offline historical producers in an isolated copy.

Requires the retained original server files. This does not reacquire RPC data,
certify provider independence, or establish decision-time availability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from reconcile_temporal_core import canon, read_core
from verify_server_recovery import require, sha

SOURCES = {
    'rmc015_interest_candidate_envelope.py': '01e328bfc4598c183e093bfaa11adaa5e721d8ff9bbf08c474499aecb130c522',
    'rmc015_candidate_state_replay.py': '41f951b8a3daf57a5b1e720d35d7a02aaf85c5a73694a63fa2370552189cb00f',
}
STAGES = [
    ('rmc015_interest_candidate_envelope.py', [
        'interest-only-crossing-candidate-envelope.jsonl',
        'interest-only-crossing-candidate-envelope-summary.json']),
    ('rmc015_candidate_state_replay.py', ['candidate-state-transition-replay-summary.json']),
]
CATALOGS = {
    'd08-raw/closeout/market-state-manifest.jsonl': 'c64719793eed5fd5b09eb725f18b811746b1a50e101bfa00b9569be65282d19e',
    'd09-raw/closeout/account-manifest.jsonl': '87ab2c50aa1b83759e53c7e6afe2f961d28a412ec370363dff66b3d859ea487c',
}


def file_sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def replay(source_root, core, output):
    files = read_core(core)
    source_root, output = source_root.resolve(), output.resolve()
    require(not output.is_relative_to(source_root), 'output must be outside original source tree')
    original_sources = {}
    for name, expected in SOURCES.items():
        raw = (source_root / name).read_bytes()
        require(sha(raw) == expected, 'reviewed offline source pin: ' + name)
        original_sources[name] = raw
    docs = {n: json.loads(files[n]) for n in [
        'pool-trigger-dual-provider-summary.json', 'token-triggers-dual-provider-summary.json',
        'start-risk/start-account-risk-summary.json', 'start-risk/start-risk-authority.json',
        'interest-only-crossing-candidate-envelope-summary.json', 'candidate-state-transition-replay-summary.json']}
    state = docs['candidate-state-transition-replay-summary.json']
    pins = {
        'start-risk/start-account-risk.jsonl': docs['start-risk/start-risk-authority.json']['risk_ledger_sha256'],
        'interest-only-crossing-candidate-envelope.jsonl': docs['interest-only-crossing-candidate-envelope-summary.json']['output_sha256'],
        'derived-start-scaled-state.jsonl': docs['start-risk/start-account-risk-summary.json']['scaled_state_sha256'],
        'candidate-start-user-state-authority.jsonl': state['start_user_state_sha256'],
        'candidate-end-user-state-nodies.jsonl': state['end_user_state_sha256'],
        'candidate-end-user-state-tenderly.jsonl': state['end_user_state_sha256'],
        'token-universe.json': 'c8c1aa82f652bd4002b8c7446351b3ae5e6d12a239ad718358694750a3c115eb',
    }
    for kind in ['pool', 'token']:
        summary = 'pool-trigger-dual-provider-summary.json' if kind == 'pool' else 'token-triggers-dual-provider-summary.json'
        for provider in ['tenderly', 'mevblocker']:
            pins[f'{kind}-triggers-{provider}.jsonl'] = docs[summary]['semantic_sha256']
    output.mkdir(parents=True, exist_ok=False)
    work = output / 'work'
    work.mkdir()
    staged = work / 'RMC015_REPLAY_30D'
    staged.mkdir()
    inventory = []
    for name, raw in files.items():
        p = staged / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
    original_inputs = {**{f'RMC015_REPLAY_30D/{n}': h for n, h in pins.items()}, **CATALOGS}
    for name, expected in original_inputs.items():
        src, dst = source_root / name, work / name
        require(file_sha(src) == expected, 'original input hash: ' + name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        require(file_sha(dst) == expected, 'copy hash: ' + name)
        inventory.append({'file': name, 'bytes': src.stat().st_size, 'sha256': expected})
    (output / 'input-inventory.json').write_bytes(canon(inventory))
    report = {
        'schema': 'nqc-temporal-upstream-replay-v1', 'status': 'RUNNING',
        'driver_sha256': file_sha(Path(__file__)), 'source_git_identity_authenticated': False,
        'source_root': str(source_root), 'output_root': str(output), 'stages': [],
        'input_inventory_sha256': file_sha(output / 'input-inventory.json'),
        'catalog_pins_origin': 'ORIGINAL_D08_D09_ARCHIVE_MEMBERS',
        'token_universe_pin_origin': 'RECOVERY_TRANSPORT_ONLY',
        'new_rpc_acquisition': False, 'independent_provider_acquisition_authenticated': False,
        'decision_time_availability_proven': False, 'full_upstream_reconstruction_complete': False,
        'new_producer_certified': False,
    }
    try:
        for name, outputs in STAGES:
            raw = original_sources[name]
            adapted = raw
            replacements = {'/root/workspace/RMC015_REPLAY_30D': str(staged)}
            replacements.update({f'/root/workspace/{n}': str(work / n) for n in CATALOGS})
            for old, new in replacements.items():
                old_assignment = ('Path(' + json.dumps(old) + ')').encode()
                require(adapted.count(old_assignment) == 1, 'one exact path assignment: ' + old)
                adapted = adapted.replace(old_assignment, ('Path(' + repr(new) + ')').encode())
            (output / ('original-' + name)).write_bytes(raw)
            script = output / ('adapted-' + name)
            script.write_bytes(adapted)
            expected_outputs = {n: file_sha(staged / n) for n in outputs}
            for n in outputs:
                (staged / n).unlink()
            result = subprocess.run([sys.executable, str(script)], cwd=work, capture_output=True, timeout=300)
            (output / (name + '.stdout')).write_bytes(result.stdout)
            (output / (name + '.stderr')).write_bytes(result.stderr)
            stage = {'source': name, 'source_sha256': SOURCES[name],
                     'adapted_source_sha256': sha(adapted), 'adaptation': 'THREE_PATH_ASSIGNMENTS_ONLY',
                     'exit_code': result.returncode, 'outputs': []}
            report['stages'].append(stage)
            require(result.returncode == 0, 'producer failed: ' + name)
            for n, expected in expected_outputs.items():
                actual = file_sha(staged / n)
                stage['outputs'].append({'file': n, 'sha256': actual, 'byte_identical': actual == expected})
                require(actual == expected, 'reproduced output hash: ' + n)
        for name, expected in original_inputs.items():
            require(file_sha(work / name) == expected, 'staged input changed: ' + name)
            require(file_sha(source_root / name) == expected, 'original input changed: ' + name)
        for name, raw in files.items():
            require(file_sha(staged / name) == sha(raw), 'core file changed: ' + name)
        report.update(status='PASS', all_original_inputs_unchanged=True,
                      all_staged_inputs_unchanged=True, output_file_count=3)
    except Exception as e:
        report.update(status='FAIL', failure=str(e))
        raise
    finally:
        (output / 'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['source-root', 'core', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(replay(a.source_root, a.core, a.output), sort_keys=True))
