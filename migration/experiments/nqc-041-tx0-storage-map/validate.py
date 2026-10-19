"""Regenerate offline evidence; writes only inside this experiment directory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import storage_map as m

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = HERE.parent / 'nqc-037-historical-state'


def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    diagnostic = PREVIOUS / 'inputs/augmented-prestate.json'
    state = json.loads(diagnostic.read_text())['result'][m.ARBOS]['storage']
    controls = m.control_slots()
    describe = lambda slots: {name: {'slot': slot, 'diagnostic_value': state.get(slot)}
                              for name, slot in slots.items()}
    decoded = {name: None if state.get(slot) is None else int(state[slot], 16)
               for name, slot in controls.items()}
    model = m.pricing_model(decoded['arbos_version'], decoded['single_constraints_length'],
                            decoded['multi_constraints_length'])
    # Fixed two-item diagnostic comparison. Never expand an unbounded state length.
    assert decoded['single_constraints_length'] == 2 and model == 'single'
    report = {
        'evidence_class': 'offline diagnostic/source comparison, not authenticated parent state',
        'diagnostic_sha256': hashlib.sha256(diagnostic.read_bytes()).hexdigest(),
        'arbos_account': m.ARBOS,
        'diagnostic_arbos_slot_count': len(state),
        'control_candidates': describe(controls),
        'diagnostic_selected_model': model,
        'single_constraints': [describe(m.constraint_slots('single', i)) for i in range(2)],
        'conditional_l1_target_slot': m.blockhash_slot(26008730),
        'conditional_l1_target_number': 26008730,
        'fee_slot_layout_only': m.fee_slots(),
        'missing_control_candidates': [name for name, slot in controls.items() if slot not in state],
        'rpc_requests_sent': 0, 'historical_proofs_acquired': 0,
        'complete_access_list': False, 'commercial_admission': False,
    }
    write_json('SLOT_MAP.json', report)
    checks = [
        ('mapper', [sys.executable, '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']),
        ('historical_verifier', [sys.executable, '-m', 'unittest', 'discover', '-s', str(PREVIOUS / 'tests'), '-v']),
        ('isolation_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'migration', '-p', 'test_isolation.py', '-v']),
        ('isolation', [sys.executable, 'migration/verify_isolation.py']),
    ]
    (HERE / 'evidence').mkdir(exist_ok=True)
    results = []
    for name, command in checks:
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = run.stdout + run.stderr
        path = f'evidence/{name}.log'
        (HERE / path).write_text(log)
        results.append({'check': name, 'command': command, 'exit_code': run.returncode,
                        'log': path, 'sha256': hashlib.sha256(log.encode()).hexdigest()})
        print(name, run.returncode)
    write_json('VALIDATION.json', {'checks': results, 'rpc_requests_sent': 0,
                                 'historical_proofs_acquired': 0, 'commercial_admission': False})
    bindings = []
    for path in sorted(PREVIOUS.rglob('*')):
        if path.is_file() and path.suffix in ('.go', '.json', '.py') and '__pycache__' not in path.parts:
            bindings.append({'path': str(path.relative_to(ROOT)),
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    plan = HERE.parent / 'nqc-038-archive-access/TRIPORT_PLAN.json'
    bindings.append({'path': str(plan.relative_to(ROOT)), 'sha256': hashlib.sha256(plan.read_bytes()).hexdigest()})
    write_json('SOURCE_BINDING.json', {'base_commit': 'bfed312ca1675aaa8869b8788bfc3b501243f1a0',
                                      'files': bindings})
    manifest = [{'path': str(path.relative_to(HERE)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in sorted(HERE.rglob('*')) if path.is_file()
                and '__pycache__' not in path.parts and path.name != 'MANIFEST.json']
    write_json('MANIFEST.json', {'files': manifest, 'evidence_class': 'offline artifact integrity only'})
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
