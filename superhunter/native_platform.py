"""One local acceptance path: whole-package QA -> fixed EVM -> committed units.

No target/source/calldata/RPC input is accepted. The existing numerical review
keeps its narrower contract; this separate profile requires actual native replay.
Unit mocks exercise orchestration only, never count as EVM acceptance evidence.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

from . import platform as local, quality, review, evm_accounting as effects
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'whole-package-and-fixed-native-evm-v1'
LOCAL_FILES = (set(local.INPUT_FILES) |
               {'review/' + n for n in local.SUMMARY_FILES | {'COMPLETE.json'}} |
               {'publication/' + n for n in review.ALL_FILES | {'COMPLETE.json'}})
NATIVE_FILES = effects.FILES | {'COMPLETE.json'}
REPORT_FILES = {'acceptance.json', 'audit.json', 'REVIEW.md', 'index.html'}
MAX_TREE_BYTES = 64_000_000
HEX64 = re.compile(r'[a-f0-9]{64}\Z')


class NativeReviewError(ValueError):
    """Fixed diagnostic codes; private inputs are never printed by the CLI."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise NativeReviewError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_digest() -> str:
    return sha(canonical(quality.source_snapshot()))


def preflight(solc: Path, evm: Path) -> dict:
    """Check actual executable bytes and installed solver before expensive QA."""
    effects.evm.compiler.read_pinned_binary(solc)
    effects.evm.read_evm(evm)
    return effects.identity()


def _tree(root: Path, expected: set[str]) -> dict[str, str]:
    """Closed inventory, regular bounded files only; no extra untracked material."""
    need(not root.is_symlink() and root.is_dir(), 'EVIDENCE_ROOT_REQUIRED')
    parents = {str(p) for name in expected for p in PurePosixPath(name).parents if str(p) != '.'}
    found = set()
    directories = set()
    total = 0
    hashes = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            need(not path.is_symlink() and relative in parents, 'UNEXPECTED_EVIDENCE_DIRECTORY')
            directories.add(relative)
        for name in files:
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            need(relative in expected and stat.S_ISREG(path.lstat().st_mode), 'UNEXPECTED_EVIDENCE_FILE')
            raw = read_artifact(root, relative)
            total += len(raw)
            need(total <= MAX_TREE_BYTES, 'EVIDENCE_BUDGET')
            found.add(relative)
            hashes[relative] = sha(raw)
    need(found == expected and directories == parents, 'INCOMPLETE_EVIDENCE_INVENTORY')
    return dict(sorted(hashes.items()))


def _inputs(root: Path) -> dict:
    need(not root.is_symlink() and root.is_dir() and {p.name for p in root.iterdir()} in
         ({'local', 'native'}, {'local', 'native', 'review'}), 'JOINT_STAGE_INVENTORY')
    return {'local': _tree(root / 'local', LOCAL_FILES),
            'native': _tree(root / 'native', NATIVE_FILES)}


def _check_source_maps(node: dict, snapshot: dict) -> None:
    """Bind every EVM-side source identity to the same source bytes as package QA."""
    for key, value in node.items():
        if key == 'sources_sha256':
            need(type(value) is dict and bool(value), 'NATIVE_SOURCE_IDENTITY')
            for name, digest in value.items():
                need(snapshot.get(name) == digest, 'QA_NATIVE_SOURCE_MISMATCH')
        elif type(value) is dict:
            _check_source_maps(value, snapshot)


def collect(root: Path, solc: Path, evm: Path, expected_source: str) -> dict:
    """Revalidate QA and actually rerun native tools; never infer replay from JSON.

    QA tests are not rerun here. Their complete receipts and current source
    inventory are checked by the original platform verifier. EVM IS rerun.
    """
    need(type(expected_source) is str and HEX64.fullmatch(expected_source) is not None,
         'EXPECTED_SOURCE_DIGEST_REQUIRED')
    snapshot = quality.source_snapshot()
    need(sha(canonical(snapshot)) == expected_source, 'EXPECTED_SOURCE_MISMATCH')
    engine = preflight(solc, evm)
    captured = _inputs(root)
    checked = local.verify_platform(root / 'local')
    need(checked['status'] == 'LOCAL_DEFENSIVE_REVIEW_PASS' and
         checked['source_digest'] == expected_source and checked['platform_complete'] is False and
         checked['vulnerability_confirmed'] is False, 'LOCAL_QA_IDENTITY_OR_STATUS')
    count = checked['stages']['qa']['tests_run']
    need(type(count) is int and count > 0, 'QA_COUNT')
    # This function runs solc, Z3, constructors and message calls from fixed code.
    replayed = effects.replay(root / 'native', solc, evm)
    record = strict_json(read_artifact(root / 'native', 'effects.json'))
    execution = strict_json(read_artifact(root / 'native', 'evm--result.json'))
    need(canonical(record['engine']) == canonical(engine), 'NATIVE_ENGINE_MISMATCH')
    _check_source_maps(record['engine'], snapshot)
    wanted = {k: record[k] for k in ('status', 'calls_checked', 'transfer_count',
                                     'failed_calls_without_transfer', 'vulnerability_confirmed')}
    wanted.update(native_execution_performed_here=True, same_engines_replayed=True,
                  monetary_valuation_usd=None)
    need(canonical(replayed) == canonical(wanted), 'NATIVE_REPLAY_RECEIPT_MISMATCH')
    need(execution['execution_sha256'] == record['execution_sha256'], 'NATIVE_EXECUTION_BINDING')
    need(type(execution['constructor_calls']) is int and execution['constructor_calls'] == 3 and
         type(record['calls_checked']) is int and record['calls_checked'] == 18 and
         type(record['transfer_count']) is int and record['transfer_count'] == 5 and
         type(record['failed_calls_without_transfer']) is int and record['failed_calls_without_transfer'] == 13,
         'FIXED_NATIVE_COVERAGE')
    need(record['status'] == 'FIXED_EVM_UNIT_EFFECTS_RECONCILED' and
         record['vulnerability_confirmed'] is False and record['network_used'] is False and
         record['platform_complete'] is False and record['monetary_valuation_usd'] is None,
         'UNSUPPORTED_NATIVE_CLAIM')
    at = record['created_at']
    need(type(at) is str and datetime.fromisoformat(at).tzinfo is not None, 'NATIVE_RECORD_TIME')
    qa_receipt = strict_json(read_artifact(root / 'local', 'qa/receipt.json'))
    result = {
        'schema_version': 1, 'profile': PROFILE, 'status': 'FIXED_NATIVE_PLATFORM_REVIEW_PASS',
        'source_digest': expected_source, 'evidence_sha256': captured, 'native_recorded_at': at,
        'engine_identity': engine,
        'qa': {'tests_run': count, 'status': checked['stages']['qa']['status'],
               'inventory_sha256': sha(canonical(sorted(qa_receipt['discovered']))),
               'tests_reexecuted_by_verifier': False},
        'local_controls': {
            'numerical_cases': checked['stages']['lab']['cases_passed'],
            'fuzz_cases': checked['stages']['fuzz']['cases_verified'],
            'accounting_cases': checked['stages']['economics']['cases_checked'],
            'permission_cases': checked['stages']['benchmark_control']['cases'],
            'sequence_cases': checked['stages']['sequence']['cases_checked']},
        'native_controls': {
            'constructors': execution['constructor_calls'], 'calls': record['calls_checked'],
            'outcomes': record['call_outcomes'], 'applied_transfers': record['transfer_count'],
            'failed_calls_without_transfer': record['failed_calls_without_transfer'],
            'execution_sha256': record['execution_sha256'], 'same_engine_replay_required': True,
            'cases': {name: {'final_units': row['final_units'],
                              'source_property_status': row['source_property_status'],
                              'applied_units': row['applied_transfer_units']}
                      for name, row in record['cases'].items()}},
        'plans': {'integration_ids': [x['id'] for x in checked['integration']['items']],
                  'capability_ids': [x['id'] for x in checked['capabilities']['items']],
                  'initiative_ids': [x['id'] for x in checked['research_initiatives']['items']]},
        'fixed_owned_controls_only': True, 'independent_evm_used': False,
        'producer_authenticated': False, 'platform_complete': False,
        'vulnerability_confirmed': False, 'external_targets_executed': False,
        'network_used': False, 'monetary_valuation_usd': None,
    }
    need(snapshot == quality.source_snapshot() and captured == _inputs(root) and
         canonical(engine) == canonical(effects.identity()), 'SOURCE_OR_EVIDENCE_CHANGED_DURING_REVIEW')
    return result


def render(result: dict) -> str:
    n = result['native_controls']
    lines = ['# SUPERHUNTER — revisión conjunta con aceptación EVM real', '',
             f"Estado: {result['status']}", f"Código: `{result['source_digest']}`", '',
             f"Pruebas del paquete: {result['qa']['tests_run']}.",
             f"Constructores por recorrido nativo: {n['constructors']}; llamadas: {n['calls']}.",
             f"Transferencias de unidades internas aplicadas: {n['applied_transfers']}.",
             f"Llamadas fallidas sin transferencia aplicada: {n['failed_calls_without_transfer']}.", '',
             '## Estado persistente observado', '']
    for name, case in sorted(n['cases'].items()):
        lines.append(f"{name}: debit={case['final_units']['debit']}, credit={case['final_units']['credit']}; "
                     f"unidades trasladadas={case['applied_units']}.")
    lines += ['', '## Qué exige esta revisión', '',
              'La generación ejecuta primero la suite completa y los controles locales. Luego ejecuta',
              'el compilador, Z3 y la EVM, y exige una segunda ejecución nativa antes de emitir éxito.',
              'La verificación posterior comprueba los recibos QA sin repetir sus tests, pero SÍ',
              'recompila y ejecuta los controles nativos de nuevo. Falta de binarios o desacuerdo bloquean.',
              'Los subreportes local/ conservan su alcance exclusivamente local-numérico; este informe',
              'es el que añade la etapa EVM bajo native/. Sus fuentes deben ser las mismas.', '',
              '## Límites', '',
              'Solo tres contratos propios conocidos, sin fondos ni objetivos externos. Las unidades',
              'no son tokens ni dinero. Los fallos y el gas agotado esperados comprueban controles,',
              'no son hallazgos. No hay compilador o EVM independiente ni autenticación remota.',
              'Los hashes y la bitácora no autentican por sí solos la veracidad de un productor.',
              'Plataforma completa: NO. Vulnerabilidad confirmada: NO. Los planes 27/50/25 se conservan.', '']
    return '\n'.join(lines)


def documents(result: dict) -> dict[str, bytes]:
    audit = load_components().audit.AuditLog(clock=lambda: result['native_recorded_at'])
    audit.append('acceptance.qa', {'source_digest': result['source_digest'], 'qa': result['qa']})
    audit.append('acceptance.native', {'native_controls': result['native_controls']})
    audit.append('acceptance.artifacts', {'evidence_sha256': result['evidence_sha256']})
    audit.append('acceptance.complete', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    markdown = render(result)
    return {'acceptance.json': canonical(result), 'REVIEW.md': markdown.encode(),
            'index.html': review.render_html(markdown),
            'audit.json': canonical({'events': [asdict(e) for e in audit.entries]})}


def create(solc: Path, evm: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.parent),
         'NEW_OUTPUT_OUTSIDE_CODE_REQUIRED')
    snapshot = quality.source_snapshot()
    expected = sha(canonical(snapshot))
    engine = preflight(solc, evm)  # No output/QA if either executable is absent or wrong.
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(mode=0o700)
    local_result = local.run_platform(out / 'local')
    need(local_result['status'] == 'LOCAL_DEFENSIVE_REVIEW_PASS' and
         local_result['source_digest'] == expected, 'QA_STAGE_NOT_APPROVED')
    need(snapshot == quality.source_snapshot(), 'SOURCE_CHANGED_AFTER_QA')
    effects.create(solc, evm, out / 'native')
    result = collect(out, solc, evm, expected)  # Includes actual second native execution.
    need(snapshot == quality.source_snapshot() and canonical(engine) == canonical(result['engine_identity']),
         'SOURCE_CHANGED_BEFORE_COMPLETION')
    write_new_bundle(out / 'review', documents(result))  # COMPLETE written only after all stages.
    return result


def verify(root: Path, solc: Path, evm: Path, expected_source: str) -> dict:
    need(not root.is_symlink() and root.is_dir() and {p.name for p in root.iterdir()} ==
         {'local', 'native', 'review'}, 'JOINT_STAGE_INVENTORY')
    # Check final report bytes before invoking native tools.
    report_hashes = _tree(root / 'review', REPORT_FILES | {'COMPLETE.json'})
    marker = strict_json(read_artifact(root / 'review', 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and
         set(marker['sha256']) == REPORT_FILES, 'JOINT_REPORT_MANIFEST')
    need(all(marker['sha256'][n] == report_hashes[n] for n in REPORT_FILES), 'JOINT_REPORT_HASH')
    result = collect(root, solc, evm, expected_source)
    wanted = documents(result)
    for name, raw in wanted.items():
        need(read_artifact(root / 'review', name) == raw, 'JOINT_REPORT_DIFFERS_FROM_REPLAY')
    need(_tree(root / 'review', REPORT_FILES | {'COMPLETE.json'}) == report_hashes,
         'REPORT_CHANGED_DURING_REPLAY')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Own-package QA and fixed owned native EVM acceptance; no targets')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('review-native-platform')
    run.add_argument('--out', type=Path, required=True)
    check = sub.add_parser('verify-native-platform')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-source', required=True)
    for p in (run, check):
        p.add_argument('--solc', type=Path, required=True)
        p.add_argument('--evm', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        r = (create(args.solc, args.evm, args.out) if args.command == 'review-native-platform'
             else verify(args.bundle, args.solc, args.evm, args.expected_source))
        print(json.dumps({'status': r['status'], 'source_digest': r['source_digest'],
                          'tests_run': r['qa']['tests_run'], 'native_calls': r['native_controls']['calls'],
                          'native_replayed_in_this_invocation': True,
                          'platform_complete': False, 'vulnerability_confirmed': False}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, RecursionError,
            OverflowError, subprocess.TimeoutExpired):
        print(json.dumps({'status': 'NATIVE_PLATFORM_REVIEW_BLOCKED',
                          'platform_complete': False, 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
