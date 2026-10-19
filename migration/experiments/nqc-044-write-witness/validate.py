"""Offline synthetic verification; writes evidence only under this experiment."""
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
import proof_trial as p

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def main():
    for row in json.loads((HERE / 'SOURCE_BINDING.json').read_text())['files']:
        data = (ROOT / row['path']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Bound source changed: ' + row['path'])
    vendor = (HERE / 'vendor/go-ethereum__trie__trie.go').read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(vendor)).encode() + b'\0' + vendor).hexdigest()
    if blob != '1ef2c2f1a66e0d80b324fa87550307ea563d699c':
        raise ValueError('Pinned upstream blob mismatch')
    if importlib.metadata.version('trie') != '4.0.0':
        raise ValueError('This experiment pins trie==4.0.0')
    (HERE / 'evidence').mkdir(exist_ok=True)
    save('evidence/SYNTHETIC_WRITE_CASE.json', p.demonstration())
    save('RUNTIME.json', {
        'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in ('trie', 'rlp', 'eth-hash', 'pycryptodome')},
        'module_sha256': {mod.__name__: hashlib.sha256(Path(inspect.getfile(mod)).read_bytes()).hexdigest()
                          for mod in (trie.hexary, trie.exceptions)},
        'go_executed': False, 'nitro_replayed': False})
    checks = [
        ('write_coverage', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
        ('original_verifier', [sys.executable, '-m', 'unittest', 'discover', '-s', str(p.PREVIOUS / 'tests'), '-v']),
        ('isolation_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
        ('isolation', [sys.executable, 'migration/verify_isolation.py']),
    ]
    results = []
    for name, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = run.stdout + run.stderr
        path = 'evidence/' + name + '.log'
        (HERE / path).write_text(log)
        result = {'name': name, 'command': command, 'exit_code': run.returncode,
                  'log': path, 'sha256': hashlib.sha256(log.encode()).hexdigest()}
        match = re.search(r'Ran (\d+) tests? in ', log)
        if match and not run.returncode:
            result['tests_passed'] = int(match.group(1))
        results.append(result)
        print(name, run.returncode)
    save('VALIDATION.json', {'checks': results, 'tests_passed': sum(r.get('tests_passed', 0) for r in results),
                            'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
                            'commercial_admission': False})
    save('MANIFEST.json', {'scope': 'offline artifact integrity only',
                          'files': [{'path': str(f.relative_to(HERE)), 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()}
                                    for f in sorted(HERE.rglob('*')) if f.is_file()
                                    and '__pycache__' not in f.parts and f.name != 'MANIFEST.json']})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
