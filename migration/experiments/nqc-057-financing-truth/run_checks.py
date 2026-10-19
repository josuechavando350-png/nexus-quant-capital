"""Offline checks only. Regenerates the consolidated book and validation logs."""
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
    ('reconciliation.json', [sys.executable, str(HERE / 'audit.py')]),
    ('tests.log', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
    ('isolation-tests.log', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
    ('isolation.json', [sys.executable, 'migration/verify_isolation.py']),
]
results = []
for filename, args in commands:
    result = subprocess.run(args, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    path = HERE / 'evidence' / filename
    path.write_bytes(result.stdout)
    match = re.search(rb'Ran (\d+) tests?', result.stdout)
    results.append({'artifact': str(path.relative_to(HERE)), 'command': args, 'exit_code': result.returncode,
                    'tests': int(match[1]) if match else None, 'sha256': hashlib.sha256(result.stdout).hexdigest()})
passed = all(row['exit_code'] == 0 for row in results) and [row['tests'] for row in results] == [None, 8, 9, None]
validation = {'passed': passed, 'commands': results, 'python': sys.version,
              'dependencies': 'Python standard library and Git; no installation',
              'tests_failed': 0 if passed else 'see logs', 'tests_skipped': 0 if passed else 'see logs',
              'new_EVM_executions': 0, 'network_requests_by_checks': 0,
              'not_rerun': ['Old equivalent synthetic simulations and their suites', 'Rust/Solidity: unchanged',
                            'NQC018/023 CI exports: published audit summaries only; no new export recovery',
                            'Provider acceptance, signature, bundle, RPC and financial execution: unauthorized'],
              'discovery_issue': 'One metadata inspection assumed an object where prior public-sources.json is a list (AttributeError). Corrected read succeeded. No source edit or test-result change.',
              'public_read_limits': 'Both documentation llms.txt index reads returned reader internal errors; not retried. Eight scoped official pages were readable.',
              'commercial_admission': False}
(HERE / 'VALIDATION.json').write_text(json.dumps(validation, indent=2) + '\n')
print(json.dumps(validation, indent=2))
raise SystemExit(0 if passed else 1)
