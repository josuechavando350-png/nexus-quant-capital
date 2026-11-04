"""Executable QA gate for this package, not an autonomous security scanner.

Runs only the repository's own unit/regression suites through a fixed worker.
Module mappings are declared architecture, NOT inferred call graphs or coverage.
Receipts establish local consistency, not remote producer authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
COMPONENTS = {
    'programs': {'files': ['program_registry.py', 'privacy.py'], 'tests': ['test_program_registry.'], 'depends': ['native', 'io']},
    'source_graph': {'files': ['source_graph.py'], 'tests': ['test_source_graph.'], 'depends': ['io']},
    'static-intake': {'files': ['static_intake.py'], 'tests': ['test_static_intake.'], 'depends': ['io']},
    'io': {'files': ['safe_io.py'], 'tests': ['test_integration.'], 'depends': []},
    'transport': {'files': ['bridge.py', 'integration.py'], 'tests': ['test_bridge.', 'test_integration.'], 'depends': ['io']},
    'native': {'files': ['native_runtime.py', 'native_sources/diablo/models.py', 'native_sources/diablo/audit.py',
                         'native_sources/diablo/scope.py', 'native_sources/nqc/capacity.py'],
               'tests': ['test_local_lab.'], 'depends': ['io']},
    'audit': {'files': ['audit_links.py', 'proof_graph.py'],
              'tests': ['test_audit_links.', 'test_proof_graph.'], 'depends': ['io']},
    'lab': {'files': ['local_lab.py', 'lab_worker.py', 'lab_cli.py'],
            'tests': ['test_local_lab.', 'test_audit_links.'], 'depends': ['native', 'audit']},
    'fuzz': {'files': ['fuzz_lab.py', 'fuzz_worker.py', 'fuzz_cli.py'],
             'tests': ['test_fuzz_lab.', 'test_fuzz_evidence.'], 'depends': ['native', 'lab', 'audit']},
    'quality': {'files': ['quality.py', 'quality_worker.py'], 'tests': ['test_quality.'], 'depends': ['transport', 'lab', 'fuzz', 'static-intake', 'source_graph']},
    'review': {'files': ['review.py'], 'tests': ['test_review.'], 'depends': ['quality', 'lab', 'fuzz']},
    'entrypoints': {'files': ['__init__.py', '__main__.py'],
                    'tests': ['test_integration.', 'test_local_lab.', 'test_fuzz_lab.'], 'depends': ['transport', 'lab', 'fuzz', 'quality', 'review', 'static-intake', 'source_graph']},
}
REQUIRED_TESTS = (
    'test_bridge.BridgeTests.test_forge_wrong_target',
    'test_bridge.BridgeTests.test_nqc_unbound_economics',
    'test_integration.IntegrationTests.test_native_roundtrip_always_requires_review',
    'test_integration.IntegrationTests.test_cli_export_then_import',
    'test_integration.IntegrationTests.test_symlink_leaf_rejected',
    'test_local_lab.LocalLabTests.test_real_nqc_and_diablo_functions_are_called',
    'test_local_lab.LocalLabTests.test_cli_complete_run_and_verification',
    'test_audit_links.AuditLinkTests.test_input_hash_substitution_rejected_even_after_rehash',
    'test_proof_graph.CausalGraphTests.test_stored_bundle_receipt_catches_graph_reseal',
    'test_quality.QualityTests.test_skip_never_counts_as_pass',
    'test_quality.QualityTests.test_source_change_blocks_success',
    'test_fuzz_lab.FuzzLabTests.test_differential_64_cases',
    'test_fuzz_lab.FuzzLabTests.test_resealed_scope_decision_mismatch',
    'test_fuzz_lab.FuzzLabTests.test_cli_runs_bounded_fuzz_and_reverification',
    'test_fuzz_evidence.FuzzEvidenceTests.test_contradictory_completion_rejected_after_rehash',
    'test_fuzz_evidence.FuzzEvidenceTests.test_counts_require_integers',
    'test_review.ReviewTests.test_resealed_report_cannot_claim_production',
    'test_review.ReviewTests.test_missing_milestone_test_blocks_review',
)
REQUIRED_TESTS += (
    'test_static_intake.StaticIntakeTests.test_expected_source_span_and_rule',
    'test_static_intake.StaticIntakeTests.test_source_hash_mismatch_rejected',
    'test_static_intake.StaticIntakeTests.test_missing_detector_key_is_unknown_not_clean',
)
REQUIRED_TESTS += (
    'test_source_graph.SourceGraphTests.test_removed_module_detected',
    'test_source_graph.SourceGraphTests.test_no_analyzed_code_is_executed',
    'test_source_graph.SourceGraphTests.test_resealed_runtime_claim_rejected',
)
REQUIRED_TESTS += (
    'test_program_registry.ProgramRegistryTests.test_exclusion_overrides_inclusion',
    'test_program_registry.ProgramRegistryTests.test_normalized_change_invalidates_review',
    'test_program_registry.ProgramRegistryTests.test_historical_success_can_be_currently_expired',
    'test_program_registry.ProgramRegistryTests.test_live_scan_and_submission_are_never_enabled',
)
COMPONENTS['quality']['depends'].append('programs')
COMPONENTS['entrypoints']['depends'].append('programs')
FILES = {'receipt.json' , 'quality.json', 'source-snapshot.json', 'CHECKLIST.md', 'tests.log'}


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_snapshot(root: Path = ROOT) -> dict[str, str]:
    """Capture executable package/test bytes and policy inputs; reject symlinks."""
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for name in dirs:
            if (Path(base)/name).is_symlink():
                raise ValueError('source directory symlink rejected')
        for name in sorted(files):
            rel = (Path(base)/name).relative_to(root).as_posix()
            if name.endswith('.py') or rel in ('capabilities.json', 'integration_milestones.json', 'requirements-local-lab.txt'):
                result[rel] = sha(read_artifact(root, rel))
                if len(result) > 500:
                    raise ValueError('source inventory limit exceeded')
    if not result:
        raise ValueError('empty source inventory')
    return dict(sorted(result.items()))


def validate_components(snapshot: dict, components: dict = COMPONENTS) -> list[str]:
    errors, owners = [], {}
    for name, item in components.items():
        if not item['files'] or not item['tests']:
            errors.append(f'{name}: empty component definition')
        for path in item['files']:
            if path not in snapshot:
                errors.append(f'{name}: missing source {path}')
            if path in owners:
                errors.append(f'{name}: source assigned twice {path}')
            owners[path] = name
        if any(dep not in components for dep in item['depends']):
            errors.append(f'{name}: unknown dependency')
    for path in snapshot:
        if path.endswith('.py') and not path.startswith('tests/') and path not in owners:
            errors.append(f'unmapped runtime source: {path}')
    visiting, done = set(), set()

    def walk(name):
        if name in visiting:
            raise ValueError('component dependency cycle')
        if name in done:
            return
        visiting.add(name)
        for dep in components[name]['depends']:
            if dep in components:
                walk(dep)
        visiting.remove(name); done.add(name)
    try:
        for name in components:
            walk(name)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def catalog(root: Path = ROOT) -> dict:
    data = strict_json(read_artifact(root, 'capabilities.json'))
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported capability catalog')
    items = data.get('items')
    if (type(items) is not list or len(items) != 50 or
            any(type(x) is not dict or type(x.get('id')) is not int for x in items) or
            [x['id'] for x in items] != list(range(1,51))):
        raise ValueError('catalog must preserve all 50 ordered unique IDs')
    for item in items:
        if set(item) != {'id', 'title', 'status', 'scope', 'components'}:
            raise ValueError('capability fields mismatch')
        if item['status'] not in ('PLANNED', 'PARTIAL', 'REDESIGN_REQUIRED'):
            raise ValueError('no capability may be certified complete by this catalog')
        if any(type(item[k]) is not str or not item[k].strip() for k in ('title','scope')):
            raise ValueError('capability title/scope missing')
        refs = item['components']
        if (type(refs) is not list or any(type(ref) is not str or ref not in COMPONENTS for ref in refs) or
                len(set(refs)) != len(refs)):
            raise ValueError('unknown or duplicate capability component')
        if (item['status'] == 'PARTIAL') != bool(refs):
            raise ValueError('partial capability requires actual components; planned capabilities cannot borrow proof')
    return data


def assess(receipt: dict, snapshot: dict) -> dict:
    """Recompute the gate; a claimed PASS in the receipt is never trusted."""
    errors = validate_components(snapshot)
    if receipt.get('schema_version') != 1 or type(receipt.get('schema_version')) is not int:
        errors.append('invalid receipt schema')
    if receipt.get('sources_before') != snapshot or receipt.get('sources_after') != snapshot:
        errors.append('source changed, missing or stale')
    rows, expected = receipt.get('tests'), receipt.get('discovered')
    if type(rows) is not list or not rows or type(expected) is not list or not expected:
        raise ValueError('nonempty discovered tests and results required')
    if any(type(row) is not dict or set(row) != {'id', 'outcome'} or
           type(row['id']) is not str or type(row['outcome']) is not str for row in rows):
        raise ValueError('malformed per-test record')
    ids = [row['id'] for row in rows]
    if (any(type(x) is not str for x in expected) or len(ids) != len(set(ids)) or
            len(expected) != len(set(expected)) or sorted(ids) != sorted(expected)):
        errors.append('test identities are duplicate, missing or unexpected')
    if type(receipt.get('tests_run')) is not int or receipt['tests_run'] != len(rows):
        errors.append('test count mismatch')
    if any(row['outcome'] != 'PASS' for row in rows):
        errors.append('at least one test failed, errored, skipped or was incomplete')
    for key in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'):
        if type(receipt.get(key)) is not int or receipt[key] != 0:
            errors.append(f'{key} not zero')
    for required in REQUIRED_TESTS:
        if required not in ids:
            errors.append('missing mandatory test: ' + required)
    checks = {}
    for name, component in COMPONENTS.items():
        assigned = [row for row in rows if any(row['id'].startswith(p) for p in component['tests'])]
        checks[name] = {'status': 'TESTS_PASSED_LOCAL' if assigned and all(r['outcome']=='PASS' for r in assigned) else 'BLOCKED',
                        'test_count': len(assigned), 'depends_on': component['depends'], 'files': component['files']}
        if not assigned:
            errors.append(name + ': no execution evidence')
    prefixes = {p for c in COMPONENTS.values() for p in c['tests']}
    if any(not any(i.startswith(p) for p in prefixes) for i in ids):
        errors.append('unmapped test suite')
    if errors:
        for check in checks.values():
            check['status'] = 'BLOCKED'
    return {'schema_version': 1, 'status': 'LOCAL_QA_PASS' if not errors else 'LOCAL_QA_BLOCKED',
            'source_digest': sha(canonical(snapshot)), 'tests_run': len(rows), 'components': checks,
            'reasons': errors, 'vulnerability_confirmed': False, 'production_certified': False}


def checklist(data: dict, result: dict | None = None) -> str:
    lines = ['# SUPERHUNTER — estado de las 50 capacidades', '',
             'Las pruebas del paquete no demuestran detección de vulnerabilidades ni completan estas capacidades.',
             '○ Pendiente · ◐ Parcial · ↻ Requiere reformulación defensiva. Ninguna está certificada completa.', '']
    if result:
        lines += [f"Comprobación local: {result['status']}; pruebas: {result['tests_run']}; código: `{result['source_digest']}`.", '']
    for item in data['items']:
        mark = {'PLANNED': '○', 'PARTIAL': '◐', 'REDESIGN_REQUIRED': '↻'}[item['status']]
        lines += [f"{mark} **{item['id']}. {item['title']}** — {item['scope']}", '']
    return '\n'.join(lines)


def verify_bundle(root: Path) -> dict:
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    if (type(marker.get('schema_version')) is not int or marker['schema_version'] != 1 or
            type(marker.get('sha256')) is not dict or set(marker['sha256']) != FILES):
        raise ValueError('QA bundle manifest mismatch')
    values = {}
    for name, expected in marker['sha256'].items():
        raw = read_artifact(root, name)
        if sha(raw) != expected:
            raise ValueError('QA artifact digest mismatch')
        values[name] = raw
    snapshot = source_snapshot()
    if strict_json(values['source-snapshot.json']) != snapshot:
        raise ValueError('QA source snapshot is not the current package')
    result = assess(strict_json(values['receipt.json']), snapshot)
    if canonical(result) != values['quality.json']:
        raise ValueError('QA claimed verdict differs from recomputed verdict')
    if checklist(catalog(), result).encode() != values['CHECKLIST.md']:
        raise ValueError('capability checklist not bound to current catalog/verdict')
    return result


def run_check(out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError('QA requires a new private output directory')
    snapshot = source_snapshot()
    data = catalog()
    if validate_components(snapshot):
        raise ValueError('; '.join(validate_components(snapshot)))
    with tempfile.TemporaryDirectory(prefix='superhunter-qa-') as temp:
        work = Path(temp)/'worker'
        proc = subprocess.run([sys.executable, '-I', '-B', str(ROOT/'quality_worker.py'), str(work)],
                              cwd=ROOT.parent, env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'},
                              capture_output=True, timeout=180, check=False)
        if proc.returncode not in (0,1):
            raise RuntimeError(f'QA worker infrastructure failure ({proc.returncode})')
        receipt_bytes = read_artifact(work, 'receipt.json')
        receipt = strict_json(receipt_bytes)
        # Recheck worker sources, parent sources, test outcomes and catalog.
        after = source_snapshot()
        result = assess(receipt, snapshot)
        if after != snapshot:
            raise ValueError('source changed during QA run')
        if (proc.returncode == 0) != (result['status'] == 'LOCAL_QA_PASS'):
            raise ValueError('worker exit/verdict mismatch')
        write_new_bundle(out, {'receipt.json': receipt_bytes, 'quality.json': canonical(result),
                              'source-snapshot.json': canonical(snapshot), 'CHECKLIST.md': checklist(data,result).encode(),
                              'tests.log': read_artifact(work,'tests.log')})
    return verify_bundle(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verify this package, never scan external targets')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check').add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-check').add_argument('--bundle', type=Path, required=True)
    sub.add_parser('capabilities')
    args = parser.parse_args(argv)
    try:
        if args.command == 'capabilities':
            print(checklist(catalog()))
            return 0
        result = run_check(args.out) if args.command=='check' else verify_bundle(args.bundle)
        print(json.dumps({k: result[k] for k in ('status','source_digest','tests_run','vulnerability_confirmed')}))
        return 0 if result['status']=='LOCAL_QA_PASS' else 1
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired,KeyError,TypeError) as exc:
        print(json.dumps({'status':'LOCAL_QA_ERROR','error_type':type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
