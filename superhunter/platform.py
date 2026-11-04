"""Unified, local defensive QA review. Never a discovery/exploitation workflow.

The only executable stages are this package's tests and fixed numerical labs.
Both user checklists are retained; local PASS never means platform completion.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from contextlib import redirect_stdout
import hashlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any

from . import quality
from .fuzz_cli import main as fuzz_main
from .fuzz_lab import ARTIFACT_FILES, verify_fuzz
from .lab_cli import main as lab_main
from .local_lab import BUNDLE_FILES, verify_local_bundle
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SUMMARY_FILES = {'review.json', 'INTEGRATION.md', 'CAPABILITIES.md', 'STATUS.md'}
INPUT_FILES = tuple(sorted(
    [f'qa/{n}' for n in quality.FILES | {'COMPLETE.json'}] +
    [f'lab/{n}' for n in BUNDLE_FILES | {'COMPLETE.json'}] +
    [f'fuzz/{n}' for n in ARTIFACT_FILES | {'COMPLETE.json'}]))
STATUSES = ('IMPLEMENTED_BOUNDED', 'PARTIAL', 'PENDING')


def integration_plan() -> dict:
    """Strict registry data, not placeholder implementations of planned engines."""
    data = strict_json(read_artifact(ROOT, 'integration-checklist.json'))
    if set(data) != {'schema_version', 'baseline', 'groups', 'items'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('invalid integration plan schema')
    if type(data['baseline']) is not str or not data['baseline'].strip():
        raise ValueError('missing integration plan context')
    groups = data['groups']
    if type(groups) is not dict or set(groups) != {'1','2','3','4','5'} or any(type(v) is not str or not v for v in groups.values()):
        raise ValueError('original integration groups must be retained')
    items = data['items']
    if type(items) is not list or len(items) != 27 or any(type(i) is not dict for i in items):
        raise ValueError('all original 27 integration items required')
    expected_groups = [1]*4 + [2]*5 + [3]*6 + [4]*6 + [5]*6
    for number, (item, group) in enumerate(zip(items, expected_groups), 1):
        if set(item) != {'id','group','title','status','scope','components','required_tests'}:
            raise ValueError('integration item fields mismatch')
        if type(item['id']) is not int or item['id'] != number or type(item['group']) is not int or item['group'] != group:
            raise ValueError('original integration order/group mismatch')
        if item['status'] not in STATUSES or any(type(item[k]) is not str or not item[k].strip() for k in ('title','scope')):
            raise ValueError('invalid integration status/text')
        refs, tests = item['components'], item['required_tests']
        if type(refs) is not list or any(type(c) is not str or c not in quality.COMPONENTS for c in refs) or len(set(refs)) != len(refs):
            raise ValueError('invalid integration components')
        if type(tests) is not list or any(type(t) is not str or not t.startswith('test_') for t in tests) or len(set(tests)) != len(tests):
            raise ValueError('invalid integration test requirements')
        if (item['status'] != 'PENDING') != bool(refs) or bool(refs) != bool(tests):
            raise ValueError('implemented/partial items need explicit evidence requirements')
    return data


def _test_inventory() -> list[str]:
    """Read static unittest identities from the current, own-package sources.

    Unsupported dynamic/top-level test generators are not silently accepted.
    This does not import test modules or execute test bodies.
    """
    names = []
    for path in sorted((ROOT/'tests').glob('test*.py')):
        tree = ast.parse(read_artifact(ROOT, 'tests/'+path.name), filename=path.name)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'load_tests':
                raise ValueError('dynamic unittest inventory needs explicit review')
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test')]
            if not methods:
                continue
            if len(node.bases) != 1 or ast.unparse(node.bases[0]) != 'unittest.TestCase':
                raise ValueError('unsupported inherited unittest inventory')
            names.extend(path.stem+'.'+node.name+'.'+method.name for method in methods)
    if not names or len(names) != len(set(names)):
        raise ValueError('empty or duplicate static unittest inventory')
    return sorted(names)


def _hash_inputs(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256(read_artifact(root, name)).hexdigest() for name in INPUT_FILES}


def collect(root: Path) -> dict:
    """Recompute all stage verifiers and bind their input bytes and current code.

    This is integrity and local recalculation, not authenticated remote execution.
    """
    before = quality.source_snapshot()
    evidence = _hash_inputs(root)
    qa = quality.verify_bundle(root/'qa')
    if qa['status'] != 'LOCAL_QA_PASS':
        raise ValueError('package QA is blocked')
    lab = verify_local_bundle(root/'lab')
    fuzz = verify_fuzz(root/'fuzz')
    if lab['status'] != 'LOCAL_INTEGRATION_PASS' or fuzz['status'] != 'LOCAL_FUZZ_PASS':
        raise ValueError('local laboratory stage is blocked')
    receipt = strict_json(read_artifact(root, 'qa/receipt.json'))
    if sorted(receipt['discovered']) != _test_inventory():
        raise ValueError('QA evidence must include the complete current test inventory')
    outcomes = {row['id']: row['outcome'] for row in receipt['tests']}
    plan, caps = integration_plan(), quality.catalog()
    items = []
    for item in plan['items']:
        if any(outcomes.get(test) != 'PASS' for test in item['required_tests']):
            raise ValueError(f"integration item {item['id']} has missing or failed test evidence")
        if any(qa['components'][c]['status'] != 'TESTS_PASSED_LOCAL' for c in item['components']):
            raise ValueError('integration item component is blocked')
        items.append({**item, 'evidence_level': 'BOUNDED_LOCAL_TESTS' if item['required_tests'] else 'NOT_IMPLEMENTED'})
    if before != quality.source_snapshot() or evidence != _hash_inputs(root):
        raise ValueError('sources or artifacts changed during review')
    return {
        'schema_version': 1, 'status': 'LOCAL_DEFENSIVE_REVIEW_PASS',
        'platform_complete': False, 'vulnerability_confirmed': False,
        'independently_authenticated': False, 'scope': 'own-package-tests-and-synthetic-numerical-labs',
        'source_digest': quality.sha(canonical(before)), 'evidence_sha256': evidence,
        'stages': {'qa': qa, 'lab': lab, 'fuzz': fuzz},
        'integration': {'groups': plan['groups'], 'items': items, 'counts': dict(Counter(i['status'] for i in items))},
        'capabilities': {'items': caps['items'], 'counts': dict(Counter(i['status'] for i in caps['items']))},
        'not_demonstrated': [
            'Motor completo de descubrimiento de DIABLO', 'Reconstrucción de contratos y pruebas de invariantes EVM',
            'Verificación independiente de una vulnerabilidad real', 'Fondos en riesgo verificados y severidad final',
            'Elegibilidad vigente del programa y duplicados', 'Operación continua sobre 20 programas',
            'Las 50 capacidades solicitadas', 'Aptitud de producción o recompensas acreditadas'],
    }


def render_integration(result: dict) -> str:
    lines = ['# Integración NQC + DIABLO — los 27 puntos originales', '',
             '✓ Implementado con alcance limitado · ◐ Parcial · ○ Pendiente.',
             'Una palomita acredita solo el alcance escrito, no el Hunter completo.', '']
    group = None
    for item in result['integration']['items']:
        if item['group'] != group:
            group = item['group']
            lines += ['## ' + result['integration']['groups'][str(group)], '']
        mark = {'IMPLEMENTED_BOUNDED':'✓','PARTIAL':'◐','PENDING':'○'}[item['status']]
        lines += [f"{mark} {item['id']}. **{item['title']}**", item['scope']]
        if item['required_tests']:
            lines += ['Evidencia local: ' + ', '.join('`'+t+'`' for t in item['required_tests']) + '.']
        lines += ['']
    return '\n'.join(lines)


def render_status(result: dict) -> str:
    qa, lab, fuzz = (result['stages'][key] for key in ('qa','lab','fuzz'))
    counts = result['integration']['counts']
    return ('# SUPERHUNTER — revisión defensiva conjunta\n\n'
            '**Plataforma completa: NO. Hallazgo confirmado: NO.**\n\n'
            f"Estado de esta revisión: `{result['status']}`.\n\n"
            f"Código y políticas: `{result['source_digest']}`.\n\n"
            '## Ejecución comprobada\n\n'
            f"Suite del paquete: {qa['tests_run']} pruebas; resultado {qa['status']}.\n"
            f"Laboratorio nativo: {lab['cases_passed']} casos numéricos fijos.\n"
            f"Fuzzing numérico: {fuzz['cases_verified']} casos; semilla {fuzz['seed']}.\n\n"
            f"Los 27 puntos originales: {counts.get('IMPLEMENTED_BOUNDED',0)} implementados con límites, "
            f"{counts.get('PARTIAL',0)} parciales y {counts.get('PENDING',0)} pendientes. "
            'No se convierte ese conteo en un porcentaje de capacidad.\n\n'
            'Se conservan los 50 puntos adicionales; su estado está en CAPABILITIES.md.\n\n'
            '## Límites\n\n'
            'Esta revisión ejecuta y contrasta únicamente código del propio paquete y modelos sintéticos. '
            'No ejecuta Forge, contratos externos, explotación, RPC ni envíos de reportes. '
            'Los hashes vinculan artefactos y fuentes; no autentican a un productor remoto. '
            'El comprobador vuelve a calcular resultados y relaciones, pero no certifica ausencia de errores.\n\n'
            '## Pendientes materiales\n\n' + '\n'.join('- '+x for x in result['not_demonstrated']) + '\n')


def _documents(result: dict) -> dict[str, bytes]:
    return {'review.json': canonical(result), 'STATUS.md': render_status(result).encode(),
            'INTEGRATION.md': render_integration(result).encode(),
            'CAPABILITIES.md': quality.checklist({'items': result['capabilities']['items']}, result['stages']['qa']).encode()}


def verify_platform(root: Path) -> dict:
    if {p.name for p in root.iterdir()} != {'qa','lab','fuzz','review'}:
        raise ValueError('unexpected or missing platform stages')
    marker = strict_json(read_artifact(root, 'review/COMPLETE.json'))
    if type(marker.get('schema_version')) is not int or marker['schema_version'] != 1 or type(marker.get('sha256')) is not dict or set(marker['sha256']) != SUMMARY_FILES:
        raise ValueError('platform review manifest mismatch')
    result = collect(root)
    for name, expected in _documents(result).items():
        actual = read_artifact(root, 'review/'+name)
        if quality.sha(actual) != marker['sha256'][name] or actual != expected:
            raise ValueError('platform report differs from recomputed evidence')
    return result


def _finish(root: Path) -> dict:
    result = collect(root)
    write_new_bundle(root/'review', _documents(result))
    return verify_platform(root)


def run_platform(out: Path) -> dict:
    """Run fixed local stages. An interrupted directory is never marked complete."""
    if out.exists() or out.is_symlink():
        raise FileExistsError('platform review requires a new output directory')
    if out.resolve().is_relative_to(ROOT.parent):
        raise ValueError('keep generated evidence outside the source checkout')
    source = quality.source_snapshot()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    qa = quality.run_check(out/'qa')
    if qa['status'] != 'LOCAL_QA_PASS':
        raise ValueError('package QA is blocked; remaining stages not run')
    with redirect_stdout(io.StringIO()):
        if lab_main(['--out', str(out/'lab')]) != 0:
            raise RuntimeError('native laboratory stage failed')
        if fuzz_main(['--out', str(out/'fuzz'), '--seed', '20261104', '--cases', '256']) != 0:
            raise RuntimeError('fuzz laboratory stage failed')
    if source != quality.source_snapshot():
        raise ValueError('source changed during the combined execution')
    return _finish(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Unified local review; never an autonomous security attack')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('review-platform').add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-platform').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_platform(args.out) if args.command == 'review-platform' else verify_platform(args.bundle)
        print(json.dumps({'status': result['status'], 'platform_complete': False,
                          'tests_run': result['stages']['qa']['tests_run'],
                          'source_digest': result['source_digest'], 'vulnerability_confirmed': False}))
        return 0
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'LOCAL_DEFENSIVE_REVIEW_ERROR','error_type':type(exc).__name__,
                          'platform_complete':False,'vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
