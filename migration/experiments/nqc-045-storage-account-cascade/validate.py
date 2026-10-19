"""Consolidated offline regression; writes only NQC045 evidence."""
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

import trie.hexary
import trie.exceptions
import cases

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXPERIMENTS = HERE.parent


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def main():
    for row in json.loads((HERE / 'SOURCE_BINDING.json').read_text())['files']:
        if hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Bound input changed: ' + row['path'])
    if importlib.metadata.version('trie') != '4.0.0':
        raise ValueError('This experiment pins trie==4.0.0')
    (HERE / 'evidence').mkdir(exist_ok=True)
    save('evidence/SYNTHETIC_CASCADE.json', cases.demonstration())
    save('RUNTIME.json', {
        'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in ('trie', 'rlp', 'eth-hash', 'pycryptodome')},
        'module_sha256': {mod.__name__: hashlib.sha256(Path(inspect.getfile(mod)).read_bytes()).hexdigest()
                          for mod in (trie.hexary, trie.exceptions)},
        'go_executed': False, 'nitro_replayed': False})
    suites = [
        ('cascade', HERE),
        ('raw_write_coverage', EXPERIMENTS / 'nqc-044-write-witness'),
        ('account_facts', EXPERIMENTS / 'nqc-043-account-facts'),
        ('prefix_review', EXPERIMENTS / 'nqc-042-block-prefix'),
        ('storage_map', EXPERIMENTS / 'nqc-041-tx0-storage-map'),
        ('session', EXPERIMENTS / 'nqc-040-resumable-intake'),
        ('exporter', EXPERIMENTS / 'nqc-039-authenticated-intake'),
        ('transport', EXPERIMENTS / 'nqc-038-archive-access'),
        ('original_verifier', EXPERIMENTS / 'nqc-037-historical-state/tests'),
    ]
    checks = [(name, [sys.executable, '-m', 'unittest', 'discover', '-s', str(path), '-p', 'test_*.py', '-v'])
              for name, path in suites]
    checks += [
        ('isolation_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
        ('isolation', [sys.executable, 'migration/verify_isolation.py']),
    ]
    results = []
    for name, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = run.stdout + run.stderr
        path = 'evidence/' + name + '.log'
        (HERE / path).write_text(log)
        row = {'name': name, 'command': command, 'exit_code': run.returncode,
               'log': path, 'sha256': hashlib.sha256(log.encode()).hexdigest()}
        match = re.search(r'Ran (\d+) tests? in ', log)
        if match and not run.returncode:
            row['tests_passed'] = int(match.group(1))
        results.append(row)
        print(name, run.returncode, row.get('tests_passed', 'not a unittest suite'))
    save('VALIDATION.json', {'checks': results, 'tests_passed': sum(r.get('tests_passed', 0) for r in results),
                            'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
                            'commercial_admission': False,
                            'unrun': ['NQC036 blob/KZG audit', 'Rust', 'Go', 'Nitro replay', 'historical acquisition', 'economic replay']})
    save('MANIFEST.json', {'scope': 'offline artifact integrity only',
                          'files': [{'path': str(f.relative_to(HERE)), 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()}
                                    for f in sorted(HERE.rglob('*')) if f.is_file()
                                    and '__pycache__' not in f.parts and f.name != 'MANIFEST.json']})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
