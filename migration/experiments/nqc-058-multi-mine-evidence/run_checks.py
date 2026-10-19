"""Reproduce the comparison and affected checks, offline, without installations."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
commands = [
    ('comparison.json', [sys.executable, str(HERE / 'miner.py')]),
    ('tests.log', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
    ('isolation-tests.log', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
    ('isolation.json', [sys.executable, 'migration/verify_isolation.py'])]
results = []
for filename, args in commands:
    result = subprocess.run(args, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    path = HERE / 'evidence' / filename
    path.write_bytes(result.stdout)
    match = re.search(rb'Ran (\d+) tests?', result.stdout)
    results.append({'artifact': str(path.relative_to(HERE)), 'command': args, 'exit_code': result.returncode,
                    'tests': int(match[1]) if match else None, 'sha256': hashlib.sha256(result.stdout).hexdigest()})
passed = all(r['exit_code'] == 0 for r in results) and [r['tests'] for r in results] == [None, 12, 9, None]
validation = {'passed': passed, 'commands': results, 'python': sys.version,
              'dependencies': 'Python standard library, Git, hash-pinned NQC055 core; no installation',
              'tests_failed': 0 if passed else 'see logs', 'tests_skipped': 0 if passed else 'see logs',
              'new_EVM_executions': 0, 'network_requests_by_checks': 0,
              'unrun': ['Earlier unchanged experiment suites and synthetic EVM simulations',
                        'Rust/Solidity: no changed sources', 'Canonical Aave proof/replay: missing inputs',
                        'All RPC, provider acceptance, bundles and financial execution: unauthorized'],
              'public_read_failures': 'PUBLIC_REVIEW.json: six limited page-read failures; no denied target retried or proxy/provider substituted.',
              'environment_notes': 'Initial old checkout absent; full authorized repo clone succeeded. Original Morpho files reside at pinned Git commit, not current tree; read with git show.',
              'commercial_admission': False}
(HERE / 'VALIDATION.json').write_text(json.dumps(validation, indent=2) + '\n')
if passed:
    report = json.loads((HERE / 'evidence/comparison.json').read_bytes())
    summary = {k:v for k,v in report.items() if k not in ('candidates', 'inherited_discarded_scenarios')}
    summary['candidate_count'] = len(report['candidates'])
    (HERE / 'evidence/summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
print(json.dumps(validation, indent=2))
raise SystemExit(0 if passed else 1)
