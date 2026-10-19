"""Offline tests and synthetic evidence generation. No acquisition side effects."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import account_facts as facts
from fixtures import fixture, absence_shape_fixtures

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def main():
    for row in json.loads((HERE / 'SOURCE_BINDING.json').read_text())['files']:
        if hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('bound source changed: ' + row['path'])
    (HERE / 'evidence').mkdir(exist_ok=True)
    cases = absence_shape_fixtures()
    cases['empty_root'] = fixture({}, facts.FILTERED_ACCOUNT)
    cases['present_nonce_one'] = fixture({facts.FILTERED_ACCOUNT: {'nonce': 1}}, facts.FILTERED_ACCOUNT)
    results = []
    for label, (root, proof) in cases.items():
        old = facts.v.account_proof(root, facts.FILTERED_ACCOUNT, [], proof)
        result = facts.verify_account_facts(root, facts.FILTERED_ACCOUNT, [], proof)
        results.append({'case': label, 'synthetic_root': root, 'synthetic_proof': proof,
                        'original_output_fields': sorted(old), 'new_output': result})
    save('evidence/SYNTHETIC_CASES.json', {
        'evidence_class': 'locally generated HexaryTrie fixtures; NOT Robinhood state',
        'cases': results, 'historical_proofs_acquired': 0, 'commercial_admission': False})
    checks = [
        ('facts', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
        ('original_verifier', [sys.executable, '-m', 'unittest', 'discover', '-s', str(facts.PREVIOUS / 'tests'), '-v']),
        ('isolation_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
        ('isolation', [sys.executable, 'migration/verify_isolation.py']),
    ]
    validation = []
    for name, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = run.stdout + run.stderr
        path = f'evidence/{name}.log'
        (HERE / path).write_text(log)
        row = {'name': name, 'command': command, 'exit_code': run.returncode,
               'log': path, 'sha256': hashlib.sha256(log.encode()).hexdigest()}
        match = re.search(r'Ran (\d+) tests? in ', log)
        if match and run.returncode == 0:
            row['tests_passed'] = int(match.group(1))
        validation.append(row)
        print(name, run.returncode)
    save('VALIDATION.json', {'checks': validation,
                            'tests_passed': sum(r.get('tests_passed', 0) for r in validation),
                            'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
                            'commercial_admission': False})
    save('MANIFEST.json', {'scope': 'offline artifact integrity only',
                          'files': [{'path': str(p.relative_to(HERE)),
                                     'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                    for p in sorted(HERE.rglob('*')) if p.is_file()
                                    and '__pycache__' not in p.parts and p.name != 'MANIFEST.json']})
    return int(any(r['exit_code'] for r in validation))


if __name__ == '__main__':
    raise SystemExit(main())
