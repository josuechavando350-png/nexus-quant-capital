"""Offline regeneration. Writes only NQC042 artifacts; no network."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import audit_prefix as audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def write(name, obj):
    (HERE / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def main():
    write('PREFIX_REVIEW.json', audit.review())
    (HERE / 'evidence').mkdir(exist_ok=True)
    checks = [
        ('prefix', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
        ('mapper', [sys.executable, '-m', 'unittest', 'discover', '-s', str(audit.MAP), '-p', 'test_*.py', '-v']),
        ('historical_verifier', [sys.executable, '-m', 'unittest', 'discover', '-s', str(audit.PREVIOUS / 'tests'), '-v']),
        ('isolation_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
        ('isolation', [sys.executable, 'migration/verify_isolation.py']),
    ]
    results = []
    for name, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = run.stdout + run.stderr
        path = f'evidence/{name}.log'
        (HERE / path).write_text(log)
        results.append({'name': name, 'command': command, 'exit_code': run.returncode,
                        'log': path, 'sha256': hashlib.sha256(log.encode()).hexdigest()})
        match = re.search(r'Ran (\d+) tests? in ', log)
        if match and run.returncode == 0:
            results[-1]['tests_passed'] = int(match.group(1))
        print(name, run.returncode)
    write('VALIDATION.json', {'checks': results, 'tests_passed': sum(r.get('tests_passed', 0) for r in results),
                             'Go_executed': False, 'Nitro_replay_executed': False,
                             'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
                             'commercial_admission': False})
    paths = set(audit.SOURCE_PATHS.values())
    paths.update([audit.MAP / 'storage_map.py', audit.PREVIOUS / 'src/verify.py',
                  audit.PREVIOUS / 'vendor/nqc031/storage_proof.py',
                  audit.PREVIOUS / 'vendor/nqc031/util.py',
                  audit.PREVIOUS / 'inputs/parent-header.json',
                  audit.PREVIOUS / 'inputs/target-header.json',
                  audit.PREVIOUS / 'inputs/augmented-prestate.json',
                  HERE.parent / 'nqc-038-archive-access/TRIPORT_PLAN.json'])
    write('SOURCE_BINDING.json', {'base_commit': 'c8b9a675ff564b2ce82b6021f9f9a1fa61b9784d',
                                  'files': [{'path': str(p.relative_to(ROOT)),
                                             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                            for p in sorted(paths)]})
    write('MANIFEST.json', {'evidence_class': 'offline artifact integrity only',
                           'files': [{'path': str(p.relative_to(HERE)),
                                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                     for p in sorted(HERE.rglob('*')) if p.is_file()
                                     and '__pycache__' not in p.parts and p.name != 'MANIFEST.json']})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
